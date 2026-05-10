"""
Input Sanitizer - Sanitización de inputs para producción.
Limpia y valida inputs antes de procesarlos.
"""
import re
import unicodedata
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def sanitize_text(text: str, max_length: int = 5000) -> str:
    """
    Sanitiza texto entrada de usuario.
    - Trim whitespace
    - Remueve control characters
    - Limita longitud
    """
    if not text:
        return ""
    
    # Strip whitespace
    text = text.strip()
    
    # Remover caracteres de control (excepto saltos de línea normales)
    text = ''.join(
        c for c in text 
        if unicodedata.category(c) != 'Cc' or c in '\n\r\t'
    )
    
    # Remover múltiples espacios
    text = re.sub(r' +', ' ', text)
    
    # Remover múltiples saltos de línea
    text = re.sub(r'\n\n+', '\n\n', text)
    
    # Limitar longitud
    if max_length and len(text) > max_length:
        text = text[:max_length]
    
    return text


def sanitize_phone(phone: str) -> str:
    """
    Sanitiza número de teléfono.
    - Solo dígitos
    - Remueve prefijo +
    """
    if not phone:
        return ""
    
    # Remover todo excepto dígitos
    phone = re.sub(r'\D', '', phone)
    
    return phone


def sanitize_criteria(criteria: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitiza criterios de búsqueda.
    - Trim valores
    - Remueve caracteres especiales peligrosos
    - Valida tipos
    """
    if not criteria:
        return {}
    
    sanitized = {}
    
    for key, value in criteria.items():
        if value is None:
            continue
            
        # Sanitize key
        key = key.strip().lower()
        
        # Skip keys vacías
        if not key:
            continue
            
        # Sanitize value based on type
        if isinstance(value, str):
            value = value.strip()
            # Remover caracteres SQL injection básicos
            value = re.sub(r'[;\'\"\\]', '', value)
            # Remover keywords SQL
            value = re.sub(r'\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER)\b', '', value, flags=re.IGNORECASE)
            
            if not value:
                continue
                
        elif isinstance(value, (int, float)):
            # Validar que sea número válido
            if isinstance(value, float) and (value != value):  # NaN check
                continue
            # Validar rangos razonables
            if key in ('bedrooms', 'bathrooms') and value > 20:
                value = 20
            elif key in ('budget_max', 'budget_min'):
                if value > 100000000:  # 100M max
                    value = 100000000
                if value < 0:
                    value = abs(value)
        elif isinstance(value, list):
            # Lista de strings
            value = [sanitize_text(v) for v in value if v]
            if not value:
                continue
        
        sanitized[key] = value
    
    return sanitized


# Street prefixes to strip for normalized location search
_STREET_PREFIXES = [
    "calle", "av", "av.", "avenida", "avda", "pasaje", "psje",
    "boulevard", "bvar", "ruta", "camino", "autopista",
]

# Spanish → English mapping for property_type to extra_data['building_type']
# LLM sends Spanish types ("casa", "departamento"), DB stores English ("house", "apartment")
_PROPERTY_TYPE_MAP = {
    "casa": "house",
    "departamento": "apartment",
    "terreno": "land",
    "local": "commercial",
    "oficina": "office",
    "galpón": "commercial",
    "galpon": "commercial",
    "ph": "apartment",
    "duplex": "apartment",
    "cabaña": "house",
    "cabana": "house",
    "quincho": "house",
}


def map_property_type_to_building_type(property_type: str) -> Optional[str]:
    """
    Converts Spanish property_type from LLM to English building_type in extra_data.
    Returns None if no mapping exists — filter is skipped.
    """
    if not property_type:
        return None
    return _PROPERTY_TYPE_MAP.get(property_type.strip().lower())


def normalize_location(location: str) -> str:
    """
    Normaliza una ubicación para búsqueda flexible.
    - Quita prefijos de calle/avenida
    - Quita números de altura
    - Retorna término limpio para ILIKE matching
    """
    if not location:
        return location
    loc = location.strip().lower()
    # Strip street prefixes (e.g. "calle sarmiento" → "sarmiento")
    for prefix in _STREET_PREFIXES:
        if loc.startswith(prefix + " ") or loc == prefix:
            loc = loc[len(prefix):].strip()
            break
    # Remove street numbers at end (e.g. "sarmiento 285" → "sarmiento")
    loc = re.sub(r'\s+\d+\s*$', '', loc).strip()
    return loc


def sanitize_date_input(date_str: str) -> str:
    """
    Sanitiza input de fecha.
    - Solo caracteres válidos para fechas
    - Trim
    """
    if not date_str:
        return ""
    
    date_str = date_str.strip()
    
    # Solo permitir caracteres válidos para fechas
    # Dígitos, /, -, de, espacio, y, mes (incluye ñ y acentos del español)
    date_str = re.sub(r'[^\d/\- deenerofebreromarabrilmayojuniojulioagostoseptiembreoctubrenoviembrebediciembreyñáéíóúü]', ' ', date_str.lower())
    date_str = re.sub(r' +', ' ', date_str).strip()
    
    return date_str


def sanitize_time_input(time_str: str) -> str:
    """
    Sanitiza input de hora.
    """
    if not time_str:
        return ""
    
    time_str = time_str.strip().lower()
    
    # Normalizar pm/am
    time_str = time_str.replace('p.m.', 'pm').replace('a.m.', 'am')
    time_str = time_str.replace('p.m', 'pm').replace('a.m', 'am')
    
    # Solo dígitos, :, pm, am, espacio
    time_str = re.sub(r'[^\d:\sampm]', ' ', time_str)
    time_str = re.sub(r' +', ' ', time_str).strip()
    
    return time_str


def sanitize_property_id(prop_id: str) -> str:
    """
    Sanitiza ID de propiedad.
    - Solo alfanumérico y guiones bajos
    - Max longitud
    """
    if not prop_id:
        return ""
    
    prop_id = prop_id.strip()
    
    # Solo caracteres seguros
    prop_id = re.sub(r'[^a-zA-Z0-9\-_]', '', prop_id)
    
    # Limitar longitud
    if len(prop_id) > 50:
        prop_id = prop_id[:50]
    
    return prop_id.lower()


def sanitize_html_tags(text: str) -> str:
    """
    Remueve tags HTML.
    - Previene XSS básico
    """
    if not text:
        return ""
    
    # Remover tags HTML
    text = re.sub(r'<[^>]+>', '', text)
    
    # Normalizar entidades
    text = text.replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&amp;', '&')
    
    return text


def sanitize_for_llm(text: str, max_length: int = 4000) -> str:
    """
    Sanitiza texto para enviar al LLM.
    - Similar a sanitize_text pero más permisivo para el LLM
    """
    if not text:
        return ""
    
    text = text.strip()
    
    # Quite control characters peligrosos
    dangerous_chars = ['\x00', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07',
                       '\x0e', '\x0f', '\x10', '\x11', '\x12', '\x13', '\x14', '\x15',
                       '\x16', '\x17', '\x18', '\x19', '\x1a', '\x1b', '\x1c', '\x1d',
                       '\x1e', '\x1f']
    for char in dangerous_chars:
        text = text.replace(char, '')
    
    # Limitar longitud (menor para LLM)
    if len(text) > max_length:
        text = text[:max_length]
    
    return text


# Alias para backwards compatibility
clean_text = sanitize_text
clean_phone = sanitize_phone
clean_criteria = sanitize_criteria


# ── Output sanitizer (bot responses before sending to WhatsApp) ────────────────

# Patterns that indicate internal errors that must NEVER reach users
_INTERNAL_ERROR_PATTERNS_RAW = [
    r"El ID '[^']*' no es válido",
    r"ID '[^']*' no válido",
    r"No encontré la propiedad con ID",
    r"Property not found",
    r"Propiedad no encontrada",
    r"Invalid property",
    r"ID de propiedad '[^']*' no es válido",
    r"Error al ejecutar",
    r"Error de tipos en",
    r"Herramienta '[^']*' no encontrada",
    r"SQLAlchemy",
    r"ProgrammingError",
    r"asyncpg",
    r"InterfaceError",
    r"Database error",
    r"Error en get_property_images",
    r"Traceback",
    r'File ".*", line \d+',
    r"Exception:",
    r"Error:.*at 0x[0-9a-fA-F]+",
]

_COMPILED_INTERNAL_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _INTERNAL_ERROR_PATTERNS_RAW]

_SAFE_FALLBACK_MESSAGE = (
    "Perdón, ocurrió un inconveniente al procesar la información de la propiedad. "
    "Un asesor humano se contactará con vos a la brevedad para ayudarte."
)

def is_internal_error(text: str) -> bool:
    """Detecta si un texto contiene errores internos que no deben llegar al usuario."""
    if not text:
        return False
    for pattern in _COMPILED_INTERNAL_PATTERNS:
        if pattern.search(text):
            return True
    return False

def sanitize_bot_response(text: str) -> str:
    """
    Limpia la respuesta del bot antes de enviarla a WhatsApp.
    - Elimina URLs de imágenes (se envían por separado como media)
    - Elimina paths internos y artefactos de tool-calling
    - Reemplaza errores internos con mensajes profesionales
    """
    if not text:
        return text
    
    # First: detect and replace internal errors with safe fallback
    if is_internal_error(text):
        logger.warning(f"[Sanitizer] ⚠️ Detectado error interno en respuesta: {text[:80]}...")
        return _SAFE_FALLBACK_MESSAGE
    
    # Strip technical patterns
    for pattern in _OUTPUT_LEAK_PATTERNS:
        text = pattern.sub('', text)
    
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── Output leak patterns (stripped before sending to WhatsApp) ─────────────────

_OUTPUT_LEAK_PATTERNS = [
    # Markdown images: ![alt](url)
    re.compile(r'!\[[^\]]*\]\(https?://[^\)]+\)', re.IGNORECASE),
    # Raw media/property URLs embedded in text
    re.compile(r'https?://\S+/media/property/\S+', re.IGNORECASE),
    # base64 data URIs
    re.compile(r'data:image/[a-zA-Z]+;base64,[A-Za-z0-9+/=]{20,}', re.DOTALL),
    # Internal file paths
    re.compile(r'/app/[^\s]+'),
    re.compile(r'[A-Za-z]:\\[^\s]+'),
    # Tool call artifacts
    re.compile(r'<tool[_\\s][^>]*>'),
    re.compile(r'\[function[^\]]*\]'),
    # HTML comments with CONFIRMED metadata (LLM consumption only)
    re.compile(r'<!--CONFIRMED:[^>]+-->'),
]
