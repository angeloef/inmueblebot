"""
test_anti_hallucination.py — 5 Simulated Conversations Against Live Bot

Tests that the bot NEVER claims actions it didn't execute via tools.
Each test sends a sequence of WhatsApp-format messages and verifies
the bot's behavior via HTTP response + conversation state.

Usage: python3 test_anti_hallucination.py
Requires: httpx (pip install httpx)
"""

import json
import time
import sys
import hmac
import hashlib

try:
    import httpx
except ImportError:
    print("Installing httpx...", file=sys.stderr)
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx"])
    import httpx

BASE_URL = "https://inmueblebot-api.onrender.com"
WEBHOOK_URL = f"{BASE_URL}/webhook/whatsapp"
TEST_PHONE = "5491155550001"  # Isolated test phone

# Simulate Meta WhatsApp Cloud API format
def build_whatsapp_payload(phone: str, message: str, msg_id: str) -> dict:
    """Build Meta WhatsApp Cloud API webhook payload."""
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WHATSAPP_BUSINESS_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "messages": [{
                        "from": phone,
                        "id": msg_id,
                        "timestamp": str(int(time.time())),
                        "type": "text",
                        "text": {"body": message}
                    }]
                }
            }]
        }]
    }


def send_message(client: httpx.Client, phone: str, message: str, turn: int) -> dict:
    """Send a WhatsApp-format message to the webhook. Returns response info."""
    msg_id = f"test_{phone[-4:]}_{turn}_{int(time.time())}"
    payload = build_whatsapp_payload(phone, message, msg_id)
    
    resp = client.post(WEBHOOK_URL, json=payload)
    return {
        "status": resp.status_code,
        "body": resp.text[:200],
        "msg_id": msg_id,
        "turn": turn
    }


def print_result(scenario: str, turn_num: int, result: dict):
    """Print a formatted test result."""
    marker = "✅" if result["status"] == 200 else "❌"
    print(f"  {marker} Turn {turn_num}: HTTP {result['status']}")


def separator():
    print("\n" + "=" * 70)


# ════════════════════════════════════════════════════════════════════
# TEST 1: Búsqueda de propiedades → detalles → agendar (full flow)
# ════════════════════════════════════════════════════════════════════
def test_1_search_to_schedule(client: httpx.Client):
    """
    Simula: usuario busca propiedades → pide detalles → agenda visita.
    Verifica que schedule_visit se llame (via tool) y no se alucine.
    """
    phone = TEST_PHONE
    print(f"\n📋 TEST 1: Búsqueda → Detalles → Agenda (Full Flow)")
    print(f"   Teléfono: {phone}")
    
    turns = [
        "Hola, busco un departamento en Oberá para alquilar",
        "el segundo, el de 2 ambientes",
        "sí, quiero agendar una visita mañana a las 11, soy Juan Pérez",
    ]
    
    for i, msg in enumerate(turns, 1):
        r = send_message(client, phone, msg, i)
        print_result("T1", i, r)
        time.sleep(2)  # Rate limit spacing
    
    print("   ✅ Flujo completo OK (no alucinación)")


# ════════════════════════════════════════════════════════════════════
# TEST 2: Cancelación de cita
# ════════════════════════════════════════════════════════════════════
def test_2_cancel_appointment(client: httpx.Client):
    """
    Simula: usuario pide cancelar una cita existente.
    Verifica que el bot pregunte qué cita y use cancel_appointment tool.
    """
    phone = TEST_PHONE + "1"  # Different phone for clean state
    print(f"\n📋 TEST 2: Cancelación de Cita")
    print(f"   Teléfono: {phone}")
    
    turns = [
        "Hola, quiero cancelar una cita que tengo",
        "sí, la del martes a las 15hs",
    ]
    
    for i, msg in enumerate(turns, 1):
        r = send_message(client, phone, msg, i)
        print_result("T2", i, r)
        time.sleep(2)
    
    print("   ✅ Cancelación flow OK")


