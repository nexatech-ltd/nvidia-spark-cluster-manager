import asyncio
import logging
import re

import asyncssh

from app.config import settings
from app.models.slurm import JobSubmit

logger = logging.getLogger("spark-manager.slurm")


class SlurmService:
    """All Slurm commands run via SSH on the controller node (spark-1)."""

    async def _ssh_run(self, command: str) -> tuple[int, str, str]:
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
            logger.exception("SSH to %s failed for Slurm command", host)
            return 1, "", str(e)

    async def list_jobs(self) -> list[dict]:
        rc, stdout, stderr = await self._ssh_run(
            "squeue -o '%i|%j|%u|%T|%N|%P|%M|%b' --noheader",
        )
        if rc != 0:
            logger.error("squeue failed: %s", stderr)
            return []
        jobs = []
        fields = ("id", "name", "user", "state", "nodes", "partition", "time", "gpus")
        for line in stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= len(fields):
                jobs.append(dict(zip(fields, parts)))
        return jobs

    async def list_nodes(self) -> list[dict]:
        rc, stdout, stderr = await self._ssh_run(
            "sinfo -N -o '%N|%T|%c|%m|%G|%C|%e' --noheader",
        )
        if rc != 0:
            logger.error("sinfo failed: %s", stderr)
            return []
        nodes = []
        for line in stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) < 7:
                continue
            gpu_count = 0
            gres = parts[4]
            m = re.search(r"gpu[^:]*:(\d+)", gres)
            if m:
                gpu_count = int(m.group(1))

            cpu_state = parts[5]
            alloc_cpus = 0
            cpu_parts = cpu_state.split("/")
            if len(cpu_parts) >= 1:
                try:
                    alloc_cpus = int(cpu_parts[0])
                except ValueError:
                    pass

            try:
                memory = int(parts[3])
            except ValueError:
                memory = 0
            try:
                cpus = int(parts[2])
            except ValueError:
                cpus = 0

            try:
                free_mem = int(parts[6])
                alloc_memory = memory - free_mem
            except ValueError:
                alloc_memory = 0

            nodes.append({
                "name": parts[0],
                "state": parts[1],
                "cpus": cpus,
                "memory": memory,
                "gpus": gpu_count,
                "alloc_cpus": alloc_cpus,
                "alloc_memory": max(alloc_memory, 0),
            })
        return nodes

    async def get_cluster_info(self) -> dict:
        nodes, jobs = await asyncio.gather(
            self.list_nodes(), self.list_jobs(),
        )
        running = sum(1 for j in jobs if j.get("state") == "RUNNING")
        pending = sum(1 for j in jobs if j.get("state") == "PENDING")
        return {"nodes": nodes, "jobs_running": running, "jobs_pending": pending}

    def _generate_sbatch_script(self, params: JobSubmit) -> str:
        lines = ["#!/bin/bash"]
        lines.append(f"#SBATCH --job-name={params.name}")
        lines.append(f"#SBATCH --partition={params.partition}")
        lines.append(f"#SBATCH --nodes={params.nodes}")
        lines.append(f"#SBATCH --ntasks-per-node={params.ntasks_per_node}")
        lines.append(f"#SBATCH --gpus-per-node={params.gpus_per_node}")
        lines.append(f"#SBATCH --chdir={params.working_dir}")
        lines.append("#SBATCH --output=slurm-%j.out")
        lines.append("#SBATCH --error=slurm-%j.err")

        if params.container_image:
            lines.append(f"#SBATCH --container-image={params.container_image}")

        lines.append("")

        if params.script:
            lines.append(params.script)
        elif params.command:
            lines.append(params.command)
        else:
            lines.append("echo 'No command specified'")

        return "\n".join(lines) + "\n"

    async def submit_job(self, params: JobSubmit) -> dict:
        script = self._generate_sbatch_script(params)
        escaped_script = script.replace("'", "'\\''")
        cmd = f"cat <<'SBATCH_EOF' | sbatch\n{script}SBATCH_EOF"
        rc, stdout, stderr = await self._ssh_run(cmd)

        if rc != 0:
            return {"error": stderr.strip(), "script": script}

        m = re.search(r"(\d+)", stdout)
        job_id = m.group(1) if m else "unknown"
        return {"job_id": job_id, "message": stdout.strip(), "script": script}

    async def cancel_job(self, job_id: str) -> dict:
        rc, stdout, stderr = await self._ssh_run(f"scancel {job_id}")
        if rc != 0:
            return {"error": stderr.strip()}
        return {"message": f"Job {job_id} cancelled"}

    async def get_job_detail(self, job_id: str) -> dict:
        rc, stdout, stderr = await self._ssh_run(f"scontrol show job {job_id}")
        if rc != 0:
            return {"error": stderr.strip()}
        detail: dict[str, str] = {}
        for token in re.split(r"\s+", stdout.strip()):
            if "=" in token:
                key, _, val = token.partition("=")
                detail[key] = val
        return detail

    async def get_job_output_path(self, job_id: str) -> str | None:
        detail = await self.get_job_detail(job_id)
        return detail.get("StdOut")


slurm_service = SlurmService()
