from typing import Literal

import httpx
from mcp.server.fastmcp import FastMCP

from prowl_mcp.clients import jellyfin
from prowl_mcp.config import Settings
from prowl_mcp.services import library as library_service
from prowl_mcp.services.library import LibraryListing


def register_library_tools(mcp: FastMCP, jf_client: httpx.Client, settings: Settings) -> None:
    @mcp.tool()
    def list_library(kind: Literal["tv", "movies"]) -> LibraryListing:
        """List the files already on the Jellyfin server under its TV or Movies folder. Use it before transferring, to see what is already there."""
        return library_service.list_library(settings, kind)

    @mcp.tool()
    def list_server_folder(kind: Literal["tv", "movies"], folder: str) -> LibraryListing:
        """Read-only: list the files in one folder inside the Jellyfin TV or Movies library, such as 'Example Show (2025)/Season 02'. An empty folder or a missing one returns no files. It changes nothing on the server."""
        return library_service.list_folder(settings, kind, folder)

    @mcp.tool()
    def request_library_delete(kind: Literal["tv", "movies"], path: str) -> library_service.DeletePlan:
        """Step 1 of 2 to delete a file or folder on the Jellyfin server. Returns what would be deleted and a code. Show this to the user and ask for approval. Nothing is deleted yet."""
        return library_service.request_delete(settings, kind, path)

    @mcp.tool()
    def confirm_library_delete(code: str) -> str:
        """Step 2 of 2: delete the item from request_library_delete. Only call it after the user has approved that exact item in chat."""
        return library_service.confirm_delete(settings, code)

    @mcp.tool()
    def refresh_library() -> str:
        """Ask Jellyfin to rescan all libraries so newly transferred files appear, then wait for the scan to finish and report how it ended."""
        status = jellyfin.refresh_and_wait(jf_client, settings.jellyfin_scan_timeout_seconds, settings.jellyfin_scan_poll_seconds)
        return f"Jellyfin library refresh requested: {status}."
