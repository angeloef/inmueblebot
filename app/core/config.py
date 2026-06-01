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

    # === TTL Configuration ===
    WORKING_MEMORY_TTL: int = Field(default=86400, description="TTL for working memory (Redis)")
    CONTEXT_TTL: int = Field(default=86400, description="TTL for user context in Redis (24h)")
    STATE_TTL: int = Field(default=86400, description="TTL for conversation state in Redis (24h)")
    PERSONA_TTL: int = Field(default=7776000, description="TTL for user persona in Redis (90 days)")
    EPISODIC_TTL: int = Field(default=7776000, description="TTL for episodic memory in Redis (90 days)")

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

    # === LLM Provider Selection ===
    LLM_PROVIDER: str = Field(
        default="openai",
        description="Proveedor LLM activo: openai | deepseek | openrouter",
    )

    # === OpenAI ===
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="API key de OpenAI")
    OPENAI_MODEL: str = Field(default="gpt-4o-mini", description="Modelo de OpenAI a usar")

    # === DeepSeek ===
    DEEPSEEK_API_KEY: Optional[str] = Field(default=None, description="API key de DeepSeek")
    DEEPSEEK_MODEL: str = Field(
        default="deepseek-chat",
        description="Modelo DeepSeek: deepseek-chat (V3) | deepseek-reasoner (R1)",
    )

    # === OpenRouter ===
    OPENROUTER_API_KEY: Optional[str] = Field(default=None, description="API key de OpenRouter")
    OPENROUTER_MODEL: str = Field(
        default="deepseek/deepseek-chat",
        description="Modelo a usar vía OpenRouter (ej: deepseek/deepseek-chat, openai/gpt-4o-mini)",
    )

    # === LLM Configuration ===
    LLM_TIMEOUT_SECONDS: int = Field(default=25, description="Timeout para llamadas al LLM")
    LLM_MAX_RETRIES: int = Field(default=2, description="Máximo de reintentos por proveedor")
    LLM_TEMPERATURE: float = Field(default=0.5, description="Temperatura por defecto para LLM")
    LLM_MAX_TOKENS: int = Field(default=1000, description="Máximo de tokens en respuesta")

    # === Session config ===
    SESSION_INACTIVITY_TIMEOUT: int = Field(default=43200, description="Session inactivity timeout in seconds (12 hours)")

    # === History window ===
    HISTORY_WINDOW: int = Field(default=8, description="Number of recent messages to keep in history")

    # === LLM Tiering ===
    LLM_TIERING_ENABLED: bool = Field(default=False, description="Enable role-based model tiering (strong/fast)")
    LLM_MODEL_REASONING: Optional[str] = Field(default=None, description="Strong model for tool decisions (overrides OPENAI_MODEL_REASONING when set)")
    LLM_MODEL_CLASSIFY: Optional[str] = Field(default=None, description="Fast model for intent classification (overrides OPENAI_MODEL_FAST when set)")
    LLM_MODEL_SYNTH: Optional[str] = Field(default=None, description="Fast model for final text synthesis (overrides OPENAI_MODEL_FAST when set)")

    # === Default tiered models (OpenAI only) ===
    OPENAI_MODEL_REASONING: str = Field(default="gpt-5.5", description="Strong model for reasoning/tool decisions")
    OPENAI_MODEL_FAST: str = Field(default="gpt-5.4-mini", description="Fast model for classification and synthesis")

    # === Directive engine ===
    USE_DIRECTIVE_ENGINE: bool = Field(default=True, description="Use directive-based context engine instead of legacy imperative stacking")

    # === Modular Prompts (Feature Flag) ===
    USE_MODULAR_PROMPTS: bool = Field(
        default=True,
        description="Usar prompts modulares por capacidad. False = usa SYSTEM_PROMPT monolito."
    )

    # === WhatsApp (Twilio) ===
    TWILIO_ACCOUNT_SID: Optional[str] = Field(default=None, description="Twilio Account SID")
    TWILIO_AUTH_TOKEN: Optional[str] = Field(default=None, description="Twilio Auth Token")
    TWILIO_WHATSAPP_NUMBER: Optional[str] = Field(default=None, description="Twilio WhatsApp number (e.g. +14155238886)")
    TWILIO_WEBHOOK_VERIFY_TOKEN: Optional[str] = Field(default=None, description="Optional webhook verification")
    
    # === WhatsApp (Meta) ===
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = Field(default=None, description="Phone Number ID de Meta")
    WHATSAPP_ACCESS_TOKEN: Optional[str] = Field(default=None, description="Access Token de Meta")
    WHATSAPP_GRAPH_API_VERSION: str = Field(
        default="v25.0",
        description="Versión de la Graph API para llamadas salientes (v18.0 está sunset). "
                    "Alineada con la versión del webhook 'messages' en el App Dashboard de Meta. Override por env.",
    )
    WHATSAPP_SEND_BY_BSUID: bool = Field(
        default=True,
        description="BSUID-first sending: si hay BSUID, el mensaje se direcciona al BSUID; el "
                    "cliente cae automáticamente al teléfono si Meta rechaza el envío por BSUID "
                    "(habilitado ~junio 2026). Seguro por el fallback. Poné False para evitar el "
                    "intento-fallido+reintento extra por mensaje mientras el envío por BSUID no esté activo.",
    )
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: str = Field(
        default="change-me",
        description="Token para verificar webhook de Meta"
    )
    AGENT_WHATSAPP_NUMBER: Optional[str] = Field(default=None, description="Número WhatsApp del agente humano para handoffs")

    # === Identidad del negocio ===
    COMPANY_NAME: str = Field(default="la inmobiliaria", description="Nombre de la inmobiliaria (usado en saludo inicial y mensajes de alcance)")
    INMOBILIARIA_NAME: str = Field(default="Inmobiliaria Oberá", description="Nombre completo de la inmobiliaria (usado en greetings)")

    # === v2.0 Router Feature Flags (ChatbotSerio merge) ===
    USE_V2_ROUTER: bool = Field(default=False, description="Usar el nuevo router S1+S2 de ChatbotSerio. False = router v1.x")
    S1_CONFIDENCE_THRESHOLD: float = Field(default=0.70, description="Umbral de confianza para aceptar match de S1 (regex)")
    MAX_SCHEDULING_LOOPS: int = Field(default=5, description="Máximo de turnos en bucle de scheduling antes de escape")
    MEMORY_TIERS_ENABLED: bool = Field(default=True, description="Activar memoria episódica/semántica para cross-session context")

    # === Configuración de la aplicación ===
    API_PREFIX: str = Field(default="/api", description="Prefijo para rutas API")
    CORS_ORIGINS: list[str] = Field(default=["*"], description="Orígenes permitidos para CORS")

    # === Public API URL ===
    API_BASE_URL: str = Field(
        default_factory=lambda: (
            os.environ.get("RENDER_EXTERNAL_URL") or "http://localhost:8000"
        ),
        description="Public base URL for this API (e.g. https://inmueblebot-api.onrender.com)"
    )

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
    GOOGLE_TOKEN_JSON: Optional[str] = Field(
        default=None,
        description="Google OAuth token as JSON string (Render secret file or env var)"
    )
    GOOGLE_CREDENTIALS_JSON: Optional[str] = Field(
        default=None,
        description="Google client secrets as JSON string (Render secret file or env var)"
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
    def resolved_database_url(self) -> str:
        """
        Resuelve la URL de la base de datos.
        - Agrega +asyncpg si usa postgresql:// (Render proporciona postgresql://)
        - Mantiene postgresql+asyncpg:// si ya lo tiene
        - Reemplaza ?sslmode= por ?ssl= (asyncpg usa ?ssl=, psycopg2 usa ?sslmode=)
        """
        if not self.DATABASE_URL:
            return ""
        url = self.DATABASE_URL.strip()
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        url = url.replace("?sslmode=require", "?ssl=require")
        url = url.replace("&sslmode=require", "&ssl=require")
        return url


@lru_cache
def get_settings() -> Settings:
    """
    Obtiene la configuración de forma cached.
    Incluye logging de las variables críticas al iniciar.
    """
    settings = Settings()

    def get_var_source(key: str, default: str = "NOT SET") -> str:
        if key in os.environ:
            return "SYSTEM_ENV"
        field_value = getattr(settings, key.lower(), None)
        if field_value and field_value != default:
            return ".env_FILE"
        return "DEFAULT"

    logger.info("=" * 50)
    logger.info("InmuebleBot Configuration")
    logger.info("=" * 50)

    if _is_render():
        logger.info("Platform: RENDER.COM")
    else:
        logger.info("Platform: LOCAL DEVELOPMENT")

    env_files = _get_env_files()
    if env_files:
        logger.info(f".env file: {env_files[0]}")
    else:
        logger.info(".env file: NONE (using system env only)")

    logger.info("-" * 50)
    logger.info(f"ENVIRONMENT: {settings.ENVIRONMENT} (source: {get_var_source('ENVIRONMENT', 'development')})")
    logger.info(f"DEBUG: {settings.DEBUG}")
    logger.info(f"DATABASE_URL: {'***SET***' if settings.DATABASE_URL and 'postgres' in settings.DATABASE_URL else 'NOT SET'}")
    logger.info(f"Resolved DB: {settings.resolved_database_url[:40]}...")
    logger.info(f"REDIS_URL: {settings.resolve_redis_url()[:30]}... (resolved)")

    _provider = settings.LLM_PROVIDER.lower()
    _llm_key = (
        settings.DEEPSEEK_API_KEY if _provider == "deepseek" else
        settings.OPENROUTER_API_KEY if _provider == "openrouter" else
        settings.OPENAI_API_KEY
    )
    _llm_model = (
        settings.DEEPSEEK_MODEL if _provider == "deepseek" else
        settings.OPENROUTER_MODEL if _provider == "openrouter" else
        settings.OPENAI_MODEL
    )
    logger.info(f"LLM: {_provider} / {_llm_model} [{'SET' if _llm_key else 'NOT SET'}]")

    _wa_meta = "SET" if settings.WHATSAPP_PHONE_NUMBER_ID and settings.WHATSAPP_ACCESS_TOKEN else "NOT SET"
    _wa_twilio = "SET" if settings.TWILIO_ACCOUNT_SID else "NOT SET"
    logger.info(f"WhatsApp Meta: [{_wa_meta}]  Twilio: [{_wa_twilio}]")

    _admin = "SET" if settings.ADMIN_API_KEY and settings.ADMIN_API_KEY != "admin-secret-key" else "DEFAULT"
    logger.info(f"ADMIN_API_KEY: [{_admin}]")
    logger.info("=" * 50)

    return settings
