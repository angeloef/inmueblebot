"""Preference extraction: structured preferences (incl. qualitative) from user messages."""
import json

from .base import HybridParser, ParseResult

_PREFERENCE_SYSTEM_PROMPT = (
    "Sos un extractor de preferencias para un chatbot de bienes raices en Argentina/Paraguay.\n"
    "Del siguiente mensaje del usuario, extrae TODAS las preferencias que puedas identificar.\n\n"
    "Responde SOLO con JSON. Campos disponibles:\n"
    "{{\n"
    '  "location": "nombre de ciudad o null",\n'
    '  "budget_max": numero en USD o null,\n'
    '  "budget_min": numero en USD o null,\n'
    '  "property_type": "casa|departamento|terreno|oficina|local|ph|duplex|cabana" o null,\n'
    '  "operation_type": "venta|alquiler" o null,\n'
    '  "bedrooms": numero o null,\n'
    '  "bathrooms": numero o null,\n'
    '  "features": ["balcon", "cochera", "patio", "pileta", "ascensor", "parrilla", "seguridad", "jardin", "quincho"] o [],\n'
    '  "qualitative": ["tranquilo", "centrico", "nuevo", "amplio", "luminoso", "silencioso", "acogedor"] o []\n'
    "}}\n\n"
    "Reglas:\n"
    "- Solo extrae lo que el usuario EXPRESAMENTE menciono.\n"
    "- Si no hay informacion nueva, responde {{\"features\":[], \"qualitative\":[]}}.\n"
    "- Nunca inventes preferencias.\n"
    "- Nunca des explicaciones ni texto fuera del JSON."
)


class PreferenceExtractor(HybridParser):
    """Extract structured preferences (incl. qualitative) from user messages."""

    def __init__(self):
        super().__init__(component="PREFERENCE", default_strategy="hybrid")

    async def parse_llm(self, raw: str, ctx: dict) -> ParseResult:
        from app.agents.llm_router import llm_router

        if not raw or len(raw.strip()) < 5:
            return ParseResult(None, 0.0, "llm")

        result, usage = await llm_router.chat(
            message=raw,
            system_prompt=_PREFERENCE_SYSTEM_PROMPT,
            max_completion_tokens=120,
            response_format={"type": "json_object"},
            return_usage=True,
        )
        result = (result or "").strip()
        tokens = (usage or {}).get("completion_tokens", 0)

        if not result:
            return ParseResult(None, 0.0, "llm", llm_tokens=tokens)

        try:
            data = json.loads(result)
            # Validate: at least one field must be non-null or non-empty
            has_content = (
                any(
                    v
                    for k, v in data.items()
                    if k
                    in (
                        "location",
                        "budget_max",
                        "budget_min",
                        "property_type",
                        "operation_type",
                        "bedrooms",
                        "bathrooms",
                    )
                    and v is not None
                )
                or data.get("features")
                or data.get("qualitative")
            )
            if has_content:
                return ParseResult(
                    value=data,
                    confidence=0.85,
                    parser_used="llm",
                    llm_tokens=tokens,
                )
        except (json.JSONDecodeError, TypeError):
            pass

        return ParseResult(None, 0.0, "llm", llm_tokens=tokens)

    async def parse_code(self, raw: str, ctx: dict) -> ParseResult:
        """Current regex-based extraction, wrapped in ParseResult."""
        try:
            phone = ctx.get("phone", "unknown")
            current_prefs = ctx.get("current_prefs", {})
            from app.core.memory import memory_manager
            prefs = await memory_manager.extract_and_save_preferences(phone, raw, current_prefs)
            if prefs:
                return ParseResult(value=prefs, confidence=0.6, parser_used="code")
        except Exception:
            pass
        return ParseResult(None, 0.0, "code")


preference_extractor = PreferenceExtractor()
