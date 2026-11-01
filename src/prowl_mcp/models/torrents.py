from pydantic import BaseModel, ConfigDict, Field


class TorrentInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    info_hash: str = Field(alias="hash")
    name: str
    state: str
    size: int
    progress: float
    eta: int
    dlspeed: int
    num_seeds: int
    save_path: str
    tags: str
