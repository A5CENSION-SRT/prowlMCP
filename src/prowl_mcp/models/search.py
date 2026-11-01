from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Category(BaseModel):
    id: int
    name: str | None = None


class SearchResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    title: str
    indexer: str
    indexer_id: int = Field(alias="indexerId")
    guid: str
    info_hash: str = Field(alias="infoHash")
    size: int
    seeders: int
    leechers: int
    publish_date: datetime = Field(alias="publishDate")
