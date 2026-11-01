import httpx

from prowl_mcp.config import Settings
from prowl_mcp.models.torrents import TorrentFile, TorrentInfo

TAG = "prowl"


class QBittorrentError(Exception):
    pass


def make_client(settings: Settings) -> httpx.Client:
    return httpx.Client(
        base_url=settings.qbittorrent_url,
        headers={"Referer": settings.qbittorrent_url},
        timeout=settings.request_timeout,
    )


def login(client: httpx.Client, settings: Settings) -> None:
    credentials = {
        "username": settings.qbittorrent_username,
        "password": settings.qbittorrent_password.get_secret_value(),
    }
    # Drop the old session cookie first. qBittorrent does not send a new one to a client that already has a valid session.
    client.cookies.clear()
    try:
        response = client.post("/api/v2/auth/login", data=credentials)
    except httpx.HTTPError as exc:
        raise QBittorrentError(f"Could not reach qBittorrent: {exc}") from exc

    if response.status_code == 403:
        raise QBittorrentError("qBittorrent blocked this IP (403) after failed logins.")
    # qBittorrent 5.x names the session cookie after the port, e.g. QBT_SID_11112.
    has_session = any("SID" in name for name in response.cookies)
    if not has_session:
        raise QBittorrentError("qBittorrent rejected the username or password.")


def _post(client: httpx.Client, path: str, data: dict[str, str]) -> httpx.Response:
    try:
        response = client.post(path, data=data)
    except httpx.HTTPError as exc:
        raise QBittorrentError(f"Could not reach qBittorrent: {exc}") from exc

    if response.status_code >= 400:
        raise QBittorrentError(f"qBittorrent returned {response.status_code} for {path}.")
    return response


def list_torrents(client: httpx.Client) -> list[TorrentInfo]:
    try:
        response = client.get("/api/v2/torrents/info")
    except httpx.HTTPError as exc:
        raise QBittorrentError(f"Could not reach qBittorrent: {exc}") from exc

    if response.status_code >= 400:
        raise QBittorrentError(f"qBittorrent returned {response.status_code} for the torrent list.")
    return [TorrentInfo.model_validate(item) for item in response.json()]


def list_files(client: httpx.Client, info_hash: str) -> list[TorrentFile]:
    try:
        response = client.get("/api/v2/torrents/files", params={"hash": info_hash})
    except httpx.HTTPError as exc:
        raise QBittorrentError(f"Could not reach qBittorrent: {exc}") from exc

    if response.status_code >= 400:
        raise QBittorrentError(f"qBittorrent returned {response.status_code} for the file list.")
    return [TorrentFile.model_validate(item) for item in response.json()]


def add_torrent(client: httpx.Client, magnet: str) -> None:
    # Share limits are set in the same request, so the torrent stops as soon as it finishes downloading:
    # ratioLimit 0 is reached immediately once seeding starts. -1 turns off the seeding-time limits.
    payload = {
        "urls": magnet,
        "tags": TAG,
        "ratioLimit": "0",
        "seedingTimeLimit": "-1",
        "inactiveSeedingTimeLimit": "-1",
        "shareLimitsMode": "MatchAny",
        "shareLimitAction": "Stop",
    }
    response = _post(client, "/api/v2/torrents/add", payload)
    if response.text != "Ok.":
        raise QBittorrentError(f"qBittorrent did not add the torrent: {response.text}")


# qBittorrent 5.x calls pause "stop" and resume "start". The old names return 404 on this server.
def stop_torrent(client: httpx.Client, info_hash: str) -> None:
    _post(client, "/api/v2/torrents/stop", {"hashes": info_hash})


def start_torrent(client: httpx.Client, info_hash: str) -> None:
    _post(client, "/api/v2/torrents/start", {"hashes": info_hash})


def delete_torrent(client: httpx.Client, info_hash: str, delete_files: bool) -> None:
    payload = {"hashes": info_hash, "deleteFiles": "true" if delete_files else "false"}
    _post(client, "/api/v2/torrents/delete", payload)
