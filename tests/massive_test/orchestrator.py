"""
orchestrator.py — Monte Carlo test orchestrator (v3).

Executes N sessions per profile against the live Render API
via the /admin/simulate endpoint. Reports progress in real-time.

v3 changes:
- Added states: completed, lead_capture, preferences, handoff
- Added tools: refine_search, recommend_properties, save_lead_info,
  request_human_assistance, update_user_preferences, get_user_preferences
- Updated state inference for new tools
- Per-profile session counts for better weight distribution
"""

import json
import sys
import time
import random
import traceback

import httpx

# Local modules
from profiles import PROFILES
from validators import validate_all
from coverage_tracker import CoverageTracker, KNOWABLE_STATES

# ── Config ─────────────────────────────────────────────────────────
BASE_URL = "https://inmueblebot-api.onrender.com"
SIMULATE_URL = f"{BASE_URL}/admin/simulate"
ADMIN_API_KEY = "your-secure-admin-key-here"
HEADERS = {"X-API-Key": ADMIN_API_KEY, "Content-Type": "application/json"}

# Per-profile session counts (v3: weighted by importance)
# Key = profile index, Value = sessions count
PER_PROFILE_SESSIONS = {
    0: 5,   # Alquiler específico (errático) — core flow
    1: 3,   # Busca compra
    2: 4,   # Consulta vaga + intent change
    3: 3,   # FAQ → fotos → agenda
    4: 3,   # No encuentra + confusión
    5: 4,   # Cliente existente
    6: 3,   # Pide fotos
    7: 3,   # Compara propiedades
    8: 4,   # Guarda lead + agenda (NEW) — important new flow
    9: 3,   # Pide agente humano (NEW)
    10: 3,  # Preferencias guardadas (NEW)
    11: 3,  # Reprograma/Cancela (NEW)
}
TOTAL_SESSIONS = sum(PER_PROFILE_SESSIONS.values())

MAX_TURNS = 10               # Safety limit per session
TURN_DELAY = 1.5             # Seconds between turns
SESSION_DELAY = 3.0          # Seconds between sessions
KEEPALIVE_INTERVAL = 120     # Seconds between health pings

TIMEOUT_PER_TURN = 60  # seconds; LLM calls can take 25s


# ── State inference ────────────────────────────────────────────────

