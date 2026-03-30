from pydantic import BaseModel


class InterfaceInfo(BaseModel):
    name: str
    state: str
    mac: str
    mtu: int
    addresses: list[str]
    type: str = ""
    master: str | None = None


class BridgeCreate(BaseModel):
    name: str
    node: str = "spark-1"


class BridgePortAction(BaseModel):
    bridge: str
    port: str
    action: str
    node: str = "spark-1"


class VlanCreate(BaseModel):
    parent: str
    vlan_id: int
    node: str = "spark-1"


class IPAction(BaseModel):
    interface: str
    address: str
    action: str
    node: str = "spark-1"


class RouteInfo(BaseModel):
    destination: str
    gateway: str | None
    interface: str
    metric: int = 0


class RouteAction(BaseModel):
    destination: str
    gateway: str
    interface: str | None = None
    action: str = "add"
    node: str = "spark-1"
