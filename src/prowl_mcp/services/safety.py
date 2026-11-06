from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel

from prowl_mcp.models.torrents import TorrentFile
from prowl_mcp.services.search import format_size

EXECUTABLE_EXTENSIONS = {
    "exe", "msi", "msp", "bat", "cmd", "com", "scr", "pif", "cpl", "ps1", "vbs", "vbe",
    "js", "jse", "wsf", "wsh", "hta", "lnk", "reg", "jar", "apk", "dll", "sh", "app", "run",
}  # fmt: skip

ARCHIVE_EXTENSIONS = {"zip", "rar", "7z", "tar", "gz", "iso", "img", "cab"}

LINK_EXTENSIONS = {"url"}

MEDIA_EXTENSIONS = {"mkv", "mp4", "avi", "m4v", "mov", "wmv", "ts", "srt", "sub", "idx", "ass", "nfo", "txt", "jpg", "jpeg", "png"}

Verdict = Literal["ok", "suspicious", "unsafe", "unknown"]


class SafetyReport(BaseModel):
    verdict: Verdict
    file_count: int
    unsafe: list[str]
    warnings: list[str]
    contents: list[str] = []


def _extension(path: PurePosixPath) -> str:
    return path.suffix.lstrip(".").lower()


def render_tree(files: list[TorrentFile]) -> list[str]:
    lines: list[str] = []
    seen_folders: set[tuple[str, ...]] = set()
    for file in sorted(files, key=lambda f: f.name.lower()):
        parts = PurePosixPath(file.name).parts
        for depth in range(len(parts) - 1):
            folder = parts[: depth + 1]
            if folder not in seen_folders:
                seen_folders.add(folder)
                lines.append(f"{'  ' * depth}{parts[depth]}/")
        lines.append(f"{'  ' * (len(parts) - 1)}{parts[-1]} ({format_size(file.size)})")
    return lines


def check_files(files: list[TorrentFile]) -> SafetyReport:
    if not files:
        return SafetyReport(verdict="unknown", file_count=0, unsafe=[], warnings=["No file list yet. The torrent metadata has not arrived."])

    unsafe: list[str] = []
    warnings: list[str] = []
    for file in files:
        path = PurePosixPath(file.name)
        extension = _extension(path)
        suffixes = [s.lstrip(".").lower() for s in path.suffixes]

        if extension in EXECUTABLE_EXTENSIONS:
            if len(suffixes) >= 2 and suffixes[-2] in MEDIA_EXTENSIONS:
                unsafe.append(f"disguised executable: {file.name}")
            else:
                unsafe.append(f"executable file: {file.name}")
        elif extension in ARCHIVE_EXTENSIONS:
            warnings.append(f"archive, contents not checked: {file.name}")
        elif extension in LINK_EXTENSIONS:
            warnings.append(f"link file: {file.name}")

        if any(part.startswith(".") and part not in (".", "..") for part in path.parts):
            warnings.append(f"hidden file or folder: {file.name}")

    if unsafe:
        verdict: Verdict = "unsafe"
    elif warnings:
        verdict = "suspicious"
    else:
        verdict = "ok"

    return SafetyReport(verdict=verdict, file_count=len(files), unsafe=unsafe[:10], warnings=warnings[:10], contents=render_tree(files))
