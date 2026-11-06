import fcntl
import logging
import threading
from pathlib import Path
from typing import IO

import httpx

from prowl_mcp.clients import qbittorrent
from prowl_mcp.config import Settings
from prowl_mcp.services import subtitles

log = logging.getLogger(__name__)

# The lock frees itself when the holding process exits, even after a crash.
LOCK_PATH = Path.home() / ".cache" / "prowl-mcp" / "runner.lock"


def process_completed(client: httpx.Client, settings: Settings) -> None:
    qbittorrent.login(client, settings)
    for torrent in qbittorrent.list_torrents(client):
        if torrent.progress < 1 or settings.qbittorrent_processed_tag in torrent.tags.split(", "):
            continue
        try:
            outcome = subtitles.process_subtitles(client, settings, torrent.info_hash)
        except Exception:
            log.warning("Could not process %s; will retry at the next check.", torrent.name, exc_info=True)
            continue
        qbittorrent.add_tags(client, torrent.info_hash, settings.qbittorrent_processed_tag)
        log.info("%s: %s", torrent.name, outcome)


class CompletionRunner:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="completion-runner", daemon=True)
        self._lock_file: IO[str] | None = None

    def start(self) -> None:
        # Only one server at a time runs the check, so a torrent is never processed twice.
        if not self._acquire_lock():
            log.warning("Another prowl-mcp server already runs the completion check; this one will not.")
            return
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=30)
        if self._lock_file:
            self._lock_file.close()
            self._lock_file = None

    def _acquire_lock(self) -> bool:
        LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        lock_file = LOCK_PATH.open("w")
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_file.close()
            return False
        self._lock_file = lock_file
        return True

    def _loop(self) -> None:
        client = qbittorrent.make_client(self._settings)
        while not self._stop.is_set():
            try:
                process_completed(client, self._settings)
            except Exception:
                log.exception("Completion check failed; will retry at the next check.")
            self._stop.wait(self._settings.completion_check_seconds)
        client.close()
