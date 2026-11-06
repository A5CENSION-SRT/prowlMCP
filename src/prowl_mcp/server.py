from mcp.server.fastmcp import FastMCP

from prowl_mcp.clients import jellyfin, qbittorrent
from prowl_mcp.clients.prowlarr import make_client
from prowl_mcp.config import Settings
from prowl_mcp.models.search import SearchResult
from prowl_mcp.tools.downloads import register_download_tools
from prowl_mcp.tools.library import register_library_tools
from prowl_mcp.tools.processing import register_processing_tools
from prowl_mcp.tools.search import register_search_tools
from prowl_mcp.tools.transfer import register_transfer_tools

settings = Settings()
releases: dict[str, SearchResult] = {}

mcp = FastMCP("prowl-mcp")
register_search_tools(mcp, make_client(settings), settings, releases)
register_download_tools(mcp, qbittorrent.make_client(settings), settings, releases)
register_transfer_tools(mcp, qbittorrent.make_client(settings), jellyfin.make_client(settings), settings)
register_library_tools(mcp, jellyfin.make_client(settings), settings)
register_processing_tools(mcp, qbittorrent.make_client(settings), settings)


if __name__ == "__main__":
    mcp.run()