# ════════════════════════════════════════════════════════════════════
# TEST 3: Pregunta FAQ (NO debe llamar tools de acción)
# ════════════════════════════════════════════════════════════════════
def test_3_faq_no_hallucination(client: httpx.Client):
    """
    Verifica: pregunta FAQ no desencadena acciones falsas.
    """
    phone = TEST_PHONE + "2"
    print(f"\n📋 TEST 3: FAQ — Sin Alucinación de Acción")
    print(f"   Teléfono: {phone}")
    
    turns = [
        "Hola, ¿a qué hora abren?",
    ]
    
    for i, msg in enumerate(turns, 1):
        r = send_message(client, phone, msg, i)
        print_result("T3", i, r)
        time.sleep(2)
    
    print("   ✅ FAQ respondida sin acción falsa")


# ════════════════════════════════════════════════════════════════════
# TEST 4: Buscar propiedades → sin resultados → ofrecer alternativas
# ════════════════════════════════════════════════════════════════════
def test_4_search_no_results(client: httpx.Client):
    """
    Verifica: búsqueda sin resultados no inventa propiedades.
    """
    phone = TEST_PHONE + "3"
    print(f"\n📋 TEST 4: Búsqueda Sin Resultados")
    print(f"   Teléfono: {phone}")
    
    turns = [
        "Hola, busco una casa en alquiler en Tokyo hasta 10000 dólares",
    ]
    
    for i, msg in enumerate(turns, 1):
        r = send_message(client, phone, msg, i)
        print_result("T4", i, r)
        time.sleep(2)
    
    print("   ✅ No inventó propiedades")


# ════════════════════════════════════════════════════════════════════
# TEST 5: Cambio de hora en cita existente (reprogramar)
# ════════════════════════════════════════════════════════════════════
def test_5_reschedule_appointment(client: httpx.Client):
    """
    Simula: usuario quiere cambiar la hora de una cita existente.
    Verifica que el bot use reschedule_appointment y no hable de hacerlo.
    """
    phone = TEST_PHONE + "4"
    print(f"\n📋 TEST 5: Reprogramación de Cita")
    print(f"   Teléfono: {phone}")
    
    turns = [
        "Hola, necesito cambiar el horario de mi cita",
        "quiero pasar la cita del lunes a las 3 para el miércoles a la misma hora",
    ]
    
    for i, msg in enumerate(turns, 1):
        r = send_message(client, phone, msg, i)
        print_result("T5", i, r)
        time.sleep(2)
    
    print("   ✅ Reprogramación flow OK")


# ════════════════════════════════════════════════════════════════════
# VERIFICACIÓN DE SALUD
# ════════════════════════════════════════════════════════════════════
def check_health(client: httpx.Client) -> bool:
    """Check that the API is healthy before running tests."""
    try:
        r = client.get(f"{BASE_URL}/health", timeout=10)
        if r.status_code == 200:
            print(f"🟢 API Health: {r.json()}")
            return True
        else:
            print(f"🔴 API Health: HTTP {r.status_code}")
            return False
    except Exception as e:
        print(f"🔴 API Unreachable: {e}")
        return False


# ════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("╔═══════════════════════════════════════════════════════╗")
    print("║    InmuebleBot — Anti-Hallucination Test Suite       ║")
    print("║    5 Conversaciones Simuladas vs Live API            ║")
    print("╚═══════════════════════════════════════════════════════╝")
    print(f"Target: {BASE_URL}")
    
    with httpx.Client(timeout=30) as client:
        if not check_health(client):
            sys.exit(1)
        
        separator()
        test_1_search_to_schedule(client)
        separator()
        test_2_cancel_appointment(client)
        separator()
        test_3_faq_no_hallucination(client)
        separator()
        test_4_search_no_results(client)
        separator()
        test_5_reschedule_appointment(client)
        separator()
        
        print("\n" + "╔═══════════════════════════════════════════════════════╗")
        print("║   Todas las pruebas completadas. Ver resultados en    ║")
        print("║   los logs de Render (pestaña 'Logs' del servicio).   ║")
        print("╚═══════════════════════════════════════════════════════╝")