def infer_state(response_text: str, tools_used: list, previous_state: str) -> str:
    """
    Infer the bot's state from its response + tools.
    This is the inverse of the Markov chain: given output, deduce where we are.
    """
    text_lower = (response_text or "").lower()
    tools = set(tools_used or [])

    # Direct tool indicators (highest confidence)
    if "schedule_visit" in tools:
        return "scheduling"
    if "reschedule_appointment" in tools:
        return "scheduling"
    if "cancel_appointment" in tools:
        return "cancelling"
    if "get_my_appointments" in tools:
        return "appointments"
    if "get_faq_answer" in tools:
        return "faq"
    if "get_property_details" in tools:
        return "viewing_property"
    if "get_property_images" in tools:
        return "viewing_property"
    if "search_properties" in tools:
        return "searching"
    if "refine_search" in tools:  # NEW
        return "searching"
    if "save_lead_info" in tools:  # NEW
        return "lead_capture"
    if "request_human_assistance" in tools:  # NEW
        return "handoff"
    if "recommend_properties" in tools:  # NEW
        return "preferences"
    if "update_user_preferences" in tools:  # NEW
        return "preferences"
    if "get_user_preferences" in tools:  # NEW
        return "preferences"

    # Text-based heuristics
    if any(p in text_lower for p in ["cita agendada", "te esperamos", "visitarnos", "confirmada"]):
        return "completed"
    if any(p in text_lower for p in ["gracias por contactarnos", "buen día", "que tengas"]):
        return "idle"
    if any(p in text_lower for p in ["qué zona", "qué tipo", "alquilar o comprar",
                                      "cuál es tu presupuesto", "dormitorios",
                                      "en mente", "preferencia"]):
        return "qualifying"
    if any(p in text_lower for p in ["encontré", "acá tenés", "resultados", "mostrándote"]):
        if "propiedades" in text_lower or "te muestro" in text_lower or "🏠" in response_text:
            return "searching"
    if any(p in text_lower for p in ["detalles", "información de", "características", "📐", "💰", "🏠"]):
        if "ID" in response_text or "ambientes" in text_lower or "habitaciones" in text_lower:
            return "viewing_property"
    if any(p in text_lower for p in ["cuándo", "fecha", "horario"]):
        if "detalles" not in text_lower:
            return "scheduling"
    # "agendar" alone is not enough (bot asks "¿querés agendar?" after showing details)
    if "agendar" in text_lower and "querés" not in text_lower and "quieres" not in text_lower:
        return "scheduling"
    if any(p in text_lower for p in ["horario", "lunes a viernes", "forma de pago",
                                      "faq", "preguntas frecuentes"]):
        return "faq"
    if any(p in text_lower for p in ["tus citas", "tus turnos", "tienes citas", "tienes turnos"]):
        return "appointments"
    if any(p in text_lower for p in ["no encontré", "no tengo propiedades", "sin resultados",
                                      "intentar con otros", "alternativas"]):
        return "searching"

    # NEW: lead capture heuristics (bot asking for contact info)
    if any(p in text_lower for p in ["nombre", "teléfono", "correo", "email",
                                      "datos de contacto", "cómo te llamás"]):
        if ("decime" in text_lower or "dame" in text_lower or "podrías" in text_lower):
            return "lead_capture"

    # NEW: handoff heuristics (bot offering transfer)
    if any(p in text_lower for p in ["conectar con un asesor", "transferir con",
                                      "agente humano", "paso con un agente"]):
        return "handoff"

    # If nothing specific found, stay in previous state
    return previous_state or "idle"


def is_exit_state(text_lower: str) -> bool:
    """Detect if the user said goodbye and the conversation should end."""
    user_exit = any(p in text_lower for p in
                     ["gracias", "chau", "adiós", "después vuelvo", "después te confirmo",
                      "ya fue", "era lo que necesitaba",
                      "no encontré lo que buscaba",
                      "después te llamo", "después retomo",
                      "espero que me contacten", "que me contacten"])
    bot_exit = any(p in text_lower for p in
                    ["que tengas un buen", "cuando quieras", "buen día",
                     "quedo a tu disposición", "un buen día",
                     "que estés bien"])
    return user_exit or bot_exit


# ── Core simulation ────────────────────────────────────────────────

def simulate_turn(client: httpx.Client, phone: str, message: str,
                  reset: bool = False) -> dict:
    """Send one message to /admin/simulate and return parsed result."""
    payload = {"phone": phone, "message": message, "reset": reset}
    resp = client.post(
        SIMULATE_URL,
        json=payload,
        headers=HEADERS,
        timeout=TIMEOUT_PER_TURN,
    )
    if resp.status_code != 200:
        return {
            "error": f"HTTP {resp.status_code}: {resp.text[:300]}",
            "response_text": "",
            "tools_used": [],
            "rich_content": None,
            "next_state": "",
            "timing": {"turn_seconds": 0},
        }
    return resp.json()


def infer_state_from_response(data: dict, prev_state: str) -> tuple:
    """
    (inferred_state, is_done)
    """
    text = data.get("response_text", "")
    tools = data.get("tools_used", [])
    state = infer_state(text, tools, prev_state)

    # Detect conversation end
    if is_exit_state(text.lower()):
        return "exit", True

    return state, False


