"""
profiles.py (v3) — 12 user profiles for enhanced Monte Carlo test.

New in v3:
- Profile 9: Lead capture → schedule (save_lead_info)
- Profile 10: Human handoff (request_human_assistance)
- Profile 11: Preferences save/load (update/get_user_preferences + recommend)
- Profile 12: Reschedule/Cancel existing appointments

v3 updates to existing:
- Profile 1: Added refine_search path
- Profile 6: Added UUID-based selection + reschedule/cancel split
- Profile 8: Added recommend_properties path

All profiles have erratic behaviors: wrong IDs, contradictions,
intent changes, confusion, incomplete info, typos.
"""

import random
import time

random.seed(int(time.time()))  # New seed every run

# ── Shared message parts for variation ─────────────────────────────

GREETINGS = [
    "Hola", "Buenas", "Hola buenas tardes", "Hola buenas noches",
    "Buen día", "Hola que tal", "Buenas noches", "Ey hola",
]

LOCATIONS = [
    "Oberá", "Obera", "Posadas", "Candelaria", "Oberá centro",
    "Oberá", "Oberá", "Garupá", "Oberá", "Obera",
]

TYPES = [
    "departamento", "depto", "casa", "departamento", "ph",
    "casa", "departamento", "casa", "departamento", "terreno",
]

BUDGETS = [
    "económico", "hasta 200000", "200000", "200mil", "barato",
    "hasta 150000", "hasta 300000", "económico", "lo más barato",
    "hasta 250000", "accesible", "no sé, algo barato",
]

BUDGETS_MEDIUM = [
    "hasta 350000", "normal", "350000", "estándar", "hasta 400000",
]

DATES = [
    "mañana", "mañana a las 10", "mañana a las 15", "pasado mañana",
    "el viernes", "el martes que viene", "hoy a las 17", "mañana a las 11",
    "este sábado", "el lunes", "mañana a las 9", "el jueves a las 14",
    "el miércoles a las 16",
]

NAMES = [
    "Juan", "María", "Pedro", "Ana", "Carlos", "Lucía",
    "Martín", "Sofía", "José", "Laura", "Franco", "Valentina",
]

REFERENCES = [
    "la primera", "la 1", "muéstrame los detalles", "el ID 20",
    "la que tiene 1 habitación", "la de 150mil", "la segunda",
    "la opción 3", "el ID 6", "la más barata",
]

# ── Wrong/hallucinated IDs (for stress testing) ────────────────────

WRONG_IDS = [
    "el ID 99", "la número 999", "la propiedad abc-123",
    "muéstrame la número 50", "el ID 100", "el 999",
    "la que está en Tokyo", "la propiedad XXL",
]

CONFUSED_RESPONSES = [
    "no, me equivoqué, es la otra",
    "no esa, la que sigue",
    "no la primera, la segunda",
    "perdón, me confundí, la de 2 ambientes",
    "no me refiero a esa, la otra",
    "ah no, la que tiene patio",
    "no esa no, la de más abajo",
]

# ── Utility helpers ─────────────────────────────────────────────────

def greet() -> str:
    return random.choice(GREETINGS) + ("!" if random.random() < 0.3 else "")


def maybe_confuse() -> bool:
    """~20% chance the user does something erratic/confused."""
    return random.random() < 0.20


def maybe_wrong_id() -> str or None:
    """~30% chance of giving a hallucinated/wrong ID (v3: bumped from 25%)."""
    if random.random() < 0.30:
        return random.choice(WRONG_IDS)
    return None


def maybe_change_intent() -> bool:
    """~20% chance user changes their mind mid-conversation (v3: bumped from 15%)."""
    return random.random() < 0.20


def maybe_typo() -> bool:
    """~25% chance user makes a typo (v3: bumped from 15%)."""
    return random.random() < 0.25


def maybe_contradict() -> bool:
    """~15% chance user contradicts their own preference (NEW in v3)."""
    return random.random() < 0.15


# ═══════════════════════════════════════════════════════════════════
# PROFILE 1:  Busca alquiler específico (complex flow + refine)
# ═══════════════════════════════════════════════════════════════════

