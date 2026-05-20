from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "URL Shortener API"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/url_shortener"
    short_code_length: int = 6
    short_code_alphabet: str = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "url_shortener"
    postgres_port: int = 5432

    jwt_key: str = "8Zq3nVxP9mL2kR5tY7wE1aC4bD6fG8hJ2kL4mN6pQ8rS"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()