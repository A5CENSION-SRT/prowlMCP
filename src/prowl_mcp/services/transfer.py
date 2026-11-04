import re
import shlex
import subprocess
from pathlib import Path, PurePosixPath
from typing import Literal

import httpx
from pydantic import BaseModel

from prowl_mcp.clients import jellyfin, qbittorrent
from prowl_mcp.config import Settings
from prowl_mcp.services.downloads import find_one

TV_PATTERN = re.compile(r"S\d{1,2}E\d{1,3}", re.IGNORECASE)
Kind = Literal["tv", "movies"]


class TransferError(Exception):
    pass


class TransferReport(BaseModel):
    remote_path: str
    copied: list[str]
    skipped: list[str]


def library_root(settings: Settings, kind: Kind) -> str:
    return settings.tv_library_path if kind == "tv" else settings.movies_library_path


def library_for(name: str, settings: Settings) -> Kind:
    return "tv" if TV_PATTERN.search(name) else "movies"


def resolve_destination(settings: Settings, kind: Kind | None, folder: str | None, name: str) -> str:
    root = library_root(settings, kind or library_for(name, settings))
    if folder is None:
        return root
    parts = PurePosixPath(folder).parts
    if not parts or folder.startswith("/") or any(part in ("..", ".") for part in parts) or "\n" in folder:
        raise TransferError("folder must be a path inside the library, such as 'Show (2025)/Season 01'.")
    return f"{root}/{'/'.join(parts)}"


def host_path(save_path: str, name: str, settings: Settings) -> Path:
    container_root = PurePosixPath(settings.qbittorrent_save_path)
    try:
        relative = PurePosixPath(save_path).relative_to(container_root)
    except ValueError as exc:
        raise TransferError(f"Save path {save_path} is outside {container_root}.") from exc
    return Path(settings.downloads_path).expanduser() / relative / name


def _ssh_options(settings: Settings) -> list[str]:
    key = str(Path(settings.ssh_key_path).expanduser())
    return ["-p", str(settings.ssh_port), "-i", key, "-o", "BatchMode=yes"]


def _ssh_target(settings: Settings) -> str:
    return f"{settings.ssh_user}@{settings.ssh_host}"


def _ssh_run(settings: Settings, script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", *_ssh_options(settings), _ssh_target(settings), script],
        capture_output=True,
        text=True,
        check=False,
    )


def local_files(local: Path) -> dict[str, int]:
    if local.is_file():
        return {local.name: local.stat().st_size}
    return {str(file.relative_to(local)): file.stat().st_size for file in local.rglob("*") if file.is_file()}


def remote_files(settings: Settings, remote_path: str) -> dict[str, int]:
    script = f"find {shlex.quote(remote_path)} -type f -printf '%P\\t%s\\n' 2>/dev/null"
    result = _ssh_run(settings, script)
    if result.returncode != 0:
        raise TransferError(f"Could not list the server folder: {result.stderr.strip()}")

    files = {}
    for line in result.stdout.splitlines():
        relative, _, size = line.rpartition("\t")
        files[relative or PurePosixPath(remote_path).name] = int(size)
    return files


def copy_to_destination(settings: Settings, local: Path, destination: str, dry_run: bool = False) -> None:
    flags = ["-a", "--partial", "--ignore-existing"] + (["--dry-run"] if dry_run else [])
    rsh = " ".join(["ssh", *_ssh_options(settings)])
    result = subprocess.run(
        ["rsync", *flags, "-e", rsh, str(local), f"{_ssh_target(settings)}:{destination}/"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise TransferError(f"rsync failed: {result.stderr.strip()}")


def transfer(settings: Settings, local: Path, destination: str) -> TransferReport:
    remote_path = f"{destination}/{local.name}"
    made = _ssh_run(settings, f"mkdir -p -- {shlex.quote(destination)}")
    if made.returncode != 0:
        raise TransferError(f"Could not create {destination}: {made.stderr.strip()}")

    before = remote_files(settings, remote_path)
    copy_to_destination(settings, local, destination)
    after = remote_files(settings, remote_path)

    copied, skipped = [], []
    for name, size in local_files(local).items():
        if name in before:
            skipped.append(name)
            continue
        if after.get(name) != size:
            raise TransferError(f"Size mismatch for {name}: local {size} bytes, server {after.get(name)} bytes.")
        copied.append(name)
    return TransferReport(remote_path=remote_path, copied=copied, skipped=skipped)


def transfer_torrent(
    client_qb: httpx.Client,
    client_jf: httpx.Client,
    settings: Settings,
    info_hash: str,
    kind: Kind | None = None,
    folder: str | None = None,
) -> str:
    qbittorrent.login(client_qb, settings)
    torrent = find_one(client_qb, info_hash)
    if torrent.progress < 1:
        raise TransferError(f"{torrent.name} is not finished ({torrent.progress:.0%}).")

    destination = resolve_destination(settings, kind, folder, torrent.name)
    report = transfer(settings, host_path(torrent.save_path, torrent.name, settings), destination)
    jellyfin.refresh_library(client_jf)

    message = f"Copied {len(report.copied)} new file(s) to {report.remote_path}."
    if report.skipped:
        message += f" Skipped {len(report.skipped)} already on the server: {', '.join(report.skipped)}."
    return message + " Local files are kept."