def p1_turn1(_last_response=None):
    """Search with full criteria, occasionally with misspellings"""
    loc = random.choice(LOCATIONS)
    if maybe_typo():
        loc = loc.replace("á", "a").replace("é", "e").replace("ó", "o")
    budget = random.choice(BUDGETS)
    typ = random.choice(TYPES)
    return f"{greet()} busco un {typ} en {loc} para alquilar {budget}"


def p1_turn2(_last_response=None):
    """After results: confused pick, comparison, refine, or details"""
    wrong = maybe_wrong_id()
    if wrong:
        return wrong

    action = random.choices(
        ["details", "compare", "nope", "refine", "exit"],
        weights=[0.35, 0.15, 0.2, 0.2, 0.1],  # v3: added refine (20%)
    )[0]
    if action == "details":
        return random.choice(REFERENCES)
    elif action == "compare":
        ids = random.choice(["la 1 y la 2", "la primera y la tercera",
                             "compara la 1 con la 2", "la 2 y la 5"])
        return f"compará {ids}"
    elif action == "refine":  # NEW: refine_search path
        return random.choice([
            f"refiná la búsqueda, algo más barato en {random.choice(LOCATIONS)}",
            "filtrá mejor, con 2 ambientes nomás",
            f"ajustá la búsqueda, en {random.choice(LOCATIONS)} más céntrico",
        ])
    elif action == "exit":
        return random.choice(["gracias, después vuelvo", "no me interesan, chau"])
    return f"mostrame algo más barato en {random.choice(LOCATIONS)}"


def p1_turn3(_last_response=None):
    """After details/compare: schedule, photos, confused, or back"""
    if maybe_confuse():
        return random.choice(CONFUSED_RESPONSES)

    action = random.choices(
        ["schedule", "photos", "back", "wrong_id"],
        weights=[0.4, 0.2, 0.2, 0.2],
    )[0]
    if action == "schedule":
        return f"quiero agendar para {random.choice(DATES)}, soy {random.choice(NAMES)}"
    elif action == "photos":
        return random.choice(["mandame las fotos", "quiero ver las imágenes",
                              "mostrame las imágenes", "fotos"])
    elif action == "wrong_id":
        return random.choice(WRONG_IDS)
    return "mostrame otra"


def p1_turn4(_last_response=None):
    """After scheduling: may accept, reject, or change mind"""
    resp = (_last_response or "").lower()
    if maybe_change_intent() or "ocupado" in resp or "alternativa" in resp:
        return f"ok, entonces {random.choice(DATES)}"
    if random.random() < 0.15:
        return "no, al final no, cancelá eso"
    if random.random() < 0.10 and "agendada" in resp:
        return "gracias, ahora mostrame otra propiedad"
    return random.choice(["gracias, perfecto", "genial, muchas gracias",
                          "listo, después vuelvo"])


# ═══════════════════════════════════════════════════════════════════
# PROFILE 2:  Busca compra
# ═══════════════════════════════════════════════════════════════════

def p2_turn1(_last_response=None):
    loc = random.choice(LOCATIONS)
    budget = random.choice(["hasta 300000", "económico", "hasta 500000", "hasta 250000"])
    return f"{greet()} quiero comprar una {random.choice(TYPES)} en {loc} {budget}"


def p2_turn2(_last_response=None):
    """After results: 30% chance of wrong pick then correct"""
    if maybe_wrong_id():
        return random.choice(WRONG_IDS)
    return random.choice(REFERENCES)


def p2_turn3(_last_response=None):
    """After details: schedule, but 20% chance confused first"""
    if maybe_confuse():
        return random.choice(CONFUSED_RESPONSES)
    return f"quiero visitarla {random.choice(DATES)}, soy {random.choice(NAMES)}"


def p2_turn4(_last_response=None):
    """After scheduling: confirm, change intent, or exit"""
    if maybe_change_intent():
        return "no, mejor busco otra propiedad"
    return "gracias, después te confirmo"


# ═══════════════════════════════════════════════════════════════════
# PROFILE 3:  Consulta vaga → intent change → complex flow
# ═══════════════════════════════════════════════════════════════════

def p3_turn1(_last_response=None):
    return random.choice([
        f"{greet()} estoy buscando algo",
        f"{greet()} quiero mudarme",
        f"{greet()} necesito un lugar para vivir",
        f"{greet()} ando buscando propiedades",
    ])


