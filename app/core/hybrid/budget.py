"""Budget tier resolution: vague price terms -> numeric ranges."""
import json

from .base import HybridParser, ParseResult

_BUDGET_SYSTEM_PROMPT = (
    "Sos un resolvedor de presupuestos para bienes raices en Argentina/Paraguay.\n"
    "Converti terminos vagos de presupuesto a rangos numericos en USD.\n\n"
    "Ciudad: {city}\n"
    "Mediana de precios en esta ciudad: ${median_price}\n"
    "Termino del usuario: \"{term}\"\n\n"
    "Reglas:\n"
    "- Responde SOLO con JSON: {{\"min\": N, \"max\": N}} o 'UNKNOWN'.\n"
    "- 'economico'/'barato'/'no muy caro' -> por debajo de la mediana.\n"
    "- 'normal'/'promedio'/'intermedio' -> alrededor de la mediana (+/-20%).\n"
    "- 'premium'/'caro'/'lujoso' -> por encima de la mediana.\n"
    "- 'lo mas barato'/'lo minimo' -> min=0, max=60% de la mediana.\n"
    "- Si el termino no es de presupuesto -> 'UNKNOWN'.\n"
    "- Nunca des explicaciones."
)


class BudgetTierParser(HybridParser):
    """Interpret 'economico', 'normal', 'premium' -> [min, max] range."""

    def __init__(self):
        super().__init__(component="BUDGET", default_strategy="hybrid")

    async def parse_llm(self, raw: str, ctx: dict) -> ParseResult:
        from app.agents.llm_router import llm_router

        city = ctx.get("city", "desconocida")
        median = ctx.get("median_price", 500)

        result, usage = await llm_router.chat(
            message=raw,
            system_prompt=_BUDGET_SYSTEM_PROMPT.format(
                city=city, median_price=median, term=raw,
            ),
            temperature=0,
            max_completion_tokens=50,
            response_format={"type": "json_object"},
            return_usage=True,
        )
        result = (result or "").strip()
        tokens = (usage or {}).get("completion_tokens", 0)

        if not result or result.upper() == "UNKNOWN":
            return ParseResult(None, 0.0, "llm", llm_tokens=tokens)

        try:
            data = json.loads(result)
            min_v = int(data.get("min", 0))
            max_v = int(data.get("max", 0))
            if max_v > 0 and min_v >= 0:
                return ParseResult(
                    value={"budget_min": min_v, "budget_max": max_v},
                    confidence=0.85,
                    parser_used="llm",
                    llm_tokens=tokens,
                )
        except (ValueError, json.JSONDecodeError):
            pass

        return ParseResult(None, 0.0, "llm", llm_tokens=tokens)

    async def parse_code(self, raw: str, ctx: dict) -> ParseResult:
        """Current budget_tiers.py logic using in-memory cache when possible,
        falling back to static defaults."""
        raw_lower = raw.lower().strip()
        # Static default tiers (matching typical Argentina/Paraguay real estate)
        DEFAULT_TIERS = {"low_max": 300, "med_max": 700}

        try:
            # Try to use cached tiers from the module-level cache
            from app.agents.budget_tiers import _cache as _tiers_cache

            if _tiers_cache:
                tiers = _tiers_cache
            else:
                tiers = DEFAULT_TIERS
        except Exception:
            tiers = DEFAULT_TIERS

        if raw_lower in ("economico", "barato"):
            return ParseResult(
                value={"budget_max": tiers["low_max"]},
                confidence=0.7,
                parser_used="code",
            )
        elif raw_lower in ("normal", "promedio", "intermedio"):
            return ParseResult(
                value={
                    "budget_min": tiers["low_max"] + 1,
                    "budget_max": tiers["med_max"],
                },
                confidence=0.7,
                parser_used="code",
            )
        elif raw_lower in ("premium", "caro", "lujoso"):
            return ParseResult(
                value={"budget_min": tiers["med_max"] + 1},
                confidence=0.7,
                parser_used="code",
            )
        return ParseResult(None, 0.0, "code")


budget_parser = BudgetTierParser()
