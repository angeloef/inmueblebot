"""City spelling-variant resolution (search-time, no DB canonicalization).

Covers the two layers of app/tools/v2/city_resolver.py:
  - _code_match: free deterministic matcher (substring + token overlap, accent-folded)
  - resolve_city_variants: orchestration (code hits + LLM hits, with cost guards)

Plus the search-side wiring in app/tools/v2/search_properties.py:
  - _build_zone_filters injects city-variant clauses (extra_data['city'] equality +
    location substring) and a reference_points clause.

The matcher tests are pure. The orchestration tests monkeypatch the DB and LLM
helpers so they stay deterministic and offline. The SQL tests compile clauses to
PostgreSQL strings (no DB needed), mirroring tests/test_search_zone.py.
"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from app.tools.v2 import city_resolver
from app.tools.v2.city_resolver import _code_match, _fold, resolve_city_variants

# A realistic "Leandro N. Alem" family plus unrelated cities for false-positive checks.
_ALEM_FAMILY = ["Leandro N. Alem", "LN Alem", "Alem"]
_CITIES = _ALEM_FAMILY + ["Oberá", "Posadas", "Puerto Iguazú"]


# ── _fold ────────────────────────────────────────────────────────────────────────

class TestFold:
    def test_lowercases_strips_accents_and_trims(self):
        assert _fold("  Oberá ") == "obera"
        assert _fold("Puerto Iguazú") == "puerto iguazu"
        assert _fold("LEANDRO") == "leandro"

    def test_none_and_empty_safe(self):
        assert _fold("") == ""
        assert _fold(None) == ""


# ── _code_match (pure: substring + token overlap) ─────────────────────────────────

class TestCodeMatch:
    def test_substring_matches_whole_alem_family(self):
        # "Alem" is a substring of every family variant (accent/case-folded).
        assert set(_code_match("Alem", _CITIES)) == set(_ALEM_FAMILY)

    def test_lowercase_user_input_still_matches(self):
        assert set(_code_match("alem", _CITIES)) == set(_ALEM_FAMILY)

    def test_token_overlap_matches_expanded_form(self):
        # "leandro alem" shares no substring with "LN Alem"/"Alem" but shares the
        # >2-char token "alem"; it shares "leandro" + "alem" with the full form.
        hits = set(_code_match("leandro alem", _CITIES))
        assert "Leandro N. Alem" in hits
        assert "Alem" in hits          # via "alem" token
        assert "LN Alem" in hits       # via "alem" token

    def test_accent_folding_matches_obera(self):
        assert _code_match("obera", _CITIES) == ["Oberá"]
        assert _code_match("Oberá", _CITIES) == ["Oberá"]

    def test_unrelated_term_returns_empty(self):
        assert _code_match("Córdoba", _CITIES) == []

    def test_blank_term_returns_empty(self):
        assert _code_match("", _CITIES) == []
        assert _code_match("   ", _CITIES) == []

    def test_short_tokens_do_not_cause_false_positives(self):
        # "ln" folds to a 2-char token and is dropped, so "ln" alone relies on
        # substring only — it must NOT token-match unrelated cities like Posadas.
        assert "Posadas" not in _code_match("ln", _CITIES)


# ── resolve_city_variants (orchestration, offline) ────────────────────────────────

def _patch(monkeypatch, *, cities, llm_return=None, llm_raises=False):
    """Stub the DB + LLM helpers; return a dict tracking whether the LLM ran."""
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


class TestResolveCityVariants:
    async def test_blank_term_skips_db_and_llm(self, monkeypatch):
        state = _patch(monkeypatch, cities=_CITIES, llm_return=["Alem"])
        assert await resolve_city_variants("  ") == []
        assert state["llm_called"] is False

    async def test_no_cities_returns_empty(self, monkeypatch):
        state = _patch(monkeypatch, cities=[], llm_return=["Alem"])
        assert await resolve_city_variants("Alem") == []
        assert state["llm_called"] is False

    async def test_code_matches_all_skips_llm(self, monkeypatch):
        # When code already matched EVERY known city, the LLM can add nothing.
        state = _patch(monkeypatch, cities=_ALEM_FAMILY, llm_return=["Alem"])
        result = await resolve_city_variants("Alem")
        assert set(result) == set(_ALEM_FAMILY)
        assert state["llm_called"] is False

    async def test_single_city_skips_llm(self, monkeypatch):
        state = _patch(monkeypatch, cities=["Oberá"], llm_return=["Oberá"])
        assert await resolve_city_variants("obera") == ["Oberá"]
        assert state["llm_called"] is False

    async def test_llm_recovers_variants_code_missed(self, monkeypatch):
        # "leandro" matches the full form by code but misses "LN Alem"/"Alem";
        # the LLM recovers them and the union is returned (code hits first).
        state = _patch(
            monkeypatch, cities=_CITIES, llm_return=["LN Alem", "Alem"],
        )
        result = await resolve_city_variants("leandro")
        assert state["llm_called"] is True
        assert set(result) == {"Leandro N. Alem", "LN Alem", "Alem"}
        assert result[0] == "Leandro N. Alem"  # code hit kept first

    async def test_llm_failure_falls_back_to_code_hits(self, monkeypatch):
        state = _patch(monkeypatch, cities=_CITIES, llm_raises=True)
        result = await resolve_city_variants("leandro")
        assert state["llm_called"] is True
        assert result == ["Leandro N. Alem"]  # only the code hit survives

    async def test_llm_candidate_list_is_capped(self, monkeypatch):
        # Many distinct cities -> the LLM prompt list is bounded by _MAX_LLM_CITIES.
        many = [f"Ciudad {i}" for i in range(200)]
        state = _patch(monkeypatch, cities=many, llm_return=[])
        await resolve_city_variants("algo")
        assert state["llm_called"] is True
        assert len(state["llm_arg"]) == city_resolver._MAX_LLM_CITIES

    async def test_dedup_preserves_order(self, monkeypatch):
        # LLM returns a city already found by code -> no duplicate.
        state = _patch(monkeypatch, cities=_CITIES, llm_return=["Alem", "LN Alem"])
        result = await resolve_city_variants("alem")
        assert len(result) == len(set(result))


# ── search-side wiring: _build_zone_filters with city variants + ref points ───────

def _sql(clause) -> str:
    return str(
        clause.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    ).lower()


class TestZoneFiltersWithVariants:
    def test_city_variants_add_extra_data_and_location_clauses(self):
        from app.tools.v2.search_properties import _build_zone_filters

        filters = _build_zone_filters("alem", city_variants=["Leandro N. Alem", "LN Alem"])
        joined = " || ".join(_sql(f) for f in filters)
        # extra_data['city'] equality for each variant (folded), plus location match.
        assert "extra_data" in joined
        assert "leandro n. alem" in joined
        assert "ln alem" in joined

    def test_reference_points_clause_present(self):
        from app.tools.v2.search_properties import _build_zone_filters

        filters = _build_zone_filters("hospital")
        joined = " || ".join(_sql(f) for f in filters)
        assert "reference_points" in joined
        assert "%hospital%" in joined

    def test_no_variants_keeps_base_behavior(self):
        from app.tools.v2.search_properties import _build_zone_filters

        # Without variants: title + location + reference_points, no extra_data equality.
        filters = _build_zone_filters("centro")
        joined = " || ".join(_sql(f) for f in filters)
        assert "properties.title" in joined
        assert "properties.location" in joined
        assert "reference_points" in joined


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
