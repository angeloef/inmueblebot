from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "InmuebleBot"
    DEBUG: bool = True
    SECRET_KEY: str = "change-me-in-production"

    # Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "inmueblebot"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "inmueblebot"

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # WhatsApp / Meta
    META_TOKEN: str = ""
    META_PHONE_NUMBER_ID: str = ""
    META_WEBHOOK_VERIFY_TOKEN: str = "change-me"
    
    # WhatsApp / Meta (alt names)
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: str = "change-me"

    # LLM
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4-turbo-preview"

    # Calendar
    GOOGLE_CALENDAR_ENABLED: bool = False
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # Storage
    S3_BUCKET: str = ""
    S3_REGION: str = "us-east-1"

    # Rate Limiting
    RATE_LIMIT_MESSAGES: int = 20
    RATE_LIMIT_WINDOW: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()