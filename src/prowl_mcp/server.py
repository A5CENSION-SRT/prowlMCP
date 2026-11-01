from mcp.server.fastmcp import FastMCP

from prowl_mcp.clients import qbittorrent
from prowl_mcp.clients.prowlarr import make_client
from prowl_mcp.config import Settings
from prowl_mcp.models.search import SearchResult
from prowl_mcp.tools.downloads import register_download_tools
from prowl_mcp.tools.search import register_search_tools

settings = Settings()
releases: dict[str, SearchResult] = {}

mcp = FastMCP("prowl-mcp")
register_search_tools(mcp, make_client(settings), settings, releases)
register_download_tools(mcp, qbittorrent.make_client(settings), settings, releases)


if __name__ == "__main__":
    mcp.run()
