"""Regression tests for the errors found in test chat #4 (the "21 opciones" / casa
conversation). Offline only — belief/criteria/anaphora logic, no LLM/DB calls.

Covered:
  A — criteria become authoritative: explicit type/operation/zone/bedrooms OVERRIDE
      (not first-mention-wins); a type switch resets zone; "cualquier zona" clears zone.
  B — _run_belief_search builds search args straight from the belief (no LLM arg drift).
  C — "me interesa más la casa" resolves to a VIEWED property, not a fresh search.

Run: pytest tests/test_chat4_fixes_regression.py -v
"""
import asyncio

import pytest

from app.core.belief_state import get_belief
import app.core.state_transitioner as st
import app.routers.router as router


def _fresh(session):
    b = get_belief(session)
    b.operation = b.property_type = b.zone = b.budget_max = b.bedrooms_min = None
    b.viewed_properties = []
    b.last_search_ids = []
    return b


class TestGroupA_CriteriaOverride:
    def test_type_switch_overrides_and_resets_zone(self):
        b = _fresh("a-switch")
        st.update_belief(b, "busco departamento en alquiler en el centro")
        assert (b.property_type, b.operation, b.zone) == ("departamento", "alquiler", "Centro")
        st.update_belief(b, "y alguna casa de 1 dormitorio?")
        assert b.property_type == "casa"          # switched (was departamento)
        assert b.zone is None                      # zone reset on type switch
        assert b.bedrooms_min == 1                 # bedrooms kept/updated
        assert b.operation == "alquiler"           # operation kept

    def test_zone_broadening_clears_zone(self):
        b = _fresh("a-broaden")
        st.update_belief(b, "departamento de 1 dormitorio en el centro")
        assert b.zone == "Centro"
        st.update_belief(b, "me podes pasar en cualquier otra zona, todos los de 1 dormitorio?")
        assert b.zone is None
        assert b.property_type == "departamento"
        # "cualquier zona" must mark zone as explicitly-any so narrowing won't re-ask
        assert "zone" in b.criteria_any

    def test_operation_switch_overrides(self):
        b = _fresh("a-op")
        st.update_belief(b, "quiero alquilar")
        assert b.operation == "alquiler"
        st.update_belief(b, "mejor para comprar")
        assert b.operation == "venta"

    def test_zone_override(self):
        b = _fresh("a-zone")
        st.update_belief(b, "en el centro")
        assert b.zone == "Centro"
        st.update_belief(b, "mejor en krause")
        assert b.zone == "Barrio Krause"

    def test_bedrooms_override(self):
        b = _fresh("a-bed")
        st.update_belief(b, "de 1 dormitorio")
        assert b.bedrooms_min == 1
        st.update_belief(b, "ahora de 2 dormitorios")
        assert b.bedrooms_min == 2


class TestGroupB_DeterministicSearch:
    def test_run_belief_search_uses_belief_criteria(self, monkeypatch):
        captured = {}

        async def _fake_search(**kwargs):
            captured.update(kwargs)
            return "Encontre 3 propiedades:\n  [1] Casa en Centro -- $100/mes"

        import app.tools.v2.search_properties as sp
        monkeypatch.setattr(sp, "search_properties", _fake_search)

        b = _fresh("b-search")
        b.operation = "alquiler"
        b.property_type = "casa"
        b.zone = None
        b.bedrooms_min = 1
        b.budget_max = 200000

        result = asyncio.run(router._run_belief_search(b))
        assert captured["operation"] == "alquiler"
        assert captured["tipo"] == "casa"
        assert captured["zona"] == ""           # None → "" (any zone)
        assert captured["dormitorios"] == 1
        assert captured["presupuesto_max"] == 200000
        assert "search_properties" in result.tools_called


class TestGroupC_ViewedReference:
    def _belief_with_views(self):
        b = _fresh("c-view")
        b.viewed_properties = [
            {"id": 15, "tipo": "casa", "titulo": "Casa 4 dormitorios UNAM"},
            {"id": 2, "tipo": "departamento", "titulo": "Departamento 1 amb"},
        ]
        return b

    @pytest.mark.parametrize("msg", [
        "me interesa mas la casa",
        "prefiero la casa",
        "me quedo con el departamento",
    ])
    def test_preference_ref_matches(self, msg):
        assert router._PREFERENCE_REF.search(msg) is not None

    def test_refinement_not_treated_as_selection(self):
        # "una casa de 1 dormitorio en centro" carries non-type criteria → NOT a selection.
        assert router._has_non_type_criteria("una casa de 1 dormitorio en centro") is True
        assert router._has_non_type_criteria("me interesa mas la casa") is False

    def test_resolves_single_viewed_house(self):
        b = self._belief_with_views()
        status, matches = router._resolve_viewed_reference(b, "casa")
        assert status == "one"
        assert matches[0]["id"] == 15

    def test_disambiguates_two_viewed_houses(self):
        b = _fresh("c-two")
        b.viewed_properties = [
            {"id": 15, "tipo": "casa", "titulo": "Casa en UNAM"},
            {"id": 22, "tipo": "casa", "titulo": "Casa en Centro"},
        ]
        status, matches = router._resolve_viewed_reference(b, "casa")
        assert status == "many"
        assert {m["id"] for m in matches} == {15, 22}

    def test_no_viewed_of_type(self):
        b = _fresh("c-none")
        b.viewed_properties = [{"id": 2, "tipo": "departamento", "titulo": "Depto Centro"}]
        status, _ = router._resolve_viewed_reference(b, "casa")
        assert status == "none"

    def test_match_disambiguation_by_zone_word(self):
        cands = [
            {"id": 15, "tipo": "casa", "titulo": "Casa en UNAM"},
            {"id": 22, "tipo": "casa", "titulo": "Casa en Centro"},
        ]
        pick = router._match_disambiguation("la de unam", cands)
        assert pick and pick["id"] == 15

    def test_classify_and_extract_title(self):
        blob = (
            "🏠 Casa 4 dormitorios UNAM\n"
            "━━━━━━━━━━\n"
            "📋 ID: 15 | ALQUILER\n"
            "📍 Calle Paraguay 2187, UNAM\n"
        )
        title = router._extract_detail_title(blob)
        assert title == "Casa 4 dormitorios UNAM"
        assert router._classify_title_type(title) == "casa"
