import httpx
from pydantic import BaseModel

from prowl_mcp.clients.prowlarr import search
from prowl_mcp.config import Settings
from prowl_mcp.models.search import SearchResult


class ReleaseSummary(BaseModel):
    title: str
    size: str
    seeders: int
    info_hash: str


def format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def find_releases(client: httpx.Client, queries: list[str], releases: dict[str, SearchResult], settings: Settings, limit: int) -> list[ReleaseSummary]:
    cleaned = [q.strip() for q in queries if q.strip()]
    if not 1 <= len(cleaned) <= settings.max_search_queries:
        raise ValueError(f"Give between 1 and {settings.max_search_queries} non-empty queries.")

    found: dict[str, SearchResult] = {}
    for query in cleaned:
        seeded = [r for r in search(client, query, settings.prowlarr_indexer_ids) if r.seeders > 0]
        best_for_query = sorted(seeded, key=lambda r: r.seeders, reverse=True)[: settings.search_results_per_query]
        for r in best_for_query:
            found.setdefault(r.info_hash.upper(), r)

    ranked = sorted(found.values(), key=lambda r: r.seeders, reverse=True)
    results = ranked[:limit]
    for r in results:
        releases[r.info_hash.upper()] = r
    return [
        ReleaseSummary(
            title=r.title,
            size=format_size(r.size),
            seeders=r.seeders,
            info_hash=r.info_hash,
        )
        for r in results
    ]
