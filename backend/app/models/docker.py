from pydantic import BaseModel


class StackCreate(BaseModel):
    name: str
    compose_content: str
    env_vars: dict[str, str] = {}


class StackInfo(BaseModel):
    name: str
    services: int


class ServiceInfo(BaseModel):
    id: str
    name: str
    mode: str
    replicas: str
    image: str
    ports: list[str]


class ContainerInfo(BaseModel):
    id: str
    name: str
    image: str
    status: str
    state: str
    node: str
    ports: list[str]
    created: str


class ImageInfo(BaseModel):
    id: str
    tags: list[str]
    size: int
    created: str


class RegistryAuth(BaseModel):
    server: str
    username: str
    password: str


class PullRequest(BaseModel):
    image: str
    tag: str = "latest"
    registry: str | None = None


class BuildRequest(BaseModel):
    dockerfile: str
    tag: str
    context_path: str = "."
