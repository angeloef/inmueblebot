"""
Configuración centralizada de la aplicación usando Pydantic Settings.
Carga variables de entorno desde múltiples fuentes:
1. Sistema (Render Dashboard)
2. /etc/secrets/.env (Render Secret Files)
3. /app/.env (alternative)
4. .env local (desarrollo)
"""
from functools import lru_cache
from typing import Optional, Union, List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import os
import logging

logger = logging.getLogger(__name__)


def _get_env_files() -> List[str]:
    """
    Returns list of .env file paths to check.
    Priority (first found is used):
    1. /etc/secrets/.env (Render Secret Files - PRIMARY for production)
    2. /app/.env (alternative Render location)
    3. .env (local development)
    """
    possible_paths = [
        "/etc/secrets/.env",  # Render Secret Files mount here
        "/app/.env",          # Alternative location
        ".env",               # Local development
    ]
    
    found_paths = []
    for path in possible_paths:
        if os.path.isfile(path):
            found_paths.append(path)
            logger.info(f"✅ Found .env at: {path}")
    
    if found_paths:
        logger.info(f"📄 Using .env from: {found_paths[0]}")
        return found_paths
    else:
        logger.info("📄 No .env file found - using system environment variables only")
        return []


def _is_render() -> bool:
    """Check if running on Render.com"""
    return bool(os.environ.get("RENDER"))


class Settings(BaseSettings):
    """
    Configuración de la aplicación.
    
    Priority order (highest to lowest):
    1. System environment variables (Render Dashboard)
    2. .env files (Render Secret Files or local)
    3. Default values in code
    
    On Render: Variables come from:
    - Environment Variables (Dashboard)
    - Secret Files (.env mounted at /etc/secrets/.env)
    """
    env_file: Union[str, List[str], None] = _get_env_files() if _get_env_files() else None
    
    model_config = SettingsConfigDict(
        env_file=env_file,
        env_file_encoding="utf-8",
        env_file_priority=0,  # System env vars take priority over .env file
        extra="ignore",
        case_sensitive=False,
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
    
    # Detect source of key variables
    def get_var_source(key: str, default: str = "NOT SET") -> str:
        """Check if variable came from system env or .env file"""
        if key in os.environ:
            return "SYSTEM_ENV"
        # Check if it's set to a non-default value
        field_value = getattr(settings, key.lower(), None)
        if field_value and field_value != default:
            return ".env_FILE"
        return "DEFAULT"
    
    # Enhanced startup logging with source tracking
    logger.info("=" * 50)
    logger.info("🚀 InmuebleBot Configuration")
    logger.info("=" * 50)
    
    # Platform detection
    if _is_render():
        logger.info("🌐 Platform: RENDER.COM")
    else:
        logger.info("💻 Platform: LOCAL DEVELOPMENT")
    
    # Env file status
    env_files = _get_env_files()
    if env_files:
        logger.info(f"📄 .env file: {env_files[0]}")
    else:
        logger.info("📄 .env file: NONE (using system env only)")
    
    logger.info("-" * 50)
    logger.info(f"ENVIRONMENT: {settings.ENVIRONMENT} (source: {get_var_source('ENVIRONMENT', 'development')})")
    logger.info(f"DEBUG: {settings.DEBUG}")
    logger.info(f"🗄️  DATABASE_URL: {'***SET***' if settings.DATABASE_URL and 'postgres' in settings.DATABASE_URL else 'NOT SET'}")
    logger.info(f"📡 REDIS_URL: {settings.resolve_redis_url()[:30]}... (resolved)")
    
    # LLM Providers status
    _gemini = "✅ SET" if settings.GEMINI_API_KEY else "❌ NOT SET"
    _minimax = "✅ SET" if settings.MINIMAX_API_KEY else "❌ NOT SET"
    _openrouter = "✅ SET" if settings.OPENROUTER_API_KEY else "❌ NOT SET"
    logger.info(f"🤖 LLM Providers:")
    logger.info(f"   - Gemini: {settings.GEMINI_MODEL} [{_gemini}]")
    logger.info(f"   - MiniMax: [{_minimax}]")
    logger.info(f"   - OpenRouter: [{_openrouter}]")
    
    # WhatsApp status
    _wa_meta = "✅ SET" if settings.WHATSAPP_PHONE_NUMBER_ID and settings.WHATSAPP_ACCESS_TOKEN else "❌ NOT SET"
    _wa_twilio = "✅ SET" if settings.TWILIO_ACCOUNT_SID else "❌ NOT SET"
    logger.info(f"💬 WhatsApp:")
    logger.info(f"   - Meta Cloud API: [{_wa_meta}]")
    logger.info(f"   - Twilio: [{_wa_twilio}]")
    
    # Admin
    _admin = "✅ SET" if settings.ADMIN_API_KEY and settings.ADMIN_API_KEY != "admin-secret-key" else "⚠️ DEFAULT"
    logger.info(f"🔑 ADMIN_API_KEY: [{_admin}]")
    
    logger.info("=" * 50)
    
    return settings