def run_session(client: httpx.Client, profile: dict, session_num: int,
                tracker: CoverageTracker) -> dict:
    """Run a single multi-turn session."""
    phone = f"549115555{session_num:04d}"
    profile_name = profile["name"]
    prev_state = "idle"
    state = "idle"
    turns = []
    session_id = hash(phone) % 100000

    # Reset context to start fresh
    reset_data = simulate_turn(client, phone, "", reset=True)
    if "error" in reset_data:
        return {"phone": phone, "profile": profile_name, "error": reset_data["error"], "turns": []}

    for turn_num in range(1, profile["max_turns"] + 1):
        # Get the next human message based on current state
        states = profile["states"]
        if state not in states:
            # If state not in profile's states, fallback to searching
            state = "searching"

        handler_fn, expected_next = states[state]

        try:
            # Get last response for context-aware handlers
            last_response = turns[-1]["bot_response"] if turns else ""
            human_msg = handler_fn(last_response)
        except Exception as e:
            print(f"⚠️  Handler error for {profile_name} turn {turn_num}: {e}")
            break

        # Send to simulate endpoint
        data = simulate_turn(client, phone, human_msg, reset=False)

        if "error" in data:
            print(f"  ❌  Turn {turn_num}: {data['error']}")
            tracker.record_violation(session_id, turn_num, "API_ERROR", data["error"])
            break

        # Infer bot state from response
        inferred_state, is_done = infer_state_from_response(data, prev_state)

        # Also check if the HUMAN message was an exit (user said goodbye)
        if not is_done and is_exit_state(human_msg.lower()):
            is_done = True
            inferred_state = "exit"

        # Validate
        validations = validate_all(
            data.get("response_text", ""),
            data.get("tools_used", []),
            data.get("timing", {}),
        )
        for rule, status, msg in validations:
            if status == "FAIL":
                tracker.record_violation(session_id, turn_num, rule, msg)

        # Track coverage
        tracker.record_turn(prev_state, inferred_state, session_id)

        # Store turn
        turn_data = {
            "turn": turn_num,
            "human_message": human_msg,
            "bot_response": data.get("response_text", ""),
            "tools_used": data.get("tools_used", []),
            "inferred_state": inferred_state,
            "timing": data.get("timing", {}),
            "validations": [(r, s) for r, s, _ in validations if s != "PASS"],
        }
        turns.append(turn_data)

        prev_state = inferred_state
        state = inferred_state

        if is_done or state == "exit":
            break

        # Delay between turns
        time.sleep(TURN_DELAY)

    tracker.record_session()
    return {"phone": phone, "profile": profile_name, "turns": turns, "total_turns": len(turns)}


# ── Health check ───────────────────────────────────────────────────

def check_health(client: httpx.Client) -> bool:
    try:
        r = client.get(f"{BASE_URL}/health", timeout=10)
        return r.status_code == 200
    except Exception:
        return False


# ── Main ───────────────────────────────────────────────────────────

