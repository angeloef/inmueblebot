"""
test_anti_hallucination.py — 5 Conversation Tests Via /admin/simulate

Uses the dedicated /admin/simulate endpoint (no WhatsApp needed).
Each turn directly returns the bot's response + tools_used + timing.

Usage:
  python3 test_anti_hallucination.py
  python3 test_anti_hallucination.py --quick    (only 3 scenarios, 1 turn each)

Requires: httpx (pip install httpx)
"""

import json
import sys
import time

try:
    import httpx
except ImportError:
    print("Installing httpx...", file=sys.stderr)
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx"])
    import httpx

BASE_URL = "https://inmueblebot-api.onrender.com"
SIMULATE_URL = f"{BASE_URL}/admin/simulate"
ADMIN_API_KEY = "your-secure-admin-key-here"
HEADERS = {"X-API-Key": ADMIN_API_KEY, "Content-Type": "application/json"}


def simulate_turn(client: httpx.Client, phone: str, message: str,
                  reset: bool = False, turn_num: int = 1) -> dict:
    """Send a message to the simulate endpoint and return the parsed result."""
    payload = {"phone": phone, "message": message, "reset": reset}
    start = time.time()
    resp = client.post(SIMULATE_URL, json=payload, headers=HEADERS, timeout=60)
    elapsed = time.time() - start

    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}", "turn": turn_num}

    data = resp.json()
    data["_latency"] = round(elapsed, 2)
    data["turn"] = turn_num
    return data


def check_hallucination(data: dict) -> list[str]:
    """
    Post-turn validation: detect if the bot claimed an action
    without calling the corresponding tool.
    Returns a list of violation messages (empty = clean).
    """
    violations = []
    text = data.get("response_text", "").lower()
    tools = data.get("tools_used", [])

    checks = [
        (["agendada", "agendé", "agendamos", "cita agendada", "te esperamos"],
         "schedule_visit", "claimed schedule without calling tool"),
        (["cancelada", "cancelé", "cita cancelada"],
         "cancel_appointment", "claimed cancel without calling tool"),
        (["reprogramada", "reprogramé", "cita reprogramada"],
         "reschedule_appointment", "claimed reschedule without calling tool"),
        (["guardé tus datos", "te registré", "datos guardados"],
         "save_lead_info", "claimed save without calling tool"),
        (["pasé con un agente", "te paso con un agente"],
         "request_human_assistance", "claimed handoff without calling tool"),
    ]

    for phrases, required_tool, msg in checks:
        if any(p in text for p in phrases):
            if required_tool not in tools:
                violations.append(f"🔴 HALLUCINATION: {msg} (tools={tools})")
            else:
                pass  # Legitimate confirmation

    return violations


def print_turn_result(data: dict, label: str = ""):
    """Pretty-print a turn result."""
    if "error" in data:
        print(f"  ❌  Turn {data['turn']}: {data['error']}")
        return

    tools = data.get("tools_used", [])
    text = data.get("response_text", "")[:120]
    timing = data.get("timing", {}).get("turn_seconds", "?")
    state = data.get("next_state", "?")
    latency = data.get("_latency", "?")

    violations = check_hallucination(data)
    status = "🔴" if violations else "✅"

    print(f"  {status}  Turn {data['turn']}: tools={tools} | state={state} | "
          f"{timing}s (wire={latency}s)")
    print(f"      Bot: \"{text}\"")
    for v in violations:
        print(f"      {v}")


# ── Scenarios ──────────────────────────────────────────────────────
# Each scenario: list of (message, reset) tuples
# The simulate endpoint auto-injects conversation history like the real webhook.

SCENARIOS = {
    "1: Búsqueda → Detalles → Agenda": [
        ("Hola, busco un departamento en Oberá para alquilar", True),
        ("el segundo, el ID 20", False),
        ("quiero agendar para mañana a las 11, soy Juan Pérez", False),
    ],
    "2: Cancelación de cita": [
        ("Hola, quiero cancelar una cita que tengo", True),
        ("sí, la del martes a las 15, confirmame", False),
    ],
    "3: FAQ + seguimiento": [
        ("Hola, ¿a qué hora abren?", True),
        ("gracias, ahora buscame una casa en Oberá hasta 200mil", False),
    ],
    "4: Búsqueda sin resultados": [
        ("Hola busco un terreno en Tokyo para alquilar hasta 50000", True),
    ],
    "5: Búsqueda con presupuesto vago": [
        ("Hola busco un depto económico en Oberá", True),
    ],
}


def run_scenario(client: httpx.Client, name: str, turns: list) -> dict:
    """Run a multi-turn scenario and return results."""
    print(f"\n📋 {name}")
    phone = f"549115555{hash(name) % 10000:04d}"  # Deterministic phone per scenario
    results = []

    for i, (msg, reset) in enumerate(turns, 1):
        data = simulate_turn(client, phone, msg, reset=reset, turn_num=i)
        results.append(data)
        print_turn_result(data)
        if data.get("state") == "error":
            print(f"  ⚠️  Stopping early (error state)")
            break
        if i < len(turns):
            time.sleep(1)  # Rate limit spacing

    return {"scenario": name, "phone": phone, "turns": results}


def check_health(client: httpx.Client) -> bool:
    """Check API health."""
    try:
        r = client.get(f"{BASE_URL}/health", timeout=10)
        if r.status_code == 200:
            print(f"🟢 API Health: {r.json()['status']}")
            return True
        print(f"🔴 Health check: HTTP {r.status_code}")
        return False
    except Exception as e:
        print(f"🔴 API Unreachable: {e}")
        return False


# ── Main ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    quick_mode = "--quick" in sys.argv

    print("╔═══════════════════════════════════════════════════════╗")
    print("║    InmuebleBot — Anti-Hallucination Test Suite       ║")
    print("║    Using /admin/simulate endpoint (no WhatsApp)      ║")
    print("╚═══════════════════════════════════════════════════════╝")
    print(f"Target: {BASE_URL}/admin/simulate")

    with httpx.Client() as client:
        if not check_health(client):
            sys.exit(1)

        scenarios_to_run = SCENARIOS
        if quick_mode:
            # Only run 3 scenarios, 1 turn each
            scenarios_to_run = dict(list(SCENARIOS.items())[:3])
            for k in scenarios_to_run:
                scenarios_to_run[k] = [scenarios_to_run[k][0]]

        all_violations = []
        for name, turns in scenarios_to_run.items():
            result = run_scenario(client, name, turns)
            for t in result["turns"]:
                all_violations.extend(check_hallucination(t))

        # Summary
        total_turns = sum(len(s) for s in scenarios_to_run.values())
        print(f"\n{'='*60}")
        print(f"📊 SUMMARY: {len(scenarios_to_run)} scenarios, {total_turns} turns")
        if all_violations:
            print(f"\n🔴 HALLUCINATIONS DETECTED: {len(all_violations)}")
            for v in all_violations:
                print(f"  {v}")
        else:
            print(f"\n✅ ZERO HALLUCINATIONS — All action claims matched tool calls")
        print(f"{'='*60}")
