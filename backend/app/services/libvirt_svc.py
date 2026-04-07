import logging
import os
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import libvirt

from app.config import settings
from app.models.vm import DiskCreate, VMCreate

logger = logging.getLogger("spark-manager.libvirt")

_STATE_MAP = {
    libvirt.VIR_DOMAIN_NOSTATE: "nostate",
    libvirt.VIR_DOMAIN_RUNNING: "running",
    libvirt.VIR_DOMAIN_BLOCKED: "blocked",
    libvirt.VIR_DOMAIN_PAUSED: "paused",
    libvirt.VIR_DOMAIN_SHUTDOWN: "shutdown",
    libvirt.VIR_DOMAIN_SHUTOFF: "shutoff",
    libvirt.VIR_DOMAIN_CRASHED: "crashed",
    libvirt.VIR_DOMAIN_PMSUSPENDED: "pmsuspended",
}


class LibvirtService:
    def __init__(self):
        self._conns: dict[str, libvirt.virConnect] = {}

    # ── Connection management ────────────────────────────────────────────

    def _get_conn(self, node: str) -> libvirt.virConnect:
        if node in self._conns:
            conn = self._conns[node]
            try:
                conn.getHostname()
                return conn
            except libvirt.libvirtError:
                self._conns.pop(node, None)

        if node == settings.node1_hostname:
            uri = settings.libvirt_uri_local
        else:
            uri = settings.libvirt_uri_remote_template.format(
                user=settings.ssh_user, host=settings.node2_ip,
            )

        conn = libvirt.open(uri)
        if conn is None:
            raise RuntimeError(f"Failed to open libvirt connection to {node}")
        self._conns[node] = conn
        return conn

    def _both_nodes(self) -> list[str]:
        return [settings.node1_hostname, settings.node2_hostname]

    def _resolve_node(self, node: str | None) -> list[str]:
        if node is None:
            return self._both_nodes()
        return [node]

    # ── Domain XML parsing helpers ───────────────────────────────────────

    def _parse_domain_info(self, dom: libvirt.virDomain, node: str) -> dict:
        xml_str = dom.XMLDesc(0)
        root = ET.fromstring(xml_str)

        disks = []
        for disk_el in root.findall(".//disk"):
            source = disk_el.find("source")
            target = disk_el.find("target")
            disks.append({
                "device": disk_el.get("device", "disk"),
                "source": source.get("file", "") if source is not None else "",
                "target": target.get("dev", "") if target is not None else "",
                "bus": target.get("bus", "") if target is not None else "",
            })

        interfaces = []
        for iface_el in root.findall(".//interface"):
            source = iface_el.find("source")
            mac = iface_el.find("mac")
            model = iface_el.find("model")
            interfaces.append({
                "type": iface_el.get("type", ""),
                "source": source.get("bridge", source.get("network", "")) if source is not None else "",
                "mac": mac.get("address", "") if mac is not None else "",
                "model": model.get("type", "") if model is not None else "",
            })

        vnc_port = None
        graphics = root.find(".//graphics[@type='vnc']")
        if graphics is not None:
            port_str = graphics.get("port", "-1")
            if port_str and port_str != "-1":
                vnc_port = int(port_str)

        state_id, _ = dom.state()

        return {
            "name": dom.name(),
            "state": _STATE_MAP.get(state_id, "unknown"),
            "vcpus": dom.maxVcpus(),
            "memory_mb": dom.maxMemory() // 1024,
            "disks": disks,
            "interfaces": interfaces,
            "vnc_port": vnc_port,
            "autostart": bool(dom.autostart()),
            "node": node,
        }

    # ── VM listing ───────────────────────────────────────────────────────

    def list_vms(self, node: str | None = None) -> list[dict]:
        results = []
        for n in self._resolve_node(node):
            try:
                conn = self._get_conn(n)
                for dom in conn.listAllDomains(0):
                    try:
                        results.append(self._parse_domain_info(dom, n))
                    except libvirt.libvirtError as e:
                        logger.warning("Error parsing domain on %s: %s", n, e)
            except libvirt.libvirtError as e:
                logger.error("Error listing VMs on %s: %s", n, e)
        return results

    def get_vm(self, name: str, node: str) -> dict:
        conn = self._get_conn(node)
        try:
            dom = conn.lookupByName(name)
        except libvirt.libvirtError:
            raise ValueError(f"VM '{name}' not found on {node}")
        return self._parse_domain_info(dom, node)

    # ── VM creation ──────────────────────────────────────────────────────

    def build_virt_install_cmd(self, params: VMCreate, host_arch: str = "aarch64") -> str:
        """Build the virt-install shell command to run on the target node."""
        disk_path = os.path.join(
            settings.vm_storage_path, f"{params.name}.{params.disk_format}",
        )

        is_arm = host_arch in ("aarch64", "arm64")

        parts = [
            "sudo virt-install",
            "--connect qemu:///system",
            f"--name {params.name}",
            f"--vcpus {params.vcpus}",
            f"--memory {params.memory_mb}",
            f"--disk path={disk_path},size={params.disk_size_gb},format={params.disk_format},bus=virtio",
            f"--network bridge={params.network},model=virtio",
            "--graphics vnc,listen=0.0.0.0",
            f"--os-variant {params.os_variant}",
            "--noautoconsole",
        ]

        if is_arm:
            parts += [
                "--arch aarch64",
                "--machine virt",
                "--boot uefi",
            ]

        if params.iso:
            iso_path = params.iso if params.iso.startswith("/") else os.path.join(settings.iso_storage_path, params.iso)
            parts.append(f"--cdrom {iso_path}")
        else:
            parts.append("--import")

        return " ".join(parts)

    # ── VM actions ───────────────────────────────────────────────────────

    _ACTION_MAP = {
        "start": "create",
        "shutdown": "shutdown",
        "reboot": "reboot",
        "suspend": "suspend",
        "resume": "resume",
        "destroy": "destroy",
    }

    def vm_action(self, name: str, node: str, action: str) -> dict:
        conn = self._get_conn(node)
        try:
            dom = conn.lookupByName(name)
        except libvirt.libvirtError:
            raise ValueError(f"VM '{name}' not found on {node}")

        if action == "undefine":
            return self.delete_vm(name, node)

        method_name = self._ACTION_MAP.get(action)
        if method_name is None:
            raise ValueError(f"Unknown action: {action}")

        try:
            getattr(dom, method_name)()
        except libvirt.libvirtError as e:
            raise RuntimeError(f"Action '{action}' failed on '{name}': {e}")

        return {"message": f"Action '{action}' performed on VM '{name}'"}

    def delete_vm(self, name: str, node: str) -> dict:
        conn = self._get_conn(node)
        try:
            dom = conn.lookupByName(name)
        except libvirt.libvirtError:
            raise ValueError(f"VM '{name}' not found on {node}")

        state_id, _ = dom.state()
        if state_id == libvirt.VIR_DOMAIN_RUNNING:
            dom.destroy()

        flags = (
            libvirt.VIR_DOMAIN_UNDEFINE_MANAGED_SAVE
            | libvirt.VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA
        )
        try:
            flags |= libvirt.VIR_DOMAIN_UNDEFINE_STORAGE
        except AttributeError:
            pass

        dom.undefineFlags(flags)
        return {"message": f"VM '{name}' deleted from {node}"}

    # ── Snapshots ────────────────────────────────────────────────────────

    def list_snapshots(self, name: str, node: str) -> list[dict]:
        conn = self._get_conn(node)
        try:
            dom = conn.lookupByName(name)
        except libvirt.libvirtError:
            raise ValueError(f"VM '{name}' not found on {node}")

        snapshots = []
        for snap in dom.listAllSnapshots(0):
            xml_str = snap.getXMLDesc(0)
            root = ET.fromstring(xml_str)
            creation = root.findtext("creationTime", "0")
            try:
                ts = datetime.fromtimestamp(int(creation), tz=timezone.utc).isoformat()
            except (ValueError, OSError):
                ts = creation
            state = root.findtext("state", "unknown")
            snapshots.append({
                "name": snap.getName(),
                "creation_time": ts,
                "state": state,
            })
        return snapshots

    def create_snapshot(self, vm_name: str, snap_name: str, node: str) -> dict:
        conn = self._get_conn(node)
        try:
            dom = conn.lookupByName(vm_name)
        except libvirt.libvirtError:
            raise ValueError(f"VM '{vm_name}' not found on {node}")

        xml = f"<domainsnapshot><name>{snap_name}</name></domainsnapshot>"
        dom.snapshotCreateXML(xml, 0)
        return {"message": f"Snapshot '{snap_name}' created for VM '{vm_name}'"}

    def restore_snapshot(self, vm_name: str, snap_name: str, node: str) -> dict:
        conn = self._get_conn(node)
        try:
            dom = conn.lookupByName(vm_name)
        except libvirt.libvirtError:
            raise ValueError(f"VM '{vm_name}' not found on {node}")

        try:
            snap = dom.snapshotLookupByName(snap_name, 0)
        except libvirt.libvirtError:
            raise ValueError(f"Snapshot '{snap_name}' not found")

        dom.revertToSnapshot(snap, 0)
        return {"message": f"VM '{vm_name}' reverted to snapshot '{snap_name}'"}

    def delete_snapshot(self, vm_name: str, snap_name: str, node: str) -> dict:
        conn = self._get_conn(node)
        try:
            dom = conn.lookupByName(vm_name)
        except libvirt.libvirtError:
            raise ValueError(f"VM '{vm_name}' not found on {node}")

        try:
            snap = dom.snapshotLookupByName(snap_name, 0)
        except libvirt.libvirtError:
            raise ValueError(f"Snapshot '{snap_name}' not found")

        snap.delete(0)
        return {"message": f"Snapshot '{snap_name}' deleted from VM '{vm_name}'"}

    # ── VNC ──────────────────────────────────────────────────────────────

    def get_vnc_port(self, name: str, node: str) -> int | None:
        conn = self._get_conn(node)
        try:
            dom = conn.lookupByName(name)
        except libvirt.libvirtError:
            raise ValueError(f"VM '{name}' not found on {node}")

        xml_str = dom.XMLDesc(0)
        root = ET.fromstring(xml_str)
        graphics = root.find(".//graphics[@type='vnc']")
        if graphics is None:
            return None
        port_str = graphics.get("port", "-1")
        if port_str and port_str != "-1":
            return int(port_str)
        return None

    # ── ISOs ─────────────────────────────────────────────────────────────

    def _scan_isos_local(self, directory: str) -> list[dict]:
        d = Path(directory)
        if not d.is_dir():
            return []
        return [
            {"name": f.name, "size": f.stat().st_size, "path": str(f)}
            for f in d.iterdir()
            if f.suffix.lower() == ".iso"
        ]

    def _scan_isos_remote(self, directory: str) -> list[dict]:
        result = subprocess.run(
            [
                "ssh", f"{settings.ssh_user}@{settings.node2_ip}",
                "find", directory, "-maxdepth", "1", "-name", "*.iso",
                "-printf", "%s %p\\n",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        isos = []
        for line in result.stdout.strip().split("\n"):
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                isos.append({
                    "name": os.path.basename(parts[1]),
                    "size": int(parts[0]),
                    "path": parts[1],
                })
        return isos

    def list_isos(self, node: str | None = None) -> list[dict]:
        target_node = node or settings.node1_hostname
        dirs = [settings.iso_storage_path] + list(settings.nfs_roots)
        is_remote = target_node != settings.node1_hostname

        all_isos = []
        seen = set()
        for d in dirs:
            entries = self._scan_isos_remote(d) if is_remote else self._scan_isos_local(d)
            for iso in entries:
                if iso["path"] not in seen:
                    seen.add(iso["path"])
                    all_isos.append(iso)
        return all_isos

    def upload_iso(self, filename: str, data: bytes, node: str | None = None) -> dict:
        target_node = node or settings.node1_hostname
        iso_dir = Path(settings.iso_storage_path)

        if target_node != settings.node1_hostname:
            tmp_path = Path(f"/tmp/{filename}")
            tmp_path.write_bytes(data)
            result = subprocess.run(
                [
                    "scp", str(tmp_path),
                    f"{settings.ssh_user}@{settings.node2_ip}:{iso_dir / filename}",
                ],
                capture_output=True, text=True, timeout=600,
            )
            tmp_path.unlink(missing_ok=True)
            if result.returncode != 0:
                raise RuntimeError(f"Failed to upload ISO to {target_node}: {result.stderr}")
        else:
            iso_dir.mkdir(parents=True, exist_ok=True)
            (iso_dir / filename).write_bytes(data)

        return {"message": f"ISO '{filename}' uploaded to {target_node}"}

    # ── Disks / Storage ──────────────────────────────────────────────────

    def list_disks(self, pool: str = "default", node: str | None = None) -> list[dict]:
        target_node = node or settings.node1_hostname
        conn = self._get_conn(target_node)
        try:
            sp = conn.storagePoolLookupByName(pool)
        except libvirt.libvirtError:
            raise ValueError(f"Storage pool '{pool}' not found on {target_node}")

        sp.refresh(0)
        volumes = []
        for vol_name in sp.listVolumes():
            try:
                vol = sp.storageVolLookupByName(vol_name)
                info = vol.info()
                xml_str = vol.XMLDesc(0)
                root = ET.fromstring(xml_str)
                fmt = root.findtext(".//format/@type", "raw")
                fmt_el = root.find(".//target/format")
                if fmt_el is not None:
                    fmt = fmt_el.get("type", "raw")
                volumes.append({
                    "name": vol_name,
                    "size": info[1],
                    "format": fmt,
                    "path": vol.path(),
                    "pool": pool,
                })
            except libvirt.libvirtError as e:
                logger.warning("Error reading volume %s: %s", vol_name, e)
        return volumes

    def create_disk(self, params: DiskCreate, node: str | None = None) -> dict:
        target_node = node or settings.node1_hostname
        size_str = f"{params.size_gb}G"
        cmd = [
            "virsh",
            "vol-create-as",
            params.pool,
            params.name,
            size_str,
            "--format", params.format,
        ]

        if target_node != settings.node1_hostname:
            uri = settings.libvirt_uri_remote_template.format(
                user=settings.ssh_user, host=settings.node2_ip,
            )
            cmd = ["virsh", f"--connect={uri}", "vol-create-as",
                   params.pool, params.name, size_str, "--format", params.format]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create disk: {result.stderr}")
        return {"message": f"Disk '{params.name}' created in pool '{params.pool}'"}

    def attach_disk(self, vm_name: str, disk_path: str, node: str | None = None) -> dict:
        target_node = node or settings.node1_hostname
        target_dev = self._next_disk_target(vm_name, target_node)
        cmd = ["virsh", "attach-disk", vm_name, disk_path, target_dev,
               "--persistent", "--subdriver", "qcow2"]

        if target_node != settings.node1_hostname:
            uri = settings.libvirt_uri_remote_template.format(
                user=settings.ssh_user, host=settings.node2_ip,
            )
            cmd.insert(1, f"--connect={uri}")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to attach disk: {result.stderr}")
        return {"message": f"Disk '{disk_path}' attached to VM '{vm_name}' as {target_dev}"}

    def detach_disk(self, vm_name: str, disk_path: str, node: str | None = None) -> dict:
        target_node = node or settings.node1_hostname
        cmd = ["virsh", "detach-disk", vm_name, disk_path, "--persistent"]

        if target_node != settings.node1_hostname:
            uri = settings.libvirt_uri_remote_template.format(
                user=settings.ssh_user, host=settings.node2_ip,
            )
            cmd.insert(1, f"--connect={uri}")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to detach disk: {result.stderr}")
        return {"message": f"Disk '{disk_path}' detached from VM '{vm_name}'"}

    def _next_disk_target(self, vm_name: str, node: str) -> str:
        """Find the next available vdX target for a VM."""
        try:
            info = self.get_vm(vm_name, node)
            used = {d.get("target", "") for d in info["disks"]}
        except (ValueError, libvirt.libvirtError):
            used = set()
        for letter in "bcdefghijklmnop":
            dev = f"vd{letter}"
            if dev not in used:
                return dev
        return "vdz"

    # ── Storage pools ────────────────────────────────────────────────────

    def list_storage_pools(self, node: str | None = None) -> list[dict]:
        target_node = node or settings.node1_hostname
        conn = self._get_conn(target_node)
        pools = []
        for sp in conn.listAllStoragePools(0):
            info = sp.info()
            pools.append({
                "name": sp.name(),
                "state": "active" if sp.isActive() else "inactive",
                "capacity": info[1],
                "allocation": info[2],
                "available": info[3],
            })
        return pools

    # ── Autostart ────────────────────────────────────────────────────────

    def set_autostart(self, name: str, node: str, enabled: bool) -> dict:
        conn = self._get_conn(node)
        try:
            dom = conn.lookupByName(name)
        except libvirt.libvirtError:
            raise ValueError(f"VM '{name}' not found on {node}")

        dom.setAutostart(1 if enabled else 0)
        state = "enabled" if enabled else "disabled"
        return {"message": f"Autostart {state} for VM '{name}'"}


libvirt_service = LibvirtService()
