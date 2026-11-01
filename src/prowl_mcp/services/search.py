import httpx
from pydantic import BaseModel

from prowl_mcp.clients.prowlarr import search

class ReleaseSummary(BaseModel):
    title: str
    size: str
    seeders: int
    leechers: int
    indexer: str
    info_hash: str


def format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"



def find_releases(client: httpx.Client, query: str, limit: int = 20) -> list[ReleaseSummary]:
    results = sorted(search(client, query), key=lambda r: r.seeders, reverse=True)
    return [
        ReleaseSummary(
            title=r.title,
            size=format_size(r.size),
            seeders=r.seeders,
            leechers=r.leechers,
            indexer=r.indexer,
            info_hash=r.info_hash,
        )
        for r in results[:limit]
    ]
