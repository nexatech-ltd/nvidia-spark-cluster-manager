import logging

from fastapi import APIRouter, HTTPException, Query

from app.models.network import (
    BridgeCreate,
    BridgePortAction,
    InterfaceInfo,
    IPAction,
    RouteAction,
    RouteInfo,
    VlanCreate,
)
from app.services.network_svc import network_service

logger = logging.getLogger("spark-manager.network")
router = APIRouter()


# ── Interfaces ───────────────────────────────────────────────────────────────


@router.get("/interfaces", response_model=list[InterfaceInfo])
async def list_interfaces(node: str = Query("spark-1")):
    try:
        ifaces = await network_service.list_interfaces(node)
        return [InterfaceInfo(**i) for i in ifaces]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Bridges ──────────────────────────────────────────────────────────────────


@router.post("/bridges")
async def create_bridge(body: BridgeCreate):
    result = await network_service.create_bridge(body.name, body.node)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.delete("/bridges/{name}")
async def delete_bridge(name: str, node: str = Query("spark-1")):
    result = await network_service.delete_bridge(name, node)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.post("/bridges/ports")
async def bridge_port_action(body: BridgePortAction):
    if body.action == "add":
        result = await network_service.add_bridge_port(
            body.bridge, body.port, body.node,
        )
    elif body.action == "remove":
        result = await network_service.remove_bridge_port(
            body.bridge, body.port, body.node,
        )
    else:
        raise HTTPException(
            status_code=400, detail="action must be 'add' or 'remove'",
        )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


# ── VLANs ────────────────────────────────────────────────────────────────────


@router.post("/vlans")
async def create_vlan(body: VlanCreate):
    result = await network_service.create_vlan(body.parent, body.vlan_id, body.node)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.delete("/vlans/{name}")
async def delete_vlan(name: str, node: str = Query("spark-1")):
    result = await network_service.delete_vlan(name, node)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


# ── IP Addresses ─────────────────────────────────────────────────────────────


@router.post("/addresses")
async def ip_action(body: IPAction):
    if body.action == "add":
        result = await network_service.add_address(
            body.interface, body.address, body.node,
        )
    elif body.action == "remove":
        result = await network_service.remove_address(
            body.interface, body.address, body.node,
        )
    else:
        raise HTTPException(
            status_code=400, detail="action must be 'add' or 'remove'",
        )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


# ── Routes ───────────────────────────────────────────────────────────────────


@router.get("/routes", response_model=list[RouteInfo])
async def list_routes(node: str = Query("spark-1")):
    try:
        routes = await network_service.list_routes(node)
        return [RouteInfo(**r) for r in routes]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/routes")
async def route_action(body: RouteAction):
    if body.action == "add":
        result = await network_service.add_route(
            body.destination, body.gateway, body.interface, body.node,
        )
    elif body.action == "remove":
        result = await network_service.remove_route(
            body.destination, body.gateway, body.node,
        )
    else:
        raise HTTPException(
            status_code=400, detail="action must be 'add' or 'remove'",
        )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


# ── Topology ─────────────────────────────────────────────────────────────────


@router.get("/topology")
async def get_topology():
    try:
        return await network_service.get_topology()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
