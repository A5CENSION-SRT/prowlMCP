import httpx

from prowl_mcp.config import Settings
from prowl_mcp.models.search import SearchResult


class ProwlarrError(Exception):
    pass


def make_client(settings: Settings) -> httpx.Client:
    return httpx.Client(
        base_url=settings.prowlarr_url,
        headers={"X-Api-Key": settings.prowlarr_api_key.get_secret_value()},
        timeout=settings.request_timeout,
    )


def search(client: httpx.Client, query: str) -> list[SearchResult]:
    try:
        response = client.get(
            "/api/v1/search",
            params={"query": query, "type": "search", "indexerIds": -2},
        )
    except httpx.HTTPError as exc:
        raise ProwlarrError(f"Could not reach Prowlarr: {exc}") from exc

    if response.status_code == 401:
        raise ProwlarrError("Prowlarr rejected the API key (401).")
    if response.status_code >= 400:
        raise ProwlarrError(f"Prowlarr returned {response.status_code}.")

    return [SearchResult.model_validate(item) for item in response.json()]
