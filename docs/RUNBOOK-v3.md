<!-- docs/RUNBOOK-v3.md — V3 router operations runbook. Phase 7. Author: Hermes Agent. Date: 2026-06-04 -->
# InmuebleBot V3 — Operations Runbook

> **Audience:** the operator/owner running InmuebleBot in production on Render.
> **Scope:** how to switch routers, roll back instantly, onboard a tenant, run the
> eval gate, and what happens when a dependency fails. Companion to
> [`v3-router-build-plan.md`](../v3-router-build-plan.md) (the *how it was built*).

V1, V2 and V3 all ship in the same image and are switchable **per the `active_router`
setting** — no redeploy is needed to change routers. V2 stays the default until the
owner flips a tenant to V3 (decision **D5**: promotion is manual + owner-tested).

---

## 1. Router switch & instant rollback

The live router is resolved by `_resolve_active_router` in
[`app/api/routes/webhook.py`](../app/api/routes/webhook.py) from the `active_router`
key in `bot_settings` (`"v1" | "v2" | "v3"`). Back-compat: if `active_router` is
unset, the legacy `use_v2_router` boolean is used (`true→v2`, `false→v1`).

### Flip to V3
1. Open the **Dashboard → Config** section.
2. Set the **router selector** to **V3** (segmented control V1 / V2 / V3).
3. Save. This `PATCH /admin/settings` with `{"active_router": "v3"}`.
4. The next inbound WhatsApp turn is served by V3. No deploy, no restart.

### 🔴 Instant rollback (V3 → V2)
**Rollback is a single dashboard toggle. There is no migration to undo.**
1. Dashboard → Config → set the router selector back to **V2**.
2. Save. The very next turn is served by V2 again.

Because V3 is additive (new tables/columns only — see the compatibility contract in
the build plan §3), reverting the switch is sufficient; **no schema rollback is
required**. If the dashboard is unreachable, set the `active_router` row directly:

```sql
-- emergency rollback via psql (Render shell)
UPDATE bot_settings SET value = 'v2' WHERE key = 'active_router';
```

Then bust the in-process settings cache by redeploying or waiting out the cache TTL
(`_get_cached_bot_settings` in `app/agents/prompts.py`).

---

## 2. Failure modes (fail-open guarantees)

V3 **never crashes the webhook**. Every dependency failure degrades to a safe Spanish
message. These are proven by `tests/v3/test_failure_drills.py`.

| Failure | What happens | Where |
|---|---|---|
| **LLM timeout / network error** | Engine call returns `(None, _)` → regex fallback fills the belief → safe clarify message (`_SAFE_CLARIFY_ES`), `confidence=0.0` | `engine._call_engine`, `engine._apply_fallback` |
| **Malformed structured output / refusal** | Same path as timeout — unparseable content → `(None, usage)` → fallback | `engine._call_engine` |
| **Tool exception** (DB down mid-tool, bad args) | Per-tool `try/except` → error string in `tool_results`, `booking_succeeded` stays `False`; no fake confirmation can leak | `engine._execute_tools`, `_assemble_response` Path 0b |
| **Redis down** (belief load/save) | `load_belief_v5` returns a fresh belief; `save_belief_v5` fails silently; turn still completes | `belief.load_belief_v5/save_belief_v5` |
| **Quality judge / FSM error** | Wrapped in `try/except` → original response kept (fail-open) | `engine` Step 8b / Step 7c |
| **Unexpected crash in `run_turn`** | Adapter converts it to the `v3::error` contract dict (valid shape, Spanish apology) | `adapter.process_turn_v3` |

**Structural anti-hallucination:** a turn is "booked" **iff** `schedule_visit` returned
the `<!--CONFIRMED:` marker. If a booking tool fails, any drafted confirmation is
discarded before it reaches the user (Phase 4, R10).

---

## 3. Tenant onboarding

Tenants are admin-provisioned (decision **D6** — no self-serve signup yet). The
existing production account is the **default tenant** (backfilled in Phase 1).

