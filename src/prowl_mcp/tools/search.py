from typing import Literal

import httpx
from mcp.server.fastmcp import FastMCP

from prowl_mcp.config import Settings
from prowl_mcp.models.search import SearchResult
from prowl_mcp.services.search import ReleaseSummary, find_releases
from prowl_mcp.services.trending import TrendingItem, trending_items


def register_search_tools(mcp: FastMCP, client: httpx.Client, settings: Settings, releases: dict[str, SearchResult]) -> None:
    @mcp.tool()
    def search_torrents(queries: list[str], limit: int | None = None) -> list[ReleaseSummary]:
        """Search torrent indexers with a few query variations, and return the best matches sorted by seeders.

        Each query runs separately, and duplicates across queries are merged. Each result has a
        condensed size (such as "3.0 GiB") and an info_hash. Use short keywords, such as "ubuntu",
        and vary them: a shorter keyword, the full release name, or the title without punctuation.
        """
        return find_releases(client, queries, releases, settings, limit or settings.default_search_limit)


def register_trending_tools(mcp: FastMCP, client: httpx.Client, settings: Settings, releases: dict[str, SearchResult]) -> None:
    @mcp.tool()
    def trending_releases(kind: Literal["tv", "movies"] = "movies", limit: int | None = None) -> list[TrendingItem]:
        """List recent releases with the most seeders that are not in the Jellyfin library yet. This is a popularity proxy from the indexer, not real trending data: it lags behind new releases. Each item has an info_hash that add_torrent accepts."""
        results, items = trending_items(client, settings, kind, limit or settings.trending_limit)
        for result in results:
            releases[result.info_hash.upper()] = result
        return items
