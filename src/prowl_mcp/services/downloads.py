import time

import httpx
from pydantic import BaseModel

from prowl_mcp.clients import qbittorrent
from prowl_mcp.config import Settings
from prowl_mcp.models.search import SearchResult
from prowl_mcp.models.torrents import TorrentFile, TorrentInfo
from prowl_mcp.services.safety import SafetyReport, check_files
from prowl_mcp.services.search import format_size


class TorrentSummary(BaseModel):
    info_hash: str
    name: str
    state: str
    size: str
    progress: str
    eta: str
    speed: str
    seeds: int
    save_path: str


def format_eta(seconds: int, no_eta: int) -> str:
    if seconds >= no_eta:
        return "unknown"
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def summarize(torrent: TorrentInfo, settings: Settings) -> TorrentSummary:
    return TorrentSummary(
        info_hash=torrent.info_hash,
        name=torrent.name,
        state=torrent.state,
        size=format_size(torrent.size),
        progress=f"{torrent.progress:.0%}",
        eta=format_eta(torrent.eta, settings.qbittorrent_no_eta),
        speed=f"{format_size(torrent.dlspeed)}/s",
        seeds=torrent.num_seeds,
        save_path=torrent.save_path,
    )


def find_one(client: httpx.Client, info_hash: str) -> TorrentInfo:
    for torrent in qbittorrent.list_torrents(client):
        if torrent.info_hash.upper() == info_hash.upper():
            return torrent
    raise ValueError(f"No torrent with info_hash {info_hash} in qBittorrent.")


def wait_for_files(client: httpx.Client, info_hash: str, timeout_seconds: int, poll_seconds: int) -> list[TorrentFile]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        files = qbittorrent.list_files(client, info_hash)
        if files or time.monotonic() >= deadline:
            return files
        time.sleep(poll_seconds)


def add_release(client: httpx.Client, settings: Settings, releases: dict[str, SearchResult], info_hash: str) -> str:
    release = releases.get(info_hash.upper())
    if release is None:
        message = f"No search result with info_hash {info_hash}. Search for it first."
        raise ValueError(message)

    qbittorrent.login(client, settings)
    already_added = {torrent.info_hash.upper() for torrent in qbittorrent.list_torrents(client)}
    if release.info_hash.upper() in already_added:
        return f"Already added: {release.title}"

    qbittorrent.add_torrent(client, release.guid, settings.qbittorrent_tag)
    report = check_files(wait_for_files(client, release.info_hash, settings.metadata_timeout_seconds, settings.metadata_poll_seconds))

    reasons = "; ".join(report.unsafe + report.warnings) or "no file list arrived in time"

    if report.verdict == "ok":
        qbittorrent.start_torrent(client, release.info_hash)
        return f"Added and started: {release.title}. Check: ok, {report.file_count} files.\n" + "\n".join(report.contents)

    if report.verdict == "unsafe":
        qbittorrent.delete_torrent(client, release.info_hash, delete_files=True)
        return f"Removed with its files: {release.title}. Check: unsafe ({reasons})."

    qbittorrent.stop_torrent(client, release.info_hash)
    return f"Held, not started: {release.title}. Check: {report.verdict} ({reasons}). Use resume_torrent to start it.\n" + "\n".join(report.contents)


def find_torrents(client: httpx.Client, settings: Settings, query: str) -> list[TorrentSummary]:
    needle = query.strip().lower()
    if not needle:
        raise ValueError("Give a name or info_hash to search for.")

    qbittorrent.login(client, settings)
    matches = [torrent for torrent in qbittorrent.list_torrents(client) if torrent.info_hash.lower() == needle or needle in torrent.name.lower()]
    return [summarize(torrent, settings) for torrent in matches]


def get_torrent_status(client: httpx.Client, settings: Settings, info_hash: str) -> TorrentSummary:
    qbittorrent.login(client, settings)
    return summarize(find_one(client, info_hash), settings)


def pause_torrent(client: httpx.Client, settings: Settings, info_hash: str) -> str:
    qbittorrent.login(client, settings)
    torrent = find_one(client, info_hash)
    qbittorrent.stop_torrent(client, torrent.info_hash)
    return f"Paused: {torrent.name}"


def resume_torrent(client: httpx.Client, settings: Settings, info_hash: str) -> str:
    qbittorrent.login(client, settings)
    torrent = find_one(client, info_hash)
    qbittorrent.start_torrent(client, torrent.info_hash)

    time.sleep(settings.resume_check_seconds)
    qbittorrent.login(client, settings)
    torrent = find_one(client, info_hash)
    summary = summarize(torrent, settings)
    message = f"Resumed: {torrent.name}. After {settings.resume_check_seconds}s: {summary.state}, {summary.progress} done, {summary.speed}, {summary.seeds} seeds."
    if torrent.progress < 1 and torrent.dlspeed == 0:
        message += " No data is coming in yet, so it may be stalled until peers reconnect."
    return message


class DiskSpace(BaseModel):
    free: str
    free_bytes: int
    save_path: str


def check_disk_space(client: httpx.Client, settings: Settings) -> DiskSpace:
    qbittorrent.login(client, settings)
    free_bytes = qbittorrent.free_space_bytes(client)
    return DiskSpace(free=format_size(free_bytes), free_bytes=free_bytes, save_path=settings.qbittorrent_save_path)


def check_torrent(client: httpx.Client, settings: Settings, info_hash: str) -> SafetyReport:
    qbittorrent.login(client, settings)
    torrent = find_one(client, info_hash)
    return check_files(qbittorrent.list_files(client, torrent.info_hash))


def remove_torrent(client: httpx.Client, settings: Settings, info_hash: str, delete_files: bool) -> str:
    qbittorrent.login(client, settings)
    torrent = find_one(client, info_hash)
    qbittorrent.delete_torrent(client, torrent.info_hash, delete_files)
    suffix = " and its files" if delete_files else ", files kept"
    return f"Removed: {torrent.name}{suffix}"
