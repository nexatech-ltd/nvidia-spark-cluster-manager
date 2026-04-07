import logging
import os
import stat
from datetime import datetime, timezone

import asyncssh

from app.config import settings

logger = logging.getLogger("spark-manager.files")


def _permission_string(mode: int) -> str:
    parts = []
    for who in ("USR", "GRP", "OTH"):
        r = "r" if mode & getattr(stat, f"S_IR{who}") else "-"
        w = "w" if mode & getattr(stat, f"S_IW{who}") else "-"
        x = "x" if mode & getattr(stat, f"S_IX{who}") else "-"
        parts.extend([r, w, x])
    return "".join(parts)


class FileService:
    """All file operations go through SSH/SFTP since we run inside a container."""

    def _validate_path(self, path: str) -> str:
        resolved = os.path.normpath(path)
        allowed = False
        for root in settings.nfs_roots:
            root_resolved = os.path.normpath(root)
            if resolved == root_resolved or resolved.startswith(root_resolved + "/"):
                allowed = True
                break
            if root_resolved.startswith(resolved + "/"):
                allowed = True
                break
        if not allowed:
            raise ValueError(
                f"Access denied: '{path}' is outside allowed NFS roots"
            )
        return resolved

    def _host_for_node(self, node: str) -> str:
        if node in (settings.node1_hostname, "localhost", "local"):
            return settings.node1_ip
        if node == settings.node2_hostname:
            return settings.node2_ip
        return node

    async def _get_sftp(self, node: str) -> tuple[asyncssh.SSHClientConnection, asyncssh.SFTPClient]:
        host = self._host_for_node(node)
        conn = await asyncssh.connect(
            host,
            username=settings.ssh_user,
            known_hosts=None,
            client_keys=[settings.ssh_key_path],
        )
        sftp = await conn.start_sftp_client()
        return conn, sftp

    async def _ssh_run(self, node: str, command: str) -> tuple[int, str, str]:
        host = self._host_for_node(node)
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

    async def list_dir(self, node: str, path: str) -> list[dict]:
        self._validate_path(path)
        conn, sftp = await self._get_sftp(node)
        try:
            entries = []
            for entry in await sftp.readdir(path):
                name = entry.filename
                if name in (".", ".."):
                    continue
                a = entry.attrs
                perm = a.permissions if a else None
                ftype = "dir" if perm and stat.S_ISDIR(perm) else "file"
                if perm and stat.S_ISLNK(perm):
                    ftype = "link"
                perms = _permission_string(perm) if perm else "---------"
                modified = ""
                mtime = a.mtime if a else None
                if mtime is not None:
                    modified = datetime.fromtimestamp(
                        mtime, tz=timezone.utc,
                    ).isoformat()
                entries.append({
                    "name": name,
                    "path": os.path.join(path, name),
                    "type": ftype,
                    "size": (a.size or 0) if a else 0,
                    "permissions": perms,
                    "owner": str((a.uid if a else "") or ""),
                    "group": str((a.gid if a else "") or ""),
                    "modified": modified,
                })
            entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
            return entries
        finally:
            sftp.exit()
            conn.close()

    async def download_file(self, node: str, path: str) -> bytes:
        self._validate_path(path)
        conn, sftp = await self._get_sftp(node)
        try:
            data = await sftp.read(path)
            return data
        finally:
            sftp.exit()
            conn.close()

    async def upload_file(
        self, node: str, path: str, file_data: bytes, filename: str,
    ) -> dict:
        self._validate_path(path)
        target = os.path.join(path, filename)
        conn, sftp = await self._get_sftp(node)
        try:
            await sftp.makedirs(path, exist_ok=True)
            async with sftp.open(target, "wb") as f:
                await f.write(file_data)
        finally:
            sftp.exit()
            conn.close()
        return {"message": f"Uploaded '{filename}' to {path}"}

    async def upload_file_stream(self, node: str, path: str, upload_file) -> dict:
        """Stream upload: write to /tmp via SFTP, then sudo mv to target."""
        self._validate_path(path)
        filename = upload_file.filename
        tmp_name = f"/tmp/.spark-upload-{os.getpid()}-{filename}"
        target = os.path.join(path, filename)

        conn, sftp = await self._get_sftp(node)
        try:
            async with sftp.open(tmp_name, "wb") as f:
                while True:
                    chunk = await upload_file.read(2 * 1024 * 1024)
                    if not chunk:
                        break
                    await f.write(chunk)
        finally:
            sftp.exit()
            conn.close()

        rc, _, stderr = await self._ssh_run(
            node,
            f"sudo mkdir -p '{path}'"
            f" && sudo mv '{tmp_name}' '{target}'"
            f" && sudo chmod 644 '{target}'",
        )
        if rc != 0:
            await self._ssh_run(node, f"rm -f '{tmp_name}'")
            raise RuntimeError(f"Failed to move uploaded file: {stderr}")

        return {"message": f"Uploaded '{filename}' to {path}"}

    async def mkdir(self, node: str, path: str) -> dict:
        self._validate_path(os.path.dirname(path))
        conn, sftp = await self._get_sftp(node)
        try:
            await sftp.makedirs(path, exist_ok=True)
        finally:
            sftp.exit()
            conn.close()
        return {"message": f"Created directory '{path}'"}

    async def chmod(
        self, node: str, path: str, mode: str, recursive: bool = False,
    ) -> dict:
        self._validate_path(path)
        flag = "-R " if recursive else ""
        rc, _, stderr = await self._ssh_run(
            node, f"chmod {flag}{mode} {path}",
        )
        if rc != 0:
            raise RuntimeError(f"chmod failed: {stderr}")
        return {"message": f"Changed permissions of '{path}' to {mode}"}

    async def rename(self, node: str, old_path: str, new_path: str) -> dict:
        self._validate_path(old_path)
        self._validate_path(new_path)
        conn, sftp = await self._get_sftp(node)
        try:
            await sftp.rename(old_path, new_path)
        finally:
            sftp.exit()
            conn.close()
        return {"message": f"Renamed '{old_path}' to '{new_path}'"}

    async def delete(
        self, node: str, path: str, recursive: bool = False,
    ) -> dict:
        self._validate_path(path)
        flag = "-rf" if recursive else "-f"
        rc, _, stderr = await self._ssh_run(node, f"rm {flag} '{path}'")
        if rc != 0:
            raise RuntimeError(f"Delete failed: {stderr}")
        return {"message": f"Deleted '{path}'"}

    async def stat(self, node: str, path: str) -> dict:
        self._validate_path(path)
        conn, sftp = await self._get_sftp(node)
        try:
            attrs = await sftp.stat(path)
            is_dir = stat.S_ISDIR(attrs.permissions or 0)
            perms = _permission_string(attrs.permissions or 0) if attrs.permissions else "---------"
            modified = ""
            if attrs.mtime is not None:
                modified = datetime.fromtimestamp(
                    attrs.mtime, tz=timezone.utc,
                ).isoformat()

            size = attrs.size or 0
            if is_dir:
                rc, stdout, _ = await self._ssh_run(node, f"du -sb '{path}'")
                if rc == 0 and stdout.strip():
                    try:
                        size = int(stdout.strip().split()[0])
                    except ValueError:
                        pass

            return {
                "name": os.path.basename(path),
                "path": path,
                "type": "dir" if is_dir else "file",
                "size": size,
                "permissions": perms,
                "owner": str(attrs.uid or ""),
                "group": str(attrs.gid or ""),
                "modified": modified,
            }
        finally:
            sftp.exit()
            conn.close()


file_service = FileService()
