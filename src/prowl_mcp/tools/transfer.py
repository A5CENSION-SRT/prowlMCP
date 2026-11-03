import httpx
from mcp.server.fastmcp import FastMCP

from prowl_mcp.config import Settings
from prowl_mcp.services import transfer


def register_transfer_tools(mcp: FastMCP, qb_client: httpx.Client, jf_client: httpx.Client, settings: Settings) -> None:
    @mcp.tool()
    def transfer_torrent(info_hash: str) -> str:
        """Copy a finished download to the Jellyfin server by its info_hash, check the size, then refresh Jellyfin. Local files are kept."""
        return transfer.transfer_torrent(qb_client, jf_client, settings, info_hash)
