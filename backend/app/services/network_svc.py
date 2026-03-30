import asyncio
import json
import logging

import asyncssh

from app.config import settings

logger = logging.getLogger("spark-manager.network")


class NetworkService:
    """All network operations go through SSH since we run inside a container."""

    def _host_for_node(self, node: str) -> str:
        if node in (settings.node1_hostname, "localhost", "local"):
            return settings.node1_ip
        if node == settings.node2_hostname:
            return settings.node2_ip
        return node

    async def _ssh_run(self, host: str, command: str) -> tuple[int, str, str]:
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
            logger.exception("SSH to %s failed", host)
            return 1, "", str(e)

    # ── Interfaces ───────────────────────────────────────────────────

    async def list_interfaces(self, node: str = "spark-1") -> list[dict]:
        host = self._host_for_node(node)
        rc, stdout, stderr = await self._ssh_run(host, "ip -j addr show")
        if rc != 0:
            logger.error("ip addr failed on %s: %s", host, stderr)
            return []
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            logger.error("Failed to parse ip JSON from %s", host)
            return []

        interfaces = []
        for iface in data:
            addresses = []
            for ai in iface.get("addr_info", []):
                local = ai.get("local", "")
                prefix = ai.get("prefixlen", "")
                if local:
                    addresses.append(f"{local}/{prefix}" if prefix else local)
            flags = iface.get("flags", [])
            state = "UP" if "UP" in flags else "DOWN"
            link_type = iface.get("link_type", "")
            if iface.get("linkinfo", {}).get("info_kind"):
                link_type = iface["linkinfo"]["info_kind"]
            interfaces.append({
                "name": iface.get("ifname", ""),
                "state": state,
                "mac": iface.get("address", ""),
                "mtu": iface.get("mtu", 0),
                "addresses": addresses,
                "type": link_type,
                "master": iface.get("master"),
            })
        return interfaces

    # ── Bridges ──────────────────────────────────────────────────────

    async def create_bridge(self, name: str, node: str = "spark-1") -> dict:
        host = self._host_for_node(node)
        rc, _, stderr = await self._ssh_run(
            host,
            f"sudo ip link add name {name} type bridge && sudo ip link set {name} up",
        )
        if rc != 0:
            return {"error": stderr}
        return {"message": f"Bridge '{name}' created on {node}"}

    async def delete_bridge(self, name: str, node: str = "spark-1") -> dict:
        host = self._host_for_node(node)
        rc, _, stderr = await self._ssh_run(
            host,
            f"sudo ip link set {name} down && sudo ip link del {name}",
        )
        if rc != 0:
            return {"error": stderr}
        return {"message": f"Bridge '{name}' deleted on {node}"}

    async def add_bridge_port(
        self, bridge: str, port: str, node: str = "spark-1"
    ) -> dict:
        host = self._host_for_node(node)
        rc, _, stderr = await self._ssh_run(
            host, f"sudo ip link set {port} master {bridge}",
        )
        if rc != 0:
            return {"error": stderr}
        return {"message": f"Port '{port}' added to bridge '{bridge}' on {node}"}

    async def remove_bridge_port(
        self, bridge: str, port: str, node: str = "spark-1"
    ) -> dict:
        host = self._host_for_node(node)
        rc, _, stderr = await self._ssh_run(
            host, f"sudo ip link set {port} nomaster",
        )
        if rc != 0:
            return {"error": stderr}
        return {"message": f"Port '{port}' removed from bridge '{bridge}' on {node}"}

    # ── VLANs ────────────────────────────────────────────────────────

    async def create_vlan(
        self, parent: str, vlan_id: int, node: str = "spark-1"
    ) -> dict:
        host = self._host_for_node(node)
        vlan_name = f"{parent}.{vlan_id}"
        rc, _, stderr = await self._ssh_run(
            host,
            f"sudo ip link add link {parent} name {vlan_name} type vlan id {vlan_id}"
            f" && sudo ip link set {vlan_name} up",
        )
        if rc != 0:
            return {"error": stderr}
        return {"message": f"VLAN '{vlan_name}' created on {node}", "name": vlan_name}

    async def delete_vlan(self, name: str, node: str = "spark-1") -> dict:
        host = self._host_for_node(node)
        rc, _, stderr = await self._ssh_run(
            host,
            f"sudo ip link set {name} down && sudo ip link del {name}",
        )
        if rc != 0:
            return {"error": stderr}
        return {"message": f"VLAN '{name}' deleted on {node}"}

    # ── IP Addresses ─────────────────────────────────────────────────

    async def add_address(
        self, interface: str, address: str, node: str = "spark-1"
    ) -> dict:
        host = self._host_for_node(node)
        rc, _, stderr = await self._ssh_run(
            host, f"sudo ip addr add {address} dev {interface}",
        )
        if rc != 0:
            return {"error": stderr}
        return {"message": f"Address {address} added to {interface} on {node}"}

    async def remove_address(
        self, interface: str, address: str, node: str = "spark-1"
    ) -> dict:
        host = self._host_for_node(node)
        rc, _, stderr = await self._ssh_run(
            host, f"sudo ip addr del {address} dev {interface}",
        )
        if rc != 0:
            return {"error": stderr}
        return {"message": f"Address {address} removed from {interface} on {node}"}

    # ── Routes ───────────────────────────────────────────────────────

    async def list_routes(self, node: str = "spark-1") -> list[dict]:
        host = self._host_for_node(node)
        rc, stdout, stderr = await self._ssh_run(host, "ip -j route show")
        if rc != 0:
            logger.error("Route listing failed on %s: %s", host, stderr)
            return []
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return []
        routes = []
        for r in data:
            routes.append({
                "destination": r.get("dst", "default"),
                "gateway": r.get("gateway"),
                "interface": r.get("dev", ""),
                "metric": r.get("metric", 0),
            })
        return routes

    async def add_route(
        self,
        destination: str,
        gateway: str,
        interface: str | None = None,
        node: str = "spark-1",
    ) -> dict:
        host = self._host_for_node(node)
        cmd = f"sudo ip route add {destination} via {gateway}"
        if interface:
            cmd += f" dev {interface}"
        rc, _, stderr = await self._ssh_run(host, cmd)
        if rc != 0:
            return {"error": stderr}
        return {"message": f"Route to {destination} via {gateway} added on {node}"}

    async def remove_route(
        self,
        destination: str,
        gateway: str,
        node: str = "spark-1",
    ) -> dict:
        host = self._host_for_node(node)
        rc, _, stderr = await self._ssh_run(
            host, f"sudo ip route del {destination} via {gateway}",
        )
        if rc != 0:
            return {"error": stderr}
        return {"message": f"Route to {destination} via {gateway} removed on {node}"}

    # ── Topology ─────────────────────────────────────────────────────

    async def get_topology(self) -> dict:
        node1_ifaces, node2_ifaces = await asyncio.gather(
            self.list_interfaces(settings.node1_hostname),
            self.list_interfaces(settings.node2_hostname),
        )

        def _build_node(hostname: str, ip: str, ifaces: list[dict]) -> dict:
            bridges = [i for i in ifaces if i.get("type") == "bridge"]
            bridge_names = {b["name"] for b in bridges}
            connections = []
            for iface in ifaces:
                if iface.get("master") and iface["master"] in bridge_names:
                    connections.append({
                        "port": iface["name"],
                        "bridge": iface["master"],
                    })
            return {
                "hostname": hostname,
                "ip": ip,
                "interfaces": ifaces,
                "bridges": bridges,
                "connections": connections,
            }

        return {
            "nodes": [
                _build_node(
                    settings.node1_hostname, settings.node1_ip, node1_ifaces,
                ),
                _build_node(
                    settings.node2_hostname, settings.node2_ip, node2_ifaces,
                ),
            ],
        }


network_service = NetworkService()
