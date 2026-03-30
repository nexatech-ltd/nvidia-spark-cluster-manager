import json
import logging
import os
from asyncio.subprocess import PIPE

import asyncssh
import docker

from app.config import settings

logger = logging.getLogger("spark-manager.docker")


class DockerService:
    def __init__(self):
        self.client = docker.from_env()

    async def _ssh_run(self, command: str) -> tuple[int, str, str]:
        """Run a command on the manager node via SSH (for docker stack etc.)."""
        host = settings.node1_ip
        try:
            async with asyncssh.connect(
                host,
                username=settings.ssh_user,
                known_hosts=None,
                client_keys=[settings.ssh_key_path],
            ) as conn:
                result = await conn.run(command, check=False)
                return (
                    result.exit_status or 0,
                    result.stdout or "",
                    result.stderr or "",
                )
        except Exception as e:
            logger.exception("SSH to %s failed for Docker command", host)
            return 1, "", str(e)

    async def list_stacks(self) -> list[dict]:
        """List docker stacks via SSH (SDK doesn't support stacks)."""
        rc, stdout, stderr = await self._ssh_run(
            "docker stack ls --format json",
        )
        stacks = []
        for line in stdout.strip().split("\n"):
            if line:
                try:
                    stacks.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return stacks

    async def deploy_stack(
        self, name: str, compose_content: str, env_vars: dict | None = None
    ) -> dict:
        """Deploy a stack from compose content via SSH."""
        escaped = compose_content.replace("'", "'\\''")
        env_str = ""
        if env_vars:
            env_str = " ".join(f"{k}={v}" for k, v in env_vars.items()) + " "

        cmd = (
            f"mkdir -p /tmp/spark-stacks/{name} && "
            f"cat > /tmp/spark-stacks/{name}/docker-compose.yml << 'COMPOSE_EOF'\n"
            f"{compose_content}\n"
            f"COMPOSE_EOF\n"
            f"{env_str}docker stack deploy -c /tmp/spark-stacks/{name}/docker-compose.yml {name}"
        )
        rc, stdout, stderr = await self._ssh_run(cmd)
        return {
            "exit_code": rc,
            "stdout": stdout,
            "stderr": stderr,
        }

    async def remove_stack(self, name: str) -> dict:
        rc, stdout, stderr = await self._ssh_run(f"docker stack rm {name}")
        return {
            "exit_code": rc,
            "stdout": stdout,
            "stderr": stderr,
        }

    async def get_stack_compose(self, name: str) -> str | None:
        search_paths = " ".join([
            f"/tmp/spark-stacks/{name}/docker-compose.yml",
            f"/opt/{name}/docker-compose.yml",
            f"/opt/{name}/deploy/docker-compose.yml",
            f"/opt/{name}/deploy/docker-compose.prod.yml",
        ])
        rc, stdout, _ = await self._ssh_run(
            f'for f in {search_paths}; do [ -f "$f" ] && cat "$f" && exit 0; done; exit 1'
        )
        if rc != 0 or not stdout.strip():
            return None
        return stdout

    def list_services(self) -> list[dict]:
        services = self.client.services.list()
        result = []
        for s in services:
            attrs = s.attrs
            spec = attrs.get("Spec", {})
            mode = spec.get("Mode", {})
            if "Replicated" in mode:
                replicas_spec = mode["Replicated"].get("Replicas", 0)
            else:
                replicas_spec = "global"

            tasks = s.tasks(filters={"desired-state": "running"})
            running = len(
                [t for t in tasks if t.get("Status", {}).get("State") == "running"]
            )
            if isinstance(replicas_spec, int):
                replicas_str = f"{running}/{replicas_spec}"
            else:
                replicas_str = f"{running} (global)"

            ports = []
            endpoint = attrs.get("Endpoint", {}).get("Ports", [])
            for p in endpoint or []:
                ports.append(
                    f"{p.get('PublishedPort', '?')}:{p.get('TargetPort', '?')}"
                    f"/{p.get('Protocol', 'tcp')}"
                )

            result.append({
                "id": attrs["ID"][:12],
                "name": spec.get("Name", ""),
                "mode": "replicated" if "Replicated" in mode else "global",
                "replicas": replicas_str,
                "image": spec.get("TaskTemplate", {})
                    .get("ContainerSpec", {})
                    .get("Image", "")
                    .split("@")[0],
                "ports": ports,
            })
        return result

    def list_containers(self, all_containers: bool = False) -> list[dict]:
        containers = self.client.containers.list(all=all_containers)
        result = []
        for c in containers:
            ports = []
            for k, v in (c.ports or {}).items():
                if v:
                    for binding in v:
                        ports.append(f"{binding.get('HostPort', '?')}:{k}")
                else:
                    ports.append(k)
            result.append({
                "id": c.short_id,
                "name": c.name,
                "image": c.image.tags[0] if c.image.tags else c.image.short_id,
                "status": c.status,
                "state": c.attrs.get("State", {}).get("Status", ""),
                "node": c.labels.get("com.docker.swarm.node.id", "local"),
                "ports": ports,
                "created": c.attrs.get("Created", ""),
            })
        return result

    def get_container(self, container_id: str) -> dict:
        c = self.client.containers.get(container_id)
        return c.attrs

    def container_action(self, container_id: str, action: str):
        c = self.client.containers.get(container_id)
        getattr(c, action)()

    def container_logs(
        self, container_id: str, tail: int = 100, follow: bool = False
    ):
        c = self.client.containers.get(container_id)
        return c.logs(stream=follow, follow=follow, tail=tail, timestamps=True)

    def list_images(self) -> list[dict]:
        images = self.client.images.list()
        result = []
        for img in images:
            result.append({
                "id": img.short_id,
                "tags": img.tags,
                "size": img.attrs.get("Size", 0),
                "created": img.attrs.get("Created", ""),
            })
        return result

    def pull_image(
        self, image: str, tag: str = "latest", auth_config: dict | None = None
    ):
        return self.client.api.pull(
            image, tag=tag, stream=True, decode=True, auth_config=auth_config,
        )

    def build_image(
        self, path: str, tag: str, dockerfile: str = "Dockerfile"
    ):
        return self.client.api.build(
            path=path, tag=tag, dockerfile=dockerfile, decode=True, rm=True,
        )

    def remove_image(self, image_id: str, force: bool = False):
        self.client.images.remove(image_id, force=force)

    def prune_images(self) -> dict:
        return self.client.images.prune()

    def scale_service(self, service_id: str, replicas: int):
        svc = self.client.services.get(service_id)
        svc.scale(replicas)

    def service_logs(
        self, service_id: str, tail: int = 100, follow: bool = False
    ):
        svc = self.client.services.get(service_id)
        return svc.logs(
            stdout=True, stderr=True, follow=follow, tail=tail, timestamps=True,
        )

    def login_registry(self, server: str, username: str, password: str) -> dict:
        return self.client.login(
            username=username, password=password, registry=server,
        )


docker_service = DockerService()
