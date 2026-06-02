#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
"""
InmuebleBot — Stress Test Suite
================================
Tests de conversación no-lineales que simulan usuarios reales:
topic-jumping, referencias ambiguas, multi-intent, out-of-scope, escalación.

Endpoint: POST /simulate/multi  (no requiere auth)

Uso:
  python tests/stress_test.py                       # todos los escenarios
  python tests/stress_test.py --list                # listar escenarios disponibles
  python tests/stress_test.py --only s1 s3 s7       # solo esos escenarios
  python tests/stress_test.py --skip s4 s5          # saltar esos
  python tests/stress_test.py --verbose             # muestra respuesta completa
  python tests/stress_test.py --delay 2             # segundos entre turnos (default: 1)
  python tests/stress_test.py --output results.json # guardar resultados

Env:
  INMUEBLEBOT_API_URL  default: https://inmueblebot-api.onrender.com
"""

import json
import sys
import time
import os
import argparse
import urllib.request
import urllib.error
import uuid
from dataclasses import dataclass, field
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────
API_URL = os.getenv("INMUEBLEBOT_API_URL", "https://inmueblebot-api.onrender.com").rstrip("/")
ENDPOINT = f"{API_URL}/simulate/multi"
DEFAULT_DELAY = 1  # segundos entre turnos de la misma conversación

# ── Terminal colors ───────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BLUE   = "\033[94m"
MAGENTA= "\033[95m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def ok(s):      return f"{GREEN}{s}{RESET}"
def fail(s):    return f"{RED}{s}{RESET}"
def warn(s):    return f"{YELLOW}{s}{RESET}"
def info(s):    return f"{CYAN}{s}{RESET}"
def dim(s):     return f"{DIM}{s}{RESET}"
def bold(s):    return f"{BOLD}{s}{RESET}"
def magenta(s): return f"{MAGENTA}{s}{RESET}"


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Turn:
    user: str
    # Assertions — todas opcionales
    expect_tools: list[str] = field(default_factory=list)       # tools que DEBEN aparecer
    forbid_tools: list[str] = field(default_factory=list)       # tools que NO deben aparecer
    expect_router: Optional[str] = None                         # "s1", "s2", "rapport", etc.
    response_contains: list[str] = field(default_factory=list)  # frases esperadas (case-insensitive)
    response_not_contains: list[str] = field(default_factory=list)
    min_confidence: Optional[float] = None
    note: str = ""  # descripción del comportamiento esperado


@dataclass
class Scenario:
    id: str
    name: str
    description: str
    turns: list[Turn]
    phone: str = ""         # se genera automáticamente si está vacío
    session_id: str = ""    # se genera automáticamente si está vacío


# ── Escenarios ────────────────────────────────────────────────────────────────

