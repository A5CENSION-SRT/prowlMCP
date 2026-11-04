import json
import re
import subprocess
from pathlib import Path, PurePosixPath

import httpx

from prowl_mcp.clients import qbittorrent
from prowl_mcp.config import Settings
from prowl_mcp.models.torrents import TorrentFile
from prowl_mcp.services.downloads import find_one
from prowl_mcp.services.transfer import host_path

ENGLISH_TAGS = {"eng", "en", "english"}
VIDEO_EXTENSIONS = {"mkv", "mp4", "m4v", "avi", "mov", "wmv", "ts"}


class SubtitleError(Exception):
    pass


def _subtitle_streams(video: Path) -> list[dict]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-select_streams", "s", str(video)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SubtitleError(f"ffprobe could not read {video.name}: {result.stderr.strip()}")
    return json.loads(result.stdout).get("streams", [])


def has_embedded_english_srt(video: Path) -> bool:
    return any(stream.get("codec_name") == "subrip" and stream.get("tags", {}).get("language", "").lower() in ENGLISH_TAGS for stream in _subtitle_streams(video))


def find_english_srt(files: list[TorrentFile]) -> str | None:
    matches = []
    for file in files:
        if PurePosixPath(file.name).suffix.lower() != ".srt":
            continue
        if set(re.split(r"[^a-z]+", file.name.lower())) & ENGLISH_TAGS:
            matches.append(file.name)
    return min(matches, default=None)


def embed_srt(video: Path, srt: Path) -> None:
    existing = len(_subtitle_streams(video))
    temp = video.with_name(f"{video.stem}.tmp.mkv")
    result = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-i", str(video), "-i", str(srt),
            "-map", "0", "-map", "1",
            "-c", "copy", "-c:s", "srt",
            f"-metadata:s:s:{existing}", "language=eng",
            str(temp),
        ],
        capture_output=True,
        text=True,
        check=False,
    )  # fmt: skip
    if result.returncode != 0:
        temp.unlink(missing_ok=True)
        raise SubtitleError(f"ffmpeg failed for {video.name}: {result.stderr.strip()}")

    streams = _subtitle_streams(temp)
    added = streams[-1] if len(streams) == existing + 1 else None
    if added is None or added.get("codec_name") != "subrip" or added.get("tags", {}).get("language") != "eng":
        temp.unlink(missing_ok=True)
        raise SubtitleError(f"Embedding check failed for {video.name}; the original is unchanged.")

    temp.replace(video)


def process_subtitles(client: httpx.Client, settings: Settings, info_hash: str) -> str:
    qbittorrent.login(client, settings)
    torrent = find_one(client, info_hash)
    if torrent.progress < 1:
        raise SubtitleError(f"{torrent.name} is not finished ({torrent.progress:.0%}).")

    files = qbittorrent.list_files(client, torrent.info_hash)
    videos = [f for f in files if PurePosixPath(f.name).suffix.lower().lstrip(".") in VIDEO_EXTENSIONS]
    if len(videos) != 1:
        raise SubtitleError(f"{torrent.name} has {len(videos)} video files; only single-video torrents are handled for now.")

    base = host_path(torrent.save_path, "", settings)
    video = base / videos[0].name
    if has_embedded_english_srt(video):
        return f"Kept the embedded English subtitles in {video.name}."

    external = find_english_srt(files)
    if external is None:
        return f"No English SRT found for {video.name}; left as it is."

    embed_srt(video, base / external)
    return f"Embedded {external} into {video.name}. The sidecar SRT is kept."
