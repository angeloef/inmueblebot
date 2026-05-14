"""Abstract base + data classes for all hybrid parsers."""
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    """Normalised output from any parser strategy."""

    value: Any  # Parsed value (None = failure)
    confidence: float = 0.0  # 0.0–1.0
    parser_used: str = "unknown"  # "llm" | "code" | "llm_fallback_code"
    latency_ms: float = 0.0
    llm_tokens: int = 0
    error: str | None = None


class ParserConfig:
    """Per-component strategy config, driven by env var + defaults."""

    VALID_STRATEGIES = {"code", "llm", "hybrid"}

    def __init__(self, component: str, default_strategy: str = "code"):
        self.component = component.upper()
        self.env_key = f"PARSER_{self.component}"
        raw = os.getenv(self.env_key, default_strategy).lower()
        if raw not in self.VALID_STRATEGIES:
            logger.warning(
                "PARSER_%s=%r invalido, usando 'code'. Valores permitidos: %s",
                self.component,
                raw,
                self.VALID_STRATEGIES,
            )
            raw = "code"
        self._strategy = raw

    @property
    def strategy(self) -> str:
        return self._strategy

    def __repr__(self) -> str:
        return f"ParserConfig({self.component}={self.strategy})"


class HybridParser(ABC):
    """
    One per component. Subclass MUST implement:
      - parse_llm(raw, ctx)  → ParseResult
      - parse_code(raw, ctx) → ParseResult

    See existing impl in app/utils/date_parser.py::parse_datetime_llm.
    """

    def __init__(self, component: str, default_strategy: str = "code"):
        self.config = ParserConfig(component, default_strategy)
        self.logger = logging.getLogger(f"hybrid.{component}")

    @abstractmethod
    async def parse_llm(self, raw: str, ctx: dict) -> ParseResult:
        """LLM-based parsing. Must handle temperature=0, max_tokens <= 50."""

    @abstractmethod
    def parse_code(self, raw: str, ctx: dict) -> ParseResult:
        """Deterministic (regex/map) parsing. Must never raise."""

    async def parse(self, raw: str, ctx: dict | None = None) -> ParseResult:
        """Main entry point. Routes based on configured strategy."""
        ctx = ctx or {}
        t0 = time.perf_counter()

        if self.config.strategy == "code":
            result = self.parse_code(raw, ctx)
        elif self.config.strategy == "llm":
            result = await self.parse_llm(raw, ctx)
        else:  # "hybrid" — LLM first, code fallback
            result = await self.parse_llm(raw, ctx)
            if result.value is None and result.error is None:
                self.logger.info(
                    "LLM parser sin resultado para %r — fallback a code", raw
                )
                code_result = self.parse_code(raw, ctx)
                result = ParseResult(
                    value=code_result.value,
                    confidence=code_result.confidence,
                    parser_used="llm_fallback_code",
                    latency_ms=code_result.latency_ms,
                    llm_tokens=result.llm_tokens,
                    error=code_result.error,
                )

        latency = (time.perf_counter() - t0) * 1000
        result.latency_ms = round(latency, 1)
        self._emit_metric(result, raw)
        return result

    def _emit_metric(self, result: ParseResult, raw: str) -> None:
        """Log structured metric for dashboard / log analysis."""
        self.logger.info(
            "PARSER_METRIC | component=%s strategy=%s parser=%s "
            "latency_ms=%.1f tokens=%d confidence=%.2f error=%s | raw=%r value=%r",
            self.config.component,
            self.config.strategy,
            result.parser_used,
            result.latency_ms,
            result.llm_tokens,
            result.confidence,
            result.error or "none",
            raw[:80],
            str(result.value)[:80] if result.value is not None else "None",
        )
