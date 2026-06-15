"""Debate harness — how well does city-variant resolution handle spelling drift?

NOT YET RUN — these encode our *predictions* so we can argue about the expected
behavior first, then run them to see where reality differs.

Two layers are under test:
  - _code_match: deterministic (substring either-direction + token-overlap on
    accent-folded text). No regex. This is the layer we're debating.
  - the LLM layer is NOT unit-tested here (non-deterministic); the cases the code
    *misses* are exactly what the LLM must rescue — validated live, not here.

Stored cities (what the DB holds via extra_data['city']) — a realistic Misiones
sample chosen to expose both recall and precision behavior.
"""

from __future__ import annotations

import pytest

from app.tools.v2 import city_resolver
from app.tools.v2.city_resolver import _code_match

# The "ground truth" the tenant has in the DB. Note the deliberately tricky ones:
# two "San X" towns (token-overlap precision risk) and the short "Alem".
_STORED = [
    "Garupá", "Posadas", "Candelaria", "Eldorado",
    "San Vicente", "San Javier",
    "Leandro N. Alem", "Alem",
]


def _match(term: str) -> set[str]:
    return set(_code_match(term, _STORED))


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 1 — RECALL: variations the CODE layer should catch on its own.
# These should pass WITHOUT any LLM. If any fail, the deterministic floor is
# weaker than we think.
# ─────────────────────────────────────────────────────────────────────────────
class TestCodeRecall:
    @pytest.mark.parametrize("term, expected", [
        # exact / case / accent — folding handles these
        ("Garupá",   {"Garupá"}),
        ("Garupa",   {"Garupá"}),   # accent dropped
        ("GARUPÁ",   {"Garupá"}),   # uppercase
        ("garupa",   {"Garupá"}),   # lowercase, no accent
        # suffix truncation — substring(term in city)
        ("Garup",    {"Garupá"}),
        ("Garu",     {"Garupá"}),
        # leading-letter drop — STILL a substring ("arupa" ⊂ "garupa").
        # This is the case I previously (wrongly) said would miss.
        ("arupá",    {"Garupá"}),
        ("arupa",    {"Garupá"}),
        # other cities, same mechanics
        ("candela",  {"Candelaria"}),
        ("posada",   {"Posadas"}),
        # UNIFICATION: "alem" is a substring of both stored spellings → both come back
        ("alem",     {"Alem", "Leandro N. Alem"}),
        ("Alem",     {"Alem", "Leandro N. Alem"}),
    ])
    def test_code_catches(self, term, expected):
        assert _match(term) == expected


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 2 — MISSES: variations the CODE layer CANNOT catch (no shared substring
# in either direction, no shared >2-char token). These return nothing from code
# and MUST be rescued by the LLM. We assert == empty to pin down the gap exactly.
# ─────────────────────────────────────────────────────────────────────────────
class TestCodeMisses:
    @pytest.mark.parametrize("term", [
        "Gaurpa",    # internal transposition (u/r swapped)
        "Grupa",     # dropped interior letter (no 'a' after G)
        "Garuppa",   # doubled/extra letter
        "Garupica",  # inserted interior letters
        "Garpa",     # two interior letters dropped — not contiguous
    ])
    def test_code_misses_garupa_typos(self, term):
        # Documents the LLM's job: these should NOT be matched by code.
        assert "Garupá" not in _match(term)
        assert _match(term) == set()


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 3 — PRECISION CONCERNS: cases where the heuristic matches something it
# arguably SHOULD NOT. We assert the DESIRED (clean) behavior and mark xfail,
# because we predict the current code violates it. Running tells us:
#   - xfail  → the concern is real (current code over-matches)
#   - XPASS  → the concern doesn't exist, remove the marker
# ─────────────────────────────────────────────────────────────────────────────
class TestPrecisionConcerns:
    @pytest.mark.xfail(reason="token-overlap on 'san' cross-matches unrelated San* towns", strict=False)
    def test_san_martin_should_not_match_other_san_towns(self):
        # User wants "San Martín" (not even stored). Token-overlap on the shared
        # token "san" pulls in San Vicente + San Javier — both wrong.
        assert _match("san martin") == set()

    @pytest.mark.xfail(reason="bare 'san' floods every San* town via substring", strict=False)
    def test_bare_san_should_not_flood(self):
        # Is "san" alone a legit query that SHOULD return both, or noise we should
        # reject? Open question — encoded as a concern for now.
        assert _match("san") == set()

    @pytest.mark.xfail(reason="short city 'Alem' is a substring of unrelated words", strict=False)
    def test_alemania_should_not_match_city_alem(self):
        # Searching the country "Alemania" must not surface the town "Alem".
        assert "Alem" not in _match("alemania")


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 4 — ORCHESTRATION CONTRACT (LLM mocked, deterministic): how the code +
# LLM layers combine in resolve_city_variants. Confirms the LLM rescues a code
# miss, and that an LLM failure degrades to "no variants" (search then falls back
# to its base zone substring match — never an error).
# ─────────────────────────────────────────────────────────────────────────────
def _patch(monkeypatch, *, cities, llm_return=None, llm_raises=False):
    state = {"llm_called": False, "llm_arg": None}

    async def fake_cities() -> list[str]:
        return list(cities)

    async def fake_llm(term: str, candidates: list[str]) -> list[str]:
        state["llm_called"] = True
        state["llm_arg"] = candidates
        if llm_raises:
            raise RuntimeError("llm down")
        return list(llm_return or [])

    monkeypatch.setattr(city_resolver, "_distinct_tenant_cities", fake_cities)
    monkeypatch.setattr(city_resolver, "_llm_match", fake_llm)
    return state


class TestOrchestrationContract:
    async def test_llm_rescues_a_code_miss(self, monkeypatch):
        # "Gaurpa" misses in code; the LLM recognizes the typo and returns Garupá.
        state = _patch(monkeypatch, cities=_STORED, llm_return=["Garupá"])
        result = await city_resolver.resolve_city_variants("Gaurpa")
        assert state["llm_called"] is True
        assert result == ["Garupá"]

    async def test_llm_failure_degrades_to_empty(self, monkeypatch):
        # If the LLM errors on a code-miss term, we get [] (search uses base zone
        # match) — never a crash.
        _patch(monkeypatch, cities=_STORED, llm_raises=True)
        assert await city_resolver.resolve_city_variants("Gaurpa") == []

    async def test_code_hit_plus_llm_union(self, monkeypatch):
        # "alem" → code finds both; LLM adds nothing new → union stays clean.
        _patch(monkeypatch, cities=_STORED, llm_return=["Alem"])
        result = await city_resolver.resolve_city_variants("alem")
        assert set(result) == {"Alem", "Leandro N. Alem"}
        assert len(result) == len(set(result))  # no dupes


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
