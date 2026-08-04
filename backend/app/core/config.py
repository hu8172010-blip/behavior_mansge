from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "behavior-management-api"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "mysql+aiomysql://app:app_password@localhost:3306/behavior_mansge"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:5173"
    jwt_secret: str = "dev-secret-key-change-in-production"
    jwt_expire_hours: int = 24
    anomaly_tracker_url: str = "http://127.0.0.1:8080"
    repair_restore_status: str = "ONLINE"
    repair_restore_health_score: int = 100
    backup_dir: str = "data_backups"
    mysql_bin_dir: str = "D:/MySQL/MySQL Server 8.0/bin"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
