"""Trending releases from the indexer, without an outside service.

Runs a fixed set of year and quality searches, groups the results by title, drops titles
already in the Jellyfin library, and ranks what is left by seeders. Seeders are a popularity
proxy: they lag behind brand-new releases and say nothing about what people actually watch.
"""

import re
from datetime import date
from typing import Literal

import httpx
from pydantic import BaseModel

from prowl_mcp.clients.prowlarr import search
from prowl_mcp.config import Settings
from prowl_mcp.models.search import SearchResult
from prowl_mcp.services import library as library_service
from prowl_mcp.services.search import format_size

Kind = Literal["tv", "movies"]

MOVIE_QUERIES = ["{year} 1080p WEB-DL", "{year} 1080p BluRay", "{year} 2160p WEB-DL", "{year} 1080p WEBRip"]
TV_QUERIES = ["{year} S01 1080p WEB-DL", "{year} S01 1080p BluRay", "{year} S02 1080p WEB-DL", "{year} S01 2160p WEB-DL"]

# Everything from the first year or release tag onward is dropped, so "Obsession 2026 1080p WEB-DL" becomes "obsession".
_CUT = re.compile(
    r"\b(19|20)\d{2}\b"
    r"|\bs\d{1,2}(e\d{1,3})?\b"
    r"|\b\d{3,4}p\b"
    r"|\b(web|webrip|webdl|bluray|bdrip|remux|hdr10|hdr|dv|x26[45]|h ?26[45]|hevc|amzn|nf|atmos|ddp?5|aac|mp4|mkv|complete|repack|multi|10bit)\b",
    re.IGNORECASE,
)


class TrendingItem(BaseModel):
    title: str
    size: str
    seeders: int
    quality: str
    info_hash: str


def title_key(raw: str) -> str:
    text = raw.replace("&amp;", "and").replace("&", "and").replace(".", " ").replace("_", " ")
    match = _CUT.search(text)
    if match:
        text = text[: match.start()]
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    return " ".join(text.split())


def library_keys(settings: Settings, kind: Kind) -> set[str]:
    # The top-level folder of each item is its title, such as "Example Show (2020)".
    listing = library_service.list_library(settings, kind)
    keys = set()
    for path in {f.path.split("/")[0] for f in listing.files}:
        key = title_key(path)
        if key:
            keys.add(key)
    return keys


def quality_of(title: str) -> str:
    for tag in ("2160p", "1080p", "720p", "480p"):
        if tag in title:
            return tag
    return "unknown"


def trending(client: httpx.Client, settings: Settings, kind: Kind, library: set[str], limit: int) -> list[SearchResult]:
    templates = MOVIE_QUERIES if kind == "movies" else TV_QUERIES
    years = [date.today().year - back for back in range(settings.trending_years)]

    best: dict[str, SearchResult] = {}
    for year in years:
        for template in templates:
            for result in search(client, template.format(year=year), settings.prowlarr_indexer_ids):
                if result.seeders <= 0:
                    continue
                key = title_key(result.title)
                if not key or key in library:
                    continue
                current = best.get(key)
                if current is None or result.seeders > current.seeders:
                    best[key] = result

    return sorted(best.values(), key=lambda r: r.seeders, reverse=True)[:limit]


def trending_items(client: httpx.Client, settings: Settings, kind: Kind, limit: int) -> tuple[list[SearchResult], list[TrendingItem]]:
    library = library_keys(settings, kind)
    results = trending(client, settings, kind, library, limit)
    items = [
        TrendingItem(
            title=r.title,
            size=format_size(r.size),
            seeders=r.seeders,
            quality=quality_of(r.title),
            info_hash=r.info_hash,
        )
        for r in results
    ]
    return results, items
