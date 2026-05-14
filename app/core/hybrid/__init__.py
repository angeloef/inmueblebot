"""
HybridParser Infrastructure.
Every NL→structured-data component follows:
  LLM-first → code-fallback (hybrid), or pure LLM, or pure code.
Togglable per-component via PARSER_{NAME} env var.
"""
from . import registry as ParserRegistry
from .base import HybridParser, ParserConfig, ParseResult

__all__ = ["HybridParser", "ParseResult", "ParserConfig", "ParserRegistry"]
