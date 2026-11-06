from typing import Literal

import httpx
from mcp.server.fastmcp import FastMCP

from prowl_mcp.config import Settings
from prowl_mcp.services import finish, transfer


def register_transfer_tools(mcp: FastMCP, qb_client: httpx.Client, jf_client: httpx.Client, settings: Settings) -> None:
    @mcp.tool()
    def finish_torrent(info_hash: str, kind: Literal["tv", "movies"] | None = None, folder: str | None = None, rename: bool = True) -> str:
        """Finish a completed download in one step: embed English subtitles (per episode for season packs), copy to the Jellyfin server, check SHA-256 checksums, and refresh Jellyfin. It never removes the torrent or its data; ask the user first, then use remove_torrent.

        Use it after the download is finished. kind, folder and rename work the same as transfer_torrent.
        """
        return finish.finish_torrent(qb_client, jf_client, settings, info_hash, kind, folder, rename)

    @mcp.tool()
    def transfer_torrent(info_hash: str, kind: Literal["tv", "movies"] | None = None, folder: str | None = None, rename: bool = True) -> str:
        """Copy a finished download to the Jellyfin server, check sizes and SHA-256 checksums, skip files already there, then refresh Jellyfin.

        Call list_library first and choose the destination yourself. kind picks the library (tv or movies). folder is a
        path inside it, such as 'Example Show (2025)/Season 02'. When folder is given, the files go straight into
        it, so a season pack does not leave a release-named folder inside. With rename on (the default) and a TV folder,
        episode videos are named 'Show (Year) - S02E01.mkv', using the first part of folder as the show name; set rename
        to false to keep the original names. The copy can only go inside the library and never overwrites a file. Without
        folder, a folder torrent keeps its own folder inside the library root.
        """
        return transfer.transfer_torrent(qb_client, jf_client, settings, info_hash, kind, folder, rename)
