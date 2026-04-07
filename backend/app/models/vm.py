from pydantic import BaseModel


class VMCreate(BaseModel):
    name: str
    vcpus: int = 4
    memory_mb: int = 4096
    disk_size_gb: int = 20
    disk_format: str = "qcow2"
    disk_bus: str = "virtio"
    nic_model: str = "virtio"
    iso: str | None = None
    network: str = "default"
    network_type: str = "bridge"
    os_variant: str = "generic"
    node: str = "spark-1"
    bios: str = "uefi"
    machine_type: str | None = None
    tpm: bool | None = None
    secure_boot: bool = False
    video: str = "virtio"
    cpu_type: str = "host-passthrough"
    custom_xml: str | None = None


class VMInfo(BaseModel):
    name: str
    state: str
    vcpus: int
    memory_mb: int
    disks: list[dict]
    interfaces: list[dict]
    vnc_port: int | None = None
    autostart: bool = False
    node: str = ""
    boot_order: list[str] = []


class VMAction(BaseModel):
    action: str
    timeout: int | None = None


class SnapshotInfo(BaseModel):
    name: str
    creation_time: str
    state: str


class ISOInfo(BaseModel):
    name: str
    size: int
    path: str


class DiskCreate(BaseModel):
    name: str
    size_gb: int
    format: str = "qcow2"
    pool: str = "default"


class DiskInfo(BaseModel):
    name: str
    size: int
    format: str
    path: str
    pool: str
