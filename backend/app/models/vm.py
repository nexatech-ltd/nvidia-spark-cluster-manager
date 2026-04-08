from pydantic import BaseModel


class VMCreate(BaseModel):
    name: str

    # ── CPU (PVE-style: sockets × cores) ──
    sockets: int = 1
    cores: int = 4
    vcpus: int | None = None  # legacy compat — overrides sockets*cores
    cpu_type: str = "host-passthrough"
    numa: bool = False

    # ── Memory ──
    memory_mb: int = 4096
    balloon: int | None = None  # 0 = disabled, None = same as memory_mb

    # ── Disk ──
    disk_size_gb: int = 20
    disk_format: str = "qcow2"
    disk_bus: str = "virtio"  # virtio | scsi | sata | ide
    cache: str = "none"  # none | writeback | writethrough | directsync | unsafe
    discard: str = "ignore"  # ignore | on
    io_thread: bool = False
    ssd_emulation: bool = False
    scsihw: str = "virtio-scsi-pci"  # virtio-scsi-pci | lsi | megasas | pvscsi

    # ── Network ──
    nic_model: str = "virtio"
    network: str = "default"
    network_type: str = "bridge"

    # ── Media ──
    iso: str | None = None
    drivers_iso: str | None = None

    # ── Display ──
    video: str = "virtio"  # virtio | std | qxl | cirrus | vmware | virtio-gl | none

    # ── Firmware / Machine ──
    bios: str = "uefi"  # uefi/ovmf | bios/seabios
    machine_type: str | None = None  # auto | pc | q35 | virt | virt-X.Y
    tpm: bool | None = None
    secure_boot: bool = False

    # ── OS ──
    os_variant: str = "generic"

    # ── Guest features ──
    agent: bool = True
    tablet: bool = True
    onboot: bool = False

    # ── Meta ──
    node: str = "spark-1"
    custom_xml: str | None = None

    def get_total_vcpus(self) -> int:
        if self.vcpus is not None:
            return self.vcpus
        return self.sockets * self.cores

    def get_topology(self) -> tuple[int, int]:
        """Return (sockets, cores_per_socket)."""
        if self.vcpus is not None:
            return (self.sockets, self.vcpus // self.sockets)
        return (self.sockets, self.cores)


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
