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
