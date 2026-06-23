"""V4 prompt construction — extends V3 prompts with sub_goals/references instructions.

CACHING INVARIANT: same as V3 — build_system_prompt_v4() returns a module-level
constant, byte-identical every call. build_tenant_policy and build_messages are
imported from V3 unchanged.
"""

from __future__ import annotations

# Re-export V3 tenant_policy and message-builder unchanged
from app.routers.v3.prompts import build_tenant_policy, build_messages  # noqa: F401

# Pull the V3 static prompt text to extend
from app.routers.v3.prompts import build_system_prompt as _v3_build

_V3_PROMPT = _v3_build()

# V4-specific additions appended once at import time
_V4_EXTENSION = """
CAMPOS NUEVOS — V4 multi-intención:

CAMPO sub_goals — descomponedor de objetivos:
Lista ORDENADA de sub-objetivos del mensaje. SIEMPRE emitir ≥1 entrada, incluso en saludos.
Para mensajes con múltiples intenciones ("quiero ver el depto del centro y agendar para el sábado") emitir ≥2 entradas.
Cada item: {intent: string, args_hint: string-JSON-encoded}.
args_hint = dict JSON con los argumentos relevantes del sub-objetivo. Usar '{}' si no hay args.

CAMPO references — resolución de anáforas:
selected_property_id: si el usuario usa "ese", "el primero", "el de arriba", "ese depto", etc., resolvé el ID aquí desde el estado. Null si no hay anáfora o no se puede resolver.
anaphora: la expresión anafórica que usó el usuario (string), o null.

EJEMPLOS sub_goals y references:

Búsqueda simple (1 intención):
usuario: "busco departamento en alquiler en el centro"
→ sub_goals: [{intent:"search", args_hint:'{"operation":"alquiler","tipo":"departamento","zona":"Centro"}'}]
→ references: {selected_property_id:null, anaphora:null}

Multi-intención (2 sub-objetivos):
usuario: "quiero ver el depto del centro y agendar una visita para el sábado"
→ sub_goals: [{intent:"search", args_hint:'{"action":"show_details"}'}, {intent:"scheduling", args_hint:'{"dia":"sabado"}'}]
→ references: {selected_property_id:null, anaphora:null}

Anáfora con propiedad en estado:
estado: {propiedad_seleccionada:42}
usuario: "¿cuánto cuesta ese?"
→ sub_goals: [{intent:"knowledge", args_hint:'{"topic":"precio"}'}]
→ references: {selected_property_id:42, anaphora:"ese"}

Saludo (≥1 sub_goal siempre):
usuario: "hola"
→ sub_goals: [{intent:"rapport", args_hint:'{}'}]
→ references: {selected_property_id:null, anaphora:null}

DISCIPLINA DE OUTPUT V4:
Respondé SIEMPRE con el JSON completo del schema:
belief_delta, intent, action, tool_calls, selected_property_id, missing_slot,
response_plan, confidence, sub_goals, references.
Todos los campos deben estar presentes.
"""

_SYSTEM_PROMPT_V4 = _V3_PROMPT + _V4_EXTENSION

# Module-level constant — byte-stable
_SYSTEM_PROMPT_V4_OBJ = _SYSTEM_PROMPT_V4


def build_system_prompt_v4() -> str:
    """Return the static V4 system prompt (byte-stable)."""
    return _SYSTEM_PROMPT_V4_OBJ