def p3_turn2(_last_response=None):
    """After bot asks: specify, possibly vaguely"""
    typ = random.choice(TYPES)
    loc = random.choice(LOCATIONS)
    if random.random() < 0.25:
        return f"no sé bien, un {typ} por {loc} capaz"
    if random.random() < 0.15:
        return f"un {typ} nomás, no sé la zona"
    return f"un {typ} en {loc}"


def p3_turn3(_last_response=None):
    """After search results: confused, compare, details"""
    if maybe_confuse():
        return random.choice(CONFUSED_RESPONSES)
    action = random.choices(
        ["details", "compare", "exit"],
        weights=[0.5, 0.2, 0.3],
    )[0]
    if action == "compare":
        return "compara la primera con la última"
    if action == "exit":
        return "gracias, después vuelvo"
    return random.choice(REFERENCES)


def p3_turn4(_last_response=None):
    """After details: schedule, FAQ, or change intent"""
    resp = (_last_response or "").lower()
    if maybe_change_intent():
        return random.choice([
            "esperá, ¿a qué hora abren la inmobiliaria?",
            "decime, ¿aceptan mascotas?",
            "cambio de opinión, mostrame casas mejor",
            "sabés qué, primero decime el horario de atención",
        ])
    if "agendar" in resp or "visit" in resp:
        return f"si, {random.choice(DATES)}, soy {random.choice(NAMES)}"
    return "gracias, era lo que necesitaba"


# ═══════════════════════════════════════════════════════════════════
# PROFILE 4:  FAQ → búsqueda → photos → schedule
# ═══════════════════════════════════════════════════════════════════

def p4_turn1(_last_response=None):
    faqs = [
        "a qué hora abren",
        "aceptan tarjetas de crédito",
        "cómo financio",
        "cuánto tarda el trámite",
        "hacen tasaciones",
        "qué requisitos piden para alquilar",
        "tienen propiedades en Posadas también",
    ]
    return f"{greet()} {random.choice(faqs)}"


def p4_turn2(_last_response=None):
    """After FAQ answer: search"""
    return f"gracias, ahora buscame un {random.choice(TYPES)} en {random.choice(LOCATIONS)} {random.choice(BUDGETS)}"


def p4_turn3(_last_response=None):
    """After search: pick one, possibly wrong first"""
    if maybe_wrong_id():
        return random.choice(WRONG_IDS)
    action = random.choices(["details", "compare"], weights=[0.7, 0.3])[0]
    if action == "compare":
        return "compará la 1 y la 3"
    return f"{random.choice(REFERENCES)}"


def p4_turn4(_last_response=None):
    """After details: ask for photos"""
    return random.choice(["mandame las fotos", "quiero ver las fotos", "mostrame las imágenes"])


def p4_turn5(_last_response=None):
    """After photos: schedule or exit"""
    action = random.choices(["schedule", "exit"], weights=[0.6, 0.4])[0]
    if action == "schedule":
        return f"agendá una visita {random.choice(DATES)}, soy {random.choice(NAMES)}"
    return "gracias era justo lo que buscaba"


# ═══════════════════════════════════════════════════════════════════
# PROFILE 5:  No encuentra + confusion + retry
# ═══════════════════════════════════════════════════════════════════

def p5_turn1(_last_response=None):
    """Extreme filters or strange requests"""
    queries = [
        f"{greet()} busco un {random.choice(TYPES)} en Tokyo para alquilar hasta 50000",
        f"{greet()} quiero un terreno en Marte para comprar",
        f"{greet()} necesito una casa en la luna hasta 1000 dólares",
        f"{greet()} busco una mansión en Oberá por 50000 pesos",
        f"{greet()} quiero alquilar una oficina en Candelaria hasta 100000",
        f"{greet()} busco un galpón en Oberá para alquilar económico",
    ]
    return random.choice(queries)


def p5_turn2(_last_response=None):
    """After fallbacks: confused, try again, or exit"""
    if maybe_confuse():
        return random.choice(["no entiendo, ¿qué significa todo eso?",
                              "eh, no me queda claro, explicame de nuevo",
                              "cuál es la más barata de todas?"])
    action = random.choices(["try_other", "exit"], weights=[0.4, 0.6])[0]
    if action == "try_other":
        return f"mm, mostrame algo en {random.choice(LOCATIONS)} entonces"
    return "gracias, no encontré lo que buscaba, chau"


