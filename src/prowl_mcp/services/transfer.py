import re
import shlex
import subprocess
from pathlib import Path, PurePosixPath

import httpx

from prowl_mcp.clients import jellyfin, qbittorrent
from prowl_mcp.config import Settings
from prowl_mcp.services.downloads import find_one

TV_PATTERN = re.compile(r"S\d{1,2}E\d{1,3}", re.IGNORECASE)


class TransferError(Exception):
    pass


def library_for(name: str, settings: Settings) -> str:
    return settings.tv_library_path if TV_PATTERN.search(name) else settings.movies_library_path


def _ssh_options(settings: Settings) -> list[str]:
    key = str(Path(settings.ssh_key_path).expanduser())
    return ["-p", str(settings.ssh_port), "-i", key, "-o", "BatchMode=yes"]


def _ssh_target(settings: Settings) -> str:
    return f"{settings.ssh_user}@{settings.ssh_host}"


def local_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


def remote_size(settings: Settings, remote_path: str) -> int:
    script = f"find {shlex.quote(remote_path)} -type f -printf '%s\\n' | awk '{{s+=$1}} END {{print s+0}}'"
    result = subprocess.run(
        ["ssh", *_ssh_options(settings), _ssh_target(settings), script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise TransferError(f"Could not read the remote size: {result.stderr.strip()}")
    return int(result.stdout.strip())


def copy_to_library(settings: Settings, local: Path, dry_run: bool = False) -> str:
    library = library_for(local.name, settings)
    remote_path = f"{library}/{local.name}"
    flags = ["-a", "--partial"] + (["--dry-run"] if dry_run else [])
    rsh = " ".join(["ssh", *_ssh_options(settings)])
    result = subprocess.run(
        ["rsync", *flags, "-e", rsh, str(local), f"{_ssh_target(settings)}:{library}/"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise TransferError(f"rsync failed: {result.stderr.strip()}")
    return remote_path


def transfer(settings: Settings, local: Path) -> str:
    remote_path = copy_to_library(settings, local)
    expected = local_size(local)
    actual = remote_size(settings, remote_path)
    if expected != actual:
        raise TransferError(f"Size mismatch for {local.name}: local {expected} bytes, server {actual} bytes.")
    return remote_path


def host_path(save_path: str, name: str, settings: Settings) -> Path:
    container_root = PurePosixPath(settings.qbittorrent_save_path)
    try:
        relative = PurePosixPath(save_path).relative_to(container_root)
    except ValueError as exc:
        raise TransferError(f"Save path {save_path} is outside {container_root}.") from exc
    return Path(settings.downloads_path).expanduser() / relative / name


def transfer_torrent(client_qb: httpx.Client, client_jf: httpx.Client, settings: Settings, info_hash: str) -> str:
    qbittorrent.login(client_qb, settings)
    torrent = find_one(client_qb, info_hash)
    if torrent.progress < 1:
        raise TransferError(f"{torrent.name} is not finished ({torrent.progress:.0%}).")

    local = host_path(torrent.save_path, torrent.name, settings)
    remote = transfer(settings, local)
    jellyfin.refresh_library(client_jf)
    return f"Copied {torrent.name} to {remote}, verified the size, and asked Jellyfin to refresh. Local files are kept."
