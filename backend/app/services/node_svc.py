import logging

import asyncssh

from app.config import settings

logger = logging.getLogger("spark-manager.node")

ARM_CORE_TYPES = {
    "0xd85": "X925",   # Cortex-X925 performance (max 3.9 GHz)
    "0xd87": "A725",   # Cortex-A725 efficiency  (max 2.8 GHz)
}

KEY_INTERFACES = [
    "bond0", "enP7s7",
    "enp1s0f0np0", "enp1s0f1np1",
    "enP2p1s0f0np0", "enP2p1s0f1np1",
    "docker0",
]


class NodeService:
    """All operations go through SSH since we run inside a container."""

    def _host_for_node(self, node: str) -> str:
        if node in (settings.node1_hostname, "localhost", "local"):
            return settings.node1_ip
        if node == settings.node2_hostname:
            return settings.node2_ip
        return node

    async def ssh_run(
        self, host: str, command: str, *, timeout: int | None = None,
    ) -> tuple[int, str, str]:
        try:
            async with asyncssh.connect(
                host,
                username=settings.ssh_user,
                known_hosts=None,
                client_keys=[settings.ssh_key_path],
            ) as conn:
                result = await conn.run(command, check=False, timeout=timeout)
                return (
                    result.exit_status or 0,
                    result.stdout or "",
                    result.stderr or "",
                )
        except Exception as e:
            logger.exception("SSH to %s failed", host)
            return 1, "", str(e)

    @staticmethod
    def _safe_int(val: str) -> int | None:
        val = val.strip()
        if not val or val.startswith("[") or val.lower() in ("n/a", "not available"):
            return None
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_float(val: str) -> float | None:
        val = val.strip()
        if not val or val.startswith("[") or val.lower() in ("n/a", "not available"):
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def _split_sections(self, stdout: str) -> dict[str, str]:
        sections: dict[str, str] = {}
        current_key = None
        current_lines: list[str] = []
        for line in stdout.split("\n"):
            if line.startswith("___DELIM_") and line.endswith("___"):
                if current_key:
                    sections[current_key] = "\n".join(current_lines)
                current_key = line.replace("___DELIM_", "").replace("___", "")
                current_lines = []
            else:
                current_lines.append(line)
        if current_key:
            sections[current_key] = "\n".join(current_lines)
        return sections

    def _parse_uptime(self, text: str) -> str:
        try:
            seconds = float(text.strip().split()[0])
            days = int(seconds // 86400)
            hours = int((seconds % 86400) // 3600)
            minutes = int((seconds % 3600) // 60)
            if days > 0:
                return f"{days}d {hours}h {minutes}m"
            if hours > 0:
                return f"{hours}h {minutes}m"
            return f"{minutes}m"
        except (ValueError, IndexError):
            return "unknown"

    def _parse_cpu_parts(self, text: str) -> dict[int, str]:
        """Parse /proc/cpuinfo to map cpu_id -> core type (X925 / A725)."""
        mapping: dict[int, str] = {}
        current_id = None
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("processor"):
                try:
                    current_id = int(line.split(":")[1].strip())
                except (ValueError, IndexError):
                    current_id = None
            elif line.startswith("CPU part") and current_id is not None:
                part = line.split(":")[1].strip()
                mapping[current_id] = ARM_CORE_TYPES.get(part, part)
        return mapping

    def _parse_proc_stat(self, text: str) -> tuple[dict, list[dict]]:
        """Parse /proc/stat into total + per-core counters."""
        total = {}
        cores = []
        for line in text.strip().split("\n"):
            if line.startswith("cpu") and not line.startswith("cpuid"):
                parts = line.split()
                label = parts[0]
                vals = [int(x) for x in parts[1:8]] if len(parts) >= 8 else [0] * 7
                entry = {
                    "user": vals[0], "nice": vals[1], "system": vals[2],
                    "idle": vals[3], "iowait": vals[4], "irq": vals[5],
                    "softirq": vals[6],
                }
                if label == "cpu":
                    total = entry
                else:
                    try:
                        core_id = int(label[3:])
                    except ValueError:
                        continue
                    entry["core_id"] = core_id
                    cores.append(entry)
        return total, cores

    def _parse_cpu_freqs(self, text: str) -> dict[int, int]:
        """Parse per-core frequencies: 'cpuN:freq_khz' lines."""
        freqs: dict[int, int] = {}
        for line in text.strip().split("\n"):
            if ":" not in line:
                continue
            try:
                cpu_part, freq_part = line.split(":", 1)
                cpu_id = int(cpu_part.strip().replace("cpu", ""))
                freq_khz = int(freq_part.strip())
                freqs[cpu_id] = freq_khz // 1000
            except (ValueError, IndexError):
                continue
        return freqs

    def _parse_meminfo(self, text: str) -> dict:
        info = {}
        for line in text.strip().split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                parts = val.strip().split()
                if parts:
                    try:
                        info[key.strip()] = int(parts[0]) * 1024
                    except ValueError:
                        pass
        return {
            "total": info.get("MemTotal", 0),
            "used": info.get("MemTotal", 0) - info.get("MemAvailable", info.get("MemFree", 0)),
            "free": info.get("MemFree", 0),
            "available": info.get("MemAvailable", info.get("MemFree", 0)),
            "buffers": info.get("Buffers", 0),
            "cached": info.get("Cached", 0),
        }

    def _parse_thermal_zones(self, text: str) -> list[dict]:
        zones = []
        for line in text.strip().split("\n"):
            if ":" not in line:
                continue
            try:
                name, temp_str = line.split(":", 1)
                temp_mc = int(temp_str.strip())
                zones.append({"name": name.strip(), "temp_c": round(temp_mc / 1000, 1)})
            except (ValueError, IndexError):
                continue
        return zones

    def _parse_gpu(self, text: str) -> dict | None:
        text = text.strip()
        if not text or "not found" in text.lower():
            return None
        parts = [p.strip() for p in text.split(",")]
        if len(parts) < 7:
            return None
        return {
            "name": parts[0],
            "temperature": self._safe_int(parts[1]),
            "utilization": self._safe_int(parts[2]),
            "power_draw": self._safe_float(parts[3]),
            "clock_mhz": self._safe_int(parts[4]),
            "pstate": parts[5] if parts[5] and parts[5] != "[N/A]" else None,
            "driver_version": parts[6] if len(parts) > 6 else None,
        }

    def _parse_nvme(self, text: str) -> dict | None:
        for line in text.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 4 and parts[0].startswith("/dev/nvme"):
                try:
                    total = int(parts[1])
                    used = int(parts[2])
                    free = int(parts[3])
                    pct = round(used / total * 100, 1) if total > 0 else 0
                    return {
                        "device": parts[0],
                        "total": total,
                        "used": used,
                        "free": free,
                        "percent": pct,
                    }
                except (ValueError, IndexError):
                    continue
        return None

    def _parse_net_dev(self, text: str) -> dict[str, dict]:
        ifaces: dict[str, dict] = {}
        for line in text.strip().split("\n"):
            if ":" not in line or "Inter" in line or "face" in line:
                continue
            name, rest = line.split(":", 1)
            name = name.strip()
            vals = rest.split()
            if len(vals) >= 10:
                ifaces[name] = {
                    "rx_bytes": int(vals[0]),
                    "rx_packets": int(vals[1]),
                    "tx_bytes": int(vals[8]),
                    "tx_packets": int(vals[9]),
                }
        return ifaces

    def _parse_net_speeds(self, text: str) -> dict[str, dict]:
        """Parse 'iface state speed_mbps' lines."""
        info: dict[str, dict] = {}
        for line in text.strip().split("\n"):
            parts = line.split()
            if len(parts) < 3:
                continue
            iface = parts[0]
            state = parts[1]
            try:
                speed = int(parts[2])
            except (ValueError, IndexError):
                speed = None
            info[iface] = {"state": state, "speed_mbps": speed}
        return info

    def _classify_interface(self, name: str) -> str:
        if name == "bond0":
            return "CX7 Bond (4x200G)"
        if name == "enP7s7":
            return "10G Ethernet"
        if name.startswith("enp1s0f") or name.startswith("enP2p1s0f"):
            return "CX7 200G"
        if name == "docker0":
            return "Docker Bridge"
        return ""

    async def get_detailed_status(self, node: str) -> dict:
        host = self._host_for_node(node)
        commands = {
            "hostname": "hostname",
            "uptime": "cat /proc/uptime",
            "cpuinfo": "grep -E '(^processor|CPU part)' /proc/cpuinfo",
            "stat": "cat /proc/stat",
            "freq": (
                "for c in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq; do"
                " n=$(echo $c | grep -oP 'cpu\\K[0-9]+');"
                " echo \"cpu${n}:$(cat $c 2>/dev/null)\";"
                " done"
            ),
            "meminfo": "cat /proc/meminfo",
            "gpu": (
                "nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,"
                "power.draw,clocks.gr,pstate,driver_version"
                " --format=csv,noheader,nounits 2>/dev/null || true"
            ),
            "thermal": (
                "for tz in /sys/class/thermal/thermal_zone*; do"
                " echo \"$(cat $tz/type 2>/dev/null):$(cat $tz/temp 2>/dev/null)\";"
                " done"
            ),
            "nvme": "df --output=source,size,used,avail -B1 / 2>/dev/null | tail -1",
            "netdev": "cat /proc/net/dev",
            "netspeeds": (
                "for iface in bond0 enP7s7 enp1s0f0np0 enp1s0f1np1"
                " enP2p1s0f0np0 enP2p1s0f1np1 docker0; do"
                " st=$(cat /sys/class/net/$iface/operstate 2>/dev/null || echo down);"
                " sp=$(cat /sys/class/net/$iface/speed 2>/dev/null || echo 0);"
                " echo \"$iface $st $sp\";"
                " done"
            ),
        }
        combined = " && ".join(
            f"echo '___DELIM_{k}___' && {v}" for k, v in commands.items()
        )
        rc, stdout, stderr = await self.ssh_run(host, combined)

        if rc != 0 and not stdout:
            return {
                "hostname": node, "ip": host,
                "error": stderr[:200],
            }

        s = self._split_sections(stdout)

        hostname = s.get("hostname", node).strip()
        uptime = self._parse_uptime(s.get("uptime", ""))

        core_types = self._parse_cpu_parts(s.get("cpuinfo", ""))
        cpu_total, cpu_cores_raw = self._parse_proc_stat(s.get("stat", ""))
        cpu_freqs = self._parse_cpu_freqs(s.get("freq", ""))

        cpu_cores = []
        perf_count = 0
        eff_count = 0
        for c in cpu_cores_raw:
            cid = c["core_id"]
            ct = core_types.get(cid, "unknown")
            if ct == "X925":
                perf_count += 1
            else:
                eff_count += 1
            cpu_cores.append({
                "core_id": cid,
                "core_type": ct,
                "freq_mhz": cpu_freqs.get(cid),
                "user": c["user"], "nice": c["nice"], "system": c["system"],
                "idle": c["idle"], "iowait": c["iowait"],
                "irq": c["irq"], "softirq": c["softirq"],
            })

        mem = self._parse_meminfo(s.get("meminfo", ""))

        gpu = self._parse_gpu(s.get("gpu", ""))

        thermal = self._parse_thermal_zones(s.get("thermal", ""))

        nvme = self._parse_nvme(s.get("nvme", ""))

        net_raw = self._parse_net_dev(s.get("netdev", ""))
        net_speeds = self._parse_net_speeds(s.get("netspeeds", ""))

        net_interfaces = []
        for name in KEY_INTERFACES:
            if name not in net_raw:
                continue
            d = net_raw[name]
            sp = net_speeds.get(name, {})
            net_interfaces.append({
                "name": name,
                "speed_mbps": sp.get("speed_mbps"),
                "rx_bytes": d["rx_bytes"],
                "tx_bytes": d["tx_bytes"],
                "rx_packets": d["rx_packets"],
                "tx_packets": d["tx_packets"],
                "state": sp.get("state", "unknown"),
                "kind": self._classify_interface(name),
            })

        return {
            "hostname": hostname,
            "ip": host,
            "uptime": uptime,
            "cpu_total": cpu_total,
            "cpu_cores": cpu_cores,
            "perf_core_count": perf_count,
            "eff_core_count": eff_count,
            "mem_total": mem["total"],
            "mem_used": mem["used"],
            "mem_free": mem["free"],
            "mem_available": mem["available"],
            "mem_buffers": mem["buffers"],
            "mem_cached": mem["cached"],
            "gpu": gpu,
            "thermal_zones": thermal,
            "nvme": nvme,
            "net_interfaces": net_interfaces,
        }

    # Legacy method kept for backward compatibility
    async def get_node_status(self, node: str) -> dict:
        host = self._host_for_node(node)
        commands = {
            "hostname": "hostname",
            "cpu_count": "nproc",
            "loadavg": "cat /proc/loadavg",
            "meminfo": "cat /proc/meminfo",
            "disk": "df --output=source,size,used -B1 /",
            "uptime": "cat /proc/uptime",
            "gpu": (
                "nvidia-smi"
                " --query-gpu=name,temperature.gpu,utilization.gpu,"
                "power.draw,clocks.gr,pstate,driver_version"
                " --format=csv,noheader,nounits 2>/dev/null || true"
            ),
        }
        combined = " && ".join(
            f"echo '___DELIM_{k}___' && {v}" for k, v in commands.items()
        )
        rc, stdout, stderr = await self.ssh_run(host, combined)

        if rc != 0 and not stdout:
            return {
                "hostname": node, "ip": host,
                "cpu_count": 0, "cpu_percent": 0.0,
                "memory_total": 0, "memory_used": 0, "memory_percent": 0.0,
                "disk_total": 0, "disk_used": 0,
                "gpu": None, "uptime": "unreachable",
                "error": stderr[:200],
            }

        s = self._split_sections(stdout)

        hostname = s.get("hostname", node).strip()
        try:
            cpu_count = int(s.get("cpu_count", "1").strip())
        except ValueError:
            cpu_count = 1

        try:
            load_1m = float(s.get("loadavg", "0").split()[0])
            cpu_percent = round((load_1m / cpu_count) * 100, 1)
        except (ValueError, IndexError):
            cpu_percent = 0.0

        mem = self._parse_meminfo(s.get("meminfo", ""))
        memory_percent = round(
            (mem["used"] / mem["total"] * 100) if mem["total"] else 0, 1,
        )

        disk_total = disk_used = 0
        try:
            disk_lines = s.get("disk", "").strip().split("\n")
            if len(disk_lines) >= 2:
                parts = disk_lines[1].split()
                disk_total = int(parts[1])
                disk_used = int(parts[2])
        except (ValueError, IndexError):
            pass

        uptime = self._parse_uptime(s.get("uptime", ""))

        gpu = self._parse_gpu(s.get("gpu", ""))

        return {
            "hostname": hostname, "ip": host,
            "cpu_count": cpu_count, "cpu_percent": cpu_percent,
            "memory_total": mem["total"], "memory_used": mem["used"],
            "memory_percent": memory_percent,
            "disk_total": disk_total, "disk_used": disk_used,
            "gpu": gpu, "uptime": uptime,
        }

    async def get_gpu_info(self, node: str) -> list[dict]:
        cmd = (
            "nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,"
            "power.draw,clocks.gr,pstate,driver_version"
            " --format=csv,noheader,nounits"
        )
        host = self._host_for_node(node)
        _, output, _ = await self.ssh_run(host, cmd)
        gpu = self._parse_gpu(output)
        return [gpu] if gpu else []


node_service = NodeService()
