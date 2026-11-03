import httpx
from mcp.server.fastmcp import FastMCP

from prowl_mcp.config import Settings
from prowl_mcp.models.search import SearchResult
from prowl_mcp.services import downloads
from prowl_mcp.services.safety import SafetyReport


def register_download_tools(mcp: FastMCP, client: httpx.Client, settings: Settings, releases: dict[str, SearchResult]) -> None:
    @mcp.tool()
    def add_torrent(info_hash: str) -> str:
        """Add a release from search_torrents by its info_hash, checking its file names before any download starts.

        Only hashes returned by search_torrents in this session can be added. The file names are checked first.
        If the verdict is ok, the download starts. If it is unsafe, the torrent and its files are removed. If it
        is suspicious or unknown, the torrent is held stopped until resume_torrent starts it.
        """
        return downloads.add_release(client, settings, releases, info_hash)

    @mcp.tool()
    def find_torrents(query: str) -> list[downloads.TorrentSummary]:
        """List qBittorrent torrents whose name contains the query, or whose info_hash matches it exactly."""
        return downloads.find_torrents(client, settings, query)

    @mcp.tool()
    def get_torrent_status(info_hash: str) -> downloads.TorrentSummary:
        """Show the state and progress of one torrent, by info_hash."""
        return downloads.get_torrent_status(client, settings, info_hash)

    @mcp.tool()
    def pause_torrent(info_hash: str) -> str:
        """Pause one torrent, by info_hash."""
        return downloads.pause_torrent(client, settings, info_hash)

    @mcp.tool()
    def resume_torrent(info_hash: str) -> str:
        """Resume one paused torrent, by info_hash."""
        return downloads.resume_torrent(client, settings, info_hash)

    @mcp.tool()
    def check_torrent(info_hash: str) -> SafetyReport:
        """Check a torrent's file names and extensions for risky content. Returns a verdict: ok, suspicious, unsafe, or unknown.

        This reads names only. It cannot prove a file is safe, and it does not open archives.
        """
        return downloads.check_torrent(client, settings, info_hash)

    @mcp.tool()
    def check_disk_space() -> downloads.DiskSpace:
        """Show how much free space qBittorrent has on its download folder. Check this before adding a large torrent."""
        return downloads.check_disk_space(client, settings)

    @mcp.tool()
    def remove_torrent(info_hash: str, delete_files: bool = False) -> str:
        """Remove one torrent, by info_hash. Files are kept unless delete_files is true."""
        return downloads.remove_torrent(client, settings, info_hash, delete_files)
