import httpx
from mcp.server.fastmcp import FastMCP

from prowl_mcp.services.search import ReleaseSummary, find_releases


def register_search_tools(mcp: FastMCP, client: httpx.Client) -> None:
    @mcp.tool()
    def search_torrents(query: str, limit: int = 20) -> list[ReleaseSummary]:
        """Search torrent indexers and return the best matches, sorted by seeders.

        Each result has a condensed size (such as "3.0 GiB") and an info_hash.
        A single keyword usually works best, so start with the main word of the
        title. If the results look wrong or empty, search again with a different
        query: a shorter keyword, the full release name, or the title without
        punctuation. For example, try "ubuntu" before "ubuntu 22.04 desktop amd64".
        """
        return find_releases(client, query, limit)
