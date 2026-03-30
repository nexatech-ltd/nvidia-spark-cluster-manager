import logging

import httpx
from fastapi import APIRouter, HTTPException

from app.config import settings

logger = logging.getLogger("spark-manager.traefik")
router = APIRouter()

TRAEFIK_URLS = [
    f"http://{settings.node1_ip}:8080",
    f"http://{settings.node2_ip}:8080",
]


async def _fetch_traefik(path: str, node_idx: int | None = None):
    urls = [TRAEFIK_URLS[node_idx]] if node_idx is not None else TRAEFIK_URLS
    results = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        for url in urls:
            try:
                resp = await client.get(f"{url}/api/{path}")
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    results.extend(data)
                else:
                    results.append(data)
            except Exception as exc:
                logger.warning("Traefik API %s/%s: %s", url, path, exc)
    return results


@router.get("/overview")
async def traefik_overview():
    """Aggregated overview from all Traefik instances."""
    nodes = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        for i, url in enumerate(TRAEFIK_URLS):
            hostname = settings.node1_hostname if i == 0 else settings.node2_hostname
            ip = settings.node1_ip if i == 0 else settings.node2_ip
            entry = {"node": hostname, "ip": ip, "status": "down", "version": None}
            try:
                resp = await client.get(f"{url}/api/version")
                if resp.status_code == 200:
                    entry["status"] = "up"
                    entry["version"] = resp.json().get("Version")
            except Exception:
                pass

            try:
                resp = await client.get(f"{url}/api/overview")
                if resp.status_code == 200:
                    entry["overview"] = resp.json()
            except Exception:
                pass
            nodes.append(entry)
    return nodes


@router.get("/routers")
async def list_routers():
    return await _fetch_traefik("http/routers")


@router.get("/services")
async def list_services():
    return await _fetch_traefik("http/services")


@router.get("/middlewares")
async def list_middlewares():
    return await _fetch_traefik("http/middlewares")


@router.get("/entrypoints")
async def list_entrypoints():
    return await _fetch_traefik("entrypoints")
