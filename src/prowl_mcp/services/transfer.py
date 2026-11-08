import hashlib
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
RENAMEABLE_EXTENSIONS = {"mkv", "mp4", "m4v", "avi", "mov", "wmv", "ts"}
ENGLISH_TAGS = {"eng", "en", "english"}
# rsync keeps an interrupted copy here, not under the final name, so a retry resumes it instead of skipping a half file.
PARTIAL_DIR = ".rsync-partial"
Kind = Literal["tv", "movies"]


class TransferError(Exception):
    pass


class TransferReport(BaseModel):
    remote_path: str
    copied: list[str]
    skipped: list[str]
    verified: list[str] = []
    left_out: list[str] = []


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


def host_content_path(content_path: str, settings: Settings) -> Path:
    """Map qBittorrent's content path (the real file or folder) onto this machine."""
    container_root = PurePosixPath(settings.qbittorrent_save_path)
    try:
        relative = PurePosixPath(content_path).relative_to(container_root)
    except ValueError as exc:
        raise TransferError(f"Content path {content_path} is outside {container_root}.") from exc
    return Path(settings.downloads_path).expanduser() / relative


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


def local_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remote_sha256(settings: Settings, remote_file: str) -> str:
    result = _ssh_run(settings, f"sha256sum -- {shlex.quote(remote_file)}")
    if result.returncode != 0:
        raise TransferError(f"Could not checksum {remote_file}: {result.stderr.strip()}")
    return result.stdout.split()[0]


def remote_files(settings: Settings, remote_path: str) -> dict[str, int]:
    # A path that does not exist yet is an empty listing, not an error.
    quoted = shlex.quote(remote_path)
    script = f"if [ -e {quoted} ]; then find {quoted} -type f -not -path '*/{PARTIAL_DIR}/*' -printf '%P\\t%s\\n'; fi"
    result = _ssh_run(settings, script)
    if result.returncode != 0:
        raise TransferError(f"Could not list the server folder: {result.stderr.strip()}")

    files = {}
    for line in result.stdout.splitlines():
        relative, _, size = line.rpartition("\t")
        files[relative or PurePosixPath(remote_path).name] = int(size)
    return files


def is_video(name: str) -> bool:
    return PurePosixPath(name).suffix.lower().lstrip(".") in RENAMEABLE_EXTENSIONS


def is_english_srt(name: str) -> bool:
    return PurePosixPath(name).suffix.lower() == ".srt" and bool(set(re.split(r"[^a-z]+", name.lower())) & ENGLISH_TAGS)


def episode_code(name: str) -> str | None:
    match = TV_PATTERN.search(PurePosixPath(name).name)
    return match.group(0).upper() if match else None


def select_files(files: dict[str, int], show: str | None, title: str | None) -> dict[str, str]:
    """Pick the files Jellyfin needs and name them: the video and its English SRT. Samples, .nfo and other extras stay local.

    Movie: the largest video becomes 'Example Movie (2020).mkv', its SRT 'Example Movie (2020).eng.srt'.
    TV: each SxxEyy video becomes 'Example Show (2020) - S01E01.mkv', keeping the largest when two share a code (a sample).
    """
    videos = {name: size for name, size in files.items() if is_video(name)}
    srts = sorted(name for name in files if is_english_srt(name))
    picked: dict[str, str] = {}
    if title is not None:
        if not videos:
            raise TransferError("No video file to copy.")
        # The largest video is the movie, so samples and extras are left out whatever they are called.
        main = max(videos, key=lambda name: videos[name])
        picked[f"{title}{PurePosixPath(main).suffix.lower()}"] = main
        if srts:
            picked[f"{title}.eng.srt"] = srts[0]
        return picked

    episodes: dict[str, str] = {}
    for name, size in videos.items():
        code = episode_code(name)
        if code is not None and (code not in episodes or size > videos[episodes[code]]):
            episodes[code] = name
    if not episodes:
        raise TransferError("No episode videos (SxxEyy) to copy. Check the folder, or turn rename off to copy the files as they are.")
    for code, name in episodes.items():
        picked[f"{show} - {code}{PurePosixPath(name).suffix.lower()}"] = name
        srt = next((s for s in srts if re.search(rf"{code}(?!\d)", s, re.IGNORECASE)), None)
        if srt is None and len(episodes) == 1 and len(srts) == 1:
            srt = srts[0]
        if srt is not None:
            picked[f"{show} - {code}.eng.srt"] = srt
    return picked


def plan_files(local: Path, flatten: bool, show: str | None, title: str | None = None) -> tuple[dict[str, Path], list[str]]:
    """Map each path on the server, relative to the destination, to the local file that goes there. Also return the files left out."""
    files = local_files(local)

    def source(name: str) -> Path:
        return local if local.is_file() else local / name

    if show is None and title is None:
        # No renaming: copy everything as it is. A folder torrent keeps its own folder unless flatten is set.
        prefix = "" if flatten or local.is_file() else f"{local.name}/"
        return {prefix + name: source(name) for name in files}, []

    picked = select_files(files, show, title)
    left_out = sorted(set(files) - set(picked.values()))
    return {target: source(name) for target, name in picked.items()}, left_out