SCENARIOS: list[Scenario] = [

    # ── S1: Indeciso que salta entre tipos de propiedad ───────────────────────
    Scenario(
        id="s1",
        name="Indeciso con topic-jumping entre tipos",
        description=(
            "Usuario que empieza buscando depto, de repente pregunta por terrenos, "
            "vuelve al depto y termina pidiendo casas. Verifica que el bot no mezcle "
            "los criterios entre búsquedas."
        ),
        turns=[
            Turn(
                user="buenas, estoy buscando un departamento para alquilar en oberá",
                note="Saludo + criterio. El bot puede buscar directo o pedir más info.",
            ),
            Turn(
                user="2 ambientes, zona centro, no sé el presupuesto todavía",
                expect_tools=["search_properties"],
                note="Suficientes criterios (tipo+op+zona+ambientes) → debe buscar sin bloquear por presupuesto",
            ),
            Turn(
                user="che, una pregunta aparte — ¿tienen terrenos en venta? me preguntó un amigo",
                expect_tools=["search_properties"],
                note="Topic jump: terrenos venta. Debe buscar terrenos, NO mezclar con la búsqueda anterior",
            ),
            Turn(
                user="ok gracias, pero volviendo a lo mío — ¿qué departamentos había?",
                note="Regreso al contexto anterior. Bot debe retomar los deptos, no repetir la búsqueda innecesariamente",
            ),
            Turn(
                user="sabés qué, mejor miremos casas en alquiler, algo más grande",
                expect_tools=["search_properties"],
                note="Otro salto: casas alquiler. Debe resetear criterios de tipo pero mantener zona/operación",
            ),
            Turn(
                user="la primera que salió, ¿tiene fotos?",
                expect_tools=["get_property_images"],
                note="Referencia por posición 'la primera'. Debe resolver a la prop activa de casas",
            ),
        ],
    ),

    # ── S2: Agendamiento con arrepentimiento y cancelación ────────────────────
    Scenario(
        id="s2",
        name="Agendamiento → cambio de fecha → cancelación",
        description=(
            "Usuario busca, completa una reserva (confirmación → booking automático), "
            "interrumpe con una pregunta de detalles, reagenda y cancela. "
            "NOTA: el flujo real reserva con schedule_visit recién en la confirmación."
        ),
        turns=[
            Turn(
                user="hola quiero alquilar un depto en oberá, 2 ambientes, hasta 80 mil pesos",
                expect_tools=["search_properties"],
                note="Búsqueda con todos los criterios",
            ),
            Turn(
                user="me interesa el primero, ¿lo puedo ir a ver?",
                note="Interés en visita. Bot pasa a recolectar día/nombre. Sin tool aún.",
            ),
            Turn(
                user="espera, antes ¿tiene garaje el depto?",
                expect_tools=["get_property_details"],
                note="Interrupción con pregunta de detalles a mitad del flujo (FIX 3).",
            ),
            Turn(
                user="ok dale. el jueves que viene a las 10, a nombre de Juan Pérez",
                note="Da día+hora+nombre. Bot arma la confirmación (awaiting=scheduling_confirm). Sin booking todavía.",
            ),
            Turn(
                user="sí, confirmo",
                expect_tools=["schedule_visit"],
                note="Confirmación → booking automático real (schedule_visit).",
            ),
            Turn(
                user="che, cambiala para el viernes a las 15",
                expect_tools=["reschedule_appointment"],
                note="Reagendar la cita ya existente.",
            ),
            Turn(
                user="no, mejor cancelala, me salió algo",
                expect_tools=["cancel_appointment"],
                note="Cancelación de la cita.",
            ),
        ],
    ),

    # ── S3: Out-of-scope x2 con regreso al tema ───────────────────────────────
    Scenario(
        id="s3",
        name="Pedidos fuera de alcance y regreso al tema",
        description=(
            "Usuario mezcla pedidos ridículos (pizza, matemáticas) con búsqueda real. "
            "Verifica que el bot rechace fuera-de-alcance consistentemente y retome "
            "el hilo inmobiliario sin perder contexto."
        ),
        turns=[
            Turn(
                user="hola",
                expect_router="rapport",
                note="Saludo simple → respuesta de bienvenida",
            ),
            Turn(
                user="me das una receta de pizza margarita paso a paso?",
                response_not_contains=["harina", "tomate", "queso", "hornear"],
                note="Out-of-scope: receta. Bot debe redirigir sin dar la receta",
            ),
            Turn(
                user="jajaja no, en serio, busco un terreno para comprar en oberá",
                expect_tools=["search_properties"],
                note="Regreso al tema. Debe buscar terrenos venta sin pedir más info innecesaria",
            ),
            Turn(
                user="¿cuánto es 15% de 2 millones? para saber si me alcanza para la seña",
                response_not_contains=["300.000", "300000", "300 mil"],
                note="Out-of-scope disfrazado de contexto. Bot NO debe calcular (FIX 2).",
            ),
            Turn(
                user="bueno no importa, ¿me mostrás los detalles del más barato?",
                expect_tools=["get_property_details"],
                note="Ref. relativa 'el más barato'. Debe identificarlo de los resultados anteriores",
            ),
            Turn(
                user="¿me podés ayudar a redactar un mail para ofrecerle al dueño?",
                response_not_contains=["Estimado", "Me dirijo", "adjunto"],
                note="Out-of-scope: redacción de mail. Debe rechazar y ofrecer alternativa inmobiliaria",
            ),
        ],
    ),

    # ── S4: Multi-intent en un solo mensaje ───────────────────────────────────
    Scenario(
        id="s4",
        name="Multi-intent simultáneo: fotos + agenda en un mensaje",
        description=(
            "Usuario pide fotos Y agenda una visita en el MISMO mensaje. "
            "Verifica que el bot llame ambas tools sin pedir confirmación intermedia."
        ),
        turns=[
            Turn(
                user="necesito departamento en alquiler en oberá, 2 ambientes, centro, hasta 90 mil",
                expect_tools=["search_properties"],
                note="Búsqueda base",
            ),
            Turn(
                user="perfecto, del primero quiero ver las fotos y también agendarme una visita",
                expect_tools=["get_property_images"],
                note="Multi-intent (FIX 6): muestra fotos Y arranca el flujo de agenda.",
            ),
            Turn(
                user="el lunes a las 11, a nombre de Ana López",
                note="Da día+hora+nombre → confirmación. Booking recién en el sí.",
            ),
            Turn(
                user="dale, confirmo",
                expect_tools=["schedule_visit"],
                note="Confirmación → booking automático (schedule_visit).",
            ),
        ],
    ),

    # ── S5: Presupuesto esquivo y cambiante ───────────────────────────────────
    Scenario(
        id="s5",
        name="Criterios contradictorios y presupuesto cambiante",
        description=(
            "Usuario cambia el presupuesto dos veces y también cambia de compra a alquiler. "
            "Verifica que el bot adapte la búsqueda sin quedarse con criterios viejos."
        ),
        turns=[
            Turn(
                user="busco casa para comprar en oberá",
                note="Criterios incompletos: faltan zona específica y presupuesto → bot debe preguntar",
            ),
            Turn(
                user="tengo 20 millones de presupuesto, zona sur o lo que haya",
                expect_tools=["search_properties"],
                note="Con presupuesto → busca. 'Lo que haya' = zona flexible",
            ),
            Turn(
                user="se me olvidó decirte, en realidad tengo 35 millones, ¿cambia mucho?",
                expect_tools=["search_properties"],
                note="Presupuesto cambia hacia arriba. Bot debe re-buscar con nuevo presupuesto",
            ),
            Turn(
                user="¿y si mejor alquilo en vez de comprar? ¿qué hay?",
                expect_tools=["search_properties"],
                note="Cambio de operación: compra → alquiler. Nuevo search con operación diferente",
            ),
            Turn(
                user="no no, mejor compro, olvidate del alquiler",
                note="Vuelve a compra. Bot debe retomar los resultados de compra o re-buscar",
            ),
            Turn(
                user="mostrame los detalles de la primera de compra",
                expect_tools=["get_property_details"],
                note="Ref. posicional sobre los resultados de compra → detalles.",
            ),
        ],
    ),

    # ── S6: El olvidadizo que repite preguntas ────────────────────────────────
    Scenario(
        id="s6",
        name="Usuario olvidadizo con preguntas repetidas",
        description=(
            "Simula un usuario mayor o distraído que pregunta lo mismo varias veces "
            "y hace referencias a cosas que el bot ya contestó. "
            "Verifica coherencia del bot sin repetir búsquedas innecesarias."
        ),
        turns=[
            Turn(
                user="hola buenos días, quiero alquilar un departamento",
                note="Inicio de conversación",
            ),
            Turn(
                user="en oberá, 2 ambientes, hasta 70 mil pesos",
                expect_tools=["search_properties"],
                note="Criterios completos → busca",
            ),
            Turn(
                user="¿y cuáles son las opciones que tengo?",
                note="Ya se mostraron. Bot debe retomar sin re-buscar (o resumir lo anterior)",
            ),
            Turn(
                user="¿cuánto sale el primero?",
                note="Precio del primero — ya estaba en los resultados. Bot debe responder sin tool call",
            ),
            Turn(
                user="¿me lo repetís? no me acordé bien el precio",
                note="Pide repetición. Bot debe responder sin llamar search_properties de nuevo",
                forbid_tools=["search_properties"],
            ),
            Turn(
                user="¿qué propiedades me mostraste antes?",
                note="Pide resumen del contexto. Bot debe listar sin llamar herramientas",
                forbid_tools=["search_properties"],
            ),
            Turn(
                user="bueno, quiero ver fotos del primero",
                expect_tools=["get_property_images"],
                note="Acción nueva: fotos. Esta sí justifica tool call",
            ),
        ],
    ),

    # ── S7: Usuario frustrado → escalación ───────────────────────────────────
    Scenario(
        id="s7",
        name="Usuario frustrado que exige hablar con humano",
        description=(
            "Usuario que llega irritado, da criterios de mala gana, y termina "
            "exigiendo un humano. Verifica que el bot maneje la escalación "
            "correctamente sin ponerse defensivo."
        ),
        turns=[
            Turn(
                user="hola",
                note="Saludo neutro",
            ),
            Turn(
                user="ya les mandé un mensaje antes y nadie me respondió, necesito un departamento urgente",
                note="Frustración inicial. Bot debe reconocer sin excusas y ponerse a ayudar",
            ),
            Turn(
                user="depto, alquiler, 2 ambientes, oberá, no me preguntes más",
                expect_tools=["search_properties"],
                note="Criterios agresivos. Bot debe buscar sin hacer más preguntas",
            ),
            Turn(
                user="todo caro, no sirve nada, quiero hablar con una persona real ya",
                expect_tools=["request_human_assistance"],
                note="Escalación explícita. Bot debe activar handoff, no intentar convencerlo de quedarse",
            ),
            Turn(
                user="¿y cuándo me llaman?",
                note="Post-escalación: pregunta de seguimiento. Bot debe gestionar expectativas",
            ),
        ],
    ),

    # ── S8: FAQ interrumpiendo búsqueda activa ────────────────────────────────
    Scenario(
        id="s8",
        name="FAQs interrumpiendo flujo de búsqueda activo",
        description=(
            "Usuario interrumpe la búsqueda con tres preguntas de FAQ seguidas "
            "y luego retoma la conversación original. "
            "Verifica que el bot responda las FAQs y luego retome el contexto."
        ),
        turns=[
            Turn(
                user="busco departamento en alquiler, 2 ambientes, zona centro oberá",
                expect_tools=["search_properties"],
                note="Búsqueda inicial completa",
            ),
            Turn(
                user="espera antes de seguir — ¿cuánto cobran de comisión?",
                expect_tools=["get_faq_answer"],
                note="FAQ de comisión. Debe responder con get_faq_answer",
            ),
            Turn(
                user="y los contratos de alquiler, ¿son de 3 años obligatorio?",
                expect_tools=["get_faq_answer"],
                note="FAQ legal. Debe responder correctamente",
            ),
            Turn(
                user="¿tienen servicio de administración de alquileres?",
                expect_tools=["get_faq_answer"],
                note="FAQ de servicio. Tercera FAQ consecutiva",
            ),
            Turn(
                user="ok perfecto, ¿y los deptos que me mostrabas?",
                note="Retoma búsqueda. Bot debe recuperar el contexto de los resultados anteriores",
            ),
            Turn(
                user="quiero ver el segundo, ¿tiene fotos?",
                expect_tools=["get_property_images"],
                note="Ref. relativa post-FAQ. Debe resolver 'el segundo' de los resultados del inicio",
            ),
        ],
    ),

    # ── S9: Referencia ambigua y navegación por posición ──────────────────────
    Scenario(
        id="s9",
        name="Referencias ambiguas: 'esa', 'la segunda', 'el más barato'",
        description=(
            "Usuario nunca usa IDs de propiedades — siempre referencias relativas. "
            "Verifica que el bot resuelva correctamente posición y contexto "
            "sin pedir aclaración innecesaria cuando el contexto es claro."
        ),
        turns=[
            Turn(
                user="quiero alquilar un depto en oberá, 2 ambientes, hasta 80 mil",
                expect_tools=["search_properties"],
                note="Búsqueda base para tener propiedades en contexto",
            ),
            Turn(
                user="¿esa tiene cochera?",
                note="Ref. ambigua 'esa' con múltiples resultados. Bot debe pedir aclaración",
            ),
            Turn(
                user="la primera que salió",
                expect_tools=["get_property_details"],
                note="Aclaración de la ref. Bot debe resolver a la primera propiedad",
            ),
            Turn(
                user="¿y la segunda?",
                expect_tools=["get_property_details"],
                note="Ref. posicional. Bot resuelve sin preguntar",
            ),
            Turn(
                user="¿cuál es la más barata?",
                note="Ref. superlativa. Bot debe identificar la de menor precio de los resultados",
            ),
            Turn(
                user="mostrame las fotos de esa",
                expect_tools=["get_property_images"],
                note="'Esa' refiere a 'la más barata'; pedido explícito de fotos.",
            ),
        ],
    ),

    # ── S10: Decisión de compra → recomendación → agenda ─────────────────────
    Scenario(
        id="s10",
        name="Decisión de compra, recomendación y agenda",
        description=(
            "Usuario ve opciones, pide detalles, pide recomendación, "
            "elige la 'peor' según el bot, pide fotos y completa una visita. "
            "Verifica el flujo completo de decisión de compra."
        ),
        turns=[
            Turn(
                user="busco departamento o casa para comprar en oberá, tengo 30 millones",
                expect_tools=["search_properties"],
                note="Búsqueda con tipo flexible (depto o casa)",
            ),
            Turn(
                user="mostrame los detalles de la primera",
                expect_tools=["get_property_details"],
                note="Ref. posicional → detalles de la primera.",
            ),
            Turn(
                user="¿cuál me recomendarías vos?",
                note="Pedido de recomendación subjetiva. Bot debe responder con criterio, no evadir",
            ),
            Turn(
                user="entiendo, pero voy con la que no recomendaste",
                note="Usuario elige la opción no recomendada. Bot debe aceptar sin juzgar",
            ),
            Turn(
                user="ok, mostrame fotos",
                expect_tools=["get_property_images"],
                note="Fotos de la propiedad activa (la que eligió, no la recomendada)",
            ),
            Turn(
                user="me convencí, ¿cómo la visito?",
                note="Interés en visita. Bot debe pedir día/nombre.",
            ),
            Turn(
                user="el próximo miércoles a las 16, a nombre de Carlos Gómez",
                note="Da día+hora+nombre → confirmación. Booking recién en el sí.",
            ),
            Turn(
                user="sí, dale, confirmo",
                expect_tools=["schedule_visit"],
                note="Confirmación → booking automático (schedule_visit).",
            ),
        ],
    ),
]


