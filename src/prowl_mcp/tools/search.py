import httpx
from mcp.server.fastmcp import FastMCP

from prowl_mcp.config import Settings
from prowl_mcp.models.search import SearchResult
from prowl_mcp.services.search import ReleaseSummary, find_releases


def register_search_tools(mcp: FastMCP, client: httpx.Client, settings: Settings, releases: dict[str, SearchResult]) -> None:
    @mcp.tool()
    def search_torrents(queries: list[str], limit: int = 20) -> list[ReleaseSummary]:
        """Search torrent indexers with a few query variations, and return the best matches sorted by seeders.

        Each query runs separately, and duplicates across queries are merged. Each result has a
        condensed size (such as "3.0 GiB") and an info_hash. Use short keywords, such as "ubuntu",
        and vary them: a shorter keyword, the full release name, or the title without punctuation.
        """
        return find_releases(
            client,
            queries,
            releases,
            settings.max_search_queries,
            settings.search_results_per_query,
            limit,
        )
