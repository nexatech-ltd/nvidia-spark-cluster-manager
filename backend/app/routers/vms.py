import asyncio
import base64
import json
import logging
import os
from shlex import quote as _shlex_quote

from fastapi import APIRouter, HTTPException, Query, UploadFile

from app.config import settings
from app.models.vm import (
    DiskCreate,
    DiskInfo,
    ISOInfo,
    SnapshotInfo,
    VMAction,
    VMCreate,
    VMInfo,
)
from app.services.libvirt_svc import OS_TYPES, libvirt_service
from app.services.node_svc import node_service

logger = logging.getLogger("spark-manager.vms")
router = APIRouter()

ALLOWED_ACTIONS = {"start", "shutdown", "reboot", "suspend", "resume", "destroy", "undefine"}


# ── ISOs (must be before /{name} catch-all) ──────────────────────────────


@router.get("/isos/", response_model=list[ISOInfo])
async def list_isos(node: str | None = Query(None)):
    """Scan ISO storage and NFS roots on the target node via SSH."""
    target = node or settings.node1_hostname
    dirs = [settings.iso_storage_path] + list(settings.nfs_roots)
    host = node_service._host_for_node(target)
    find_cmd = " ; ".join(
        f"find {d} -maxdepth 1 -iname '*.iso' -printf '%s %p\\n' 2>/dev/null"
        for d in dirs
    )
    try:
        rc, stdout, _ = await node_service.ssh_run(host, find_cmd)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    isos = []
    seen = set()
    for line in stdout.strip().split("\n"):
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[1] not in seen:
            seen.add(parts[1])
            isos.append({
                "name": os.path.basename(parts[1]),
                "size": int(parts[0]),
                "path": parts[1],
            })
    return isos