# ── HTTP client ───────────────────────────────────────────────────────────────

def call_simulate(message: str, session_id: str, phone: str) -> dict:
    payload = json.dumps({
        "message": message,
        "session_id": session_id,
        "phone": phone,
    }).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"error": f"HTTP {e.code}: {body[:300]}"}
    except urllib.error.URLError as e:
        return {"error": f"URLError: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


# ── Assertion checker ─────────────────────────────────────────────────────────

@dataclass
class AssertionResult:
    passed: bool
    failures: list[str]


def check_assertions(turn: Turn, resp: dict) -> AssertionResult:
    failures = []
    tools = resp.get("tools_called", [])
    response_text = (resp.get("response") or "").lower()
    router = resp.get("router", "")
    confidence = resp.get("confidence", 1.0)

    for t in turn.expect_tools:
        if t not in tools:
            failures.append(f"expected tool '{t}' but got {tools or '[]'}")

    for t in turn.forbid_tools:
        if t in tools:
            failures.append(f"forbidden tool '{t}' was called")

    if turn.expect_router and turn.expect_router.lower() not in router.lower():
        failures.append(f"expected router '{turn.expect_router}' but got '{router}'")

    for phrase in turn.response_contains:
        if phrase.lower() not in response_text:
            failures.append(f"expected phrase not found: '{phrase}'")

    for phrase in turn.response_not_contains:
        if phrase.lower() in response_text:
            failures.append(f"forbidden phrase found: '{phrase}'")

    if turn.min_confidence is not None and confidence < turn.min_confidence:
        failures.append(f"confidence {confidence:.2f} < min {turn.min_confidence:.2f}")

    return AssertionResult(passed=len(failures) == 0, failures=failures)


# ── Reporter ──────────────────────────────────────────────────────────────────

def print_turn(
    turn_num: int,
    turn: Turn,
    resp: dict,
    assertion: AssertionResult,
    verbose: bool,
):
    status = ok("✓") if assertion.passed else fail("✗")
    router  = resp.get("router", "?")
    latency = resp.get("latency_ms", 0)
    tools   = resp.get("tools_called", [])
    confidence = resp.get("confidence", 0)

    router_color = CYAN if "s1" in router or "rapport" in router or "faq" in router else BLUE
    tools_str = ", ".join(tools) if tools else dim("—")
    meta = dim(f"  {latency:.0f}ms  conf:{confidence:.2f}")
    router_str = f"{router_color}{router}{RESET}"

    print(f"  {status} T{turn_num}  {dim('[')}{router_str}{meta}{dim(']')}")
    print(f"     {BOLD}U:{RESET} {turn.user[:80]}{'…' if len(turn.user)>80 else ''}")

    resp_text = resp.get("response") or resp.get("error") or ""
    if verbose:
        print(f"     {BOLD}B:{RESET} {resp_text}")
    else:
        print(f"     {BOLD}B:{RESET} {resp_text[:100]}{'…' if len(resp_text)>100 else ''}")

    if tools:
        print(f"     {BOLD}T:{RESET} {magenta(tools_str)}")

    if turn.note:
        print(f"     {dim(f'↳ {turn.note}')}")

    for f in assertion.failures:
        print(f"     {fail(f'  ✗ ASSERT: {f}')}")

    print()


def print_scenario_header(scenario: Scenario, idx: int, total: int):
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}[{idx}/{total}] {scenario.id.upper()} — {scenario.name}{RESET}")
    print(f"{dim(scenario.description[:120])}")
    print(f"{'─'*60}")


