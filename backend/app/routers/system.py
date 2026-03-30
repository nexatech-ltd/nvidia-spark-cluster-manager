import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.models.system import (
    DashboardInfo,
    DetailedDashboardInfo,
    DetailedNodeStatus,
    GPUInfo,
    NodeStatus,
)
from app.services.docker_svc import docker_service
from app.services.libvirt_svc import libvirt_service
from app.services.node_svc import node_service
from app.services.slurm_svc import slurm_service

logger = logging.getLogger("spark-manager.system")
router = APIRouter()


# ── Nodes ────────────────────────────────────────────────────────────────────


@router.get("/nodes", response_model=list[NodeStatus])
async def list_nodes():
    try:
        node1, node2 = await asyncio.gather(
            node_service.get_node_status(settings.node1_hostname),
            node_service.get_node_status(settings.node2_hostname),
        )
        return [NodeStatus(**node1), NodeStatus(**node2)]
    except Exception as e:
        logger.exception("Error listing node statuses")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/nodes/{node}", response_model=NodeStatus)
async def get_node_status(node: str):
    try:
        status = await node_service.get_node_status(node)
        return NodeStatus(**status)
    except Exception as e:
        logger.exception("Error getting node status for %s", node)
        raise HTTPException(status_code=500, detail=str(e))


# ── GPU ──────────────────────────────────────────────────────────────────────


@router.get("/gpu/{node}", response_model=list[GPUInfo])
async def get_gpu_info(node: str):
    try:
        gpus = await node_service.get_gpu_info(node)
        return [GPUInfo(**g) for g in gpus]
    except Exception as e:
        logger.exception("Error getting GPU info for %s", node)
        raise HTTPException(status_code=500, detail=str(e))


# ── Dashboard ────────────────────────────────────────────────────────────────


async def _safe_gather_nodes() -> list[dict]:
    try:
        node1, node2 = await asyncio.gather(
            node_service.get_node_status(settings.node1_hostname),
            node_service.get_node_status(settings.node2_hostname),
        )
        return [node1, node2]
    except Exception as e:
        logger.warning("Failed to gather node statuses: %s", e)
        return []


async def _safe_count_stacks() -> int:
    try:
        stacks = await docker_service.list_stacks()
        return len(stacks)
    except Exception:
        return 0


async def _safe_count_containers() -> int:
    try:
        containers = await asyncio.to_thread(docker_service.list_containers)
        return len(containers)
    except Exception:
        return 0


async def _safe_count_vms() -> int:
    try:
        vms = await asyncio.to_thread(libvirt_service.list_vms)
        return len(vms)
    except Exception:
        return 0


async def _safe_slurm_info() -> tuple[int, int]:
    try:
        info = await slurm_service.get_cluster_info()
        return info.get("jobs_running", 0), info.get("jobs_pending", 0)
    except Exception:
        return 0, 0


@router.get("/dashboard", response_model=DashboardInfo)
async def get_dashboard():
    try:
        nodes, stacks, containers, vms, slurm = await asyncio.gather(
            _safe_gather_nodes(),
            _safe_count_stacks(),
            _safe_count_containers(),
            _safe_count_vms(),
            _safe_slurm_info(),
        )
        slurm_running, slurm_pending = slurm
        node_statuses = [NodeStatus(**n) for n in nodes]
        return DashboardInfo(
            nodes=node_statuses,
            stacks=stacks,
            containers=containers,
            vms=vms,
            slurm_jobs_running=slurm_running,
            slurm_jobs_pending=slurm_pending,
        )
    except Exception as e:
        logger.exception("Error building dashboard")
        raise HTTPException(status_code=500, detail=str(e))


# ── Detailed Dashboard (GB10-aware) ─────────────────────────────────────────


async def _safe_detailed_nodes() -> list[dict]:
    try:
        node1, node2 = await asyncio.gather(
            node_service.get_detailed_status(settings.node1_hostname),
            node_service.get_detailed_status(settings.node2_hostname),
        )
        return [node1, node2]
    except Exception as e:
        logger.warning("Failed to gather detailed node statuses: %s", e)
        return []


@router.get("/dashboard/detailed", response_model=DetailedDashboardInfo)
async def get_detailed_dashboard():
    try:
        nodes, stacks, containers, vms, slurm = await asyncio.gather(
            _safe_detailed_nodes(),
            _safe_count_stacks(),
            _safe_count_containers(),
            _safe_count_vms(),
            _safe_slurm_info(),
        )
        slurm_running, slurm_pending = slurm
        node_statuses = [DetailedNodeStatus(**n) for n in nodes]
        return DetailedDashboardInfo(
            nodes=node_statuses,
            stacks=stacks,
            containers=containers,
            vms=vms,
            slurm_jobs_running=slurm_running,
            slurm_jobs_pending=slurm_pending,
        )
    except Exception as e:
        logger.exception("Error building detailed dashboard")
        raise HTTPException(status_code=500, detail=str(e))
