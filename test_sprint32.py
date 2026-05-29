#!/usr/bin/env python3
"""Test conversation for Sprint 32 — cross-turn context + LLM-first disambiguation.

Uses /simulate/multi endpoint (no WhatsApp needed).
Returns belief state info so you can verify search_history works.

Usage:
    python3 test_sprint32.py                    # against localhost:8000
    python3 test_sprint32.py https://inmueblebot.onrender.com 5960  # against Render
"""

import requests, time, sys, json

BASE  = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
PHONE = sys.argv[2] if len(sys.argv) > 2 else f"test-{int(time.time()) % 10000}"

def msg(text, pause=3):
    """Send message and print response + belief state."""
    print(f"\n{'─'*60}")
    print(f"👤 {text}")
    
    r = requests.post(f"{BASE}/simulate/multi", json={
        "message": text,
        "session_id": PHONE,
        "phone": PHONE,
    }, timeout=45)
    
    if r.status_code != 200:
        print(f"❌ HTTP {r.status_code}: {r.text[:500]}")
        return None
    
    d = r.json()
    reply = d.get("response", "")[:400]
    print(f"🤖 {reply}")
    print(f"   [turn={d.get('turn')} | router={d.get('router')} | "
          f"sel={d.get('selection')} | criteria={d.get('criteria_count')} | "
          f"intents={d.get('active_intents')}]")
    time.sleep(pause)
    return d

print("=" * 60)
print("SPRINT 32 TEST — Cross-turn context + LLM disambiguation")
print(f"Target: {BASE}  |  Session: {PHONE}")
print("=" * 60)

# ── Test 1: bedrooms >= fix ────────────────────────────────────────────────
# "departamento 2 habitaciones en alquiler" should return >=2 bedroom results
print("\n─── TEST 1: bedrooms >= fix ───")
msg("Hola, busco departamento de 2 habitaciones en alquiler en Oberá")

# ── Test 2: search_history (second search, different criteria) ─────────────
# This creates a second search in the ring buffer
print("\n─── TEST 2: search_history ring buffer — second search ───")
msg("también mostrame los de 1 habitación")

# ── Test 3: descriptive reference → LLM disambiguation ─────────────────────
# "el del centro" — if BOTH 1-bed and 2-bed searches have a Centro property,
# the LLM should see both in search_history context and ask to clarify.
print("\n─── TEST 3: descriptive reference → disambiguation ───")
msg("me pasas más detalles del que está en el centro?")

# ── Test 4: fuzzy zone → auto-retry ────────────────────────────────────────
# "terminal de omnibus" — LLM should map to "Terminal" zone naturally.
# If no results, Fallback 3 drops zone filter with note.
print("\n─── TEST 4: fuzzy zone resolution ───")
msg("hay algo cerca de la terminal de omnibus?")

# ── Test 5: cross-criteria guard ───────────────────────────────────────────
# User was looking for 1-2 bedroom apartments. Asking "más barato"
# should respect those criteria — not return a house.
print("\n─── TEST 5: cross-criteria guard — respects 1-2 bedroom ───")
msg("cuál es el más barato de todos?")

# ── Test 6: multi-search context retention ─────────────────────────────────
# Bot should remember BOTH the 1-bed and 2-bed context
print("\n─── TEST 6: multi-search context survives ───")
msg("pasame fotos del más barato de 1 habitación")

print("\n" + "=" * 60)
print("VERIFY MANUALLY:")
print("  ✓ Test 1: Returned >=2 bedroom apartments (not just exactly 2)")
print("  ✓ Test 2: search_history has both 1-bed and 2-bed entries")
print("  ✓ Test 3: LLM asked to clarify WHICH 'centro' property (1-bed vs 2-bed)")
print("     OR: auto-resolved if only one search had a Centro property")
print("  ✓ Test 4: 'terminal de omnibus' mapped to zone or auto-retried with note")
print("  ✓ Test 5: 'más barato' filtered to 1-2 bedroom apartments only")
print("  ✓ Test 6: Bot remembered 1-bedroom context (not overwritten by 2-bed search)")
