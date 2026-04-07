import asyncio
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
from app.services.libvirt_svc import libvirt_service
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


# ── OS Variants (must be before /{name} catch-all) ───────────────────────


_OSINFO_ARM_SCRIPT = r"""
import gi
gi.require_version('Libosinfo', '1.0')
from gi.repository import Libosinfo
loader = Libosinfo.Loader()
loader.process_default_path()
db = loader.get_db()
os_list = db.get_os_list()
ids = set()
for i in range(os_list.get_length()):
    o = os_list.get_nth(i)
    sid = o.get_short_id()
    for getter in (o.get_tree_list, o.get_image_list):
        lst = getter()
        for j in range(lst.get_length()):
            if lst.get_nth(j).get_architecture() == 'aarch64':
                ids.add(sid)
                break
for sid in sorted(ids):
    print(sid)
""".strip()

_ARM_EXTRAS = ["win10", "win11", "generic"]


@router.get("/os-variants/")
async def list_os_variants(node: str = Query("spark-1")):
    """Return OS variants that support aarch64 on the target node."""
    host = node_service._host_for_node(node)
    try:
        rc, stdout, _ = await node_service.ssh_run(
            host, f"python3 -c {_shlex_quote(_OSINFO_ARM_SCRIPT)}",
        )
        if rc == 0 and stdout.strip():
            variants = [v.strip() for v in stdout.strip().split("\n") if v.strip()]
        else:
            rc2, stdout2, _ = await node_service.ssh_run(
                host, "virt-install --osinfo list 2>&1",
            )
            variants = [v.strip() for v in stdout2.strip().split("\n") if v.strip()] if rc2 == 0 else []
        for extra in _ARM_EXTRAS:
            if extra not in variants:
                variants.append(extra)
        return variants
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    try:
        return await asyncio.to_thread(libvirt_service.list_disks, pool, node)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disks/")
async def create_disk(params: DiskCreate, node: str | None = Query(None)):
    try:
        return await asyncio.to_thread(libvirt_service.create_disk, params, node)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    _, arch_out, _ = await node_service.ssh_run(host, "uname -m")
    host_arch = arch_out.strip() or "aarch64"
    cmd = libvirt_service.build_virt_install_cmd(params, host_arch=host_arch)
    logger.info("Creating VM on %s (%s): %s", params.node, host_arch, cmd)
    rc, stdout, stderr = await node_service.ssh_run(host, cmd)
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"virt-install failed: {stderr.strip()}")
    return {"message": f"VM '{params.name}' created on {params.node}", "stdout": stdout}


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
    try:
        return await asyncio.to_thread(
            libvirt_service.vm_action, name, node, body.action,
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
    try:
        return await asyncio.to_thread(
            libvirt_service.attach_disk, name, disk_path, node,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{name}/disks/detach")
async def detach_disk(name: str, body: dict, node: str | None = Query(None)):
    disk_path = body.get("path")
    if not disk_path:
        raise HTTPException(status_code=400, detail="Disk path is required")
    try:
        return await asyncio.to_thread(
            libvirt_service.detach_disk, name, disk_path, node,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


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