def p5_turn3(_last_response=None):
    """After retry search: pick one or exit"""
    action = random.choices(["details", "exit"], weights=[0.5, 0.5])[0]
    if action == "details":
        return random.choice(REFERENCES)
    return "no, gracias igual"


# ═══════════════════════════════════════════════════════════════════
# PROFILE 6:  Cliente existente → reschedule/cancel/search (v3: UUID pattern)
# ═══════════════════════════════════════════════════════════════════

def p6_turn1(_last_response=None):
    entrances = [
        f"{greet()} quiero ver mis citas",
        f"{greet()} tengo un turno, necesito consultar",
        f"{greet()} ya tengo una visita agendada, quiero verla",
    ]
    return random.choice(entrances)


def p6_turn2(_last_response=None):
    """After seeing appointments: complex decisions"""
    # 20% intent change
    if maybe_change_intent():
        return random.choice([
            "no, mejor buscame una propiedad nueva",
            "sabés qué, olvidate, buscame un departamento",
            "esperá, decime el horario de la inmobiliaria primero",
        ])
    action = random.choices(
        ["reschedule", "cancel", "new_search", "exit"],
        weights=[0.25, 0.25, 0.25, 0.25],
    )[0]
    if action == "reschedule":
        return random.choice([
            f"quiero reprogramar la primera cita para {random.choice(DATES)}",
            f"cambiá la del jueves para {random.choice(DATES)}",
            f"reprogramá mi visita para {random.choice(DATES)}",
        ])
    elif action == "cancel":
        return random.choice([
            "cancelá la primera cita por favor",
            "dá de baja mi turno de la semana que viene",
            "no voy a poder ir, cancelalo",
        ])
    elif action == "new_search":
        return f"buscame un {random.choice(TYPES)} en {random.choice(LOCATIONS)} {random.choice(BUDGETS)}"
    return "gracias, después vuelvo"


def p6_turn3(_last_response=None):
    """After action: confirm, change, or retry"""
    resp = (_last_response or "").lower()
    if "no tienes citas" in resp or "no encontré" in resp or "ninguna" in resp:
        return f"ah ok, buscame un {random.choice(TYPES)} en {random.choice(LOCATIONS)} entonces"
    # 20%: user changes mind about reschedule/cancel
    if maybe_change_intent() and ("reprogram" in resp or "cancel" in resp or "cambió" in resp):
        return random.choice([
            "no, dejalo como estaba mejor",
            "no sabés, dejá, no toques nada",
        ])
    return "si, confirmalo"


# ═══════════════════════════════════════════════════════════════════
# PROFILE 7:  Fotos + confused picks
# ═══════════════════════════════════════════════════════════════════

def p7_turn1(_last_response=None):
    """Search for properties — simple start"""
    return f"{greet()} mostrame {random.choice(TYPES)} en {random.choice(LOCATIONS)}"


def p7_turn2(_last_response=None):
    """After results: pick one (possibly wrong first)"""
    if maybe_confuse():
        return random.choice(WRONG_IDS)
    return f"{random.choice(REFERENCES)}"


def p7_turn3(_last_response=None):
    """After details: ask for photos — main purpose"""
    return random.choice([
        "mandame las fotos",
        "quiero ver las imágenes de la propiedad",
        "mostrame las fotos",
        "cómo es, tiene fotos?",
        "pasame las imágenes",
    ])


def p7_turn4(_last_response=None):
    """After photos: may want another's photos, schedule, or confused"""
    action = random.choices(["another_photos", "schedule", "confused", "exit"],
                            weights=[0.3, 0.3, 0.2, 0.2])[0]
    if action == "another_photos":
        return f"mostrame las fotos de {random.choice(['la otra', 'la primera', 'la de 2 ambientes', 'el ID 6'])}"
    if action == "confused":
        return random.choice(CONFUSED_RESPONSES)
    if action == "schedule":
        return f"quiero visitarla {random.choice(DATES)}, soy {random.choice(NAMES)}"
    return "gracias, lástima, no me convencieron las fotos"


# ═══════════════════════════════════════════════════════════════════
# PROFILE 8:  Comparación + recommend (v3: added recommend path)
# ═══════════════════════════════════════════════════════════════════