@router.post("/isos/upload")
async def upload_iso(file: UploadFile, node: str | None = Query(None)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    data = await file.read()
    try:
        return await asyncio.to_thread(
            libvirt_service.upload_iso, file.filename, data, node,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── OS Types (must be before /{name} catch-all) ──────────────────────────


@router.get("/os-variants/")
async def list_os_variants(node: str = Query("spark-1")):
    """Return curated OS types with labels and family metadata."""
    return [
        {"id": k, "label": v.get("label", k), "family": v.get("family", "generic")}
        for k, v in OS_TYPES.items()
    ]


# ── Hardware profiles (must be before /{name} catch-all) ─────────────────


@router.get("/hw-profile/")
async def get_hw_profile(os_variant: str = Query("generic")):
    """Return recommended disk_bus, nic_model for an OS variant."""
    return libvirt_service.get_hw_profile(os_variant)


async def _detect_machine_type(host: str, arch: str) -> str:
    """Query QEMU for the latest supported 'virt' machine version."""
    if arch not in ("aarch64", "arm64"):
        return "pc"
    rc, stdout, _ = await node_service.ssh_run(
        host,
        "qemu-system-aarch64 -machine help 2>/dev/null | grep '^virt-' | sort -t- -k2 -V | tail -1 | awk '{print $1}'",
    )
    machine = stdout.strip() if rc == 0 and stdout.strip() else "virt"
    logger.info("Detected machine type: %s", machine)
    return machine


@router.post("/preview")
async def preview_vm(params: VMCreate):
    """Return the libvirt domain XML that would be used, without creating anything."""
    host = node_service._host_for_node(params.node)
    _, arch_out, _ = await node_service.ssh_run(host, "uname -m")
    host_arch = arch_out.strip() or "aarch64"
    machine = params.machine_type or await _detect_machine_type(host, host_arch)
    xml = libvirt_service.build_domain_xml(params, arch=host_arch, machine_type=machine)
    return {"xml": xml}


# ── Bridges (must be before /{name} catch-all) ───────────────────────────


@router.get("/bridges/")
async def list_bridges(node: str = Query("spark-1")):
    """Return Linux bridges + libvirt virtual networks available on the node."""
    host = node_service._host_for_node(node)
    try:
        cmd = (
            "ip -j link show type bridge 2>/dev/null || true"
            " && echo '___SPLIT___'"
            " && virsh net-list --name 2>/dev/null || true"
        )
        rc, stdout, _ = await node_service.ssh_run(host, cmd)
        parts = stdout.split("___SPLIT___")

        results = []
        seen = set()

        if parts[0].strip():
            try:
                bridges = json.loads(parts[0].strip())
                for b in bridges:
                    name = b["ifname"]
                    if name.startswith("docker") or name.startswith("br-"):
                        continue
                    seen.add(name)
                    results.append({"name": name, "state": b.get("operstate", "unknown"), "type": "bridge"})
            except (json.JSONDecodeError, KeyError):
                pass

        if len(parts) > 1:
            for net_name in parts[1].strip().split("\n"):
                net_name = net_name.strip()
                if net_name and net_name not in seen:
                    results.append({"name": net_name, "state": "active", "type": "network"})

        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Disks (must be before /{name} catch-all) ─────────────────────────────


@router.get("/disks/", response_model=list[DiskInfo])
async def list_disks(
    pool: str = Query("default"),
    node: str | None = Query(None),
):
    """List volumes in a storage pool via SSH + virsh."""
    target = node or settings.node1_hostname
    host = node_service._host_for_node(target)
    script = (
        f"for v in $(sudo virsh vol-list {pool} 2>/dev/null | tail -n +3 | awk '{{print $1}}'); do "
        f"  echo \"$v|$(sudo virsh vol-path --pool {pool} $v 2>/dev/null)"
        f"|$(sudo virsh vol-info --pool {pool} $v 2>/dev/null | awk '/Capacity:/{{print $2,$3}}')"
        f"|$(sudo virsh vol-dumpxml --pool {pool} $v 2>/dev/null | grep -oP '(?<=type=.)[^\"]+' | head -1)\";"
        f" done"
    )
    try:
        rc, stdout, stderr = await node_service.ssh_run(host, script)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if rc != 0 and "not found" in stderr.lower():
        raise HTTPException(status_code=404, detail=f"Storage pool '{pool}' not found on {target}")
    _UNITS = {"bytes": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4, "B": 1}
    disks = []
    for line in stdout.strip().split("\n"):
        parts = line.strip().split("|")
        if len(parts) < 3 or not parts[0]:
            continue
        name = parts[0]
        path = parts[1]
        cap_parts = parts[2].strip().split()
        try:
            size = int(float(cap_parts[0]) * _UNITS.get(cap_parts[1], 1)) if len(cap_parts) >= 2 else 0
        except (ValueError, IndexError):
            size = 0
        fmt = parts[3].strip() if len(parts) > 3 and parts[3].strip() else "raw"
        disks.append({"name": name, "size": size, "format": fmt, "path": path, "pool": pool})
    return disks


@router.post("/disks/")
async def create_disk(params: DiskCreate, node: str | None = Query(None)):
    target = node or settings.node1_hostname
    host = node_service._host_for_node(target)
    size_str = f"{params.size_gb}G"
    cmd = f"sudo virsh vol-create-as {params.pool} {params.name} {size_str} --format {params.format}"
    rc, stdout, stderr = await node_service.ssh_run(host, cmd)
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Failed to create disk: {stderr.strip()}")
    return {"message": f"Disk '{params.name}' created in pool '{params.pool}'"}


# ── Storage Pools (must be before /{name} catch-all) ─────────────────────


@router.get("/pools/")
async def list_storage_pools(node: str | None = Query(None)):
    try:
        return await asyncio.to_thread(libvirt_service.list_storage_pools, node)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── VMs ──────────────────────────────────────────────────────────────────


@router.get("/", response_model=list[VMInfo])
async def list_vms(node: str | None = Query(None)):
    try:
        return await asyncio.to_thread(libvirt_service.list_vms, node)
    except Exception as e:
        logger.exception("Error listing VMs")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=dict)
async def create_vm(params: VMCreate):
    host = node_service._host_for_node(params.node)

    if params.custom_xml and params.custom_xml.strip():
        xml_content = params.custom_xml.strip()
    else:
        _, arch_out, _ = await node_service.ssh_run(host, "uname -m")
        host_arch = arch_out.strip() or "aarch64"
        machine = params.machine_type or await _detect_machine_type(host, host_arch)
        xml_content = libvirt_service.build_domain_xml(
            params, arch=host_arch, machine_type=machine,
        )

    logger.info("Creating VM '%s' on %s via XML define", params.name, params.node)

    disk_path = os.path.join(
        settings.vm_storage_path, f"{params.name}.{params.disk_format}",
    )

    # Create disk image if it doesn't already exist
    check_cmd = f"test -f {_shlex_quote(disk_path)} && echo EXISTS || echo MISSING"
    rc, out, _ = await node_service.ssh_run(host, check_cmd)
    if "MISSING" in out:
        img_cmd = (
            f"sudo qemu-img create -f {_shlex_quote(params.disk_format)}"
            f" {_shlex_quote(disk_path)} {params.disk_size_gb}G"
        )
        rc, _, stderr = await node_service.ssh_run(host, img_cmd)
        if rc != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create disk image: {stderr.strip()}",
            )

    # Write XML to remote host via base64 (avoids heredoc delimiter issues)
    tmp_xml = f"/tmp/.spark-vm-{params.name}.xml"
    b64 = base64.b64encode(xml_content.encode()).decode()
    write_cmd = f"echo '{b64}' | base64 -d | sudo tee {tmp_xml} > /dev/null"
    rc, _, stderr = await node_service.ssh_run(host, write_cmd)
    if rc != 0:
        raise HTTPException(
            status_code=500, detail=f"Failed to write VM XML: {stderr.strip()}",
        )

    # Define the VM
    rc, stdout, stderr = await node_service.ssh_run(
        host, f"sudo virsh define {tmp_xml} 2>&1",
    )
    if rc != 0:
        await node_service.ssh_run(host, f"sudo rm -f {_shlex_quote(disk_path)}")
        await node_service.ssh_run(host, f"rm -f {tmp_xml}")
        raise HTTPException(
            status_code=500, detail=f"Failed to define VM: {stderr.strip() or stdout.strip()}",
        )

    # Start the VM
    rc, stdout2, stderr2 = await node_service.ssh_run(
        host, f"sudo virsh start {_shlex_quote(params.name)} 2>&1",
    )
    await node_service.ssh_run(host, f"rm -f {tmp_xml}")

    if rc != 0:
        return {
            "message": f"VM '{params.name}' defined but failed to start: {stderr2.strip() or stdout2.strip()}",
            "stdout": stdout2,
        }

    return {"message": f"VM '{params.name}' created and started on {params.node}", "stdout": stdout2}


