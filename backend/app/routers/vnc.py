import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.config import settings
from app.services.libvirt_svc import libvirt_service

logger = logging.getLogger("spark-manager.vnc")
router = APIRouter()

TCP_READ_SIZE = 65536


@router.websocket("/ws/{vm_name}")
async def vnc_proxy(websocket: WebSocket, vm_name: str, node: str = Query(...)):
    await websocket.accept()

    try:
        vnc_port = await asyncio.to_thread(
            libvirt_service.get_vnc_port, vm_name, node,
        )
    except ValueError as e:
        await websocket.send_text(f"Error: {e}")
        await websocket.close(code=1008)
        return

    if vnc_port is None:
        await websocket.send_text(f"Error: No VNC port found for VM '{vm_name}'")
        await websocket.close(code=1008)
        return

    vnc_host = "127.0.0.1" if node == settings.node1_hostname else settings.node2_ip

    try:
        reader, writer = await asyncio.open_connection(vnc_host, vnc_port)
    except (OSError, ConnectionRefusedError) as e:
        logger.error("Failed to connect to VNC %s:%d - %s", vnc_host, vnc_port, e)
        await websocket.send_text(f"Error: Cannot connect to VNC server at {vnc_host}:{vnc_port}")
        await websocket.close(code=1011)
        return

    logger.info("VNC proxy connected: %s -> %s:%d", vm_name, vnc_host, vnc_port)

    async def ws_to_tcp():
        try:
            while True:
                data = await websocket.receive_bytes()
                writer.write(data)
                await writer.drain()
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.debug("ws_to_tcp ended: %s", e)

    async def tcp_to_ws():
        try:
            while True:
                data = await reader.read(TCP_READ_SIZE)
                if not data:
                    break
                await websocket.send_bytes(data)
        except Exception as e:
            logger.debug("tcp_to_ws ended: %s", e)

    ws_task = asyncio.create_task(ws_to_tcp())
    tcp_task = asyncio.create_task(tcp_to_ws())

    try:
        done, pending = await asyncio.wait(
            {ws_task, tcp_task}, return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("VNC proxy closed for %s", vm_name)
