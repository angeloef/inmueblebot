"""
profiles.py — 6 user profiles with probabilistic message generators.

Each profile defines:
- name, weight: for Monte Carlo distribution
- states: dict of {current_state: (handler_fn, expected_next_state)}
- handler_fn(_last_response=None) -> (human_message, expected_state)
"""

import random

# ── Shared message parts for variation ─────────────────────────────

GREETINGS = [
    "Hola", "Buenas", "Hola buenas tardes", "Hola buenas noches",
    "Buen día", "Hola que tal",
]

LOCATIONS = ["Oberá", "Obera", "Posadas", "Oberá centro", "Oberá", "Oberá"]
TYPES = ["departamento", "depto", "casa", "departamento", "ph"]
BUDGETS = ["económico", "hasta 200000", "200000", "200mil", "barato", "hasta 150000"]
DATES = ["mañana", "mañana a las 10", "mañana a las 15", "pasado mañana",
         "el viernes", "el martes que viene", "hoy a las 17", "mañana a las 11"]
NAMES = ["Juan", "María", "Pedro", "Ana", "Carlos", "Lucía", "Martín"]
REFERENCES = ["la primera", "la 1", "muéstrame los detalles", "el ID 20",
              "la que tiene 1 habitación", "la de 150mil"]


def greet() -> str:
    g = random.choice(GREETINGS)
    return g + ("!" if random.random() < 0.3 else "")


# ── All handler functions accept _last_response=None ───────────────

def p1_turn1(_last_response=None):
    """Busca alquiler específico - turn 1: search with criteria"""
    return f"{greet()} busco un {random.choice(TYPES)} en {random.choice(LOCATIONS)} para alquilar {random.choice(BUDGETS)}"


def p1_turn2(_last_response=None):
    """Busca alquiler - turn 2: pick property or exit"""
    action = random.choices(["details", "nope", "refine"], weights=[0.7, 0.2, 0.1])[0]
    if action == "details":
        return random.choice(REFERENCES)
    elif action == "nope":
        return "gracias, después vuelvo"
    return f"mostrame algo más barato en {random.choice(LOCATIONS)}"


def p1_turn3(_last_response=None):
    """Busca alquiler - turn 3: schedule, photos, or back"""
    action = random.choices(["schedule", "photos", "back"], weights=[0.6, 0.2, 0.2])[0]
    if action == "schedule":
        return f"quiero agendar para {random.choice(DATES)}, soy {random.choice(NAMES)}"
    elif action == "photos":
        return "mandame las fotos"
    return "mostrame otra"


def p1_turn4(_last_response=None):
    """Busca alquiler - turn 4: handle schedule response"""
    resp = (_last_response or "").lower()
    if "ocupado" in resp or "alternativa" in resp:
        return f"ok, entonces {random.choice(DATES)}"
    return "gracias, perfecto"


def p2_turn1(_last_response=None):
    """Busca compra - turn 1: search buy"""
    loc = random.choice(LOCATIONS)
    budget = random.choice(["hasta 300000", "económico", "hasta 500000"])
    return f"{greet()} quiero comprar una {random.choice(TYPES)} en {loc} {budget}"


def p2_turn2(_last_response=None):
    return random.choice(REFERENCES)


def p2_turn3(_last_response=None):
    return f"quiero visitarla {random.choice(DATES)}, soy {random.choice(NAMES)}"


def p2_turn4(_last_response=None):
    return "gracias, después te confirmo"


def p3_turn1(_last_response=None):
    """Consulta vaga - turn 1: vague query"""
    return f"{greet()} estoy buscando algo"


def p3_turn2(_last_response=None):
    """Consulta vaga - turn 2: specify"""
    return f"un {random.choice(TYPES)} en {random.choice(LOCATIONS)}"


def p3_turn3(_last_response=None):
    """Consulta vaga - turn 3: results"""
    return f"el {random.choice(['primero', 'segundo', 'más barato'])}"


