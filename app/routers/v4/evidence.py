"""V4 KA2 — Evidence retriever + per-turn memory injection.

The V3 stack *writes* episodic/semantic/user memory but never *reads* it back
into the turn loop — that is the root cause of the "forgets the context"
complaint. This module fixes that:

  - gather_memory_evidence(): each turn, recover the 3 memory levels
    (episodic, user persona, semantic/zone) tenant-scoped, with provenance.
  - gather_rag_evidence(): hybrid dense (pgvector) + keyword re-rank over
    FAQ/doc chunks.
  - render_memory_block(): a compact text block injected into the prompt so
    the LLM actually *sees* prior-session context.
  - build_evidence_pool(): per sub-goal, a list of evidence items each
    carrying {source, id, timestamp, score}.

Retrieval only — no LLM chat calls (cost stays in KA1). Dense RAG uses an
embedding call (vector retrieval, not chat), which is within the cost
discipline. Write-back of the resulting episode happens in KA5.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from loguru import logger

if TYPE_CHECKING:
    from app.routers.v4.belief import BeliefStateV6

# Provenance source labels
SRC_EPISODIC = "episodic"
SRC_PERSONA = "persona"
SRC_ZONE = "zone"
SRC_RAG_FAQ = "rag_faq"
SRC_RAG_PROPERTY = "rag_property"

# How many dense candidates to pull before keyword re-rank (wider than final k).
_RAG_CANDIDATE_FACTOR = 3


@dataclass(frozen=True)
class EvidenceItem:
    """A single retrieved fact with provenance. Immutable."""

    source: str          # one of SRC_*
    id: str              # source-local id (session_id, "persona", zone name, chunk id)
    text: str            # the human-readable evidence
    score: float = 0.0   # similarity / relevance, 0..1
    timestamp: str = ""  # ISO timestamp of the underlying record, "" if unknown

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "id": self.id,
            "text": self.text,
            "score": round(self.score, 4),
            "timestamp": self.timestamp,
        }


# ── Memory retrieval (3 levels) ───────────────────────────────────────────────

async def gather_memory_evidence(
    phone: str,
    belief: BeliefStateV6,
    tenant_id: UUID | None,
    episode_limit: int = 3,
) -> list[EvidenceItem]:
    """Recover episodic + persona + zone memory for this turn, tenant-scoped.

    Caller MUST have set_current_tenant + set_current_contact already (the
    memory modules key off the ambient identity/tenant). Never raises.
    """
    items: list[EvidenceItem] = []

    # Episodic — past session summaries.
    try:
        from app.memory.episodic import get_episodes

        for ep in await get_episodes(phone, limit=episode_limit):
            summary = (ep.get("summary") or "").strip()
            if not summary:
                continue
            items.append(EvidenceItem(
                source=SRC_EPISODIC,
                id=str(ep.get("session_id") or ""),
                text=summary,
                score=1.0,
                timestamp=str(ep.get("timestamp") or ""),
            ))
    except Exception as exc:
        logger.debug("[V4/evidence] episodic recall failed: {}", str(exc))

    # User persona — cross-session preferences as a ready-made context block.
    try:
        from app.memory.user_model import build_personalized_context

        persona_ctx = (await build_personalized_context(phone)).strip()
        if persona_ctx:
            items.append(EvidenceItem(
                source=SRC_PERSONA,
                id="persona",
                text=persona_ctx,
                score=1.0,
            ))
    except Exception as exc:
        logger.debug("[V4/evidence] persona recall failed: {}", str(exc))

    # Semantic — zone knowledge for the zone in the current belief.
    zone = getattr(belief, "zone", None)
    if zone:
        try:
            from app.memory.semantic import get_zone_info

            info = await get_zone_info(str(zone))
            if info:
                alq = info.get("avg_price_alquiler")
                vta = info.get("avg_price_venta")
                amen = ", ".join((info.get("amenities") or [])[:3])
                text = f"Zona {zone}: alquiler prom ~${alq}, venta prom ~${vta}. {amen}".strip()
                items.append(EvidenceItem(
                    source=SRC_ZONE,
                    id=str(zone),
                    text=text,
                    score=1.0,
                ))
        except Exception as exc:
            logger.debug("[V4/evidence] zone recall failed: {}", str(exc))

    return items


# ── Hybrid RAG retrieval (dense + keyword) ────────────────────────────────────

def _keyword_boost(items: list[EvidenceItem], query: str) -> list[EvidenceItem]:
    """Re-rank dense candidates by keyword overlap with the query.

    Pure function (offline-testable). Final score = dense_score + overlap_ratio,
    where overlap_ratio is the fraction of query content-words present in the
    chunk text. Keeps recall of semantic matches while lifting literal hits.

    ponytail: token overlap, not BM25 — upgrade to a real lexical index only if
    retrieval quality measurably falls short on KA-EVAL.
    """
    q_words = {w for w in _tokenize(query) if len(w) > 2}
    if not q_words:
        return sorted(items, key=lambda it: it.score, reverse=True)

    boosted: list[EvidenceItem] = []
    for it in items:
        text_words = set(_tokenize(it.text))
        overlap = len(q_words & text_words) / len(q_words)
        boosted.append(EvidenceItem(
            source=it.source,
            id=it.id,
            text=it.text,
            score=round(it.score + overlap, 4),
            timestamp=it.timestamp,
        ))
    return sorted(boosted, key=lambda it: it.score, reverse=True)


def _tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric word split (accent-tolerant via str.lower)."""
    import re

    return re.findall(r"\w+", (text or "").lower())


