import secrets
import shlex
import subprocess
import time
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel

from prowl_mcp.config import Settings
from prowl_mcp.services.search import format_size
from prowl_mcp.services.transfer import _ssh_options, _ssh_target, remote_files


class LibraryError(Exception):
    pass


MAX_LISTED = 200


class LibraryFile(BaseModel):
    path: str
    size: str


class LibraryListing(BaseModel):
    kind: Literal["tv", "movies"]
    total: int
    shown: int
    files: list[LibraryFile]


def list_library(settings: Settings, kind: Literal["tv", "movies"]) -> LibraryListing:
    root = settings.tv_library_path if kind == "tv" else settings.movies_library_path
    entries = sorted(remote_files(settings, root).items())
    files = [LibraryFile(path=path, size=format_size(size)) for path, size in entries[:MAX_LISTED]]
    return LibraryListing(kind=kind, total=len(entries), shown=len(files), files=files)


DELETE_CODE_SECONDS = 300
_pending_deletes: dict[str, tuple[str, float]] = {}


class DeletePlan(BaseModel):
    path: str
    files: int
    size: str
    code: str
    expires_in_seconds: int


def _library_root(settings: Settings, kind: Literal["tv", "movies"]) -> str:
    return settings.tv_library_path if kind == "tv" else settings.movies_library_path


def _server_path(settings: Settings, kind: Literal["tv", "movies"], relative: str) -> str:
    parts = PurePosixPath(relative).parts
    if not parts or ".." in parts or relative.startswith("/"):
        raise LibraryError("Give a path inside the library, such as 'Show (2025)/Season 01'.")
    return f"{_library_root(settings, kind)}/{relative}"


def _run_ssh(settings: Settings, script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", *_ssh_options(settings), _ssh_target(settings), script],
        capture_output=True,
        text=True,
        check=False,
    )


def request_delete(settings: Settings, kind: Literal["tv", "movies"], relative: str) -> DeletePlan:
    server_path = _server_path(settings, kind, relative)
    exists = _run_ssh(settings, f"test -e {shlex.quote(server_path)} && echo yes || echo no")
    if exists.stdout.strip() != "yes":
        raise LibraryError(f"Nothing at {relative} on the server.")

    entries = remote_files(settings, server_path)
    code = secrets.token_hex(3)
    _pending_deletes[code] = (server_path, time.monotonic() + DELETE_CODE_SECONDS)
    return DeletePlan(
        path=server_path,
        files=len(entries),
        size=format_size(sum(entries.values())),
        code=code,
        expires_in_seconds=DELETE_CODE_SECONDS,
    )


def confirm_delete(settings: Settings, code: str) -> str:
    entry = _pending_deletes.pop(code, None)
    if entry is None or time.monotonic() > entry[1]:
        raise LibraryError("That code is unknown or expired. Request the delete again.")

    server_path, _ = entry
    result = _run_ssh(settings, f"rm -r -- {shlex.quote(server_path)}")
    if result.returncode != 0:
        raise LibraryError(f"Delete failed: {result.stderr.strip()}")
    return f"Deleted {server_path} on the server."
