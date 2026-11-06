import fcntl
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel

from prowl_mcp.clients import jellyfin, qbittorrent
from prowl_mcp.config import Settings
from prowl_mcp.services import subtitles, transfer
from prowl_mcp.services.downloads import find_one

CACHE_PATH = Path.home() / ".cache" / "prowl-mcp"
JOBS_PATH = CACHE_PATH / "jobs"
# The old in-server runner used this lock too, so a session still running old code and this pipeline never overlap.
LOCK_PATH = CACHE_PATH / "runner.lock"

Stage = Literal["downloading", "subtitled", "delivered", "failed"]
OPEN_STAGES = ("downloading", "subtitled")


class PipelineError(Exception):
    pass


# Everything a stage can raise that a retry may fix. Anything else is a bug and should surface.
DELIVERY_ERRORS = (PipelineError, subtitles.SubtitleError, transfer.TransferError, qbittorrent.QBittorrentError, jellyfin.JellyfinError, httpx.HTTPError, ValueError, OSError)


class Job(BaseModel):
    """One torrent on its way to the Jellyfin server. The job file on disk is the state, so any worker can continue it."""

    info_hash: str
    name: str
    kind: transfer.Kind | None = None
    folder: str | None = None
    rename: bool = True
    stage: Stage = "downloading"
    attempts: int = 0
    error: str | None = None
    result: str | None = None
    updated: str = ""


def job_path(info_hash: str) -> Path:
    return JOBS_PATH / f"{info_hash.lower()}.json"


def load_job(info_hash: str) -> Job | None:
    path = job_path(info_hash)
    return Job.model_validate_json(path.read_text()) if path.exists() else None


def save_job(job: Job) -> None:
    job.updated = datetime.now(UTC).isoformat(timespec="seconds")
    JOBS_PATH.mkdir(parents=True, exist_ok=True)
    # Write then rename, so a crash never leaves half a job file.
    temp = job_path(job.info_hash).with_suffix(".tmp")
    temp.write_text(job.model_dump_json(indent=2))
    temp.replace(job_path(job.info_hash))


def list_jobs() -> list[Job]:
    if not JOBS_PATH.exists():
        return []
    return sorted((Job.model_validate_json(path.read_text()) for path in JOBS_PATH.glob("*.json")), key=lambda job: job.updated)


def drop_job(info_hash: str) -> None:
    job_path(info_hash).unlink(missing_ok=True)


def queue_delivery(client: httpx.Client, settings: Settings, info_hash: str, kind: transfer.Kind | None, folder: str | None, rename: bool = True) -> Job:
    """Record where a torrent goes once it finishes. Queuing it again replaces the old record and clears a failure."""
    qbittorrent.login(client, settings)
    torrent = find_one(client, info_hash)
    transfer.resolve_destination(settings, kind, folder, torrent.name)
    job = Job(info_hash=torrent.info_hash.lower(), name=torrent.name, kind=kind, folder=folder, rename=rename)
    save_job(job)
    return job


@contextmanager
def pipeline_lock(wait_seconds: int) -> Iterator[None]:
    """Hold the one pipeline lock, waiting up to wait_seconds for it. It frees itself when this process exits, even after a crash."""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a") as handle:
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise PipelineError(f"Another prowl-mcp process holds {LOCK_PATH}. An open session still running old server code holds it until it closes; check with: lsof {LOCK_PATH}") from None
                time.sleep(5)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def notify(title: str, body: str) -> None:
    try:
        subprocess.run(["notify-send", title, body], check=False, capture_output=True)
    except FileNotFoundError:
        pass


