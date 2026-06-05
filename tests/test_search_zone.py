"""Zone-search filtering (shared search_properties tool, used by V2 + V3).

Regression for: zone-filtered searches returned ZERO results because the filter
only matched ``location`` with a plain (accent-sensitive) ILIKE, while the zone name
actually lives in the ``title`` ("Departamento en Centro, Oberá") and the user/LLM
may send it without its accent ("obera" for stored "Oberá").

These compile the SQLAlchemy clauses to SQL (no DB needed) and assert the fix:
  - the zone term is matched against BOTH title and location,
  - matching is accent- AND case-insensitive (lower + translate fold on both sides).
"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from app.tools.v2.search_properties import _build_zone_filters, _norm_accents


def _sql(clause) -> str:
    """Compile a clause to a PostgreSQL string with literals inlined."""
    return str(
        clause.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    ).lower()


# ── _norm_accents (Python-side fold, mirrors the SQL fold) ──────────────────────

class TestNormAccents:
    def test_strips_accents_and_lowercases(self):
        assert _norm_accents("Oberá") == "obera"
        assert _norm_accents("CENTRO") == "centro"
        assert _norm_accents("Misiónes") == "misiones"
        assert _norm_accents("Ñandú") == "nandu"

    def test_already_plain_unchanged(self):
        assert _norm_accents("centro") == "centro"

    def test_none_safe(self):
        assert _norm_accents("") == ""


# ── _build_zone_filters ─────────────────────────────────────────────────────────

class TestBuildZoneFilters:
    def test_matches_title_and_location(self):
        filters = _build_zone_filters("Centro")
        sql = " || ".join(_sql(f) for f in filters)
        assert "properties.title" in sql
        assert "properties.location" in sql

    def test_accent_insensitive_term_is_folded(self):
        # "Oberá" must search for the folded "obera" so it hits stored "Oberá".
        filters = _build_zone_filters("Oberá")
        sql = " || ".join(_sql(f) for f in filters)
        # The LIKE term is the FOLDED form; the accented term must not survive.
        assert "obera" in sql
        assert "oberá" not in sql

    def test_columns_are_folded_too(self):
        # Both sides folded: lower(...) + translate(...) on the column.
        filters = _build_zone_filters("centro")
        sql = _sql(filters[0])
        assert "lower(properties.title)" in sql
        assert "translate(" in sql

    def test_landmark_alias_still_applied(self):
        # "unam" keeps its landmark expansion (title/description/location aliases).
        filters = _build_zone_filters("unam")
        # base (title, location) + 3 landmark alias clauses
        assert len(filters) >= 3
        joined = " || ".join(_sql(f) for f in filters)
        assert "%unam%" in joined


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
