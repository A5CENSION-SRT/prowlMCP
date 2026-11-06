"""Command-line entry for the delivery pipeline, so its stages can run outside an MCP tool call.

Claude Code runs these as background tasks and is woken when each one exits. The systemd timer runs `worker`.
Run from the repo folder so the .env is found: uv run python -m prowl_mcp.cli <command> ...

Exit codes: 0 done, 1 failed, 2 stalled, 3 stopped (held), 4 qBittorrent error state.
"""

import argparse
import sys

import httpx

from prowl_mcp.clients import jellyfin, qbittorrent
from prowl_mcp.config import Settings
from prowl_mcp.services import pipeline

WAIT_EXIT_CODES = {"finished": 0, "stalled": 2, "stopped": 3, "error": 4}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prowl", description="prowl-mcp delivery pipeline")
    commands = parser.add_subparsers(dest="command", required=True)

    wait = commands.add_parser("wait", help="block until a download finishes, stalls, is stopped, or errors")
    wait.add_argument("info_hash")
    wait.add_argument("--stall-minutes", type=int)
    wait.add_argument("--poll-seconds", type=int)

    deliver = commands.add_parser("deliver", help="run the queued job now: subtitles, then transfer, checksums and Jellyfin")
    deliver.add_argument("info_hash")
    deliver.add_argument("--until", choices=["subtitled"], help="stop after subtitles, to check them before the transfer")

    queue = commands.add_parser("queue", help="record where a torrent goes once it finishes")
    queue.add_argument("info_hash")
    queue.add_argument("--kind", choices=["tv", "movies"])
    queue.add_argument("--folder")
    queue.add_argument("--no-rename", action="store_true")

    commands.add_parser("jobs", help="list every job and its stage")
    commands.add_parser("worker", help="one pass over open jobs (the systemd timer runs this)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings()
    qb_client, jf_client = qbittorrent.make_client(settings), jellyfin.make_client(settings)
    try:
        return run(args, settings, qb_client, jf_client)
    except pipeline.DELIVERY_ERRORS as exc:
        print(f"Failed: {exc}")
        return 1
    finally:
        qb_client.close()
        jf_client.close()


def run(args: argparse.Namespace, settings: Settings, qb_client: httpx.Client, jf_client: httpx.Client) -> int:
    if args.command == "wait":
        outcome, message = pipeline.wait_for_download(qb_client, settings, args.info_hash, args.stall_minutes or settings.wait_stall_minutes, args.poll_seconds or settings.wait_poll_seconds)
        print(message)
        return WAIT_EXIT_CODES[outcome]

    if args.command == "deliver":
        job = pipeline.deliver(qb_client, jf_client, settings, args.info_hash, args.until)
        print(pipeline.describe(job, settings))
        if job.result:
            print(job.result)
        if job.stage == "delivered":
            print("Next: ask the user before removing the torrent and its local data.")
        return 0 if job.error is None else 1

    if args.command == "queue":
        job = pipeline.queue_delivery(qb_client, settings, args.info_hash, args.kind, args.folder, not args.no_rename)
        print(f"Queued: {job.name} -> {job.kind or 'auto'} / {job.folder or '(library root)'}")
        return 0

    if args.command == "jobs":
        jobs = pipeline.list_jobs()
        for job in jobs:
            print(f"{job.updated}  {job.info_hash[:8]}  {pipeline.describe(job, settings)}")
        if not jobs:
            print("No jobs.")
        return 0

    lines = pipeline.run_pending(settings)
    for line in lines:
        print(line)
    return 1 if any(line.startswith("failed:") for line in lines) else 0


if __name__ == "__main__":
    sys.exit(main())
