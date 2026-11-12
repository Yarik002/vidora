from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (see .env.example)."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    app_name: str = "Vidora"
    environment: str = "production"
    site_address: str = "https://"

    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "vidora"
    postgres_user: str = "vidora"
    postgres_password: str = Field(default="", repr=False)

    # Redis (queue for arq, rate limits, view dedup)
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = Field(default="", repr=False)

    # S3 / MinIO
    s3_endpoint: str = "http://minio:9000"
    s3_region: str = "us-east-1"
    s3_access_key: str = Field(default="", repr=False)
    s3_secret_key: str = Field(default="", repr=False)
    bucket_raw: str = "vidora-raw"
    bucket_media: str = "vidora-media"
    # Public path where Caddy proxies MinIO (same origin as the app, see Caddyfile).
    storage_public_prefix: str = "/storage"

    # Auth
    jwt_secret: str = Field(default="", repr=False)
    access_ttl_minutes: int = 15
    refresh_ttl_days: int = 30
    cookie_secure: bool = True

    # Uploads and processing
    max_upload_mb: int = 1024
    upload_part_mb: int = 10
    max_video_duration_sec: int = 3 * 60 * 60
    upload_url_ttl_sec: int = 3600
    playback_url_ttl_sec: int = 900
    image_url_ttl_sec: int = 3600

    # Rate limits (requests per window)
    login_rate_limit: int = 10
    register_rate_limit: int = 5
    rate_limit_window_sec: int = 60

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/0"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def upload_part_bytes(self) -> int:
        return self.upload_part_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
