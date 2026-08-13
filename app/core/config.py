"""환경 설정. .env 값을 로드해 앱 전역에서 사용한다."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    gemini_tts_model: str = "gemini-3.1-flash-tts-preview"
    cancel_threshold: float = 0.3
    rebuild_profit_threshold: int = 30000
    rebuild_return_threshold_min: int = 30
    rag_similarity_threshold: float = 0.5

    database_url: str = "sqlite:///./loadcargo.db"


settings = Settings()