def print_scenario_footer(passed_turns: int, total_turns: int, elapsed: float):
    pct = passed_turns / total_turns * 100 if total_turns else 0
    color = GREEN if pct == 100 else (YELLOW if pct >= 60 else RED)
    print(f"  Resultado: {color}{passed_turns}/{total_turns} turnos OK{RESET}  ({elapsed:.1f}s)")


def print_summary(results: list[dict]):
    print(f"\n{BOLD}{'═'*60}{RESET}")
    print(f"{BOLD}RESUMEN FINAL{RESET}")
    print(f"{'═'*60}")

    total_scenarios = len(results)
    passed_scenarios = sum(1 for r in results if r["failed_turns"] == 0)
    total_turns = sum(r["total_turns"] for r in results)
    passed_turns = sum(r["passed_turns"] for r in results)
    total_time = sum(r["elapsed_s"] for r in results)

    for r in results:
        all_ok = r["failed_turns"] == 0
        marker = ok("✓") if all_ok else fail("✗")
        print(f"  {marker} {r['id']:<6} {r['name'][:40]:<40} "
              f"{r['passed_turns']}/{r['total_turns']} turnos  "
              f"{r['elapsed_s']:.1f}s")

    print(f"\n  Escenarios: {ok(passed_scenarios)}/{total_scenarios}  |  "
          f"Turnos: {ok(passed_turns)}/{total_turns}  |  "
          f"Tiempo total: {total_time:.1f}s")

    if passed_scenarios == total_scenarios:
        print(f"\n  {ok(BOLD + '🟢  TODOS LOS ESCENARIOS PASARON' + RESET)}")
    else:
        failed = total_scenarios - passed_scenarios
        print(f"\n  {fail(BOLD + f'🔴  {failed} ESCENARIO(S) CON FALLAS' + RESET)}")


