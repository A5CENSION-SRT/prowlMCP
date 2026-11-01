import httpx
from pydantic import BaseModel

from prowl_mcp.clients.prowlarr import search
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


def find_releases(client: httpx.Client, queries: list[str], releases: dict[str, SearchResult], max_queries: int, per_query: int, limit: int = 20) -> list[ReleaseSummary]:
    cleaned = [q.strip() for q in queries if q.strip()]
    if not 1 <= len(cleaned) <= max_queries:
        raise ValueError(f"Give between 1 and {max_queries} non-empty queries.")

    found: dict[str, SearchResult] = {}
    for query in cleaned:
        seeded = [r for r in search(client, query) if r.seeders > 0]
        best_for_query = sorted(seeded, key=lambda r: r.seeders, reverse=True)[:per_query]
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
