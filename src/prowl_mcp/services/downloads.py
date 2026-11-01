import httpx
from pydantic import BaseModel

from prowl_mcp.clients import qbittorrent
from prowl_mcp.config import Settings
from prowl_mcp.models.search import SearchResult
from prowl_mcp.models.torrents import TorrentInfo
from prowl_mcp.services.search import format_size

# qBittorrent reports this many seconds when it cannot estimate the time left.
QBITTORRENT_NO_ETA = 8640000


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


def format_eta(seconds: int) -> str:
    if seconds >= QBITTORRENT_NO_ETA:
        return "unknown"
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def summarize(torrent: TorrentInfo) -> TorrentSummary:
    return TorrentSummary(
        info_hash=torrent.info_hash,
        name=torrent.name,
        state=torrent.state,
        size=format_size(torrent.size),
        progress=f"{torrent.progress:.0%}",
        eta=format_eta(torrent.eta),
        speed=f"{format_size(torrent.dlspeed)}/s",
        seeds=torrent.num_seeds,
        save_path=torrent.save_path,
    )


def find_one(client: httpx.Client, info_hash: str) -> TorrentInfo:
    for torrent in qbittorrent.list_torrents(client):
        if torrent.info_hash.upper() == info_hash.upper():
            return torrent
    raise ValueError(f"No torrent with info_hash {info_hash} in qBittorrent.")


def add_release(client: httpx.Client, settings: Settings, releases: dict[str, SearchResult], info_hash: str) -> str:
    release = releases.get(info_hash.upper())
    if release is None:
        message = f"No search result with info_hash {info_hash}. Search for it first."
        raise ValueError(message)

    qbittorrent.login(client, settings)
    already_added = {torrent.info_hash.upper() for torrent in qbittorrent.list_torrents(client)}
    if release.info_hash.upper() in already_added:
        return f"Already added: {release.title}"

    qbittorrent.add_torrent(client, release.guid)
    return f"Added to qBittorrent: {release.title}"


def find_torrents(client: httpx.Client, settings: Settings, query: str) -> list[TorrentSummary]:
    needle = query.strip().lower()
    if not needle:
        raise ValueError("Give a name or info_hash to search for.")

    qbittorrent.login(client, settings)
    matches = [torrent for torrent in qbittorrent.list_torrents(client) if torrent.info_hash.lower() == needle or needle in torrent.name.lower()]
    return [summarize(torrent) for torrent in matches]


def get_torrent_status(client: httpx.Client, settings: Settings, info_hash: str) -> TorrentSummary:
    qbittorrent.login(client, settings)
    return summarize(find_one(client, info_hash))


def pause_torrent(client: httpx.Client, settings: Settings, info_hash: str) -> str:
    qbittorrent.login(client, settings)
    torrent = find_one(client, info_hash)
    qbittorrent.stop_torrent(client, torrent.info_hash)
    return f"Paused: {torrent.name}"


def resume_torrent(client: httpx.Client, settings: Settings, info_hash: str) -> str:
    qbittorrent.login(client, settings)
    torrent = find_one(client, info_hash)
    qbittorrent.start_torrent(client, torrent.info_hash)
    return f"Resumed: {torrent.name}"


def remove_torrent(client: httpx.Client, settings: Settings, info_hash: str, delete_files: bool) -> str:
    qbittorrent.login(client, settings)
    torrent = find_one(client, info_hash)
    qbittorrent.delete_torrent(client, torrent.info_hash, delete_files)
    suffix = " and its files" if delete_files else ", files kept"
    return f"Removed: {torrent.name}{suffix}"
