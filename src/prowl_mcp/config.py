from typing import Literal
from pydantic import SecretStr
from pydantic_settings import BaseSettings , SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    prowlarr_url : str
    prowlarr_api_key : SecretStr
    request_timeout : float 
    log_level : Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

settings = Settings()