"""
Configuración centralizada de la aplicación usando Pydantic Settings.
Carga variables de entorno desde sistema (Render) o .env (local).
"""
from functools import lru_cache
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import os
import logging

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Configuración de la aplicación.
    
    Priority order:
    1. Environment variables (system) - highest priority
    2. .env file (for local development only)
    3. Default values
    
    On Render: Set all critical variables in Dashboard Environment Variables.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_file_priority=0,  # Environment variables take priority over .env file
        extra="ignore",
    )

    # === Server ===
    PORT: int = Field(default=8000, description="Server port")
    HOST: str = Field(default="0.0.0.0", description="Server host")

    # === Configuración General ===
    ENVIRONMENT: str = Field(default="development", description="Entorno de ejecución")
    DEBUG: bool = Field(default=True, description="Modo debug")
    SECRET_KEY: str = Field(default="change-me-in-production", description="Clave secreta para JWT/sessions")

    # === Base de Datos ===
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@db:5432/inmueblebot",
        description="URL de conexión a PostgreSQL"
    )

    # === Redis ===
    # Auto-detect: uses redis://redis:6379/0 for Docker, redis://localhost:6379/0 for local
    # Override by setting REDIS_URL explicitly in .env
    REDIS_URL: Optional[str] = Field(
        default=None,
        description="URL de conexión a Redis (auto-detected if not set)"
    )

    USE_LOCAL_REDIS: bool = Field(
        default=False,
        description="Set to True to use localhost instead of Docker redis service"
    )

    # === MiniMax API (Primary LLM) ===
    MINIMAX_API_KEY: Optional[str] = Field(default=None, description="API key de MiniMax via OpenRouter")
    MINIMAX_MODEL: str = Field(default="minimax/minimax-m2.5:free", description="Modelo de MiniMax (primary)")

    # === Google Gemini API (Backup LLM) ===
    GEMINI_API_KEY: Optional[str] = Field(default=None, description="API key de Google Gemini")
    GEMINI_MODEL: str = Field(default="gemini-2.5-flash", description="Modelo de Gemini a usar")

    # === OpenRouter API (Fallback LLM - GPT-Oss) ===
    OPENROUTER_API_KEY: Optional[str] = Field(default=None, description="API key de OpenRouter")
    OPENROUTER_MODEL: str = Field(default="openai/gpt-oss-120b:free", description="Modelo de OpenRouter (fallback)")

    # === LLM Configuration ===
    LLM_TIMEOUT_SECONDS: int = Field(default=25, description="Timeout para llamadas al LLM")
    LLM_MAX_RETRIES: int = Field(default=2, description="Máximo de reintentos por proveedor")
    LLM_TEMPERATURE: float = Field(default=0.5, description="Temperatura por defecto para LLM")
    LLM_MAX_TOKENS: int = Field(default=1000, description="Máximo de tokens en respuesta")

    # === WhatsApp (Twilio) ===
    TWILIO_ACCOUNT_SID: Optional[str] = Field(default=None, description="Twilio Account SID")
    TWILIO_AUTH_TOKEN: Optional[str] = Field(default=None, description="Twilio Auth Token")
    TWILIO_WHATSAPP_NUMBER: Optional[str] = Field(default=None, description="Twilio WhatsApp number (e.g. +14155238886)")
    TWILIO_WEBHOOK_VERIFY_TOKEN: Optional[str] = Field(default=None, description="Optional webhook verification")
    
    # === WhatsApp (Meta) - Legacy ===
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = Field(default=None, description="Phone Number ID de Meta")
    WHATSAPP_ACCESS_TOKEN: Optional[str] = Field(default=None, description="Access Token de Meta")
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: str = Field(
        default="change-me",
        description="Token para verificar webhook de Meta"
    )

    # === Configuración de la aplicación ===
    API_PREFIX: str = Field(default="/api", description="Prefijo para rutas API")
    CORS_ORIGINS: list[str] = Field(default=["*"], description="Orígenes permitidos para CORS")

    # === Rate Limiting ===
    RATE_LIMIT_MESSAGES: int = Field(default=20, description="Máximo de mensajes por ventana")
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, description="Ventana de tiempo en segundos")

    # === Admin ===
    ADMIN_API_KEY: str = Field(default="admin-secret-key", description="API key para rutas de admin")

    # === Google Calendar ===
    GOOGLE_CREDENTIALS_PATH: Optional[str] = Field(
        default=None,
        description="Path to Google service account JSON credentials file"
    )
    GOOGLE_TOKEN_PATH: Optional[str] = Field(
        default="/app/credentials/token.json",
        description="Path to Google OAuth token file (for user-authenticated calendar)"
    )
    GOOGLE_CALENDAR_ID: str = Field(
        default="primary",
        description="Google Calendar ID to use for appointments"
    )

    @property
    def is_production(self) -> bool:
        """Indica si estamos en entorno de producción"""
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Indica si estamos en entorno de desarrollo"""
        return self.ENVIRONMENT.lower() == "development"

    def resolve_redis_url(self) -> str:
        """
        Resuelve la URL de Redis basándose en el entorno.
        - Si REDIS_URL está configurado, úsalo
        - Si USE_LOCAL_REDIS=True, usa localhost
        - Por defecto (Docker), usa el servicio 'redis'
        """
        if self.REDIS_URL:
            return self.REDIS_URL
        if self.USE_LOCAL_REDIS:
            return "redis://localhost:6379/0"
        return "redis://redis:6379/0"

    @property
    def resolved_redis_url(self) -> str:
        """Alias para resolve_redis_url() como propiedad."""
        return self.resolve_redis_url()


@lru_cache
def get_settings() -> Settings:
    """
    Obtiene la configuración de forma cached.
    Incluye logging de las variables críticas al iniciar.
    """
    settings = Settings()
    
    # Log de variables cargadas en startup
    log_level = logging.INFO
    logger.log(log_level, "=== Configuration Loaded ===")
    logger.log(log_level, f"ENVIRONMENT: {settings.ENVIRONMENT}")
    logger.log(log_level, f"DEBUG: {settings.DEBUG}")
    logger.log(log_level, f"DATABASE_URL: {'***' if settings.DATABASE_URL else 'NOT SET'}")
    logger.log(log_level, f"REDIS_URL: {settings.resolve_redis_url()[:30]}... (resolved)")
    logger.log(log_level, f"GEMINI_API_KEY: {'***SET***' if settings.GEMINI_API_KEY else 'NOT SET'}")
    logger.log(log_level, f"MINIMAX_API_KEY: {'***SET***' if settings.MINIMAX_API_KEY else 'NOT SET'}")
    logger.log(log_level, f"WHATSAPP_PHONE_NUMBER_ID: {'***SET***' if settings.WHATSAPP_PHONE_NUMBER_ID else 'NOT SET'}")
    logger.log(log_level, f"WHATSAPP_ACCESS_TOKEN: {'***SET***' if settings.WHATSAPP_ACCESS_TOKEN else 'NOT SET'}")
    logger.log(log_level, f"ADMIN_API_KEY: {'***SET***' if settings.ADMIN_API_KEY else 'NOT SET'}")
    logger.log(log_level, "===========================")
    
    return settings