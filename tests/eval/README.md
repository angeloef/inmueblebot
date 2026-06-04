# Eval harness (Phase 0b)

Measures the router **before** we change its behavior in V3. Advisory, not blocking —
promotion is manual (D5) — but it is the signal pasted into every phase's PR.

## What it does

1. Loads multi-turn conversation **cases** from `cases/*.jsonl`, split into:
   - `dev` — prompts may derive few-shots from these (Phase 3).
   - `holdout` — **frozen**; the real release signal. Prompts must never see it.
2. Replays each case **through the adapter path** (`process_turn_v2`, later
   `process_turn_v3`) — the same code the webhook runs — not `route_message` directly.
3. Grades each turn with **layered graders**: code (deterministic) → rule (regex) →
   model (gpt-5.4-mini rubric, advisory) → human (flag).
4. Reports `pass@1`, `pass@k` (capability), `pass^k` (regression/consistency) plus
   cost/latency, and a markdown diff vs `baseline-v2.json`.

## Targets (from the build plan)

- capability: **pass@3 ≥ 0.90**
- regression: **pass^3 = 1.00** on release-critical flows

## Run it

Needs a live runtime (DB + Redis + `OPENAI_API_KEY`) because it routes through the adapter.

```bash
# V2 baseline on the frozen hold-out, k=3, with the LLM judge:
python -m tests.eval.run_eval --router v2 --split holdout --k 3

# Snapshot the current V2 result as the committed baseline (dev + holdout):
python -m tests.eval.run_eval --router v2 --split all --snapshot

# Fast, deterministic-only (no LLM judge), single run:
python -m tests.eval.run_eval --router v2 --split dev --no-model --k 1
```

The runtime-free core (schema, graders, metrics) is unit-tested in
`tests/test_eval_harness.py` and runs in plain CI without DB/Redis/LLM.

## Case grammar

See `schema.py` for the full expectation grammar (`tools_any`, `booking`, `regex_none`,
`rubric`, `flag_human`, …). Keep deterministic asserts where behavior is strongly
determined; lean on `rubric` (the LLM judge) where it isn't.

## Adding cases

Append JSON lines to `cases/dev.jsonl` (or `holdout.jsonl`). Real transcripts beat
synthetic ones — replace/extend the generated starter set as logs accumulate. **Never**
move a hold-out case into dev to make a prompt pass; that defeats the split.
