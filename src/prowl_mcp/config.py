from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    prowlarr_url: str
    prowlarr_api_key: SecretStr
    qbittorrent_url: str
    qbittorrent_username: str
    qbittorrent_password: SecretStr
    jellyfin_url: str
    jellyfin_api_key: SecretStr
    ssh_host: str
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_user: str
    ssh_key_path: str
    request_timeout: float
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    max_search_queries: int = Field(default=3, ge=1)
    search_results_per_query: int = Field(default=10, ge=1)
    metadata_timeout_seconds: int = Field(default=60, ge=1)
    resume_check_seconds: int = Field(default=10, ge=1)


settings = Settings()
