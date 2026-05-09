# DEPRECATED — MiniMax No Longer Used

> **This document is obsolete.** The multi-provider LLM chain (MiniMax, Gemini, OpenRouter) was replaced in a May 2026 refactor by a single OpenAI GPT-4o-mini provider.

The current LLM architecture:
- **Single provider:** OpenAI GPT-4o-mini via `AsyncOpenAI`
- **Implementation:** `app/agents/llm_router.py`
- **Config:** `OPENAI_API_KEY` + `OPENAI_MODEL` in `app/core/config.py`
- **Tool calling:** Native OpenAI function calling format

See `AGENTS.md` for current architecture.
