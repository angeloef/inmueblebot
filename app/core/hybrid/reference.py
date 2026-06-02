"""Property reference resolution: match user descriptions to shown properties."""

from .base import HybridParser, ParseResult

_REFERENCE_SYSTEM_PROMPT = (
    "Sos un resolvedor de referencias para un chatbot inmobiliario.\n"
    "El usuario menciono una propiedad. Tenes estas opciones disponibles:\n"
    "{options}\n\n"
    "Mensaje del usuario: \"{message}\"\n\n"
    "Reglas:\n"
    "- Responde SOLO con el ID numerico de la propiedad correcta o 'UNKNOWN'.\n"
    "- 'esa', 'esa propiedad', 'la que vimos' -> propiedad activa (ID mas relevante).\n"
    "- 'el depto de 2 ambientes' -> busca en las opciones cual tiene '2 ambientes' o '2 hab'.\n"
    "- 'la casa de Villa Edna' -> busca 'Villa Edna' en los titulos.\n"
    "- Si es ambiguo entre varias -> 'UNKNOWN'.\n"
    "- Si no coincide con ninguna -> 'UNKNOWN'.\n"
    "- Nunca inventes un ID. Solo usa los que estan en la lista.\n"
    "- Nunca des explicaciones."
)


class PropertyReferenceParser(HybridParser):
    """Resolve 'esa', 'el depto de 2 amb', 'la casa de Villa Edna' -> property ID."""

    def __init__(self):
        super().__init__(component="REFERENCE", default_strategy="hybrid")

    def _format_options(self, props: list[dict]) -> str:
        if not props:
            return "No hay propiedades disponibles."
        lines = []
        for p in props:
            pid = p.get("id", "?")
            title = p.get("title", "Sin titulo")
            lines.append(f"  - ID:{pid} -> {title}")
        return "\n".join(lines)

    async def parse_llm(self, raw: str, ctx: dict) -> ParseResult:
        from app.agents.llm_router import llm_router

        props: list[dict] = ctx.get("property_options", [])
        if not props:
            return ParseResult(None, 0.0, "llm")

        options_str = self._format_options(props)
        prompt = _REFERENCE_SYSTEM_PROMPT.format(options=options_str, message=raw)

        result, usage = await llm_router.chat(
            message=raw,
            system_prompt=prompt,
            temperature=0,
            max_completion_tokens=10,
            return_usage=True,
        )
        result = (result or "").strip()
        tokens = (usage or {}).get("completion_tokens", 0)

        if not result or result.upper() == "UNKNOWN":
            return ParseResult(None, 0.0, "llm", llm_tokens=tokens)

        # Validate: result must be an integer matching one of the options
        try:
            int_result = int(result)
            if any(int_result == int(p.get("id", 0)) for p in props):
                return ParseResult(
                    value=str(int_result),
                    confidence=0.9,
                    parser_used="llm",
                    llm_tokens=tokens,
                )
        except (ValueError, TypeError):
            import logging
            logging.getLogger("hybrid.REFERENCE").warning(
                "Reference validation error: result=%r props=%s", result, [p.get("id") for p in props]
            )

        return ParseResult(None, 0.0, "llm", llm_tokens=tokens)

    async def parse_code(self, raw: str, ctx: dict) -> ParseResult:
        """Code fallback: just return the selected_property_id from context."""
        prop_id = ctx.get("selected_property_id")
        if prop_id:
            return ParseResult(value=str(prop_id), confidence=0.5, parser_used="code")
        return ParseResult(None, 0.0, "code")


reference_parser = PropertyReferenceParser()