def main():
    print("╔════════════════════════════════════════════════════════════╗")
    print("║   InmuebleBot — Monte Carlo Mass Test Suite v3            ║")
    print("║   12 perfiles · 16 reglas · 29 edges                      ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    print(f"Target: {BASE_URL}/admin/simulate")
    print(f"Profiles: {len(PROFILES)}")
    print(f"Total sessions: {TOTAL_SESSIONS}")
    print()

    with httpx.Client() as client:
        # Health check
        if not check_health(client):
            print("🔴 API unreachable. Aborting.")
            sys.exit(1)
        print("🟢 API healthy")
        print()

        tracker = CoverageTracker()
        results = []  # list of session results
        last_keepalive = time.time()

        # Phase 1: Calibration (2 quick sessions)
        print("=" * 60)
        print("📌 PHASE 1: Calibration (warm-up + flow check)")
        print("=" * 60)
        for i in range(2):
            profile = PROFILES[i % len(PROFILES)]
            sess = run_session(client, profile, 9990 + i, tracker)
            turns = len(sess.get("turns", []))
            status = "✅" if turns > 0 else "❌"
            print(f"  Calibration {i + 1}: {profile['name']} → {turns} turns {status}")
            results.append(sess)
            time.sleep(SESSION_DELAY)
        print()

        # Phase 2: Main execution
        print("=" * 60)
        print(f"📌 PHASE 2: Main Execution ({TOTAL_SESSIONS} sessions)")
        print("=" * 60)
        session_idx = 2  # Start after calibration

        for pi, profile in enumerate(PROFILES):
            sessions_for_this = PER_PROFILE_SESSIONS.get(pi, 4)
            for si in range(sessions_for_this):
                # Keepalive
                if time.time() - last_keepalive > KEEPALIVE_INTERVAL:
                    check_health(client)
                    last_keepalive = time.time()

                progress_pct = (session_idx / TOTAL_SESSIONS) * 100
                print(f"\n[{session_idx + 1}/{TOTAL_SESSIONS} | {progress_pct:.0f}%] "
                      f"📋 {profile['name']} (session {si + 1}/{sessions_for_this})")

                sess = run_session(client, profile, session_idx + 1000, tracker)
                turns = len(sess.get("turns", []))
                tools_used = set()
                for t in sess.get("turns", []):
                    tools_used.update(t.get("tools_used", []))
                violations = tracker.violations[-5:]  # Show recent
                viol_count = sum(1 for v in tracker.violations if v[0] == hash(sess["phone"]) % 100000)

                status = "✅" if turns > 0 else "❌"
                print(f"  {status} {turns} turns | tools={list(tools_used)[:5]} | "
                      f"violations={viol_count}")

                results.append(sess)
                session_idx += 1
                time.sleep(SESSION_DELAY)

        # Phase 3: Report
        print()
        print("=" * 60)
        print("📌 PHASE 3: Final Report")
        print("=" * 60)
        print()
        print(tracker.report())
        print()

        # Per-profile scores
        print("  Per-Profile Results:")
        print(f"  {'Profile':35s} {'Sessions':>8s} {'Turns':>6s} {'Avg Turns':>9s} {'Fail Rate':>9s}")
        print(f"  {'-'*35} {'-'*8} {'-'*6} {'-'*9} {'-'*9}")
        for profile in PROFILES:
            pname = profile["name"]
            p_sessions = [r for r in results if r.get("profile") == pname]
            total_turns = sum(len(s.get("turns", [])) for s in p_sessions)
            avg_turns = total_turns / max(len(p_sessions), 1)
            p_violations = 0
            for s in p_sessions:
                for t in s.get("turns", []):
                    for v in t.get("validations", []):
                        p_violations += 1
            fail_rate = (p_violations / max(total_turns, 1)) * 100
            print(f"  {pname:35s} {len(p_sessions):>8d} {total_turns:>6d} {avg_turns:>8.1f}  {fail_rate:>8.1f}%")
        print()

        # Violation breakdown
        if tracker.violations:
            print("  Top Violations:")
            rule_counts = {}
            for _, _, rule, _ in tracker.violations:
                rule_counts[rule] = rule_counts.get(rule, 0) + 1
            for rule, count in sorted(rule_counts.items(), key=lambda x: -x[1])[:5]:
                print(f"    {rule:35s} × {count}")
            print()
            print("  Last 10 violations (for debugging):")
            for sid, turn, rule, msg in tracker.violations[-10:]:
                print(f"    session={sid} turn={turn} | {rule}: {msg[:100]}")
        else:
            print("  ✅ ZERO VIOLATIONS — All rules passed across all sessions!")

        print()
        print("=" * 60)
        print("📌 TEST COMPLETE")
        print(f"   Sessions: {tracker.sessions}")
        print(f"   Turns:    {tracker.total_turns}")
        print(f"   Coverage: {tracker.edge_coverage:.1f}%")
        print(f"   Violations: {len(tracker.violations)}")
        print("=" * 60)


if __name__ == "__main__":
    main()
