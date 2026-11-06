import httpx
from mcp.server.fastmcp import FastMCP

from prowl_mcp.config import Settings
from prowl_mcp.services import subtitles


def register_processing_tools(mcp: FastMCP, qb_client: httpx.Client, settings: Settings) -> None:
    @mcp.tool()
    def process_subtitles(info_hash: str) -> str:
        """Embed the matching English SRT into each video of a finished download (per episode for season packs), skipping videos that already have embedded English subtitles. Keeps all files."""
        return subtitles.process_subtitles(qb_client, settings, info_hash)
