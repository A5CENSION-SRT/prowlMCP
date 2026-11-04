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
    def request_library_delete(kind: Literal["tv", "movies"], path: str) -> library_service.DeletePlan:
        """Step 1 of 2 to delete a file or folder on the Jellyfin server. Returns what would be deleted and a code. Show this to the user and ask for approval. Nothing is deleted yet."""
        return library_service.request_delete(settings, kind, path)

    @mcp.tool()
    def confirm_library_delete(code: str) -> str:
        """Step 2 of 2: delete the item from request_library_delete. Only call it after the user has approved that exact item in chat."""
        return library_service.confirm_delete(settings, code)

    @mcp.tool()
    def refresh_library() -> str:
        """Ask Jellyfin to rescan all libraries so newly transferred files appear. Takes effect in the background."""
        jellyfin.refresh_library(jf_client)
        return "Jellyfin library refresh requested."