@router.get("/{name}", response_model=VMInfo)
async def get_vm(name: str, node: str = Query(...)):
    try:
        return await asyncio.to_thread(libvirt_service.get_vm, name, node)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{name}/action")
async def vm_action(name: str, body: VMAction, node: str = Query(...)):
    if body.action not in ALLOWED_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action. Allowed: {', '.join(sorted(ALLOWED_ACTIONS))}",
        )
    timeout = body.timeout or 0
    try:
        return await asyncio.to_thread(
            libvirt_service.vm_action, name, node, body.action, timeout,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{name}")
async def delete_vm(name: str, node: str = Query(...)):
    try:
        return await asyncio.to_thread(libvirt_service.delete_vm, name, node)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Snapshots ────────────────────────────────────────────────────────────


@router.get("/{name}/snapshots", response_model=list[SnapshotInfo])
async def list_snapshots(name: str, node: str = Query(...)):
    try:
        return await asyncio.to_thread(libvirt_service.list_snapshots, name, node)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{name}/snapshots")
async def create_snapshot(name: str, body: dict, node: str = Query(...)):
    snap_name = body.get("name")
    if not snap_name:
        raise HTTPException(status_code=400, detail="Snapshot name is required")
    try:
        return await asyncio.to_thread(
            libvirt_service.create_snapshot, name, snap_name, node,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{name}/snapshots/{snap_name}/restore")
async def restore_snapshot(name: str, snap_name: str, node: str = Query(...)):
    try:
        return await asyncio.to_thread(
            libvirt_service.restore_snapshot, name, snap_name, node,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{name}/snapshots/{snap_name}")
async def delete_snapshot(name: str, snap_name: str, node: str = Query(...)):
    try:
        return await asyncio.to_thread(
            libvirt_service.delete_snapshot, name, snap_name, node,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Disk attach/detach ───────────────────────────────────────────────────


@router.post("/{name}/disks/attach")
async def attach_disk(name: str, body: dict, node: str | None = Query(None)):
    disk_path = body.get("path")
    if not disk_path:
        raise HTTPException(status_code=400, detail="Disk path is required")
    target = node or settings.node1_hostname
    host = node_service._host_for_node(target)
    target_dev = await asyncio.to_thread(libvirt_service._next_disk_target, name, target)
    cmd = f"sudo virsh attach-disk {name} {disk_path} {target_dev} --persistent --subdriver qcow2"
    rc, _, stderr = await node_service.ssh_run(host, cmd)
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Failed to attach disk: {stderr.strip()}")
    return {"message": f"Disk '{disk_path}' attached to VM '{name}' as {target_dev}"}


@router.post("/{name}/disks/detach")
async def detach_disk(name: str, body: dict, node: str | None = Query(None)):
    disk_path = body.get("path")
    if not disk_path:
        raise HTTPException(status_code=400, detail="Disk path is required")
    target = node or settings.node1_hostname
    host = node_service._host_for_node(target)
    cmd = f"sudo virsh detach-disk {name} {disk_path} --persistent"
    rc, _, stderr = await node_service.ssh_run(host, cmd)
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Failed to detach disk: {stderr.strip()}")
    return {"message": f"Disk '{disk_path}' detached from VM '{name}'"}


# ── Boot order ────────────────────────────────────────────────────────────


@router.get("/{name}/boot")
async def get_boot_order(name: str, node: str = Query(...)):
    """Return the current boot device order from VM XML."""
    host = node_service._host_for_node(node)
    rc, stdout, stderr = await node_service.ssh_run(
        host, f"sudo virsh dumpxml {name} 2>&1",
    )
    if rc != 0:
        raise HTTPException(status_code=500, detail=stderr.strip())
    import re
    order = re.findall(r"<boot dev=['\"](\w+)['\"]", stdout)
    return {"order": order}


@router.put("/{name}/boot")
async def set_boot_order(name: str, body: dict, node: str = Query(...)):
    """Set boot device order via virt-xml --boot."""
    order = body.get("order", [])
    if not order:
        raise HTTPException(status_code=400, detail="Boot order list is required")
    order_csv = ",".join(order)
    host = node_service._host_for_node(node)
    cmd = f"sudo virt-xml {name} --connect qemu:///system --edit --boot {order_csv}"
    rc, stdout, stderr = await node_service.ssh_run(host, cmd)
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Failed to set boot order: {stderr.strip()}")
    return {"message": f"Boot order set to {order}", "stdout": stdout}


@router.post("/{name}/cdrom")
async def change_cdrom(name: str, body: dict, node: str = Query(...)):
    """Change or eject the CDROM ISO."""
    iso_path = body.get("iso")
    host = node_service._host_for_node(node)
    # Find the CDROM target device from VM XML
    rc, stdout, _ = await node_service.ssh_run(
        host, f"sudo virsh domblklist {name} --details 2>&1",
    )
    cdrom_target = None
    if rc == 0:
        for line in stdout.strip().split("\n"):
            if "cdrom" in line.lower():
                parts = line.split()
                if len(parts) >= 2:
                    cdrom_target = parts[1]
                    break
    if not cdrom_target:
        raise HTTPException(status_code=404, detail="No CDROM device found on this VM")

    if iso_path:
        cmd = f"sudo virsh change-media {name} {cdrom_target} '{iso_path}' --config"
        if body.get("live", True):
            cmd += " --live"
    else:
        cmd = f"sudo virsh change-media {name} {cdrom_target} --eject --config"
        if body.get("live", True):
            cmd += " --live"

    rc, stdout, stderr = await node_service.ssh_run(host, cmd)
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"CDROM operation failed: {stderr.strip()}")
    action = "ejected" if not iso_path else f"changed to {os.path.basename(iso_path)}"
    return {"message": f"CDROM {action}", "stdout": stdout}


# ── Autostart ────────────────────────────────────────────────────────────


@router.post("/{name}/autostart")
async def set_autostart(name: str, body: dict, node: str = Query(...)):
    enabled = body.get("enabled")
    if enabled is None:
        raise HTTPException(status_code=400, detail="'enabled' field is required")
    try:
        return await asyncio.to_thread(
            libvirt_service.set_autostart, name, node, bool(enabled),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── VM XML config ────────────────────────────────────────────────────────


@router.get("/{name}/xml")
async def get_vm_xml(name: str, node: str = Query(...)):
    """Return raw libvirt XML for a VM."""
    host = node_service._host_for_node(node)
    rc, stdout, stderr = await node_service.ssh_run(
        host, f"sudo virsh dumpxml {_shlex_quote(name)} 2>&1",
    )
    if rc != 0:
        raise HTTPException(status_code=500, detail=stderr.strip())
    return {"xml": stdout}


@router.put("/{name}/xml")
async def set_vm_xml(name: str, body: dict, node: str = Query(...)):
    """Update a VM definition from raw XML (VM must be shut off or will apply on next boot)."""
    xml_content = body.get("xml", "")
    if not xml_content.strip():
        raise HTTPException(status_code=400, detail="XML content is required")
    host = node_service._host_for_node(node)
    tmp = f"/tmp/.spark-vm-xml-{name}.xml"
    write_cmd = f"cat > {tmp} << 'XMLEOF'\n{xml_content}\nXMLEOF"
    rc, _, stderr = await node_service.ssh_run(host, write_cmd)
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Failed to write XML: {stderr.strip()}")
    rc2, stdout2, stderr2 = await node_service.ssh_run(
        host, f"sudo virsh define {tmp} 2>&1 && rm -f {tmp}",
    )
    if rc2 != 0:
        raise HTTPException(status_code=500, detail=f"Failed to define VM: {stderr2.strip()}")
    return {"message": f"VM '{name}' redefined", "stdout": stdout2}
