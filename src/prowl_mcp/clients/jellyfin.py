import time
from pathlib import PurePosixPath

import httpx

from prowl_mcp.config import Settings


class JellyfinError(Exception):
    pass


def make_client(settings: Settings) -> httpx.Client:
    return httpx.Client(
        base_url=settings.jellyfin_url,
        headers={"Authorization": f'MediaBrowser Token="{settings.jellyfin_api_key.get_secret_value()}"'},
        timeout=settings.request_timeout,
    )


def get_system_info(client: httpx.Client) -> dict:
    try:
        response = client.get("/System/Info")
    except httpx.HTTPError as exc:
        raise JellyfinError(f"Could not reach Jellyfin: {exc}") from exc

    if response.status_code == 401:
        raise JellyfinError("Jellyfin rejected the API key (401).")
    if response.status_code >= 400:
        raise JellyfinError(f"Jellyfin returned {response.status_code} for /System/Info.")
    return response.json()


def refresh_library(client: httpx.Client) -> None:
    try:
        response = client.post("/Library/Refresh")
    except httpx.HTTPError as exc:
        raise JellyfinError(f"Could not reach Jellyfin: {exc}") from exc

    if response.status_code >= 400:
        raise JellyfinError(f"Jellyfin returned {response.status_code} for /Library/Refresh.")


def _get(client: httpx.Client, path: str, params: dict[str, str] | None = None) -> httpx.Response:
    try:
        response = client.get(path, params=params)
    except httpx.HTTPError as exc:
        raise JellyfinError(f"Could not reach Jellyfin: {exc}") from exc

    if response.status_code >= 400:
        raise JellyfinError(f"Jellyfin returned {response.status_code} for {path}.")
    return response


def scan_task(client: httpx.Client) -> dict:
    for task in _get(client, "/ScheduledTasks").json():
        if task.get("Key") == "RefreshLibrary":
            return task
    raise JellyfinError("Jellyfin has no 'Scan Media Library' task.")


def refresh_and_wait(client: httpx.Client, timeout_seconds: int, poll_seconds: int) -> str:
    """Ask for a rescan, then wait until Jellyfin's scan task reports a new finished run."""
    before = (scan_task(client).get("LastExecutionResult") or {}).get("EndTimeUtc")
    refresh_library(client)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        time.sleep(poll_seconds)
        task = scan_task(client)
        result = task.get("LastExecutionResult") or {}
        if task.get("State") == "Idle" and result.get("EndTimeUtc") != before:
            return f"scan {str(result.get('Status', 'finished')).lower()}"
    return f"scan still running after {timeout_seconds}s"


def find_items(client: httpx.Client, file_names: set[str]) -> set[str]:
    """Return which of the given file names Jellyfin lists as an episode or movie."""
    params = {"Recursive": "true", "IncludeItemTypes": "Episode,Movie", "Fields": "Path", "SortBy": "DateCreated", "SortOrder": "Descending", "Limit": "1000"}
    items = _get(client, "/Items", params).json().get("Items", [])
    listed = {PurePosixPath(item["Path"]).name for item in items if item.get("Path")}
    return file_names & listed
