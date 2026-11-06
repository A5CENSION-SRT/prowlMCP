from typing import Literal

import httpx
from mcp.server.fastmcp import FastMCP

from prowl_mcp.config import Settings
from prowl_mcp.services import pipeline, transfer


def register_transfer_tools(mcp: FastMCP, qb_client: httpx.Client, jf_client: httpx.Client, settings: Settings) -> None:
    @mcp.tool()
    def finish_torrent(info_hash: str, kind: Literal["tv", "movies"] | None = None, folder: str | None = None, rename: bool = True) -> str:
        """Finish a completed download now, in one blocking call: embed English subtitles (per episode for season packs), copy to the Jellyfin server, check SHA-256 checksums, and refresh Jellyfin. It never removes the torrent or its data; ask the user first, then use remove_torrent.

        It queues (or re-queues) the delivery job and runs it, so it also retries a failed job. kind, folder and rename
        work the same as transfer_torrent. For a long copy, prefer queuing with add_torrent or queue_delivery and let the
        worker run it, or run `prowl deliver` as a background task.
        """
        pipeline.queue_delivery(qb_client, settings, info_hash, kind, folder, rename)
        job = pipeline.deliver(qb_client, jf_client, settings, info_hash)
        if job.error:
            return f"{pipeline.describe(job, settings)}\nRun finish_torrent again to retry; it continues where it stopped."
        return f"Subtitles and transfer done.\n{job.result}\n\nNext: ask the user before removing the torrent and its data. Only after they approve, call remove_torrent with delete_files=true."

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

    @mcp.tool()
    def queue_delivery(info_hash: str, kind: Literal["tv", "movies"] | None = None, folder: str | None = None, rename: bool = True) -> str:
        """Queue (or re-queue) delivery for a torrent already in qBittorrent. Once its download finishes, the background worker
        embeds subtitles, copies to the Jellyfin server, checks checksums and refreshes Jellyfin, with or without a chat open.
        Re-queuing replaces the destination and clears a failure, so it also retries a failed job. Never removes anything.
        """
        job = pipeline.queue_delivery(qb_client, settings, info_hash, kind, folder, rename)
        return f"Delivery queued: {job.name} -> {job.kind or 'auto'} / {job.folder or '(library root)'}."

    @mcp.tool()
    def list_jobs() -> list[pipeline.Job]:
        """List every delivery job with its stage (downloading, subtitled, delivered, failed), failed attempts, last error and last result.
        Use it at the start of a chat to report what the worker did while nobody was watching. A delivered job waits for the user to approve removing the torrent and its data.
        """
        return pipeline.list_jobs()
