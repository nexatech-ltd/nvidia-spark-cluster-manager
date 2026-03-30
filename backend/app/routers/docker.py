import asyncio
import logging
import threading

from docker.errors import APIError, NotFound
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from app.models.docker import (
    ContainerInfo,
    ServiceInfo,
    StackCreate,
    StackInfo,
)
from app.services.docker_svc import docker_service

logger = logging.getLogger("spark-manager.docker")
router = APIRouter()

ALLOWED_CONTAINER_ACTIONS = {"start", "stop", "restart", "remove"}


# ── Stacks ──────────────────────────────────────────────────────────────────


@router.get("/stacks", response_model=list[StackInfo])
async def list_stacks():
    stacks = await docker_service.list_stacks()
    return [
        StackInfo(
            name=s.get("Name", ""),
            services=int(s.get("Services", 0)),
        )
        for s in stacks
    ]


@router.post("/stacks")
async def deploy_stack(stack: StackCreate):
    result = await docker_service.deploy_stack(
        stack.name, stack.compose_content, stack.env_vars or None,
    )
    if result["exit_code"] != 0:
        raise HTTPException(status_code=500, detail=result["stderr"])
    return {"message": f"Stack '{stack.name}' deployed", **result}


@router.get("/stacks/{name}/compose")
async def get_stack_compose(name: str):
    content = await docker_service.get_stack_compose(name)
    if content is None:
        raise HTTPException(status_code=404, detail="Compose file not found")
    return {"name": name, "compose_content": content}


@router.put("/stacks/{name}")
async def update_stack(name: str, stack: StackCreate):
    result = await docker_service.deploy_stack(
        name, stack.compose_content, stack.env_vars or None,
    )
    if result["exit_code"] != 0:
        raise HTTPException(status_code=500, detail=result["stderr"])
    return {"message": f"Stack '{name}' updated", **result}


@router.delete("/stacks/{name}")
async def remove_stack(name: str):
    result = await docker_service.remove_stack(name)
    if result["exit_code"] != 0:
        raise HTTPException(status_code=500, detail=result["stderr"])
    return {"message": f"Stack '{name}' removed", **result}


# ── Services ────────────────────────────────────────────────────────────────


@router.get("/services", response_model=list[ServiceInfo])
async def list_services():
    return await asyncio.to_thread(docker_service.list_services)


@router.post("/services/{service_id}/scale")
async def scale_service(service_id: str, replicas: int = Query(..., ge=0)):
    try:
        await asyncio.to_thread(docker_service.scale_service, service_id, replicas)
    except NotFound:
        raise HTTPException(status_code=404, detail="Service not found")
    except APIError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"message": f"Service '{service_id}' scaled to {replicas}"}


# ── Containers ──────────────────────────────────────────────────────────────


@router.get("/containers", response_model=list[ContainerInfo])
async def list_containers(all: bool = Query(False)):
    return await asyncio.to_thread(docker_service.list_containers, all)


@router.get("/containers/{container_id}")
async def inspect_container(container_id: str):
    try:
        return await asyncio.to_thread(docker_service.get_container, container_id)
    except NotFound:
        raise HTTPException(status_code=404, detail="Container not found")


@router.post("/containers/{container_id}/{action}")
async def container_action(container_id: str, action: str):
    if action not in ALLOWED_CONTAINER_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action. Allowed: {', '.join(sorted(ALLOWED_CONTAINER_ACTIONS))}",
        )
    try:
        await asyncio.to_thread(docker_service.container_action, container_id, action)
    except NotFound:
        raise HTTPException(status_code=404, detail="Container not found")
    except APIError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"message": f"Action '{action}' performed on container '{container_id}'"}


# ── WebSocket helpers ──────────────────────────────────────────────────────


_SENTINEL = object()


async def _stream_logs(websocket: WebSocket, log_fn, resource_id: str, label: str):
    """Stream Docker log generator over WebSocket without blocking the event loop."""
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()
    stopped = threading.Event()

    def _reader():
        stream = None
        try:
            stream = log_fn(resource_id, tail=100, follow=True)
            for chunk in stream:
                if stopped.is_set():
                    break
                text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk)
                loop.call_soon_threadsafe(queue.put_nowait, text)
        except Exception as exc:
            if not stopped.is_set():
                loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)
            if stream is not None and hasattr(stream, "close"):
                try:
                    stream.close()
                except Exception:
                    pass

    loop.run_in_executor(None, _reader)

    try:
        while True:
            item = await queue.get()
            if item is _SENTINEL:
                break
            if isinstance(item, Exception):
                await websocket.send_text(f"Error: {item}")
                break
            await websocket.send_text(item)
    except WebSocketDisconnect:
        logger.debug("Client disconnected from %s logs: %s", label, resource_id)
    except Exception as e:
        logger.exception("Error streaming %s logs for %s", label, resource_id)
        try:
            await websocket.send_text(f"Error: {e}")
        except Exception:
            pass
    finally:
        stopped.set()
        try:
            await websocket.close()
        except Exception:
            pass


# ── WebSocket: Container Logs ───────────────────────────────────────────────


@router.websocket("/ws/logs/container/{container_id}")
async def ws_container_logs(websocket: WebSocket, container_id: str):
    await _stream_logs(websocket, docker_service.container_logs, container_id, "container")


# ── WebSocket: Service Logs ─────────────────────────────────────────────────


@router.websocket("/ws/logs/service/{service_id}")
async def ws_service_logs(websocket: WebSocket, service_id: str):
    await _stream_logs(websocket, docker_service.service_logs, service_id, "service")


# ── WebSocket: Exec into Container ──────────────────────────────────────────


@router.websocket("/ws/exec/{container_id}")
async def ws_exec(websocket: WebSocket, container_id: str):
    await websocket.accept()
    try:
        container = await asyncio.to_thread(
            docker_service.client.containers.get, container_id,
        )
        exec_id = await asyncio.to_thread(
            docker_service.client.api.exec_create,
            container.id,
            cmd="/bin/sh",
            stdin=True,
            tty=True,
            stdout=True,
            stderr=True,
        )
        sock = await asyncio.to_thread(
            docker_service.client.api.exec_start,
            exec_id["Id"],
            socket=True,
            tty=True,
        )
        raw_sock = sock._sock  # noqa: SLF001

        async def read_from_container():
            loop = asyncio.get_event_loop()
            while True:
                data = await loop.run_in_executor(None, raw_sock.recv, 4096)
                if not data:
                    break
                await websocket.send_bytes(data)

        reader_task = asyncio.create_task(read_from_container())

        try:
            while True:
                data = await websocket.receive_bytes()
                await asyncio.to_thread(raw_sock.sendall, data)
        except WebSocketDisconnect:
            logger.debug("Client disconnected from exec: %s", container_id)
        finally:
            reader_task.cancel()
            try:
                raw_sock.close()
            except Exception:
                pass

    except NotFound:
        await websocket.send_text(f"Error: container '{container_id}' not found")
        await websocket.close()
    except Exception as e:
        logger.exception("Error in exec session for %s", container_id)
        try:
            await websocket.send_text(f"Error: {e}")
            await websocket.close()
        except Exception:
            pass
