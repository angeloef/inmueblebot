"""Date/time parsing: wrap existing parse_datetime_llm into HybridParser pattern."""

from .base import HybridParser, ParseResult


class DateParser(HybridParser):
    """Spanish date/time expression -> timezone-aware datetime.
    Wraps existing parse_datetime_llm + parse_spanish_datetime."""

    def __init__(self):
        super().__init__(component="DATE", default_strategy="hybrid")

    async def parse_llm(self, raw: str, ctx: dict) -> ParseResult:
        from app.utils.date_parser import get_argentina_now, parse_datetime_llm

        date_str = ctx.get("date_str", raw)
        time_str = ctx.get("time_str")
        now = ctx.get("reference_dt", get_argentina_now())

        parsed_dt, error = await parse_datetime_llm(date_str, time_str, now)

        if error:
            return ParseResult(None, 0.0, "llm", error=error)
        if parsed_dt:
            return ParseResult(value=parsed_dt, confidence=0.95, parser_used="llm")
        return ParseResult(None, 0.0, "llm")

    async def parse_code(self, raw: str, ctx: dict) -> ParseResult:
        from app.utils.date_parser import get_argentina_now, parse_spanish_datetime

        date_str = ctx.get("date_str", raw)
        time_str = ctx.get("time_str")
        combined = f"{date_str} {time_str or ''}".strip()
        now = ctx.get("reference_dt", get_argentina_now())

        parsed_dt, error = parse_spanish_datetime(combined)

        if error:
            return ParseResult(None, 0.0, "code", error=error)
        if parsed_dt:
            return ParseResult(value=parsed_dt, confidence=0.9, parser_used="code")
        return ParseResult(None, 0.0, "code")


date_parser = DateParser()
