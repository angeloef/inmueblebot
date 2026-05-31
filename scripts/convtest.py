"""Conversation test runner against the deployed bot's /simulate/multi.

Builds JSON with json.dumps (no bash quoting bugs). Prints tools_called/router/
selection + bot response per turn, and a DB snapshot of future appointments.

Usage:  python scripts/convtest.py [scenario_substr]
        python scripts/convtest.py            # run all
        python scripts/convtest.py C1 C8      # run scenarios whose id contains C1 or C8
"""
import sys, json, time, urllib.request

try:  # Windows console is cp1252 → bot responses / router '→' break printing
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "https://inmueblebot-api.onrender.com"
AK = "your-secure-admin-key-here"

# Each scenario: (id, [turns]). One fresh session per run.
SCENARIOS = [
    ("C2-ciclo-cita", [
        "hola, me interesa la propiedad 15, quiero coordinar una visita",
        "soy angelo feier, el miercoles a las 10 de la mañana",  # agenda
        "me confirmas que dia me quedo agendado?",               # get_my_appointments
        "che, mejor pasala para el jueves a la misma hora",      # reschedule
        "pensandolo bien mejor cancelala, me surgio un viaje",   # cancel
    ]),
    ("C1-rechazo", [
        "quiero visitar la propiedad 15",
        "mi nombre es ana lopez",
        "el domingo a las 10 de la mañana",          # debe RECHAZAR (domingo)
        "bueno el lunes a las 9 de la noche",         # debe RECHAZAR (fuera de hora)
        "dale, a las 3 de la tarde",                  # debe AGENDAR lunes 15:00
    ]),
    ("C5-fallbacks", [
        "busco una casa de 5 dormitorios en obera para alquilar",
        "hasta 90 mil al mes puedo pagar",
        "y de 3 dormitorios que tenes?",
        "mostrame algo mas barato",
    ]),
    ("C6-cambiotipo", [
        "hola, busco un depto para alquilar cerca de la unam",
        "hasta 150 mil",
        "sabes si tenes casas tambien por esa zona? me interesa ver las dos cosas",
        "la primera casa me interesa, mandame fotos",
    ]),
    ("C8-trampas", [
        "me interesa una propiedad que vi, la del centro con pileta",
        "la segunda de esas",
        "quiero ir a verla dentro de 3 dias a las 5 de la tarde",   # fecha relativa
        "ana lopez",                                                 # debe AGENDAR
    ]),
    ("C10-reprog", [
        "hola, queria cambiar la fecha de mi visita",
        "ah no tenia ninguna, bueno busco un depto de 1 dormitorio en obera para alquilar",
        "me interesa el ultimo de la lista, dame los detalles",      # ordinal "ultimo"
        "lo quiero ver el sabado a las 11 de la mañana, soy ana lopez",  # multi-campo
    ]),
    ("C7-handoff", [
        "hola, quiero hablar con un asesor",                          # handoff request_human_assistance
        "es urgente, necesito hablar con una persona",                # insistencia → confirm handoff
    ]),
]


def post(sid, msg):
    data = json.dumps({"message": msg, "session_id": sid, "phone": "549" + sid}).encode("utf-8")
    req = urllib.request.Request(BASE + "/simulate/multi", data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r)
    except Exception as e:
        return {"response": f"<ERROR {e}>", "tools_called": "ERR", "router": "ERR", "selection": None}


def run(scn_id, turns):
    sid = scn_id.replace("-", "") + str(int(time.time()))
    print(f"\n############ {scn_id} (sid={sid}) ############")
    for t in turns:
        d = post(sid, t)
        print(f"> {t}")
        print(f"  tools={d.get('tools_called')} router={d.get('router')} sel={d.get('selection')}")
        print("  bot:", str(d.get("response", ""))[:180].replace("\n", " "))


def db_snapshot():
    req = urllib.request.Request(BASE + "/admin/appointments", headers={"x-api-key": AK})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    a = d.get("appointments", d) if isinstance(d, dict) else d
    fut = [x for x in a if str(x.get("start_time", "")) >= "2026-05-30"]
    print(f"\n############ DB: citas futuras = {len(fut)} ############")
    for x in sorted(fut, key=lambda y: str(y.get("start_time")))[:25]:
        print(f"  {x.get('start_time')} | prop {x.get('property_id')} | user {str(x.get('user_id'))[:8]} | {x.get('status')}")


if __name__ == "__main__":
    filt = sys.argv[1:]
    for scn_id, turns in SCENARIOS:
        if not filt or any(f.lower() in scn_id.lower() for f in filt):
            run(scn_id, turns)
    db_snapshot()
    print("\nDONE")
