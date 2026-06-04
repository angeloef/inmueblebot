"""Eval harness for the InmuebleBot router (Phase 0b of the V3 build plan).

Replays multi-turn conversation cases **through the adapter path** (`process_turn_v2`,
later `process_turn_v3`) and grades them with layered graders. Advisory, not blocking
(promotion is manual per D5) — but it's the measurable signal for every phase.
"""
