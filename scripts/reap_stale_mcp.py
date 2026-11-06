#!/usr/bin/env python3
"""Stop prowl-mcp servers whose Claude session has ended.

A server counts as orphaned when none of its ancestor processes is Claude. Servers that
belong to a session that is still open (even an idle one) are left alone.
Use --dry-run to list what would be stopped.
"""
import os
import signal
import sys
from pathlib import Path

SERVER_MARKER = "-m prowl_mcp.server"


def cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
    except OSError:
        return ""


def parent(pid: int) -> int:
    try:
        # The command name is in parentheses and may contain spaces, so split after the last ")".
        return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return 0


def has_claude_ancestor(pid: int) -> bool:
    seen: set[int] = set()
    pid = parent(pid)
    while pid > 1 and pid not in seen:
        seen.add(pid)
        if "claude" in cmdline(pid).lower():
            return True
        pid = parent(pid)
    return False


def find_orphans() -> list[tuple[int, str]]:
    me = os.getpid()
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == me:
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
        except OSError:
            continue
        command = cmdline(pid)
        if SERVER_MARKER in command and not has_claude_ancestor(pid):
            found.append((pid, command))
    return found


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    orphans = find_orphans()
    for pid, command in orphans:
        if not dry_run:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
        print(f"{'would stop' if dry_run else 'stopped'} orphaned prowl-mcp server {pid}: {command}")


if __name__ == "__main__":
    main()