def p8_turn1(_last_response=None):
    """Search — cast a wide net"""
    return f"{greet()} estoy viendo {random.choice(TYPES)} en {random.choice(LOCATIONS)} para alquilar"


def p8_turn2(_last_response=None):
    """After results: ask to compare"""
    return random.choice([
        "compara la primera y la segunda",
        "compará la 1 con la 3",
        "cuál es mejor entre la primera y la última?",
        "comparame la de 150mil con la de 200mil",
        "hacé una comparación de las primeras 2",
    ])


def p8_turn3(_last_response=None):
    """After comparison: pick one, ask for recommendation, or confused"""
    if maybe_confuse():
        return random.choice(CONFUSED_RESPONSES)
    action = random.choices(["details", "recommend", "wrong_id"],
                            weights=[0.5, 0.3, 0.2])[0]  # v3: added recommend
    if action == "recommend":
        return random.choice([
            "recomendame la mejor opción",
            "cuál me recomendás de todas?",
            "decime cuál es la mejor relación precio-calidad",
        ])
    if action == "wrong_id":
        return random.choice(WRONG_IDS)
    return f"quiero ver los detalles de {random.choice(['la primera', 'la que comparaste', 'la más barata', 'el ID 20'])}"


def p8_turn4(_last_response=None):
    """After details/recommend: schedule, compare more, or exit"""
    if maybe_change_intent() or random.random() < 0.2:
        return "ahora compará esa con la otra que vimos"
    return f"agendá una visita {random.choice(DATES)}, soy {random.choice(NAMES)}"


# ═══════════════════════════════════════════════════════════════════
# PROFILE 9:  Guarda lead + agenda (NEW — save_lead_info)
# ═══════════════════════════════════════════════════════════════════

def p9_turn1(_last_response=None):
    """Vague search — bot will qualify then ask for contact info"""
    return f"{greet()} estoy buscando un {random.choice(TYPES)} en {random.choice(LOCATIONS)} {random.choice(BUDGETS)}"


def p9_turn2(_last_response=None):
    """After search: pick a property (may be wrong first)"""
    if maybe_wrong_id():
        return random.choice(WRONG_IDS)
    return f"quiero ver {random.choice(REFERENCES)}"


def p9_turn3(_last_response=None):
    """After details: bot may ask for contact info — provide name"""
    return f"me interesa, mi nombre es {random.choice(NAMES)} y mi teléfono es el mismo"


def p9_turn4(_last_response=None):
    """After lead capture: schedule visit or confused"""
    if maybe_change_intent():
        return random.choice([
            "no, mejor busco otra propiedad primero",
            "esperá, mostrame las fotos antes",
            "cambio de idea, quiero ver otro",
        ])
    action = random.choices(["schedule", "exit"], weights=[0.7, 0.3])[0]
    if action == "schedule":
        return f"si, agendá para {random.choice(DATES)}"
    return "gracias, después te llamo"


def p9_turn5(_last_response=None):
    """After scheduling: confirm or change mind"""
    if maybe_change_intent():
        return random.choice([
            "no, mejor cambiá la fecha",
            f"en realidad mejor {random.choice(DATES)}",
        ])
    return "perfecto, gracias!"


# ═══════════════════════════════════════════════════════════════════
# PROFILE 10:  Pide agente humano (NEW — request_human_assistance)
# ═══════════════════════════════════════════════════════════════════

def p10_turn1(_last_response=None):
    """Search for something specific"""
    return f"{greet()} necesito un {random.choice(TYPES)} en {random.choice(LOCATIONS)} para comprar hasta 400000"


def p10_turn2(_last_response=None):
    """After results: pick one"""
    return f"mostrame {random.choice(REFERENCES)}"


def p10_turn3(_last_response=None):
    """After details: ask for human (or change mind — 15%)"""
    if maybe_confuse() or random.random() < 0.15:
        return random.choice([
            "no, dejá, seguimos viendo propiedades",
            "esperá, no, mejor segui mostrando",
            "sabés qué, no, olvidate",
        ])
    return random.choice([
        "quiero hablar con una persona",
        "pasame con un asesor por favor",
        "necesito hablar con un agente",
        "podés transferirme con alguien?",
    ])


def p10_turn4(_last_response=None):
    """After handoff: exit or change mind"""
    if maybe_change_intent():
        return "no, al final no hace falta, gracias"
    return "gracias, espero que me contacten"