To add a tenant:
1. **Dashboard → Tenants → New.** Provide:
   - `display_name`, `company_name`
   - `phone_number_id` **(unique — this is how inbound WhatsApp resolves the tenant)**, `waba_id`, `wa_access_token` (stored encrypted via `app/core/crypto.py`)
   - `business_hours`, `timezone` (default `America/Argentina/Cordoba`), `zones`, `branding`
2. **Point the Meta number at the shared webhook.** One Meta app, many numbers; the
   webhook maps `entry[].changes[].value.metadata.phone_number_id` → tenant (D2).
3. **Seed tenant data** — properties + FAQs. The knowledge index re-embeds on
   property/FAQ create/update (Phase 5), so RAG answers are grounded per-tenant.
4. **Leave `active_router` = `v2`** for the new tenant until you've run the eval +
   manual tests, then flip to V3.

> **Isolation guarantee:** every tenant-scoped read is enforced at four layers (RLS
> policy, transaction-scoped GUC, app ContextVar, automated tests). Proven by
> `tests/test_tenant_isolation.py` + `tests/v3/test_concurrency_isolation.py`. The app
> DB role must **not** be `BYPASSRLS`.

---

## 4. The eval gate (advisory, owner-run)

Promotion is **manual** (D5). The harness is advisory — run it, read the scorecard,
then decide. It needs a live runtime (DB + Redis + `OPENAI_API_KEY`) because it routes
through the adapter.

```bash
# Full V3 run vs the 150-conversation suite, k=3 (pass@k / pass^k), with the LLM judge:
python -m tests.eval.run_eval --router v3 --split all --k 3

# V2 baseline for comparison (or re-snapshot it):
python -m tests.eval.run_eval --router v2 --split all --k 3
```

Outputs a scorecard `tests/eval/reports/<git-sha>.json` and a markdown diff vs
`tests/eval/baseline-v2.json`. Acceptance bar (Phase 7): V3 ≥ V2 on task-completion
and **strictly better on no-loop / no-double-ask**; spot-check the raw turns (LLM
judges carry self-preference + score-compression bias — D5/§5).

---

## 5. Hardening verification (what "ready" means)

Run before cutover (Postgres required for the isolation suite):

```bash
# offline V3 unit + contract + failure drills (no external services):
pytest tests/v3 tests/test_v3_contract.py -q

# cross-tenant isolation + concurrency under the pooler (needs a throwaway Postgres):
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/inmueblebot \
    pytest tests/test_tenant_isolation.py tests/v3/test_concurrency_isolation.py -q
```

On Docker (the Postgres service supplies `TEST_DATABASE_URL`):

```bash
docker compose up -d db redis
docker run --rm --network inmueblebot_default -v "$PWD:/app" -w /app \
  -e TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/inmueblebot \
  -e DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/inmueblebot \
  -e REDIS_URL=redis://redis:6379/0 \
  inmueblebot-app:latest \
  python -m pytest tests/v3 tests/test_v3_contract.py tests/test_tenant_isolation.py -q
```

> ⚠️ The published `inmueblebot-app` image must be rebuilt from the current
> `requirements.txt` (it must include `openai`, `pgvector`, and `cryptography`).
> `cryptography` is currently **not pinned** in `requirements.txt` even though
> `app/core/crypto.py` imports it — pin it before the production rebuild.

---

## 6. Cutover checklist

- [ ] Eval run green vs the 150-set; scorecard reviewed; raw turns spot-checked.
- [ ] Manual smoke test of the critical flows (search → details → photos → booking → handoff).
- [ ] Isolation + concurrency suites green against a Postgres clone.
- [ ] Failure drills green (`tests/v3/test_failure_drills.py`).
- [ ] `requirements.txt` rebuilt image deployed (with `cryptography` pinned).
- [ ] **Flip the default tenant to V3** from the dashboard.
- [ ] Watch the per-turn metrics log (`router_label`, `action`, `latency_ms`,
      `cache_hit`, `judge_score`) for the first hour.
- [ ] Rollback rehearsed: confirm flipping back to V2 takes effect on the next turn.

**Rollback at any point = one dashboard toggle (V3 → V2).**
