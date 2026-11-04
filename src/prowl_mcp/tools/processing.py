import httpx
from mcp.server.fastmcp import FastMCP

from prowl_mcp.config import Settings
from prowl_mcp.services import subtitles


def register_processing_tools(mcp: FastMCP, qb_client: httpx.Client, settings: Settings) -> None:
    @mcp.tool()
    def process_subtitles(info_hash: str) -> str:
        """Embed the English SRT into a finished single-video download, unless it already has an embedded English SRT. Keeps all files."""
        return subtitles.process_subtitles(qb_client, settings, info_hash)
