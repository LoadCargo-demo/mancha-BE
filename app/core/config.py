"""환경 설정. .env 값을 로드해 앱 전역에서 사용한다."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    cancel_threshold: float = 0.3

    database_url: str = "sqlite:///./loadcargo.db"


settings = Settings()