# ═══════════════════════════════════════════════════════════════════
# PROFILE 11:  Preferencias guardadas (NEW — update/get_user_preferences)
# ═══════════════════════════════════════════════════════════════════

def p11_turn1(_last_response=None):
    """Search with clear preferences to save"""
    return f"{greet()} buscame un {random.choice(TYPES)} en {random.choice(LOCATIONS)} {random.choice(BUDGETS)}, prefiero con 2 dormitorios"


def p11_turn2(_last_response=None):
    """After results: save these preferences"""
    return random.choice([
        "guardá estas preferencias",
        "acordate lo que me gusta",
        "guardá mi búsqueda así la retomo después",
        "memorizá mis preferencias",
    ])


def p11_turn3(_last_response=None):
    """After saving: ask for recommendations based on saved prefs"""
    return random.choice([
        "recomendame propiedades según lo que guardé",
        "qué propiedades me recomendas con lo que ya sabés?",
        "mostrame opciones similares a lo que ya tengo guardado",
    ])


def p11_turn4(_last_response=None):
    """After recommendations: modify prefs (contradict 15%) or schedule"""
    if maybe_contradict():
        return random.choice([
            "no, cambiá, quiero casa no departamento",
            "en realidad más caro, hasta 400000",
            "no, mejor en Posadas, no Oberá",
        ])
    action = random.choices(["schedule", "exit"], weights=[0.6, 0.4])[0]
    if action == "schedule":
        return f"quiero visitar una {random.choice(DATES)}, soy {random.choice(NAMES)}"
    return "gracias, después retomo"


# ═══════════════════════════════════════════════════════════════════
# PROFILE 12:  Reprograma/Cancela cita (NEW — reschedule/cancel with UUID)
# ═══════════════════════════════════════════════════════════════════

def p12_turn1(_last_response=None):
    """Check existing appointments"""
    return random.choice([
        f"{greet()} quiero ver mis visitas agendadas",
        f"{greet()} tengo turnos, mostrame",
        f"{greet()} necesito cambiar mi cita, decime cuáles tengo",
    ])


def p12_turn2(_last_response=None):
    """After seeing appointments: reschedule or cancel"""
    resp = (_last_response or "").lower()
    if "no tienes" in resp or "no hay" in resp or "ninguna" in resp:
        # No appointments → fallback to search
        return f"ah, bueno, buscame un {random.choice(TYPES)} en {random.choice(LOCATIONS)} entonces"
    action = random.choices(["reschedule", "cancel"], weights=[0.5, 0.5])[0]
    if action == "reschedule":
        return f"reprogramá la primera para {random.choice(DATES)}"
    else:
        return random.choice([
            "cancelá la primera cita",
            "dá de baja mi turno",
            "no voy a poder ir, cancelalo",
        ])


def p12_turn3(_last_response=None):
    """After action: confirm, change mind, or give wrong info"""
    if maybe_wrong_id():
        return random.choice(["no esa, la segunda", "no, la del viernes no, la otra",
                              "la número 99, no esa"])
    if maybe_change_intent() and random.random() < 0.3:
        return "no, dejalo como estaba"
    return "si, confirmado, gracias"


# ═══════════════════════════════════════════════════════════════════
# Profile definitions
# ═══════════════════════════════════════════════════════════════════

