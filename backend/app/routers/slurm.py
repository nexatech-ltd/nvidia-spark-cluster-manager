import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.models.slurm import ClusterInfo, JobInfo, JobSubmit, NodeInfo
from app.services.slurm_svc import slurm_service

logger = logging.getLogger("spark-manager.slurm")
router = APIRouter()


# ── Jobs ─────────────────────────────────────────────────────────────────────


@router.get("/jobs", response_model=list[JobInfo])
async def list_jobs():
    jobs = await slurm_service.list_jobs()
    return [JobInfo(**j) for j in jobs]


@router.post("/jobs")
async def submit_job(params: JobSubmit):
    result = await slurm_service.submit_job(params)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.get("/jobs/{job_id}")
async def get_job_detail(job_id: str):
    detail = await slurm_service.get_job_detail(job_id)
    if "error" in detail:
        raise HTTPException(status_code=404, detail=detail["error"])
    return detail


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    result = await slurm_service.cancel_job(job_id)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


# ── Nodes / Cluster ──────────────────────────────────────────────────────────


@router.get("/nodes", response_model=list[NodeInfo])
async def list_nodes():
    nodes = await slurm_service.list_nodes()
    return [NodeInfo(**n) for n in nodes]


@router.get("/cluster", response_model=ClusterInfo)
async def get_cluster_info():
    return await slurm_service.get_cluster_info()


# ── WebSocket: Job Output Streaming ─────────────────────────────────────────


@router.websocket("/ws/jobs/{job_id}/output")
async def ws_job_output(websocket: WebSocket, job_id: str):
    await websocket.accept()
    try:
        output_path = await slurm_service.get_job_output_path(job_id)
        if not output_path:
            await websocket.send_text(f"Error: could not find output for job {job_id}")
            await websocket.close()
            return

        path = Path(output_path)
        if not path.exists():
            await websocket.send_text(f"Waiting for output file: {output_path}")
            for _ in range(30):
                await asyncio.sleep(1)
                if path.exists():
                    break
            else:
                await websocket.send_text("Output file not created within timeout")
                await websocket.close()
                return

        proc = await asyncio.create_subprocess_exec(
            "tail", "-f", "-n", "+1", str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            while True:
                line = await asyncio.wait_for(
                    proc.stdout.readline(), timeout=300,
                )
                if not line:
                    break
                await websocket.send_text(line.decode("utf-8", errors="replace"))
        except asyncio.TimeoutError:
            await websocket.send_text("[stream timeout — job may have finished]")
        finally:
            proc.kill()
            await proc.wait()

    except WebSocketDisconnect:
        logger.debug("Client disconnected from job output: %s", job_id)
    except Exception as e:
        logger.exception("Error streaming job output for %s", job_id)
        try:
            await websocket.send_text(f"Error: {e}")
            await websocket.close()
        except Exception:
            pass


# ── Templates ────────────────────────────────────────────────────────────────


JOB_TEMPLATES = [
    {
        "name": "Single-Node GPU",
        "description": "Run a single-GPU job on one node",
        "params": {
            "name": "gpu-job",
            "partition": "gpu",
            "nodes": 1,
            "ntasks_per_node": 1,
            "gpus_per_node": 1,
            "working_dir": "/data",
            "command": "nvidia-smi",
        },
    },
    {
        "name": "Multi-GPU Single Node",
        "description": "Use all GPUs on one DGX Spark node",
        "params": {
            "name": "multi-gpu-job",
            "partition": "gpu",
            "nodes": 1,
            "ntasks_per_node": 1,
            "gpus_per_node": 4,
            "working_dir": "/data",
            "command": "torchrun --nproc_per_node=4 train.py",
        },
    },
    {
        "name": "Multi-Node NCCL",
        "description": "Distributed training across both DGX Spark nodes with NCCL",
        "params": {
            "name": "nccl-job",
            "partition": "gpu",
            "nodes": 2,
            "ntasks_per_node": 4,
            "gpus_per_node": 4,
            "working_dir": "/data",
            "command": (
                "torchrun --nnodes=2 --nproc_per_node=4"
                " --rdzv_backend=c10d --rdzv_endpoint=$SLURM_NODELIST:29500"
                " train.py"
            ),
        },
    },
    {
        "name": "Container Job (Pyxis)",
        "description": "Run a job inside an NGC container via Pyxis/Enroot",
        "params": {
            "name": "container-job",
            "partition": "gpu",
            "nodes": 1,
            "ntasks_per_node": 1,
            "gpus_per_node": 1,
            "container_image": "nvcr.io/nvidia/pytorch:24.05-py3",
            "working_dir": "/data",
            "command": "python train.py",
        },
    },
]


@router.get("/templates")
async def get_templates():
    return JOB_TEMPLATES
