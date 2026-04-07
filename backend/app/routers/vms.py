import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Query, UploadFile

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
    try:
        return await asyncio.to_thread(libvirt_service.list_isos, node)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


@router.get("/os-variants/")
async def list_os_variants(node: str = Query("spark-1")):
    try:
        host = node_service._host_for_node(node)
        rc, stdout, _ = await node_service.ssh_run(host, "virt-install --osinfo list 2>&1")
        if rc != 0:
            return []
        return [v.strip() for v in stdout.strip().split("\n") if v.strip()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Bridges (must be before /{name} catch-all) ───────────────────────────


@router.get("/bridges/")
async def list_bridges(node: str = Query("spark-1")):
    try:
        host = node_service._host_for_node(node)
        rc, stdout, _ = await node_service.ssh_run(
            host, "ip -j link show type bridge",
        )
        if rc != 0:
            return []
        bridges = json.loads(stdout)
        return [{"name": b["ifname"], "state": b.get("operstate", "unknown")} for b in bridges]
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
    try:
        return await asyncio.to_thread(libvirt_service.create_vm, params)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


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
