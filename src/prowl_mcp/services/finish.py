from typing import Literal

import httpx

from prowl_mcp.config import Settings
from prowl_mcp.services import subtitles, transfer

Kind = Literal["tv", "movies"]


def finish_torrent(qb_client: httpx.Client, jf_client: httpx.Client, settings: Settings, info_hash: str, kind: Kind | None = None, folder: str | None = None, rename: bool = True) -> str:
    # Subtitles first, so the transfer copies the final file. A subtitle failure stops here, before anything is copied.
    subtitle_report = subtitles.process_subtitles(qb_client, settings, info_hash)
    transfer_report = transfer.transfer_torrent(qb_client, jf_client, settings, info_hash, kind, folder, rename)
    return f"Subtitles:\n{subtitle_report}\n\n{transfer_report}\n\nNext: ask the user before removing the torrent and its data. Only after they approve, call remove_torrent with delete_files=true."