def advance(qb_client: httpx.Client, jf_client: httpx.Client, settings: Settings, job: Job, until: Stage | None = None) -> Job:
    """Run the remaining stages of one finished job. Every stage is safe to run again, so a retry continues where the last run stopped."""
    try:
        qbittorrent.login(qb_client, settings)
        torrent = find_one(qb_client, job.info_hash)
        if torrent.progress < 1:
            return job
        if job.stage == "downloading":
            # Subtitles first, so the transfer copies the final file.
            job.result = subtitles.process_subtitles(qb_client, settings, job.info_hash)
            job.stage = "subtitled"
            save_job(job)
            if until == "subtitled":
                return job
        if job.stage == "subtitled":
            job.result = transfer.transfer_torrent(qb_client, jf_client, settings, job.info_hash, job.kind, job.folder, job.rename)
            job.stage = "delivered"
            job.attempts, job.error = 0, None
            notify("Delivered to Jellyfin", job.name)
    except DELIVERY_ERRORS as exc:
        job.attempts += 1
        job.error = str(exc)
        if job.attempts >= settings.delivery_max_attempts:
            job.stage = "failed"
            notify("Delivery failed", f"{job.name}: {exc}")
    save_job(job)
    return job


def deliver(qb_client: httpx.Client, jf_client: httpx.Client, settings: Settings, info_hash: str, until: Stage | None = None) -> Job:
    """Run one job now, on request. A failed job is retried from where it stopped."""
    with pipeline_lock(settings.pipeline_lock_wait_seconds):
        job = load_job(info_hash)
        if job is None:
            raise PipelineError(f"No delivery is queued for {info_hash}. Queue it first with a kind and folder.")
        if job.stage == "failed":
            # Starting over is safe: subtitles keep episodes already done, and the copy skips files already on the server.
            job.stage, job.attempts = "downloading", 0
        if job.stage == "delivered" or (until == "subtitled" and job.stage == "subtitled"):
            return job
        torrent_progress = _progress(qb_client, settings, job.info_hash)
        if torrent_progress < 1:
            raise PipelineError(f"{job.name} is not finished ({torrent_progress:.0%}).")
        return advance(qb_client, jf_client, settings, job, until)


def _progress(client: httpx.Client, settings: Settings, info_hash: str) -> float:
    qbittorrent.login(client, settings)
    return find_one(client, info_hash).progress


def run_pending(settings: Settings) -> list[str]:
    """One worker pass: advance every open job whose download has finished. Skips the pass if another process holds the lock."""
    try:
        with pipeline_lock(0):
            jobs = [job for job in list_jobs() if job.stage in OPEN_STAGES]
            if not jobs:
                return []
            qb_client, jf_client = qbittorrent.make_client(settings), jellyfin.make_client(settings)
            try:
                return [describe(advance(qb_client, jf_client, settings, job), settings) for job in jobs]
            finally:
                qb_client.close()
                jf_client.close()
    except PipelineError as exc:
        return [f"Skipped this pass: {exc}"]


def describe(job: Job, settings: Settings) -> str:
    line = f"{job.stage}: {job.name}"
    if job.error:
        line += f" (failed attempt {job.attempts} of {settings.delivery_max_attempts}): {job.error}"
    return line


WaitOutcome = Literal["finished", "stalled", "stopped", "error"]


def wait_for_download(client: httpx.Client, settings: Settings, info_hash: str, stall_minutes: int, poll_seconds: int) -> tuple[WaitOutcome, str]:
    """Block until the download finishes, stalls, is stopped, or errors. Polls qBittorrent only, so waiting costs nothing else."""
    last_progress, last_change = -1.0, time.monotonic()
    while True:
        try:
            qbittorrent.login(client, settings)
            torrent = find_one(client, info_hash)
        except qbittorrent.QBittorrentError:
            # qBittorrent may be restarting; count it as no progress and try again.
            torrent = None
        if torrent is not None:
            if torrent.progress >= 1:
                return "finished", f"Finished: {torrent.name}"
            if torrent.state in ("error", "missingFiles"):
                return "error", f"qBittorrent reports {torrent.state} for {torrent.name} at {torrent.progress:.0%}."
            if torrent.state == "stoppedDL":
                return "stopped", f"Stopped at {torrent.progress:.0%}: {torrent.name}. It needs resume_torrent to continue."
            if torrent.progress > last_progress:
                last_progress, last_change = torrent.progress, time.monotonic()
        if time.monotonic() - last_change >= stall_minutes * 60:
            name = torrent.name if torrent else info_hash
            return "stalled", f"No progress for {stall_minutes} minutes: {name} at {max(last_progress, 0):.0%}."
        time.sleep(poll_seconds)