# ── Runner ────────────────────────────────────────────────────────────────────

def run_scenario(scenario: Scenario, verbose: bool, delay: float) -> dict:
    session_id = scenario.session_id or f"stress-{scenario.id}-{uuid.uuid4().hex[:8]}"
    phone      = scenario.phone or f"549-stress-{scenario.id}"

    passed_turns = 0
    total_turns  = len(scenario.turns)
    turn_results = []
    t0 = time.time()

    for i, turn in enumerate(scenario.turns, start=1):
        resp = call_simulate(turn.user, session_id, phone)
        assertion = check_assertions(turn, resp)

        if assertion.passed:
            passed_turns += 1

        print_turn(i, turn, resp, assertion, verbose)
        turn_results.append({
            "turn": i,
            "user": turn.user,
            "response": resp.get("response", ""),
            "tools_called": resp.get("tools_called", []),
            "router": resp.get("router", ""),
            "latency_ms": resp.get("latency_ms", 0),
            "confidence": resp.get("confidence", 0),
            "passed": assertion.passed,
            "failures": assertion.failures,
        })

        if i < total_turns:
            time.sleep(delay)

    elapsed = time.time() - t0
    print_scenario_footer(passed_turns, total_turns, elapsed)

    return {
        "id": scenario.id,
        "name": scenario.name,
        "passed_turns": passed_turns,
        "failed_turns": total_turns - passed_turns,
        "total_turns": total_turns,
        "elapsed_s": elapsed,
        "turns": turn_results,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="InmuebleBot stress test — conversaciones no-lineales",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--list",    action="store_true",  help="Listar escenarios y salir")
    parser.add_argument("--only",    nargs="+", metavar="ID", help="Correr solo estos escenarios (ej: s1 s3)")
    parser.add_argument("--skip",    nargs="+", metavar="ID", help="Saltar estos escenarios")
    parser.add_argument("--verbose", action="store_true",  help="Mostrar respuesta completa del bot")
    parser.add_argument("--delay",   type=float, default=DEFAULT_DELAY, help=f"Segundos entre turnos (default: {DEFAULT_DELAY})")
    parser.add_argument("--output",  metavar="FILE", help="Guardar resultados en JSON")
    args = parser.parse_args()

    if args.list:
        print(f"\n{BOLD}Escenarios disponibles:{RESET}\n")
        for s in SCENARIOS:
            print(f"  {CYAN}{s.id:<6}{RESET}  {s.name}")
            print(f"         {dim(s.description[:80])}…")
        print()
        sys.exit(0)

    # Filtrar escenarios
    to_run = SCENARIOS
    if args.only:
        ids = {x.lower() for x in args.only}
        to_run = [s for s in SCENARIOS if s.id.lower() in ids]
        if not to_run:
            print(fail(f"No se encontraron escenarios con IDs: {args.only}"))
            sys.exit(1)
    if args.skip:
        ids = {x.lower() for x in args.skip}
        to_run = [s for s in to_run if s.id.lower() not in ids]

    print(f"\n{BOLD}InmuebleBot Stress Test{RESET}")
    print(f"Endpoint: {info(ENDPOINT)}")
    print(f"Escenarios: {len(to_run)}  |  Delay: {args.delay}s  |  Verbose: {args.verbose}")

    all_results = []
    for idx, scenario in enumerate(to_run, start=1):
        print_scenario_header(scenario, idx, len(to_run))
        result = run_scenario(scenario, verbose=args.verbose, delay=args.delay)
        all_results.append(result)

    print_summary(all_results)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"\n  Resultados guardados en: {info(args.output)}")

    failed = sum(1 for r in all_results if r["failed_turns"] > 0)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
