import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.models.storage import DiskUsage, MountInfo, NFSExport
from app.services.node_svc import node_service

logger = logging.getLogger("spark-manager.storage")
router = APIRouter()


# ── NFS Exports ──────────────────────────────────────────────────────────────


def _parse_exports(text: str) -> list[dict]:
    exports = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        path = parts[0]
        for client_opts in parts[1:]:
            if "(" in client_opts:
                client, _, opts = client_opts.partition("(")
                opts = opts.rstrip(")")
            else:
                client = client_opts
                opts = ""
            exports.append({"path": path, "clients": client, "options": opts})
    return exports


async def _get_exports_for_node(node: str) -> list[dict]:
    host = node_service._host_for_node(node)
    rc, stdout, _ = await node_service.ssh_run(host, "cat /etc/exports 2>/dev/null || true")
    if rc != 0:
        return []
    exports = _parse_exports(stdout)
    for exp in exports:
        exp["node"] = node
    return exports


@router.get("/exports", response_model=list[NFSExport])
async def list_exports():
    try:
        node1, node2 = await asyncio.gather(
            _get_exports_for_node(settings.node1_hostname),
            _get_exports_for_node(settings.node2_hostname),
        )
        return [NFSExport(**e) for e in node1 + node2]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/exports")
async def add_export(body: NFSExport, node: str = Query("spark-1")):
    export_line = f"{body.path} {body.clients}({body.options})"
    host = node_service._host_for_node(node)
    cmd = (
        f"echo '{export_line}' | sudo tee -a /etc/exports"
        f" && sudo exportfs -ra"
    )
    rc, _, stderr = await node_service.ssh_run(host, cmd)
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Failed: {stderr}")
    return {"message": f"Export added: {export_line}"}


@router.delete("/exports")
async def remove_export(
    path: str = Query(...), clients: str = Query(...), node: str = Query("spark-1"),
):
    host = node_service._host_for_node(node)
    escaped_path = path.replace("/", "\\/")
    cmd = (
        f"sudo sed -i '/{escaped_path}.*{clients}/d' /etc/exports"
        f" && sudo exportfs -ra"
    )
    rc, _, stderr = await node_service.ssh_run(host, cmd)
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"Failed: {stderr}")
    return {"message": f"Export removed: {path} {clients}"}


# ── Mounts ───────────────────────────────────────────────────────────────────


def _parse_mounts(mounts_text: str, df_text: str) -> list[dict]:
    df_map: dict[str, dict] = {}
    for line in df_text.strip().split("\n")[1:]:
        parts = line.split()
        if len(parts) >= 6:
            try:
                df_map[parts[5]] = {
                    "total": int(parts[1]) * 1024,
                    "used": int(parts[2]) * 1024,
                    "free": int(parts[3]) * 1024,
                }
            except ValueError:
                pass

    mounts = []
    skip_fs = {"proc", "sysfs", "devtmpfs", "devpts", "tmpfs", "cgroup", "cgroup2",
               "securityfs", "pstore", "debugfs", "hugetlbfs", "mqueue", "configfs",
               "binfmt_misc", "autofs", "fusectl", "tracefs", "bpf", "nsfs", "fuse.portal"}
    for line in mounts_text.strip().split("\n"):
        parts = line.split()
        if len(parts) < 4:
            continue
        device, mountpoint, fstype, options = parts[0], parts[1], parts[2], parts[3]
        if fstype in skip_fs:
            continue
        usage = df_map.get(mountpoint, {})
        mounts.append({
            "device": device,
            "mountpoint": mountpoint,
            "fstype": fstype,
            "options": options,
            "total": usage.get("total", 0),
            "used": usage.get("used", 0),
            "free": usage.get("free", 0),
        })
    return mounts


@router.get("/mounts", response_model=list[MountInfo])
async def list_mounts(node: str = Query("spark-1")):
    try:
        host = node_service._host_for_node(node)
        rc, stdout, _ = await node_service.ssh_run(
            host, "cat /proc/mounts && echo '===DELIM===' && df",
        )
        if rc != 0:
            return []
        parts = stdout.split("===DELIM===")
        if len(parts) < 2:
            return []
        mounts = _parse_mounts(parts[0], parts[1])
        return [MountInfo(**m) for m in mounts]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Disk Usage ───────────────────────────────────────────────────────────────


def _parse_df(text: str) -> list[dict]:
    disks = []
    for line in text.strip().split("\n")[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        try:
            total = int(parts[1]) * 1024
            used = int(parts[2]) * 1024
            free = int(parts[3]) * 1024
            percent_str = parts[4].replace("%", "")
            percent = float(percent_str)
        except ValueError:
            continue
        disks.append({
            "device": parts[0],
            "mountpoint": parts[5],
            "total": total,
            "used": used,
            "free": free,
            "percent": percent,
        })
    return disks


@router.get("/disk-usage", response_model=list[DiskUsage])
async def get_disk_usage(node: str = Query("spark-1")):
    try:
        host = node_service._host_for_node(node)
        rc, stdout, _ = await node_service.ssh_run(
            host, "df -x tmpfs -x devtmpfs -x squashfs",
        )
        if rc != 0:
            return []
        disks = _parse_df(stdout)
        return [DiskUsage(**d) for d in disks]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── NVMe Health ──────────────────────────────────────────────────────────────


@router.get("/nvme-health")
async def get_nvme_health(node: str = Query("spark-1")):
    try:
        host = node_service._host_for_node(node)
        cmd = "sudo nvme smart-log /dev/nvme0 -o json 2>/dev/null || df -h --output=source,size,used,avail,pcent -x tmpfs -x devtmpfs"
        rc, output, _ = await node_service.ssh_run(host, cmd)

        try:
            return {"type": "nvme", "data": json.loads(output)}
        except (json.JSONDecodeError, ValueError):
            lines = output.strip().split("\n")
            return {"type": "disk-fallback", "data": lines}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
