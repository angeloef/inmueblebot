"""KA2 offline tests — evidence retriever pure functions + prompt injection.

No DB / Redis / network: only the deterministic parts (keyword re-rank, block
rendering, pool assembly, message injection).
"""

from app.routers.v4 import evidence as ev
from app.routers.v4 import prompts as v4_prompts


# ── EvidenceItem ──────────────────────────────────────────────────────────────

def test_evidence_item_to_dict_rounds_score():
    item = ev.EvidenceItem(source=ev.SRC_RAG_FAQ, id="7", text="hola", score=0.123456)
    d = item.to_dict()
    assert d == {"source": "rag_faq", "id": "7", "text": "hola", "score": 0.1235, "timestamp": ""}


# ── _tokenize / _keyword_boost ────────────────────────────────────────────────

def test_tokenize_lowercases_and_splits():
    assert ev._tokenize("Hola, Mundo 2 veces!") == ["hola", "mundo", "2", "veces"]


def test_keyword_boost_lifts_literal_match_above_higher_dense_score():
    # b has lower dense score but contains both query content-words → should win.
    a = ev.EvidenceItem(source=ev.SRC_RAG_FAQ, id="a", text="texto sin relacion", score=0.80)
    b = ev.EvidenceItem(source=ev.SRC_RAG_FAQ, id="b", text="requisitos garantia propietario", score=0.60)
    ranked = ev._keyword_boost([a, b], "requisitos garantia")
    assert ranked[0].id == "b"  # 0.60 + 1.0 overlap = 1.60 > 0.80


def test_keyword_boost_empty_query_falls_back_to_dense_order():
    a = ev.EvidenceItem(source=ev.SRC_RAG_FAQ, id="a", text="x", score=0.3)
    b = ev.EvidenceItem(source=ev.SRC_RAG_FAQ, id="b", text="y", score=0.9)
    ranked = ev._keyword_boost([a, b], "  ")
    assert [it.id for it in ranked] == ["b", "a"]


# ── render_memory_block ───────────────────────────────────────────────────────

def test_render_memory_block_empty_returns_empty_string():
    assert ev.render_memory_block([]) == ""
    # RAG-only items are not memory → no block
    rag = ev.EvidenceItem(source=ev.SRC_RAG_FAQ, id="1", text="faq")
    assert ev.render_memory_block([rag]) == ""


def test_render_memory_block_includes_memory_levels():
    items = [
        ev.EvidenceItem(source=ev.SRC_EPISODIC, id="s1", text="buscaba casa en Centro"),
        ev.EvidenceItem(source=ev.SRC_PERSONA, id="persona", text="[PERFIL] prefiere alquiler"),
        ev.EvidenceItem(source=ev.SRC_ZONE, id="Centro", text="Zona Centro: cara"),
    ]
    block = ev.render_memory_block(items)
    assert block.startswith("[MEMORIA RECUPERADA]")
    assert "Sesión previa" in block
    assert "Perfil" in block
    assert "Zona" in block


# ── build_evidence_pool ───────────────────────────────────────────────────────

def _mem():
    return [ev.EvidenceItem(source=ev.SRC_EPISODIC, id="s1", text="prev")]


def _rag():
    return [ev.EvidenceItem(source=ev.SRC_RAG_FAQ, id="f1", text="faq", score=0.7)]


def test_pool_attaches_memory_to_every_sub_goal_and_rag_only_to_knowledge():
    sub_goals = [
        {"intent": "knowledge", "args_hint": "{}"},
        {"intent": "scheduling", "args_hint": "{}"},
    ]
    pool = ev.build_evidence_pool(sub_goals, _mem(), _rag())
    assert len(pool) == 2
    # knowledge goal gets memory + rag
    assert {e["source"] for e in pool[0]["evidence"]} == {ev.SRC_EPISODIC, ev.SRC_RAG_FAQ}
    # scheduling goal gets memory only
    assert {e["source"] for e in pool[1]["evidence"]} == {ev.SRC_EPISODIC}


def test_pool_defaults_one_goal_when_sub_goals_empty():
    pool = ev.build_evidence_pool([], _mem(), _rag())
    assert len(pool) == 1
    assert pool[0]["intent"] == "general"


# ── build_messages_v4 injection ───────────────────────────────────────────────

def test_build_messages_v4_inserts_memory_before_estado():
    msgs = v4_prompts.build_messages_v4(
        system="SYS",
        tenant_policy="POLICY",
        history=[],
        state_json='{"x":1}',
        user_message="hola",
        memory_block="[MEMORIA RECUPERADA]\n- (Perfil) algo",
    )
    # last is the ESTADO block, memory block immediately before it
    assert msgs[-1]["content"].startswith("[ESTADO]")
    assert msgs[-2]["content"].startswith("[MEMORIA RECUPERADA]")


def test_build_messages_v4_no_memory_is_identical_to_v3():
    args = ("SYS", "POLICY", [], '{"x":1}', "hola")
    base = v4_prompts.build_messages(*args)
    with_empty = v4_prompts.build_messages_v4(*args, memory_block="")
    assert base == with_empty
