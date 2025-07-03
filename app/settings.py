from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_key: str = "demo-secret"
    ha_url: str = "http://localhost:9000"
    request_timeout: int = 8  # seconds

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
