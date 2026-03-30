from pydantic import BaseModel


class NFSExport(BaseModel):
    path: str
    clients: str
    options: str
    node: str = ""


class MountInfo(BaseModel):
    device: str
    mountpoint: str
    fstype: str
    options: str
    total: int = 0
    used: int = 0
    free: int = 0


class DiskUsage(BaseModel):
    device: str
    mountpoint: str
    total: int
    used: int
    free: int
    percent: float
