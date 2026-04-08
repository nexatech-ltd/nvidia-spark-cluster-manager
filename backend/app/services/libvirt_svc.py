import logging
import os
import subprocess
import time
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

# ── Static OS type catalogue (Proxmox-style) ────────────────────────────

_FAMILY_DEFAULTS = {
    "windows": {"disk_bus": "virtio", "nic_model": "e1000e", "tpm": False, "video": "virtio", "secure_boot": False},
    "linux":   {"disk_bus": "virtio", "nic_model": "virtio", "tpm": False, "video": "virtio", "secure_boot": False},
    "bsd":     {"disk_bus": "virtio", "nic_model": "virtio", "tpm": False, "video": "virtio", "secure_boot": False},
    "generic": {"disk_bus": "virtio", "nic_model": "virtio", "tpm": False, "video": "virtio", "secure_boot": False},
}

OS_TYPES: dict[str, dict] = {
    "win11":          {"label": "Windows 11 / Server 2025",      "family": "windows", "tpm": True, "secure_boot": True},
    "win10":          {"label": "Windows 10 / Server 2016-2019", "family": "windows"},
    "win8":           {"label": "Windows 8.x / Server 2012",     "family": "windows"},
    "win7":           {"label": "Windows 7 / Server 2008 R2",    "family": "windows"},
    "winxp":          {"label": "Windows XP / Server 2003",      "family": "windows"},
    "ubuntu24.04":    {"label": "Ubuntu 24.04 LTS",              "family": "linux"},
    "ubuntu22.04":    {"label": "Ubuntu 22.04 LTS",              "family": "linux"},
    "ubuntu20.04":    {"label": "Ubuntu 20.04 LTS",              "family": "linux"},
    "debian12":       {"label": "Debian 12 (Bookworm)",          "family": "linux"},
    "debian11":       {"label": "Debian 11 (Bullseye)",          "family": "linux"},
    "fedora41":       {"label": "Fedora 41+",                    "family": "linux"},
    "fedora40":       {"label": "Fedora 39-40",                  "family": "linux"},
    "centos-stream9": {"label": "CentOS Stream 9",               "family": "linux"},
    "rhel9":          {"label": "RHEL 9 / Oracle Linux 9",       "family": "linux"},
    "rhel8":          {"label": "RHEL 8 / Oracle Linux 8",       "family": "linux"},
    "almalinux9":     {"label": "AlmaLinux 9",                   "family": "linux"},
    "rocky9":         {"label": "Rocky Linux 9",                 "family": "linux"},
    "opensuse15":     {"label": "openSUSE Leap 15",              "family": "linux"},
    "archlinux":      {"label": "Arch Linux",                    "family": "linux"},
    "alpine":         {"label": "Alpine Linux",                  "family": "linux"},
    "nixos":          {"label": "NixOS",                         "family": "linux"},
    "freebsd14":      {"label": "FreeBSD 14",                    "family": "bsd"},
    "freebsd13":      {"label": "FreeBSD 13",                    "family": "bsd"},
    "openbsd":        {"label": "OpenBSD",                       "family": "bsd"},
    "generic":        {"label": "Generic OS",                    "family": "generic"},
    "other":          {"label": "Other / Unknown",               "family": "generic"},
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

        boot_order = [el.get("dev") for el in root.findall(".//os/boot") if el.get("dev")]

        # Parse vCPUs and memory from XML (robust for shutoff VMs)
        vcpus_el = root.find("vcpu")
        vcpus = int(vcpus_el.text) if vcpus_el is not None and vcpus_el.text else 0
        mem_el = root.find("memory")
        memory_kb = int(mem_el.text) if mem_el is not None and mem_el.text else 0
        mem_unit = mem_el.get("unit", "KiB") if mem_el is not None else "KiB"
        if mem_unit == "GiB":
            memory_mb = memory_kb * 1024
        elif mem_unit == "MiB":
            memory_mb = memory_kb
        elif mem_unit == "KiB":
            memory_mb = memory_kb // 1024
        else:
            memory_mb = memory_kb // 1024

        try:
            state_id, _ = dom.state()
            state = _STATE_MAP.get(state_id, "unknown")
        except libvirt.libvirtError:
            state = "unknown"

        try:
            autostart = bool(dom.autostart())
        except libvirt.libvirtError:
            autostart = False

        return {
            "name": dom.name(),
            "state": state,
            "vcpus": vcpus,
            "memory_mb": memory_mb,
            "disks": disks,
            "interfaces": interfaces,
            "vnc_port": vnc_port,
            "autostart": autostart,
            "node": node,
            "boot_order": boot_order,
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

    @staticmethod
    def get_os_type_info(os_variant: str) -> dict:
        """Return merged family defaults + per-OS overrides for an OS type."""
        entry = OS_TYPES.get(os_variant, {})
        family = entry.get("family", "generic")
        result = dict(_FAMILY_DEFAULTS.get(family, _FAMILY_DEFAULTS["generic"]))
        result["family"] = family
        result["label"] = entry.get("label", os_variant)
        for k in ("tpm", "disk_bus", "nic_model", "video", "secure_boot"):
            if k in entry:
                result[k] = entry[k]
        return result

    def get_hw_profile(self, os_variant: str) -> dict:
        """Return recommended disk_bus, nic_model, tpm, family for a given OS."""
        return self.get_os_type_info(os_variant)

    def build_domain_xml(
        self,
        params: VMCreate,
        arch: str = "aarch64",
        machine_type: str = "virt",
    ) -> str:
        """Build complete libvirt domain XML (replaces virt-install)."""
        is_arm = arch in ("aarch64", "arm64")
        os_info = self.get_os_type_info(params.os_variant)
        is_windows = os_info["family"] == "windows"

        disk_bus = params.disk_bus or os_info.get("disk_bus", "virtio")
        nic_model = params.nic_model or os_info.get("nic_model", "virtio")
        video_model = params.video or os_info.get("video", "virtio")
        tpm_enabled = params.tpm if params.tpm is not None else os_info.get("tpm", False)
        sb_enabled = params.secure_boot or os_info.get("secure_boot", False)

        if is_arm and disk_bus in ("sata", "ide"):
            logger.warning("Overriding disk_bus=%s→virtio (ARM UEFI)", disk_bus)
            disk_bus = "virtio"

        disk_path = os.path.join(
            settings.vm_storage_path, f"{params.name}.{params.disk_format}",
        )

        # ── Root ──
        domain = ET.Element("domain", type="kvm")
        ET.SubElement(domain, "name").text = params.name
        ET.SubElement(domain, "memory", unit="MiB").text = str(params.memory_mb)
        ET.SubElement(domain, "currentMemory", unit="MiB").text = str(params.memory_mb)
        ET.SubElement(domain, "vcpu", placement="static").text = str(params.vcpus)

        # ── OS / firmware ──
        os_el = ET.SubElement(domain, "os")
        use_uefi = params.bios == "uefi" or is_arm

        if use_uefi and is_arm and sb_enabled:
            # pflash with Microsoft pre-enrolled Secure Boot keys (Windows 11)
            loader = ET.SubElement(
                os_el, "loader",
                readonly="yes", type="pflash",
            )
            loader.text = "/usr/share/AAVMF/AAVMF_CODE.ms.fd"
            ET.SubElement(os_el, "nvram", template="/usr/share/AAVMF/AAVMF_VARS.ms.fd")
        elif use_uefi and is_arm:
            # pflash without Secure Boot (Linux / generic ARM)
            loader = ET.SubElement(
                os_el, "loader",
                readonly="yes", type="pflash",
            )
            loader.text = "/usr/share/AAVMF/AAVMF_CODE.fd"
            ET.SubElement(os_el, "nvram", template="/usr/share/AAVMF/AAVMF_VARS.fd")
        elif use_uefi and sb_enabled and not is_arm:
            os_el.set("firmware", "efi")
            fw = ET.SubElement(os_el, "firmware")
            ET.SubElement(fw, "feature", enabled="yes", name="enrolled-keys")
            ET.SubElement(fw, "feature", enabled="yes", name="secure-boot")
        elif use_uefi:
            os_el.set("firmware", "efi")

        if is_arm:
            type_el = ET.SubElement(os_el, "type", arch="aarch64", machine=machine_type)
        else:
            mach = machine_type or "pc"
            type_el = ET.SubElement(os_el, "type", arch="x86_64", machine=mach)
        type_el.text = "hvm"
        if params.iso:
            ET.SubElement(os_el, "boot", dev="cdrom")
        ET.SubElement(os_el, "boot", dev="hd")

        # ── Features ──
        features = ET.SubElement(domain, "features")
        ET.SubElement(features, "acpi")
        if is_arm:
            ET.SubElement(features, "gic", version="3")

        # ── CPU ──
        ET.SubElement(domain, "cpu", mode=params.cpu_type, check="none")

        # ── Clock ──
        if is_windows:
            clock = ET.SubElement(domain, "clock", offset="localtime")
            ET.SubElement(clock, "timer", name="rtc", tickpolicy="catchup")
            ET.SubElement(clock, "timer", name="pit", tickpolicy="delay")
            ET.SubElement(clock, "timer", name="hpet", present="no")
        else:
            clock = ET.SubElement(domain, "clock", offset="utc")
            ET.SubElement(clock, "timer", name="rtc", tickpolicy="catchup")
            ET.SubElement(clock, "timer", name="pit", tickpolicy="delay")

        # ── Lifecycle ──
        ET.SubElement(domain, "on_poweroff").text = "destroy"
        ET.SubElement(domain, "on_reboot").text = "restart"
        ET.SubElement(domain, "on_crash").text = "destroy"

        # ── Devices ──
        devices = ET.SubElement(domain, "devices")
        emu = "/usr/bin/qemu-system-aarch64" if is_arm else "/usr/bin/qemu-system-x86_64"
        ET.SubElement(devices, "emulator").text = emu

        # Controllers
        ET.SubElement(devices, "controller", type="scsi", model="virtio-scsi")
        ET.SubElement(devices, "controller", type="usb", model="qemu-xhci")

        # Primary disk
        disk_target = "vda" if disk_bus == "virtio" else "sda"
        disk_el = ET.SubElement(devices, "disk", type="file", device="disk")
        ET.SubElement(disk_el, "driver", name="qemu", type=params.disk_format, cache="writeback")
        ET.SubElement(disk_el, "source", file=disk_path)
        ET.SubElement(disk_el, "target", dev=disk_target, bus=disk_bus)

        # Boot ISO (SCSI on ARM, IDE on x86)
        if params.iso:
            iso_path = params.iso if params.iso.startswith("/") else os.path.join(
                settings.iso_storage_path, params.iso,
            )
            cdrom_el = ET.SubElement(devices, "disk", type="file", device="cdrom")
            ET.SubElement(cdrom_el, "driver", name="qemu", type="raw")
            ET.SubElement(cdrom_el, "source", file=iso_path)
            if is_arm:
                cdrom_dev = "sdb" if disk_bus != "scsi" else "sda"
                ET.SubElement(cdrom_el, "target", dev=cdrom_dev, bus="scsi")
            else:
                ET.SubElement(cdrom_el, "target", dev="hda", bus="ide")
            ET.SubElement(cdrom_el, "readonly")

        # Drivers ISO via USB so WinPE can see it without VirtIO drivers
        if params.drivers_iso:
            drv_path = params.drivers_iso if params.drivers_iso.startswith("/") else os.path.join(
                settings.iso_storage_path, params.drivers_iso,
            )
            drv_el = ET.SubElement(devices, "disk", type="file", device="cdrom")
            ET.SubElement(drv_el, "driver", name="qemu", type="raw")
            ET.SubElement(drv_el, "source", file=drv_path)
            if is_arm:
                ET.SubElement(drv_el, "target", dev="sdc", bus="usb")
            else:
                ET.SubElement(drv_el, "target", dev="hdb", bus="ide")
            ET.SubElement(drv_el, "readonly")

        # Network
        if params.network_type == "network":
            iface_el = ET.SubElement(devices, "interface", type="network")
            ET.SubElement(iface_el, "source", network=params.network)
        else:
            iface_el = ET.SubElement(devices, "interface", type="bridge")
            ET.SubElement(iface_el, "source", bridge=params.network)
        ET.SubElement(iface_el, "model", type=nic_model)

        # Graphics
        gfx = ET.SubElement(devices, "graphics", type="vnc", port="-1", autoport="yes")
        gfx.set("listen", "0.0.0.0")
        ET.SubElement(gfx, "listen", type="address", address="0.0.0.0")

        # Video — UEFI on ARM only has GOP for ramfb and virtio-gpu-pci.
        # virtio-gpu-pci alone hangs Windows boot; ramfb as primary fixes it.
        if is_windows and is_arm:
            fb = ET.SubElement(devices, "video")
            ET.SubElement(fb, "model", type="ramfb")
            vid = ET.SubElement(devices, "video")
            ET.SubElement(vid, "model", type="virtio", heads="1")
        else:
            vid = ET.SubElement(devices, "video")
            ET.SubElement(vid, "model", type=video_model, heads="1")

        # Console / serial
        console = ET.SubElement(devices, "console", type="pty")
        ET.SubElement(console, "target", type="serial", port="0")

        # Input devices
        ET.SubElement(devices, "input", type="tablet", bus="usb")
        if is_arm:
            ET.SubElement(devices, "input", type="keyboard", bus="usb")

        # Guest agent channel
        ch = ET.SubElement(devices, "channel", type="unix")
        ET.SubElement(ch, "target", type="virtio", name="org.qemu.guest_agent.0")

        # RNG
        rng = ET.SubElement(devices, "rng", model="virtio")
        ET.SubElement(rng, "backend", model="random").text = "/dev/urandom"

        # TPM
        if tpm_enabled:
            tpm_model = "tpm-tis" if is_arm else "tpm-crb"
            tpm_el = ET.SubElement(devices, "tpm", model=tpm_model)
            ET.SubElement(tpm_el, "backend", type="emulator", version="2.0")

        ET.indent(domain, space="  ")
        return ET.tostring(domain, encoding="unicode", xml_declaration=False)

    # ── VM actions ───────────────────────────────────────────────────────

    _ACTION_MAP = {
        "start": "create",
        "shutdown": "shutdown",
        "reboot": "reboot",
        "suspend": "suspend",
        "resume": "resume",
        "destroy": "destroy",
    }

    def vm_action(self, name: str, node: str, action: str, timeout: int = 0) -> dict:
        conn = self._get_conn(node)
        try:
            dom = conn.lookupByName(name)
        except libvirt.libvirtError:
            raise ValueError(f"VM '{name}' not found on {node}")

        if action == "undefine":
            return self.delete_vm(name, node)

        # Graceful shutdown: send ACPI signal, poll, fallback to destroy
        if action == "shutdown" and timeout > 0:
            try:
                dom.shutdown()
            except libvirt.libvirtError as e:
                raise RuntimeError(f"Shutdown failed on '{name}': {e}")
            elapsed = 0
            while elapsed < timeout:
                time.sleep(2)
                elapsed += 2
                try:
                    state_id, _ = dom.state()
                    if state_id == libvirt.VIR_DOMAIN_SHUTOFF:
                        return {"message": f"VM '{name}' shut down gracefully"}
                except libvirt.libvirtError:
                    return {"message": f"VM '{name}' shut down"}
            try:
                dom.destroy()
            except libvirt.libvirtError:
                pass
            return {"message": f"VM '{name}' force-stopped after {timeout}s timeout"}

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
            | libvirt.VIR_DOMAIN_UNDEFINE_NVRAM
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