def copy_file(settings: Settings, source: Path, remote_file: str) -> None:
    parent = str(PurePosixPath(remote_file).parent)
    made = _ssh_run(settings, f"mkdir -p -- {shlex.quote(parent)}")
    if made.returncode != 0:
        raise TransferError(f"Could not create {parent}: {made.stderr.strip()}")

    rsh = " ".join(["ssh", *_ssh_options(settings)])
    result = subprocess.run(
        ["rsync", "-a", f"--partial-dir={PARTIAL_DIR}", "--ignore-existing", "-e", rsh, str(source), f"{_ssh_target(settings)}:{remote_file}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise TransferError(f"rsync failed for {source.name}: {result.stderr.strip()}")


def transfer(settings: Settings, local: Path, destination: str, flatten: bool = False, show: str | None = None, title: str | None = None) -> TransferReport:
    plan, left_out = plan_files(local, flatten, show, title)
    # An empty plan means nothing was found to copy. That is a failure, never a successful delivery.
    if not plan:
        raise TransferError(f"Nothing to copy: no files found at {local}.")
    made = _ssh_run(settings, f"mkdir -p -- {shlex.quote(destination)}")
    if made.returncode != 0:
        raise TransferError(f"Could not create {destination}: {made.stderr.strip()}")

    before = remote_files(settings, destination)
    for target, source in plan.items():
        if target not in before:
            copy_file(settings, source, f"{destination}/{target}")
    after = remote_files(settings, destination)

    copied, skipped = [], []
    for target, source in plan.items():
        size = source.stat().st_size
        if after.get(target) != size:
            # A file that was already there with another size is a different file; it is never overwritten.
            problem = "a different file with that name is already on the server" if target in before else "the copy is incomplete"
            raise TransferError(f"Size mismatch for {target}: local {size} bytes, server {after.get(target)} bytes ({problem}).")
        (skipped if target in before else copied).append(target)

    # Files skipped as already there are checked too, so a retry after a crash proves the whole set.
    verified = verify_checksums(settings, destination, plan, copied + skipped)
    return TransferReport(remote_path=destination, copied=copied, skipped=skipped, verified=verified, left_out=left_out)


def verify_checksums(settings: Settings, destination: str, plan: dict[str, Path], targets: list[str]) -> list[str]:
    verified = []
    for target in targets:
        if local_sha256(plan[target]) != remote_sha256(settings, f"{destination}/{target}"):
            raise TransferError(f"Checksum mismatch for {target}: the server copy does not match the local file.")
        verified.append(target)
    return verified


def check_jellyfin(jf_client: httpx.Client, settings: Settings, report: TransferReport) -> str:
    # The files are already copied, so a Jellyfin problem is reported here and does not fail the transfer.
    videos = {PurePosixPath(target).name for target in report.copied + report.skipped if PurePosixPath(target).suffix.lower().lstrip(".") in RENAMEABLE_EXTENSIONS}
    try:
        scan = jellyfin.refresh_and_wait(jf_client, settings.jellyfin_scan_timeout_seconds, settings.jellyfin_scan_poll_seconds)
        seen = jellyfin.find_items(jf_client, videos)
    except jellyfin.JellyfinError as exc:
        return f"Jellyfin check failed: {exc}. Files are on the server; try refresh_library."
    line = f"Jellyfin: {scan}; it lists {len(seen)} of {len(videos)} videos from this transfer."
    missing = sorted(videos - seen)
    return line + (f" Not listed yet: {', '.join(missing)}." if missing else "")


def transfer_torrent(qb_client: httpx.Client, jf_client: httpx.Client, settings: Settings, info_hash: str, kind: Kind | None = None, folder: str | None = None, rename: bool = True) -> str:
    qbittorrent.login(qb_client, settings)
    torrent = find_one(qb_client, info_hash)
    if torrent.progress < 1:
        raise TransferError(f"{torrent.name} is not finished ({torrent.progress:.0%}).")

    destination = resolve_destination(settings, kind, folder, torrent.name)
    # With a folder given, the files go straight into it. Without one, a folder torrent keeps its own folder.
    flatten = folder is not None
    is_tv = (kind or library_for(torrent.name, settings)) == "tv"
    show = PurePosixPath(folder).parts[0] if rename and flatten and is_tv else None
    # A movie's video takes the name of its folder, the same as the Jellyfin folder layout.
    title = PurePosixPath(folder).parts[0] if rename and flatten and not is_tv else None

    if not torrent.content_path:
        raise TransferError(f"qBittorrent did not report where {torrent.name} is stored.")
    report = transfer(settings, host_content_path(torrent.content_path, settings), destination, flatten, show, title)
    message = f"Copied {len(report.copied)} new file(s) to {report.remote_path}. Checksums match for {len(report.verified)}.\n{check_jellyfin(jf_client, settings, report)}"
    if report.copied:
        message += "\n" + "\n".join(report.copied)
    if report.skipped:
        message += f"\nSkipped {len(report.skipped)} already on the server: {', '.join(report.skipped)}."
    if report.left_out:
        message += f"\nLeft out {len(report.left_out)} file(s) Jellyfin does not need: {', '.join(report.left_out)}."
    return message + "\nLocal files are kept."