async def gather_rag_evidence(
    tenant_id: UUID | None,
    query: str,
    limit: int = 5,
    threshold: float = 0.5,
) -> list[EvidenceItem]:
    """Hybrid dense+keyword retrieval over FAQ/doc chunks, tenant-scoped.

    Pulls a wider dense candidate set then keyword re-ranks to the top `limit`.
    Never raises — returns [] on any failure or missing pgvector.
    """
    if tenant_id is None or not (query or "").strip():
        return []

    try:
        from app.routers.v3.knowledge.index import search_knowledge

        candidates = await search_knowledge(
            tenant_id=tenant_id,
            query=query,
            limit=limit * _RAG_CANDIDATE_FACTOR,
            threshold=threshold,
        )
    except Exception as exc:
        logger.debug("[V4/evidence] RAG dense retrieval failed: {}", str(exc))
        return []

    dense_items = [
        EvidenceItem(
            source=SRC_RAG_FAQ if c.get("source_type") == "faq" else SRC_RAG_PROPERTY,
            id=str(c.get("source_id") or ""),
            text=c.get("text") or "",
            score=float(c.get("similarity") or 0.0),
        )
        for c in candidates
    ]
    return _keyword_boost(dense_items, query)[:limit]


# ── Prompt injection + evidence pool ──────────────────────────────────────────

def render_memory_block(items: list[EvidenceItem]) -> str:
    """Render recovered memory as a compact prompt block, or "" if empty.

    Injected as a dynamic system message (placed late, near [ESTADO], so it
    does not bust the cached static prefix).
    """
    mem = [it for it in items if it.source in (SRC_EPISODIC, SRC_PERSONA, SRC_ZONE)]
    if not mem:
        return ""

    lines = ["[MEMORIA RECUPERADA]"]
    for it in mem:
        label = {
            SRC_EPISODIC: "Sesión previa",
            SRC_PERSONA: "Perfil",
            SRC_ZONE: "Zona",
        }.get(it.source, it.source)
        lines.append(f"- ({label}) {it.text}")
    return "\n".join(lines)


def build_evidence_pool(
    sub_goals: list[dict],
    memory_items: list[EvidenceItem],
    rag_items: list[EvidenceItem],
) -> list[dict]:
    """Assemble the per-sub-goal evidence pool.

    Memory evidence is conversation-wide so it attaches to every sub-goal.
    RAG evidence attaches to knowledge/search-flavored sub-goals only.
    Each entry: {sub_goal, intent, evidence: [{source,id,timestamp,score}, ...]}.
    """
    knowledge_intents = {"knowledge", "search", "answer_knowledge", "faq"}
    mem_dicts = [it.to_dict() for it in memory_items]
    rag_dicts = [it.to_dict() for it in rag_items]

    pool: list[dict] = []
    goals = sub_goals or [{"intent": "general", "args_hint": "{}"}]
    for sg in goals:
        intent = str(sg.get("intent") or "general")
        evidence = list(mem_dicts)
        if intent.lower() in knowledge_intents:
            evidence = evidence + rag_dicts
        pool.append({
            "intent": intent,
            "args_hint": sg.get("args_hint", "{}"),
            "evidence": evidence,
        })
    return pool
