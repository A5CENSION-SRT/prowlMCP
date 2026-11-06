"""Show a desktop notification for each qBittorrent download that has finished.

Runs on the laptop, outside the qBittorrent container, every 5 minutes (see scripts/systemd).
The first run only records what is already finished, so old downloads do not pop up.
"""

import json
import subprocess
from pathlib import Path

from prowl_mcp.clients import qbittorrent
from prowl_mcp.config import Settings

STATE_PATH = Path.home() / ".cache" / "prowl-mcp" / "notified.json"


def main() -> None:
    settings = Settings()
    client = qbittorrent.make_client(settings)
    try:
        qbittorrent.login(client, settings)
        finished = {torrent.info_hash.lower(): torrent.name for torrent in qbittorrent.list_torrents(client) if torrent.progress >= 1}
    finally:
        client.close()

    if STATE_PATH.exists():
        announced = set(json.loads(STATE_PATH.read_text()))
        for info_hash, name in finished.items():
            if info_hash not in announced:
                subprocess.run(["notify-send", "Download finished", name], check=False)
    # Keep only torrents that are finished now, so the state file never grows past the current list.
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(sorted(finished)))


if __name__ == "__main__":
    main()
