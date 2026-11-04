from typing import Literal

import httpx
from mcp.server.fastmcp import FastMCP

from prowl_mcp.config import Settings
from prowl_mcp.services import transfer


def register_transfer_tools(mcp: FastMCP, qb_client: httpx.Client, jf_client: httpx.Client, settings: Settings) -> None:
    @mcp.tool()
    def transfer_torrent(
        info_hash: str,
        kind: Literal["tv", "movies"] | None = None,
        folder: str | None = None,
    ) -> str:
        """Copy a finished download to the Jellyfin server, check sizes, skip files already there, then refresh Jellyfin.

        Call list_library first and choose the destination yourself. kind picks the library (tv or movies). folder is a
        path inside it, such as 'Example Show (2025)/Season 02'. The copy can only go inside that library and never
        overwrites a file. Leave both out to use the default rules.
        """
        return transfer.transfer_torrent(qb_client, jf_client, settings, info_hash, kind, folder)