PROFILES = [
    # ── Profile 1: Alquiler específico (errático + refine) ────────
    {
        "name": "Alquiler específico (errático)",
        "weight": 0.15,
        "states": {
            "idle": (p1_turn1, "searching"),
            "searching": (p1_turn2, None),
            "viewing_property": (p1_turn3, None),
            "scheduling": (p1_turn4, "idle"),
        },
        "max_turns": 8,
    },
    # ── Profile 2: Busca compra ───────────────────────────────────
    {
        "name": "Busca compra",
        "weight": 0.08,
        "states": {
            "idle": (p2_turn1, "searching"),
            "searching": (p2_turn2, "viewing_property"),
            "viewing_property": (p2_turn3, "scheduling"),
            "scheduling": (p2_turn4, "idle"),
        },
        "max_turns": 6,
    },
    # ── Profile 3: Consulta vaga + intent change ──────────────────
    {
        "name": "Consulta vaga + intent change",
        "weight": 0.12,
        "states": {
            "idle": (p3_turn1, "qualifying"),
            "qualifying": (p3_turn2, "searching"),
            "searching": (p3_turn3, None),
            "viewing_property": (p3_turn4, None),
        },
        "max_turns": 10,
    },
    # ── Profile 4: FAQ → fotos → agenda ───────────────────────────
    {
        "name": "FAQ → fotos → agenda",
        "weight": 0.08,
        "states": {
            "idle": (p4_turn1, "faq"),
            "faq": (p4_turn2, "searching"),
            "searching": (p4_turn3, "viewing_property"),
            "viewing_property": (p4_turn4, "scheduling"),
            "scheduling": (p4_turn5, "idle"),
        },
        "max_turns": 8,
    },
    # ── Profile 5: No encuentra + confusión ────────────────────────
    {
        "name": "No encuentra + confusión",
        "weight": 0.08,
        "states": {
            "idle": (p5_turn1, "searching"),
            "searching": (p5_turn2, None),
            "viewing_property": (p5_turn3, "idle"),
        },
        "max_turns": 6,
    },
    # ── Profile 6: Cliente existente (cambia opinión) ──────────────
    {
        "name": "Cliente existente (cambia opinión)",
        "weight": 0.10,
        "states": {
            "idle": (p6_turn1, "appointments"),
            "appointments": (p6_turn2, None),
            "scheduling": (p6_turn3, "idle"),
            "cancelling": (p6_turn3, "idle"),
            "searching": (p6_turn3, "idle"),
            "faq": (p6_turn3, "idle"),
        },
        "max_turns": 8,
    },
    # ── Profile 7: Pide fotos + confusión ─────────────────────────
    {
        "name": "Pide fotos + confusión",
        "weight": 0.10,
        "states": {
            "idle": (p7_turn1, "searching"),
            "searching": (p7_turn2, "viewing_property"),
            "viewing_property": (p7_turn3, "scheduling"),
            "scheduling": (p7_turn4, "idle"),
        },
        "max_turns": 8,
    },
    # ── Profile 8: Compara propiedades + recommend ────────────────
    {
        "name": "Compara propiedades",
        "weight": 0.08,
        "states": {
            "idle": (p8_turn1, "searching"),
            "searching": (p8_turn2, "viewing_property"),
            "viewing_property": (p8_turn3, "scheduling"),
            "scheduling": (p8_turn4, "idle"),
        },
        "max_turns": 8,
    },
    # ── Profile 9: Lead capture + schedule (NEW) ───────────────────
    {
        "name": "Guarda lead + agenda (NEW)",
        "weight": 0.08,
        "states": {
            "idle": (p9_turn1, "searching"),
            "searching": (p9_turn2, "viewing_property"),
            "viewing_property": (p9_turn3, "lead_capture"),
            "lead_capture": (p9_turn4, None),
            "scheduling": (p9_turn5, "idle"),
        },
        "max_turns": 8,
    },
    # ── Profile 10: Human handoff (NEW) ────────────────────────────
    {
        "name": "Pide agente humano (NEW)",
        "weight": 0.06,
        "states": {
            "idle": (p10_turn1, "searching"),
            "searching": (p10_turn2, "viewing_property"),
            "viewing_property": (p10_turn3, "handoff"),
            "handoff": (p10_turn4, "exit"),
        },
        "max_turns": 6,
    },
    # ── Profile 11: Preferences save/load (NEW) ────────────────────
    {
        "name": "Preferencias guardadas (NEW)",
        "weight": 0.06,
        "states": {
            "idle": (p11_turn1, "searching"),
            "searching": (p11_turn2, "preferences"),
            "preferences": (p11_turn3, "searching"),
            "searching": (p11_turn4, None),
        },
        "max_turns": 8,
    },
    # ── Profile 12: Reschedule/Cancel (NEW) ────────────────────────
    {
        "name": "Reprograma/Cancela (NEW)",
        "weight": 0.06,
        "states": {
            "idle": (p12_turn1, "appointments"),
            "appointments": (p12_turn2, None),
            "scheduling": (p12_turn3, "idle"),
            "cancelling": (p12_turn3, "idle"),
            "searching": (p12_turn3, "idle"),
        },
        "max_turns": 6,
    },
]
