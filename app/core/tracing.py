"""
v2.0 Lightweight Tracing Module.

Provides span-based tracing using structured logging.
Zero external dependencies — outputs JSON to loguru.
Can be upgraded to full OpenTelemetry by swapping the backend.

Usage:
    from app.core.tracing import trace_turn, span

    @trace_turn("agent.process_turn")
    async def process_turn(...):
        with span("context.assemble"):
            context = await get_context()
        with span("llm.call", attrs={"model": "gpt-4o-mini"}):
            response = await llm.ainvoke(...)
"""

from __future__ import annotations
import time
import uuid
import functools
from contextlib import contextmanager
from typing import Optional
from loguru import logger


# ── Module state ──────────────────────────────────────────────────────────

_enabled = True
_trace_counter = 0


def enable():
    global _enabled
    _enabled = True


def disable():
    global _enabled
    _enabled = False


# ── Span context manager ─────────────────────────────────────────────────

@contextmanager
def span(name: str, attrs: Optional[dict] = None, phone: str = ""):
    """Create a timed span that logs start/end with duration."""
    global _trace_counter
    if not _enabled:
        yield
        return

    _trace_counter += 1
    span_id = f"span_{_trace_counter}"
    start = time.time()

    logger.debug(
        f"[Trace] START {name} | id={span_id}"
        + (f" | {_format_attrs(attrs)}" if attrs else "")
    )

    try:
        yield
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        logger.warning(
            f"[Trace] ERROR {name} | id={span_id} | {elapsed:.1f}ms | {e}"
        )
        raise
    finally:
        elapsed = (time.time() - start) * 1000
        logger.debug(
            f"[Trace] END   {name} | id={span_id} | {elapsed:.1f}ms"
            + (f" | phone={phone[-4:]}" if phone else "")
        )


# ── Turn-level tracing ───────────────────────────────────────────────────

def trace_turn(name: str):
    """Decorator that wraps an async function in a turn-level trace span."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            global _trace_counter
            _trace_counter += 1
            trace_id = f"turn_{_trace_counter}_{uuid.uuid4().hex[:6]}"
            start = time.time()

            # Extract phone from args/kwargs for logging
            phone = kwargs.get("phone", "")
            if not phone and len(args) > 1:
                phone = str(args[1]) if len(args) > 1 else ""

            logger.info(
                f"[Trace] TURN_START {name} | trace={trace_id}"
                + (f" | phone={phone[-4:]}" if phone else "")
            )

            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start
                logger.info(
                    f"[Trace] TURN_END   {name} | trace={trace_id} | {elapsed:.2f}s"
                    + (f" | phone={phone[-4:]}" if phone else "")
                )
                return result
            except Exception as e:
                elapsed = time.time() - start
                logger.error(
                    f"[Trace] TURN_ERROR {name} | trace={trace_id} | {elapsed:.2f}s | {e}"
                )
                raise
        return wrapper
    return decorator


# ── Structured log helper ─────────────────────────────────────────────────

def log_event(event: str, **attrs):
    """Log a structured event with key=value attributes."""
    if not _enabled:
        return
    logger.info(f"[Trace] EVENT {event} | {_format_attrs(attrs)}")


def log_llm_call(model: str, tokens_prompt: int = 0, tokens_completion: int = 0,
                 latency_ms: float = 0, provider: str = "openai", phone: str = ""):
    """Log an LLM call with token usage."""
    if not _enabled:
        return
    logger.info(
        f"[Trace] LLM_CALL | model={model} | provider={provider} | "
        f"prompt_tokens={tokens_prompt} | completion_tokens={tokens_completion} | "
        f"latency_ms={latency_ms:.0f}"
        + (f" | phone={phone[-4:]}" if phone else "")
    )


def _format_attrs(attrs: Optional[dict]) -> str:
    if not attrs:
        return ""
    return " | ".join(f"{k}={v}" for k, v in attrs.items())
