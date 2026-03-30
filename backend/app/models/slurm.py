from pydantic import BaseModel


class JobSubmit(BaseModel):
    script: str | None = None
    name: str = "job"
    partition: str = "gpu"
    nodes: int = 1
    ntasks_per_node: int = 1
    gpus_per_node: int = 1
    container_image: str | None = None
    command: str | None = None
    working_dir: str = "/data"


class JobInfo(BaseModel):
    id: str
    name: str
    user: str
    state: str
    nodes: str
    partition: str
    time: str
    gpus: str = ""


class NodeInfo(BaseModel):
    name: str
    state: str
    cpus: int
    memory: int
    gpus: int
    alloc_cpus: int = 0
    alloc_memory: int = 0


class ClusterInfo(BaseModel):
    nodes: list[NodeInfo]
    jobs_running: int
    jobs_pending: int
