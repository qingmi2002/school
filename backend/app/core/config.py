from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "高校分级智能排课系统（多级通用版）"
    APP_VERSION: str = "v1.0.3"
    GITHUB_REPO: str = "qingmi2002/school"
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str = "postgresql+psycopg2://schedule_admin:change_me_in_prod@localhost:5432/smart_schedule"
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    ARCHIVE_LOCAL_ROOT: str = "/mnt/cloud_drive/SmartSchedule_Archive"
    ARCHIVE_STAGING_DIR: str = "/app/archive_staging"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
