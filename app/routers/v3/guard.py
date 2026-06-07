"""V3 Quality Guard — gated rubric LLM-judge (Phase 6, implements R6).

The guard is the *third* (and last) LLM call in the V3 budget, and it is GATED:
it runs only on the subset of turns that actually need scrutiny, never on every
turn. This keeps the median calls/turn ≤3 (engine → optional synthesis → optional
judge) while still catching the high-risk mistakes (fake bookings, bad handoffs,
hallucinated knowledge, low-confidence guesses).

Gating policy (see should_judge):
  - confidence < V3_JUDGE_CONFIDENCE_THRESHOLD, OR
  - action ∈ CRITICAL_ACTIONS (book_step, handoff, answer_knowledge)

On a judge FAIL (score < V3_JUDGE_PASS_THRESHOLD) the guard performs **one**
targeted regeneration — a single synthesis call seeded with the judge's critique —
not the up-to-2 full reroutes V2 did. If regeneration fails or yields nothing, the
guard fails open and keeps the original text (a turn must never crash here).

All judge/regeneration calls use gpt-5.4-mini (LLMRole.SYNTH) per D7 — no stronger
model, even for the judge.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from loguru import logger

# ── Gating constants ──────────────────────────────────────────────────────────

# Actions that always warrant a judge pass regardless of confidence: they either
# commit a side-effect the user relies on (booking), exit the bot (handoff), or
# carry hallucination risk (knowledge/price answers).
CRITICAL_ACTIONS: frozenset[str] = frozenset({"book_step", "handoff", "answer_knowledge"})


# ── Judge output schema (strict JSON) ─────────────────────────────────────────

_JUDGE_SCHEMA: dict = {
    "type": "json_schema",
    "json_schema": {
        "name": "judge_verdict",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "score": {
                    "type": "number",
                    "description": "Overall quality 0.0–1.0 across task-completion, faithfulness, no-loop, tone.",
                },
                "passed": {
                    "type": "boolean",
                    "description": "True if the response is acceptable to send as-is.",
                },
                "issue": {
                    "type": ["string", "null"],
                    "description": "One short phrase naming the main problem, or null if none.",
                },
            },
            "required": ["score", "passed", "issue"],
            "additionalProperties": False,
        },
    },
}

# Versioned rubric — keep deterministic; log raw turns for manual spot-check (D5).
_RUBRIC_VERSION = "v3-judge-1"

_JUDGE_SYSTEM = (
    "Sos un evaluador de calidad de un asistente inmobiliario. "
    "Calificás la ÚLTIMA respuesta del asistente al usuario según cuatro criterios:\n"
    "1. task-completion: responde lo que el usuario pidió.\n"
    "2. faithfulness: no inventa propiedades, precios ni datos; afirma una visita agendada solo si realmente se agendó.\n"
    "3. no-loop: no repite la misma pregunta ni vuelve a pedir algo ya respondido.\n"
    "4. tone: español rioplatense, claro y profesional; una sola pregunta por mensaje.\n"
    "Devolvés SIEMPRE el JSON del schema (score, passed, issue). "
    "passed=false cuando hay alucinación, doble pregunta, loop, o no responde el pedido."
)


@dataclass(frozen=True)
class JudgeVerdict:
    """Result of a judge pass. score is always populated; passed gates regeneration."""
    score: float
    passed: bool
    issue: str | None


@dataclass(frozen=True)
class GuardResult:
    """Outcome of run_guard — what the engine should surface."""
    response_text: str
    judge_score: float | None
    regenerated: bool


# ── Gating decision ───────────────────────────────────────────────────────────

def should_judge(action: str | None, confidence: float, settings) -> bool:
    """Decide whether this turn warrants a judge pass.

    Fires when judging is enabled AND (confidence below threshold OR critical action).
    Returns False fast for the common, high-confidence, non-critical turn so most
    turns stay at a single LLM call.
    """
    if not getattr(settings, "V3_JUDGE_ENABLED", True):
        return False
    if confidence < getattr(settings, "V3_JUDGE_CONFIDENCE_THRESHOLD", 0.70):
        return True
    return action in CRITICAL_ACTIONS


# ── Judge call ────────────────────────────────────────────────────────────────

async def _judge(user_message: str, response_text: str, state_json: str) -> JudgeVerdict | None:
    """Run the rubric judge (LLM call). Returns None on any failure (fail-open)."""
    from app.agents.cs_llm_client import LLMRole, get_client, get_model, max_tokens_kwarg

    messages = [
        {"role": "system", "content": _JUDGE_SYSTEM},
        {"role": "system", "content": f"[ESTADO]\n{state_json}"},
        {
            "role": "user",
            "content": (
                f"Mensaje del usuario:\n{user_message}\n\n"
                f"Respuesta del asistente a evaluar:\n{response_text}"
            ),
        },
    ]
    try:
        client = get_client(LLMRole.SYNTH)
        model = get_model(LLMRole.SYNTH)
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            response_format=_JUDGE_SCHEMA,
            **max_tokens_kwarg(256, LLMRole.SYNTH),
        )
        choice = resp.choices[0] if resp.choices else None
        if not choice or getattr(choice.message, "refusal", None):
            return None
        content = getattr(choice.message, "content", None)
        if not content:
            return None
        data = json.loads(content)
        return JudgeVerdict(
            score=float(data.get("score", 0.0)),
            passed=bool(data.get("passed", False)),
            issue=data.get("issue"),
        )
    except Exception as exc:  # never break a turn over the judge
        logger.warning("[V3] Judge call failed (fail-open): {}", str(exc))
        return None


# ── Targeted regeneration ─────────────────────────────────────────────────────

async def _regenerate(
    user_message: str,
    original_text: str,
    issue: str | None,
    tool_results: list[str],
    state_json: str,
) -> str | None:
    """One targeted regeneration seeded with the judge's critique.

    Single synthesis call (LLMRole.SYNTH). Returns the improved Spanish text, or
    None if it fails / yields nothing (caller keeps the original).
    """
    from app.agents.cs_llm_client import LLMRole, get_client, get_model, max_tokens_kwarg
    from app.core.response_parser import get_final_response_format, parse_llm_response

    critique = issue or "la respuesta no cumple los criterios de calidad"
    tool_context = "\n".join(f"[{i+1}] {r}" for i, r in enumerate(tool_results)) if tool_results else "(sin herramientas)"

    messages = [
        {
            "role": "system",
            "content": (
                "Sos un asistente inmobiliario. "
                "Reescribís una respuesta defectuosa para que sea correcta, clara y profesional, "
                "en español rioplatense. Una sola pregunta por mensaje. "
                "No inventes datos: usá solo lo que aportan los resultados de herramientas y el estado."
            ),
        },
        {"role": "system", "content": f"[ESTADO]\n{state_json}"},
        {"role": "system", "content": f"[RESULTADOS]\n{tool_context}"},
        {
            "role": "user",
            "content": (
                f"Mensaje del usuario:\n{user_message}\n\n"
                f"Respuesta defectuosa:\n{original_text}\n\n"
                f"Problema detectado: {critique}\n\n"
                "Reescribí la respuesta corrigiendo ese problema."
            ),
        },
    ]
    try:
        client = get_client(LLMRole.SYNTH)
        model = get_model(LLMRole.SYNTH)
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            response_format=get_final_response_format(),
            **max_tokens_kwarg(512, LLMRole.SYNTH),
        )
        content = resp.choices[0].message.content if resp.choices else ""
        if not content:
            return None
        text, _ = parse_llm_response(content)
        return text or None
    except Exception as exc:
        logger.warning("[V3] Regeneration failed (keeping original): {}", str(exc))
        return None


# ── Orchestrator ──────────────────────────────────────────────────────────────

async def run_guard(
    *,
    action: str | None,
    confidence: float,
    user_message: str,
    response_text: str,
    state_json: str,
    tool_results: list[str],
    settings,
) -> GuardResult:
    """Gated judge + one targeted regeneration. Never raises.

    - If the turn isn't gated → returns the original text, judge_score=None.
    - If gated and the judge passes → returns original text + the score.
    - If gated and the judge fails → one regeneration; returns the regenerated
      text if produced (else original), with regenerated flagged.

    The guard never touches rich_content (images/booking confirmations stay as the
    engine/FSM produced them); it only refines the prose of response_text. Empty
    response_text (e.g. an image-only turn) is left untouched.
    """
    if not response_text or not response_text.strip():
        return GuardResult(response_text=response_text, judge_score=None, regenerated=False)

    if not should_judge(action, confidence, settings):
        return GuardResult(response_text=response_text, judge_score=None, regenerated=False)

    verdict = await _judge(user_message, response_text, state_json)
    if verdict is None:
        return GuardResult(response_text=response_text, judge_score=None, regenerated=False)

    pass_threshold = getattr(settings, "V3_JUDGE_PASS_THRESHOLD", 0.60)
    if verdict.passed and verdict.score >= pass_threshold:
        return GuardResult(response_text=response_text, judge_score=verdict.score, regenerated=False)

    logger.info(
        "[V3] Judge fail ({}: score={:.2f}, issue={}) → regenerating once",
        _RUBRIC_VERSION, verdict.score, verdict.issue,
    )
    improved = await _regenerate(user_message, response_text, verdict.issue, tool_results, state_json)
    if improved:
        return GuardResult(response_text=improved, judge_score=verdict.score, regenerated=True)

    # Fail-open: keep original text but record the score so the failure is visible.
    return GuardResult(response_text=response_text, judge_score=verdict.score, regenerated=False)