def p3_turn4(_last_response=None):
    """Consulta vaga - turn 4: done"""
    resp = (_last_response or "").lower()
    if "agendar" in resp:
        return f"si, {random.choice(DATES)}, soy {random.choice(NAMES)}"
    return "gracias"


def p4_turn1(_last_response=None):
    """FAQ - turn 1: ask FAQ"""
    faqs = ["a qué hora abren", "aceptan tarjetas de crédito", "cómo financio",
            "cuánto tarda el trámite", "hacen tasaciones"]
    return f"{greet()} {random.choice(faqs)}"


def p4_turn2(_last_response=None):
    """FAQ - turn 2: then search"""
    return f"gracias, ahora buscame un {random.choice(TYPES)} en {random.choice(LOCATIONS)} {random.choice(BUDGETS)}"


def p4_turn3(_last_response=None):
    return f"{random.choice(REFERENCES)}"


def p4_turn4(_last_response=None):
    return "gracias, era lo que necesitaba"


def p5_turn1(_last_response=None):
    """No encuentra - extreme filters"""
    return f"{greet()} busco un {random.choice(TYPES)} en Tokyo para alquilar hasta 50000"


def p5_turn2(_last_response=None):
    """No encuentra - fallback or exit"""
    action = random.choices(["try_other", "exit"], weights=[0.3, 0.7])[0]
    if action == "try_other":
        return f"mostrame algo en {random.choice(LOCATIONS)} entonces"
    return "gracias, no encontré lo que buscaba, chau"


def p6_turn1(_last_response=None):
    """Cliente existente - check appointments"""
    return f"{greet()} quiero ver mis citas"


def p6_turn2(_last_response=None):
    """Cliente existente - reschedule, cancel, or exit"""
    action = random.choices(["reschedule", "cancel", "exit"], weights=[0.3, 0.3, 0.4])[0]
    if action == "reschedule":
        return f"quiero cambiar la hora para {random.choice(DATES)}"
    elif action == "cancel":
        return "cancelá esa cita por favor"
    return "gracias, después vuelvo"


def p6_turn3(_last_response=None):
    return "si, confirmalo"


# ── Profile definitions ────────────────────────────────────────────

PROFILES = [
    {
        "name": "Busca alquiler específico",
        "weight": 0.35,
        "states": {
            "idle": (p1_turn1, "searching"),
            "searching": (p1_turn2, None),
            "viewing_property": (p1_turn3, None),
            "scheduling": (p1_turn4, "idle"),
        },
        "max_turns": 6,
    },
    {
        "name": "Busca compra",
        "weight": 0.15,
        "states": {
            "idle": (p2_turn1, "searching"),
            "searching": (p2_turn2, "viewing_property"),
            "viewing_property": (p2_turn3, "scheduling"),
            "scheduling": (p2_turn4, "idle"),
        },
        "max_turns": 6,
    },
    {
        "name": "Consulta vaga",
        "weight": 0.20,
        "states": {
            "idle": (p3_turn1, "qualifying"),
            "qualifying": (p3_turn2, "searching"),
            "searching": (p3_turn3, None),
            "viewing_property": (p3_turn4, None),
        },
        "max_turns": 8,
    },
    {
        "name": "FAQ → búsqueda",
        "weight": 0.10,
        "states": {
            "idle": (p4_turn1, "faq"),
            "faq": (p4_turn2, "searching"),
            "searching": (p4_turn3, "viewing_property"),
            "viewing_property": (p4_turn4, "idle"),
        },
        "max_turns": 6,
    },
    {
        "name": "No encuentra",
        "weight": 0.10,
        "states": {
            "idle": (p5_turn1, "searching"),
            "searching": (p5_turn2, "idle"),
        },
        "max_turns": 4,
    },
    {
        "name": "Cliente existente",
        "weight": 0.10,
        "states": {
            "idle": (p6_turn1, "appointments"),
            "appointments": (p6_turn2, None),
            "scheduling": (p6_turn3, "idle"),
            "cancelling": (p6_turn3, "idle"),
        },
        "max_turns": 6,
    },
]
