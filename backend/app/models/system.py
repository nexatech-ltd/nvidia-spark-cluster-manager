from pydantic import BaseModel


class CpuCoreStats(BaseModel):
    core_id: int
    core_type: str  # "X925" (performance) or "A725" (efficiency)
    freq_mhz: int | None = None
    user: int = 0
    nice: int = 0
    system: int = 0
    idle: int = 0
    iowait: int = 0
    irq: int = 0
    softirq: int = 0


class CpuTotalStats(BaseModel):
    user: int = 0
    nice: int = 0
    system: int = 0
    idle: int = 0
    iowait: int = 0
    irq: int = 0
    softirq: int = 0


class GPUInfo(BaseModel):
    name: str
    temperature: int | None = None
    utilization: int | None = None
    power_draw: float | None = None
    clock_mhz: int | None = None
    pstate: str | None = None
    driver_version: str | None = None


class ThermalZone(BaseModel):
    name: str
    temp_c: float


class NetInterfaceStats(BaseModel):
    name: str
    speed_mbps: int | None = None
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_packets: int = 0
    tx_packets: int = 0
    state: str = "unknown"
    kind: str = ""  # "bond", "10g", "cx7-slave", "docker", etc.


class NvmeInfo(BaseModel):
    device: str
    total: int
    used: int
    free: int
    percent: float


class DetailedNodeStatus(BaseModel):
    hostname: str
    ip: str
    uptime: str = ""
    error: str | None = None

    cpu_total: CpuTotalStats = CpuTotalStats()
    cpu_cores: list[CpuCoreStats] = []
    perf_core_count: int = 0
    eff_core_count: int = 0

    mem_total: int = 0
    mem_used: int = 0
    mem_free: int = 0
    mem_available: int = 0
    mem_buffers: int = 0
    mem_cached: int = 0

    gpu: GPUInfo | None = None

    thermal_zones: list[ThermalZone] = []

    nvme: NvmeInfo | None = None

    net_interfaces: list[NetInterfaceStats] = []


class DetailedDashboardInfo(BaseModel):
    nodes: list[DetailedNodeStatus]
    stacks: int
    containers: int
    vms: int
    slurm_jobs_running: int
    slurm_jobs_pending: int


# Legacy models kept for backward compatibility
class NodeStatus(BaseModel):
    hostname: str
    ip: str
    cpu_count: int
    cpu_percent: float
    memory_total: int
    memory_used: int
    memory_percent: float
    disk_total: int
    disk_used: int
    gpu: GPUInfo | None = None
    uptime: str = ""
    error: str | None = None


class DashboardInfo(BaseModel):
    nodes: list[NodeStatus]
    stacks: int
    containers: int
    vms: int
    slurm_jobs_running: int
    slurm_jobs_pending: int
