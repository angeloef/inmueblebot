"""Name extraction: background LLM parser that catches 'soy Juan Perez' from any turn."""
import re

from .base import HybridParser, ParseResult

_KNOWN_TITLES = {"sr", "sra", "srta", "dr", "dra", "lic", "ingeniero", "ing"}


def _code_extract_name(text: str) -> str | None:
    """Fast regex-based name extraction for common patterns.
    Used as fallback when LLM is unavailable."""
    text_clean = text.strip()
    if not text_clean:
        return None

    patterns = [
        # "soy Juan Perez" / "Soy Juan Perez"
        r"(?:soy|me llamo|mi nombre es|me presento|habla)\s+([A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+(?:\s+[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+){0,2})",
        # "Juan Perez al habla"
        r"^([A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+(?:\s+[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+){0,2})\s+al\s+habla",
        # Signature: "-- Juan Perez"
        r"(?:^|--|—)\s*([A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+(?:\s+[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+){1,2})\s*$",
    ]
    for pat in patterns:
        m = re.search(pat, text_clean)
        if m:
            candidate = m.group(1).strip()
            parts = candidate.split()
            if len(parts) >= 2 and parts[0].lower() not in _KNOWN_TITLES:
                return candidate
    return None


_NAME_SYSTEM_PROMPT = (
    "Sos un extractor de nombres para un chatbot inmobiliario argentino.\n"
    "Tu unica tarea: extraer el nombre completo de la persona en el texto.\n\n"
    "Reglas:\n"
    "- Responde SOLO con el nombre completo o 'NONE'.\n"
    "- Nombre completo = nombre + al menos un apellido.\n"
    "- 'Juan' solo -> 'NONE' (necesitamos apellido).\n"
    "- 'Juan Perez' -> 'Juan Perez'.\n"
    "- 'Juan Carlos Perez Garcia' -> 'Juan Carlos Perez Garcia'.\n"
    "- Si hay indicacion de que es seudonimo/apodo -> 'NONE'.\n"
    "- Nunca des explicaciones, solo el nombre o 'NONE'.\n"
    "- No uses acentos (Perez no Perez)."
)


class NameExtractor(HybridParser):
    """Extract user full name from any conversational turn."""

    def __init__(self):
        super().__init__(component="NAME", default_strategy="hybrid")

    async def parse_llm(self, raw: str, ctx: dict) -> ParseResult:
        from app.agents.llm_router import llm_router

        if not raw or len(raw.strip()) < 5:
            return ParseResult(None, 0.0, "llm")

        result, usage = await llm_router.chat(
            message=raw,
            system_prompt=_NAME_SYSTEM_PROMPT,
            temperature=0,
            max_completion_tokens=15,
            return_usage=True,
        )
        result = (result or "").strip().strip('"').strip("'")
        tokens = (usage or {}).get("completion_tokens", 0)

        if not result or result.strip().lower() == "none":
            return ParseResult(None, 0.0, "llm", llm_tokens=tokens)

        return ParseResult(value=result, confidence=0.9, parser_used="llm", llm_tokens=tokens)

    async def parse_code(self, raw: str, ctx: dict) -> ParseResult:
        candidate = _code_extract_name(raw)
        if candidate:
            return ParseResult(value=candidate, confidence=0.6, parser_used="code")
        return ParseResult(None, 0.0, "code")


name_extractor = NameExtractor()
