import httpx
from mcp.server.fastmcp import FastMCP

from prowl_mcp.clients import jellyfin


def register_library_tools(mcp: FastMCP, jf_client: httpx.Client) -> None:
    @mcp.tool()
    def refresh_library() -> str:
        """Ask Jellyfin to rescan all libraries so newly transferred files appear. Takes effect in the background."""
        jellyfin.refresh_library(jf_client)
        return "Jellyfin library refresh requested."
