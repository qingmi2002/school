from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "智能排课系统"
    APP_VERSION: str = "v1.5.3"
    GITHUB_REPO: str = "qingmi2002/school"
    JWT_SECRET: str = "change_me_smart_schedule_jwt_secret_2026"
    JWT_EXPIRE_HOURS: int = 24
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str = "postgresql+psycopg2://schedule_admin:change_me_in_prod@localhost:5432/smart_schedule"
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"
    ARCHIVE_LOCAL_ROOT: str = "/mnt/cloud_drive/SmartSchedule_Archive"
    ARCHIVE_STAGING_DIR: str = "/app/archive_staging"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
