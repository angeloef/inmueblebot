# Hybrid Refactor Plan — InmuebleBot

> **Target:** Replace brittle regex/static-map NL→parameter translation with a config-driven hybrid LLM+code architecture.
> **Pattern:** Each component = `HybridParser` abstract base → LLM strategy OR code strategy OR hybrid (LLM-first, code-fallback).
> **Deployment:** Every parser is togglable via env var on Render. Switch strategies without redeploying.
> **Model context:** All LLM parser calls use the existing `llm_router.chat()` (same model as main agent: gpt-4.4-mini). Temperature=0, max_tokens ≤ 50.
> **Arch precedent:** `parse_datetime_llm()` in `app/utils/date_parser.py` (commit `21dd200`) is the validated template.

---

## How to Read This Plan

Each **Phase** is a self-contained work package. Phases can be done in parallel by different developers.

Each phase contains:

```
## Phase N: [Name]
### Context
— Why this exists, what currently breaks

### Task: [Numbered steps]
1. Create file → content
2. Modify file → content
3. Wire into existing code

### Spec: [API contract, prompt, expected behavior]

### REVIEW GATE
— Criteria the reviewer checks before approving
```

---

## Phase 0: Hybrid Infrastructure

### Context
Build the shared base classes, registry, and metrics collector that every parser will use. No parser logic yet — just the skeleton.

The pattern is **Strategy + Fallback**, validated by `parse_datetime_llm` (commit `21dd200`).

### Task 0.1 — Create `app/core/hybrid/__init__.py`

```python
"""
HybridParser Infrastructure.
Every NL→structured-data component follows: 
  LLM-first → code-fallback (hybrid), or pure LLM, or pure code.
Togglable per-component via PARSER_{NAME} env var.
"""
from .base import HybridParser, ParseResult, ParserConfig
from .registry import ParserRegistry

__all__ = ["HybridParser", "ParseResult", "ParserConfig", "ParserRegistry"]
```

### Task 0.2 — Create `app/core/hybrid/base.py`

```python
"""Abstract base + data classes for all hybrid parsers."""
import os
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    """Normalised output from any parser strategy."""
    value: Any                             # Parsed value (None = failure)
    confidence: float = 0.0                # 0.0–1.0
    parser_used: str = "unknown"           # "llm" | "code" | "llm_fallback_code"
    latency_ms: float = 0.0
    llm_tokens: int = 0
    error: Optional[str] = None


class ParserConfig:
    """Per-component strategy config, driven by env var + defaults."""

    def __init__(self, component: str, default_strategy: str = "code"):
        self.component = component.upper()
        self.env_key = f"PARSER_{self.component}"
        self._strategy = os.getenv(self.env_key, default_strategy).lower()
        valid = {"code", "llm", "hybrid"}
        if self._strategy not in valid:
            logger.warning(
                "PARSER_%s=%r invalido, usando 'code'. Valores permitidos: %s",
                self.component, self._strategy, valid,
            )
            self._strategy = "code"

    @property
    def strategy(self) -> str:
        return self._strategy

    def __repr__(self) -> str:
        return f"ParserConfig({self.component}={self.strategy})"


class HybridParser(ABC):
    """
    One per component. Subclass MUST implement:
      - parse_llm(raw, ctx)  → ParseResult
      - parse_code(raw, ctx) → ParseResult

    See existing impl in app/utils/date_parser.py::parse_datetime_llm.
    """

    def __init__(self, component: str, default_strategy: str = "code"):
        self.config = ParserConfig(component, default_strategy)
        self.logger = logging.getLogger(f"hybrid.{component}")

    @abstractmethod
    async def parse_llm(self, raw: str, ctx: dict) -> ParseResult:
        """LLM-based parsing. Must handle temperature=0, max_tokens ≤ 50."""

    @abstractmethod
    def parse_code(self, raw: str, ctx: dict) -> ParseResult:
        """Deterministic (regex/map) parsing. Must never raise."""

    async def parse(self, raw: str, ctx: dict = None) -> ParseResult:
        """Main entry point. Routes based on configured strategy."""
        ctx = ctx or {}
        t0 = time.perf_counter()

        if self.config.strategy == "code":
            result = self.parse_code(raw, ctx)

        elif self.config.strategy == "llm":
            result = await self.parse_llm(raw, ctx)

        else:  # "hybrid" — LLM first, code fallback
            result = await self.parse_llm(raw, ctx)
            if result.value is None and result.error is None:
                # LLM had a technical failure (API error, bad format)
                # → fall back to deterministic code path
                self.logger.info(
                    "LLM parser sin resultado para %r — fallback a code", raw
                )
                code_result = self.parse_code(raw, ctx)
                result = ParseResult(
                    value=code_result.value,
                    confidence=code_result.confidence,
                    parser_used="llm_fallback_code",
                    latency_ms=code_result.latency_ms,
                    llm_tokens=result.llm_tokens,
                    error=code_result.error,
                )

        latency = (time.perf_counter() - t0) * 1000
        result.latency_ms = round(latency, 1)
        self._emit_metric(result, raw)
        return result

    def _emit_metric(self, result: ParseResult, raw: str) -> None:
        """Log structured metric for dashboard / log analysis."""
        self.logger.info(
            "PARSER_METRIC | component=%s strategy=%s parser=%s "
            "latency_ms=%.1f tokens=%d confidence=%.2f error=%s | raw=%r value=%r",
            self.config.component,
            self.config.strategy,
            result.parser_used,
            result.latency_ms,
            result.llm_tokens,
            result.confidence,
            result.error or "none",
            raw[:80],
            str(result.value)[:80] if result.value else "None",
        )
```

### Task 0.3 — Create `app/core/hybrid/registry.py`

```python
"""Central registry: discover parsers by component name."""
from typing import Dict, Type, Optional
from .base import HybridParser

_registry: Dict[str, HybridParser] = {}


def register(component: str, parser: HybridParser) -> None:
    _registry[component] = parser


def get(component: str) -> Optional[HybridParser]:
    """Get parser by component name. Returns None if not registered."""
    return _registry.get(component)


def list_parsers() -> Dict[str, str]:
    """Show all registered parsers and their current strategy."""
    return {
        name: p.config.strategy
        for name, p in sorted(_registry.items())
    }
```

### REVIEW GATE 0

- [ ] `app/core/hybrid/` package exists with `__init__.py`, `base.py`, `registry.py`
- [ ] `HybridParser.parse()` correctly routes through all 3 strategies
- [ ] `llm_fallback_code` path: when LLM returns `(None, None)`, code path is called and `parser_used` field reflects the fallback
- [ ] `ParserConfig` reads from env var, falls back to default, logs warning on invalid values
- [ ] `_emit_metric` logs a single line parsable by log aggregators
- [ ] All files pass `ruff check` and `mypy --strict`
- [ ] Exports are clean: `from app.core.hybrid import HybridParser, ParseResult`

---

## Phase 1: Name Extraction (Background, Zero Risk)

### Context
The bot needs the user's full name to schedule visits. Currently:
- The LLM is told to pass `client_name` to `schedule_visit` (prompt-level instruction)
- There is no dedicated extraction — the LLM guesses from context
- If the user says "soy Juan Pérez" in turn 3, the bot doesn't know the name until turn 7 when scheduling happens
- Each extra turn asking "¿cuál es tu nombre?" is wasted latency

**LLM advantage:** Can extract name from any turn ("hola soy Juan", "Juan Pérez al habla", "me llamo Juan Pérez", signature blocks) where regex can't.

**Risk level:** ZERO — this runs as a background task after the main response. Never blocks the user.

### Task 1.1 — Create `app/core/hybrid/name.py`

```python
"""Name extraction: background LLM parser that catches 'soy Juan Pérez' from any turn."""
import re
from typing import Optional
from .base import HybridParser, ParseResult


_KNOWN_TITLES = {"sr", "sra", "srta", "dr", "dra", "lic", "ingeniero", "ing"}


def _code_extract_name(text: str) -> Optional[str]:
    """Fast regex-based name extraction for common patterns.
    Used as fallback when LLM is unavailable."""
    text_clean = text.strip()
    if not text_clean:
        return None

    patterns = [
        # "soy Juan Pérez" / "Soy Juan Perez"
        r'(?:soy|me llamo|mi nombre es|me presento|habla)\s+([A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+(?:\s+[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+){0,2})',
        # "Juan Pérez al habla"
        r'^([A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+(?:\s+[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+){0,2})\s+al\s+habla',
        # Signature: "-- Juan Pérez"
        r'(?:^|--|—)\s*([A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+(?:\s+[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+){1,2})\s*$',
    ]
    for pat in patterns:
        m = re.search(pat, text_clean)
        if m:
            candidate = m.group(1).strip()
            # Filter out false positives (single words, titles-only)
            parts = candidate.split()
            if len(parts) >= 2 and parts[0].lower() not in _KNOWN_TITLES:
                return candidate
    return None


_NAME_SYSTEM_PROMPT = (
    "Sos un extractor de nombres para un chatbot inmobiliario argentino.\n"
    "Tu única tarea: extraer el nombre completo de la persona en el texto.\n\n"
    "Reglas:\n"
    "- Respondé SOLO con el nombre completo o 'NONE'.\n"
    "- Nombre completo = nombre + al menos un apellido.\n"
    "- 'Juan' solo → 'NONE' (necesitamos apellido).\n"
    "- 'Juan Pérez' → 'Juan Pérez'.\n"
    "- 'Juan Carlos Pérez García' → 'Juan Carlos Pérez García'.\n"
    "- Si hay indicación de que es seudónimo/apodo → 'NONE'.\n"
    "- Nunca des explicaciones, solo el nombre o 'NONE'.\n"
    "- No uses acentos (Perez no Pérez)."
)


class NameExtractor(HybridParser):
    """Extract user full name from any conversational turn."""

    def __init__(self):
        super().__init__(component="NAME", default_strategy="hybrid")
        # Default is hybrid: LLM-first, code-fallback.
        # Set PARSER_NAME=code to disable LLM altogether.

    async def parse_llm(self, raw: str, ctx: dict) -> ParseResult:
        from app.agents.llm_router import llm_router

        if not raw or len(raw.strip()) < 5:
            return ParseResult(None, 0.0, "llm")

        result = await llm_router.chat(
            message=raw,
            system_prompt=_NAME_SYSTEM_PROMPT,
            temperature=0,
            max_tokens=15,
        )
        result = (result or "").strip().strip('"').strip("'")

        if not result or result.upper() == "NONE":
            return ParseResult(None, 0.0, "llm")

        return ParseResult(
            value=result,
            confidence=0.9,
            parser_used="llm",
        )

    def parse_code(self, raw: str, ctx: dict) -> ParseResult:
        candidate = _code_extract_name(raw)
        if candidate:
            return ParseResult(value=candidate, confidence=0.6, parser_used="code")
        return ParseResult(None, 0.0, "code")


# Singleton
name_extractor = NameExtractor()
```

### Task 1.2 — Wire into agent background task

Find `_extract_and_save_preferences()` in `app/agents/real_estate_agent.py` (line 833). Add name extraction before the existing preference logic:

```python
# Inside _extract_and_save_preferences, after the try/except block starts:
async def _extract_and_save_preferences(self, phone, message, current_prefs):
    try:
        # — NEW: background name extraction (runs every turn, no user-facing latency) —
        if message and phone:
            existing_name = current_prefs.get("name") or (await memory_manager.get_user_name(phone))
            if not existing_name:
                name_result = await name_extractor.parse(message, {})
                if name_result.value and name_result.confidence >= 0.6:
                    await memory_manager.save_user_name(phone, name_result.value)
                    logger.info(
                        "[NameExtractor] Extracted name %r for %s (parser=%s, conf=%.2f)",
                        name_result.value, phone, name_result.parser_used, name_result.confidence,
                    )

        # — existing preference extraction —
        await memory_manager.extract_and_save_preferences(phone, message, current_prefs)
        logger.info("Preferencias extraídas y guardadas exitosamente")
    except Exception as e:
        logger.error("Error guardando preferencias: %s", e)
```

### Task 1.3 — Add helper methods to `MemoryManager`

In `app/core/memory.py`, add:

```python
async def get_user_name(self, phone: str) -> Optional[str]:
    """Get user's full name from Redis or DB."""
    # 1. Check Redis first
    ctx = await self.get_context(phone)
    if ctx and ctx.get("name"):
        return ctx["name"]
    # 2. Check DB
    try:
        from app.db.repository import UserRepository
        from app.db.models import User
        from app.db.session import async_session_factory
        async with async_session_factory() as session:
            repo = UserRepository(User, session)
            user = await repo.get_by_phone(phone)
            return user.name if user and user.name else None
    except Exception:
        return None

async def save_user_name(self, phone: str, name: str) -> None:
    """Save user's full name to both Redis and DB."""
    # Redis
    await self.update_context_field(phone, "name", name)
    # DB
    try:
        from app.db.repository import UserRepository
        from app.db.models import User
        from app.db.session import async_session_factory
        async with async_session_factory() as session:
            repo = UserRepository(User, session)
            user = await repo.get_by_phone(phone)
            if user:
                await repo.update(user.id, name=name)
                await session.commit()
    except Exception as e:
        logger.warning("save_user_name: DB error — %s", e)
```

### REVIEW GATE 1

- [ ] `PARSER_NAME=code` → uses only regex (`_code_extract_name`). Zero LLM calls.
- [ ] `PARSER_NAME=hybrid` (default) → LLM first, code fallback on API errors.
- [ ] `PARSER_NAME=llm` → pure LLM. If LLM is down, returns `(None, ...)`.
- [ ] Name is saved to BOTH Redis and PostgreSQL. If one fails, the other still works.
- [ ] If name already exists in DB, no extraction is attempted (skip LLM call).
- [ ] Background task errors never propagate to the user response. `try/except` wraps everything.
- [ ] `ruff check app/core/hybrid/name.py` passes.
- [ ] Logs show `PARSER_METRIC | component=NAME` on every turn with a message.

---

## Phase 2: Location Normalization

### Context
`app/utils/sanitizer.py::normalize_location()` strips street prefixes + numbers with regex:
```python
for prefix in [ "calle", "av", "av.", "avenida", ... ]:  # 13 prefixes
    if loc.startswith(prefix + " "):
        loc = loc[len(prefix):].strip()
loc = re.sub(r'\s+\d+\s*$', '', loc).strip()
```

**What breaks:**
- "cerca de la terminal de Oberá" → regex keeps full string → ILIKE matches nothing
- "en el centro de Posadas" → regex keeps "centro de posadas" → no city match
- "zona norte de Encarnación" → "zona norte de encarnación" → no match
- "alquiler en Asunción cerca del Paseo La Galería" → too much noise

**LLM advantage:** Can extract the canonical city name from messy location descriptions. "Cerca de la terminal de Oberá" → "Oberá". "Zona céntrica de Posadas" → "Posadas".

**Risk level:** LOW. If LLM returns bad data, the search will just return fewer results (same as current behavior). The code fallback catches technical failures.

### Task 2.1 — Create `app/core/hybrid/location.py`

```python
"""Location normalization: extract canonical city name from messy descriptions."""
import re
from typing import Set
from .base import HybridParser, ParseResult


# All known cities/towns in the database.
# Populated from DB on startup. Fallback static list.
_KNOWN_CITIES: Set[str] = {
    "posadas", "oberá", "encarnación", "asunción", "puerto iguazú",
    "eldorado", "apóstoles", "leandro n. alem", "san javier",
    "candelaria", "garupá", "montecarlo", "puerto rico",
    "resistencia", "corrientes", "formosa",
    "ciudad del este", "luque", "lambaré", "san lorenzo",
    "fernando de la mora", "capiatá", "itaugua", "ypacarai",
}


def _code_normalize(raw: str) -> ParseResult:
    """Current regex logic, wrapped in ParseResult."""
    if not raw:
        return ParseResult(None, 0.0, "code")
    # Try exact city match first
    raw_lower = raw.lower().strip()
    for city in _KNOWN_CITIES:
        if city in raw_lower:
            return ParseResult(city.title(), 0.7, "code")
    # Fallback: strip prefixes + numbers (current logic)
    loc = raw_lower
    from app.utils.sanitizer import _STREET_PREFIXES
    for prefix in _STREET_PREFIXES:
        if loc.startswith(prefix + " ") or loc == prefix:
            loc = loc[len(prefix):].strip()
            break
    loc = re.sub(r'\s+\d+\s*$', '', loc).strip()
    if loc:
        return ParseResult(loc.title(), 0.3, "code")
    return ParseResult(None, 0.0, "code")


_LOCATION_SYSTEM_PROMPT = (
    "Sos un extractor de ubicaciones para un chatbot de bienes raíces en Argentina/Paraguay.\n"
    "Tu única tarea: extraer la ciudad o pueblo del texto del usuario.\n\n"
    "Reglas:\n"
    "- Respondé SOLO con el nombre de la ciudad o 'UNKNOWN'.\n"
    "- Ej: 'cerca de la terminal de Oberá' → 'Oberá'\n"
    "- Ej: 'en el centro de Posadas' → 'Posadas'\n"
    "- Ej: 'zona norte de Encarnación' → 'Encarnación'\n"
    "- Ej: 'alquiler en Asunción cerca del Paseo La Galería' → 'Asunción'\n"
    "- Si no hay ciudad clara → 'UNKNOWN'\n"
    "- Usá el nombre completo, no apodos.\n"
    "- Nunca des explicaciones."
)


class LocationParser(HybridParser):
    """Extract canonical city name from free-text location descriptions."""

    def __init__(self):
        super().__init__(component="LOCATION", default_strategy="hybrid")

    async def parse_llm(self, raw: str, ctx: dict) -> ParseResult:
        from app.agents.llm_router import llm_router

        if not raw or len(raw.strip()) < 3:
            return ParseResult(None, 0.0, "llm")

        result = await llm_router.chat(
            message=raw,
            system_prompt=_LOCATION_SYSTEM_PROMPT,
            temperature=0,
            max_tokens=20,
        )
        result = (result or "").strip()

        if not result or result.upper() == "UNKNOWN":
            return ParseResult(None, 0.0, "llm")

        return ParseResult(
            value=result.strip(),
            confidence=0.9,
            parser_used="llm",
        )

    def parse_code(self, raw: str, ctx: dict) -> ParseResult:
        return _code_normalize(raw)


# Singleton
location_parser = LocationParser()
```

### Task 2.2 — Wire into `search_properties()` in tools.py

Find the location normalization block in `app/agents/tools.py` (around line 202):

```python
# === REPLACE THIS ===
if criteria.get("location"):
    loc = criteria["location"].strip()
    search_criteria["location"] = loc
    logger.info(f"[TOOL] Location normalizada: '{loc}'")

# === WITH THIS ===
if criteria.get("location"):
    raw_loc = criteria["location"].strip()
    loc_result = await location_parser.parse(raw_loc, {})
    if loc_result.value:
        search_criteria["location"] = loc_result.value
        logger.info(
            "[TOOL] Location: raw=%r → parsed=%r (parser=%s, conf=%.2f)",
            raw_loc, loc_result.value, loc_result.parser_used, loc_result.confidence,
        )
    else:
        # Fallback: use original value (search will likely return empty)
        search_criteria["location"] = raw_loc
        logger.info("[TOOL] Location parser falló, usando raw: %r", raw_loc)
```

### Task 2.3 — Update `_KNOWN_CITIES` from DB on startup

In `app/core/hybrid/location.py`, add a startup hook:

```python
async def refresh_known_cities():
    """Pull distinct cities from the properties table."""
    try:
        from app.db.session import async_session_factory
        from app.db.models.property import Property
        from sqlalchemy import select, func
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.distinct(Property.location))
            )
            cities = {row[0].lower() for row in result if row[0]}
            if cities:
                _KNOWN_CITIES.clear()
                _KNOWN_CITIES.update(cities)
                logger.info("refresh_known_cities: %d cities loaded from DB", len(cities))
    except Exception as e:
        logger.warning("refresh_known_cities: DB error (using static list) — %s", e)
```

Call this from `app/main.py` lifespan:

```python
# In lifespan startup, after DB is initialized:
from app.core.hybrid.location import refresh_known_cities
await refresh_known_cities()
```

### REVIEW GATE 2

- [ ] `PARSER_LOCATION=code` → exact same behavior as current `normalize_location()`. Zero regression risk.
- [ ] `PARSER_LOCATION=hybrid` → LLM extracts city. If LLM fails (API error, bad format), code fallback runs.
- [ ] `_KNOWN_CITIES` is populated from DB on startup, with static fallback.
- [ ] When LLM returns "UNKNOWN", no city filter is applied (skips location in search_criteria).
- [ ] Logs show `PARSER_METRIC | component=LOCATION` on every search.
- [ ] `ruff check app/core/hybrid/location.py` passes.
- [ ] Manual test: `search_properties({"location": "cerca de la terminal de Oberá"})` returns Oberá properties.

---

## Phase 3: Property Reference Resolution

### Context
The bot uses `selected_property_id` — set by the last `get_property_details`/`get_property_images` call. If the user switches conversation topics:

```
User: "mostrame el depto de 2 ambientes"
Bot: shows ID:6 → selected_property_id=6
User: "y qué precio tiene el de la calle San Martín?"
Bot: 'selected_property_id' is still 6 → shows wrong property
```

**LLM advantage:** Can compare the user's description against the list of recently-shown properties and pick the correct one, even when the user doesn't use the exact ID.

**Risk level:** MEDIUM. If the LLM hallucinates a match, the user gets wrong property data. Mitigation: only override `selected_property_id` when confidence > 0.8.

### Task 3.1 — Create `app/core/hybrid/reference.py`

```python
"""Property reference resolution: match user descriptions to shown properties."""
from typing import List, Optional
from .base import HybridParser, ParseResult
from dataclasses import dataclass


@dataclass
class PropertyOption:
    id: str
    title: str
    # Optional: add location, price, bedrooms for richer matching


_REFERENCE_SYSTEM_PROMPT = (
    "Sos un resolvedor de referencias para un chatbot inmobiliario.\n"
    "El usuario mencionó una propiedad. Tenés estas opciones disponibles:\n"
    "{options}\n\n"
    "Mensaje del usuario: \"{message}\"\n\n"
    "Reglas:\n"
    "- Respondé SOLO con el ID numérico de la propiedad correcta o 'UNKNOWN'.\n"
    "- 'esa', 'esa propiedad', 'la que vimos' → propiedad activa (ID más relevante).\n"
    "- 'el depto de 2 ambientes' → buscá en las opciones cuál tiene '2 ambientes' o '2 hab'.\n"
    "- 'la casa de Villa Edna' → buscá 'Villa Edna' en los títulos.\n"
    "- Si es ambiguo entre varias → 'UNKNOWN'.\n"
    "- Si no coincide con ninguna → 'UNKNOWN'.\n"
    "- Nunca inventes un ID. Solo usá los que están en la lista.\n"
    "- Nunca des explicaciones."
)


class PropertyReferenceParser(HybridParser):
    """Resolve 'esa', 'el depto de 2 amb', 'la casa de Villa Edna' → property ID."""

    def __init__(self):
        super().__init__(component="REFERENCE", default_strategy="hybrid")

    def _format_options(self, props: List[PropertyOption]) -> str:
        if not props:
            return "No hay propiedades disponibles."
        lines = []
        for p in props:
            lines.append(f"  - ID:{p.id} → {p.title}")
        return "\n".join(lines)

    async def parse_llm(self, raw: str, ctx: dict) -> ParseResult:
        from app.agents.llm_router import llm_router

        props: List[PropertyOption] = ctx.get("property_options", [])
        if not props:
            return ParseResult(None, 0.0, "llm")

        options_str = self._format_options(props)
        prompt = _REFERENCE_SYSTEM_PROMPT.format(
            options=options_str, message=raw
        )

        result = await llm_router.chat(
            message=raw,
            system_prompt=prompt,
            temperature=0,
            max_tokens=10,
        )
        result = (result or "").strip()

        if not result or result.upper() == "UNKNOWN":
            return ParseResult(None, 0.0, "llm")

        # Validate: result must be an integer matching one of the options
        try:
            int_result = int(result)
            if any(int_result == int(p.id) for p in props):
                return ParseResult(
                    value=str(int_result),
                    confidence=0.9,
                    parser_used="llm",
                )
        except ValueError:
            pass

        return ParseResult(None, 0.0, "llm")

    def parse_code(self, raw: str, ctx: dict) -> ParseResult:
        """Code fallback: just return the selected_property_id from context."""
        prop_id = ctx.get("selected_property_id")
        if prop_id:
            return ParseResult(
                value=str(prop_id),
                confidence=0.5,
                parser_used="code",
            )
        return ParseResult(None, 0.0, "code")


# Singleton
reference_parser = PropertyReferenceParser()
```

### Task 3.2 — Wire into agent loop conditionally

In `app/agents/real_estate_agent.py`, BEFORE sending messages to the LLM, add:

```python
# === NEW: Property reference resolution ===
# Only activate when the user message doesn't explicitly mention an ID
# and the context has recent properties to match against
if (
    user_message
    and not any(id_str in user_message for id_str in ["ID:", "id ", "ID "])
    and merged_context.get("last_shown_properties")
):
    ctx = {
        "property_options": [
            PropertyOption(
                id=str(p.get("id", "")),
                title=p.get("title", ""),
            )
            for p in merged_context["last_shown_properties"]
        ],
        "selected_property_id": merged_context.get("selected_property_id"),
    }
    ref_result = await reference_parser.parse(user_message, ctx)
    if ref_result.value and ref_result.confidence >= 0.8:
        logger.info(
            "[ReferenceParser] User reference %r → property %s (conf=%.2f, parser=%s)",
            user_message, ref_result.value, ref_result.confidence, ref_result.parser_used,
        )
        # Override the selected property
        merged_context["selected_property_id"] = ref_result.value
        # Also update Redis
        await memory_manager.update_context_field(
            phone, "selected_property_id", ref_result.value
        )
```

### REVIEW GATE 3

- [ ] `PARSER_REFERENCE=code` → always returns `selected_property_id` from context (current behavior).
- [ ] `PARSER_REFERENCE=hybrid` → LLM resolves only when `last_shown_properties` is non-empty and message has no explicit ID mention.
- [ ] `PARSER_REFERENCE=llm` → LLM always resolves (even for explicit IDs — useful for A/B testing).
- [ ] LLM result is validated: must be an integer matching a known property ID.
- [ ] Confidence threshold (0.8) prevents low-confidence overrides.
- [ ] Redis is updated atomically alongside the in-memory context.
- [ ] Logs show `PARSER_METRIC | component=REFERENCE` on every attempt.

---

## Phase 4: Budget Tier Resolution

### Context
`app/agents/budget_tiers.py` computes static price thresholds (economico/normal/premium) from DB queries. The LLM tool parameter `price_tier` accepts: "economico", "normal", "premium".

**What breaks:**
- "algo económico en Posadas" → same threshold as "económico en Puerto Iguazú" (wrong — prices differ by 40%+)
- "moderado" → not in the enum → LLM won't send it
- "no muy caro" → no mapping

**LLM advantage:** Contextual interpretation: what "económico" means in Oberá vs Posadas vs Asunción.

### Task 4.1 — Create `app/core/hybrid/budget.py`

```python
"""Budget tier resolution: vague price terms → numeric ranges."""
from .base import HybridParser, ParseResult


_BUDGET_SYSTEM_PROMPT = (
    "Sos un resolvedor de presupuestos para bienes raíces en Argentina/Paraguay.\n"
    "Convertí términos vagos de presupuesto a rangos numéricos en USD.\n\n"
    "Ciudad: {city}\n"
    "Mediana de precios en esta ciudad: ${median_price}\n"
    "Término del usuario: \"{term}\"\n\n"
    "Reglas:\n"
    "- Respondé SOLO con JSON: {{\"min\": N, \"max\": N}} o 'UNKNOWN'.\n"
    "- 'económico'/'barato'/'no muy caro' → por debajo de la mediana.\n"
    "- 'normal'/'promedio'/'intermedio' → alrededor de la mediana (±20%).\n"
    "- 'premium'/'caro'/'lujoso' → por encima de la mediana.\n"
    "- 'lo más barato'/'lo mínimo' → min=0, max=60% de la mediana.\n"
    "- Si el término no es de presupuesto → 'UNKNOWN'.\n"
    "- Nunca des explicaciones."
)


class BudgetTierParser(HybridParser):
    """Interpret 'económico', 'normal', 'premium' → [min, max] range."""

    def __init__(self):
        super().__init__(component="BUDGET", default_strategy="hybrid")

    async def parse_llm(self, raw: str, ctx: dict) -> ParseResult:
        from app.agents.llm_router import llm_router
        import json

        city = ctx.get("city", "desconocida")
        median = ctx.get("median_price", 500)

        result = await llm_router.chat(
            message=raw,
            system_prompt=_BUDGET_SYSTEM_PROMPT.format(
                city=city, median_price=median, term=raw,
            ),
            temperature=0,
            max_tokens=50,
        )
        result = (result or "").strip()

        if not result or result.upper() == "UNKNOWN":
            return ParseResult(None, 0.0, "llm")

        try:
            data = json.loads(result)
            min_v = int(data.get("min", 0))
            max_v = int(data.get("max", 0))
            if max_v > 0 and min_v >= 0:
                return ParseResult(
                    value={"budget_min": min_v, "budget_max": max_v},
                    confidence=0.85,
                    parser_used="llm",
                )
        except (ValueError, json.JSONDecodeError):
            pass

        return ParseResult(None, 0.0, "llm")

    def parse_code(self, raw: str, ctx: dict) -> ParseResult:
        """Current budget_tiers.py logic."""
        from app.agents.budget_tiers import get_budget_tiers
        import asyncio

        try:
            tiers = asyncio.run(get_budget_tiers())
        except Exception:
            return ParseResult(None, 0.0, "code")

        raw_lower = raw.lower().strip()
        if raw_lower in ("económico", "economico", "barato"):
            return ParseResult(
                value={"budget_max": tiers["low_max"]},
                confidence=0.7,
                parser_used="code",
            )
        elif raw_lower in ("normal", "promedio", "intermedio"):
            return ParseResult(
                value={
                    "budget_min": tiers["low_max"] + 1,
                    "budget_max": tiers["med_max"],
                },
                confidence=0.7,
                parser_used="code",
            )
        elif raw_lower in ("premium", "caro", "lujoso"):
            return ParseResult(
                value={"budget_min": tiers["med_max"] + 1},
                confidence=0.7,
                parser_used="code",
            )
        return ParseResult(None, 0.0, "code")


# Singleton
budget_parser = BudgetTierParser()
```

### Task 4.2 — Wire into `search_properties()` in tools.py

Replace the current `price_tier` block (around line 244):

```python
# === REPLACE THIS ===
price_tier = criteria.get("price_tier")
if price_tier:
    try:
        from app.agents.budget_tiers import get_budget_tiers
        tiers = await get_budget_tiers()
        if price_tier == "economico":
            search_criteria["budget_max"] = tiers["low_max"]
        elif price_tier == "normal":
            ...
    except Exception:
        ...

# === WITH THIS ===
price_tier = criteria.get("price_tier")
if price_tier:
    ctx = {
        "city": search_criteria.get("location", "desconocida"),
        "median_price": 500,  # Could be fetched from DB per city
    }
    budget_result = await budget_parser.parse(price_tier, ctx)
    if budget_result.value and isinstance(budget_result.value, dict):
        if "budget_min" in budget_result.value:
            search_criteria["budget_min"] = budget_result.value["budget_min"]
        if "budget_max" in budget_result.value:
            search_criteria["budget_max"] = budget_result.value["budget_max"]
        logger.info(
            "[TOOL] Budget tier %r → %s (parser=%s, conf=%.2f)",
            price_tier, budget_result.value,
            budget_result.parser_used, budget_result.confidence,
        )
```

### REVIEW GATE 4

- [ ] `PARSER_BUDGET=code` → exact same behavior as current `budget_tiers.py`.
- [ ] `PARSER_BUDGET=hybrid` → LLM contextualizes by city. Falls back to static thresholds.
- [ ] LLM output is validated as `{"min": int, "max": int}` with positive values.
- [ ] City median price is passed to LLM prompt for contextualization.
- [ ] Logs show `PARSER_METRIC | component=BUDGET` on every price_tier usage.

---

## Phase 5: Preference Extraction

### Context
`app/core/memory.py::extract_and_save_preferences()` uses ~120 lines of cascading regex + static dicts for 6 preference types:
- Location (keyword matching against 14 known cities)
- Budget (4 regex patterns)
- Property type (16-entry static dict)
- Operation type (8-entry static dict)
- Bedrooms (3 regex patterns)
- Bathrooms (2 regex patterns)

**LLM advantage:** Can extract **qualitative** preferences that regex can't touch: "quiero algo tranquilo" → `quiet: true`, "prefiero balcón y patio" → `features: ["balcony", "patio"]`, "necesito cerca del centro" → `proximity: "center"`.

### Task 5.1 — Create `app/core/hybrid/preference.py`

```python
"""Preference extraction: user preferences from conversational turns."""
import json
from typing import Optional
from .base import HybridParser, ParseResult


_PREFERENCE_SYSTEM_PROMPT = (
    "Sos un extractor de preferencias para un chatbot de bienes raíces en Argentina/Paraguay.\n"
    "Del siguiente mensaje del usuario, extraé TODAS las preferencias que puedas identificar.\n\n"
    "Respondé SOLO con JSON. Campos disponibles:\n"
    "{{\n"
    '  "location": "nombre de ciudad o null",\n'
    '  "budget_max": numero en USD o null,\n'
    '  "budget_min": numero en USD o null,\n'
    '  "property_type": "casa|departamento|terreno|oficina|local|ph|duplex|cabaña" o null,\n'
    '  "operation_type": "venta|alquiler" o null,\n'
    '  "bedrooms": numero o null,\n'
    '  "bathrooms": numero o null,\n'
    '  "features": ["balcon", "cochera", "patio", "pileta", "ascensor", "parrilla", "seguridad", "jardin", "quincho"] o [],\n'
    '  "qualitative": ["tranquilo", "centrico", "nuevo", "amplio", "luminoso", "silencioso", "acogedor"] o []\n'
    "}}\n\n"
    "Reglas:\n"
    "- Solo extraé lo que el usuario EXPRESAMENTE mencionó.\n"
    "- Si no hay información nueva, respondé {{\"features\":[], \"qualitative\":[]}}.\n"
    "- Nunca inventes preferencias.\n"
    "- Nunca des explicaciones ni texto fuera del JSON."
)


class PreferenceExtractor(HybridParser):
    """Extract structured preferences (incl. qualitative) from user messages."""

    def __init__(self):
        super().__init__(component="PREFERENCE", default_strategy="hybrid")

    async def parse_llm(self, raw: str, ctx: dict) -> ParseResult:
        from app.agents.llm_router import llm_router

        if not raw or len(raw.strip()) < 5:
            return ParseResult(None, 0.0, "llm")

        result = await llm_router.chat(
            message=raw,
            system_prompt=_PREFERENCE_SYSTEM_PROMPT,
            temperature=0,
            max_tokens=120,
        )
        result = (result or "").strip()

        if not result:
            return ParseResult(None, 0.0, "llm")

        # Strip markdown code fences if present
        if result.startswith("```"):
            result = result.split("\n", 1)[-1].rsplit("\n", 1)[0] if "\n" in result else result.replace("```json", "").replace("```", "")
            result = result.strip()

        try:
            data = json.loads(result)
            # Validate: at least one field must be non-null
            has_content = any(
                v for k, v in data.items()
                if k in ("location", "budget_max", "budget_min", "property_type",
                         "operation_type", "bedrooms", "bathrooms")
                and v is not None
            ) or data.get("features") or data.get("qualitative")
            if has_content:
                return ParseResult(
                    value=data,
                    confidence=0.85,
                    parser_used="llm",
                )
        except (json.JSONDecodeError, TypeError):
            pass

        return ParseResult(None, 0.0, "llm")

    def parse_code(self, raw: str, ctx: dict) -> ParseResult:
        """Current regex-based extraction, wrapped in ParseResult."""
        # Import current extraction logic and delegate to it
        from app.core.memory import memory_manager
        import asyncio

        try:
            prefs = asyncio.run(
                memory_manager.extract_and_save_preferences(
                    ctx.get("phone", "unknown"), raw, ctx.get("current_prefs", {})
                )
            )
            if prefs:
                return ParseResult(value=prefs, confidence=0.6, parser_used="code")
        except Exception:
            pass
        return ParseResult(None, 0.0, "code")


# Singleton
preference_extractor = PreferenceExtractor()
```

### Task 5.2 — Wire into agent background task

In `app/agents/real_estate_agent.py`, replace the existing `_extract_and_save_preferences` call:

```python
async def _extract_and_save_preferences(self, phone, message, current_prefs):
    try:
        ctx = {"phone": phone, "current_prefs": current_prefs}
        pref_result = await preference_extractor.parse(message, ctx)

        if pref_result.value:
            prefs = pref_result.value

            # Save basic fields (backward-compatible with existing schema)
            if prefs.get("location"):
                current_prefs["location_preferences"] = prefs["location"]
            if prefs.get("budget_max"):
                current_prefs["budget_max"] = prefs["budget_max"]
            if prefs.get("budget_min"):
                current_prefs["budget_min"] = prefs["budget_min"]
            if prefs.get("property_type"):
                current_prefs["property_type"] = prefs["property_type"]
            if prefs.get("operation_type"):
                current_prefs["operation_type"] = prefs["operation_type"]
            if prefs.get("bedrooms"):
                current_prefs["bedrooms"] = prefs["bedrooms"]
            if prefs.get("bathrooms"):
                current_prefs["bathrooms"] = prefs["bathrooms"]

            # NEW: save qualitative preferences (features + qualitative)
            if prefs.get("features") or prefs.get("qualitative"):
                current_prefs["qualitative_prefs"] = {
                    "features": prefs.get("features", []),
                    "qualitative": prefs.get("qualitative", []),
                }

            # Save to Redis
            await memory_manager.update_context(phone, current_prefs)
            logger.info(
                "Preferencias extraídas via %s: %s",
                pref_result.parser_used,
                {k: v for k, v in prefs.items() if v},
            )
        else:
            # Fallback: existing regex extraction
            await memory_manager.extract_and_save_preferences(
                phone, message, current_prefs
            )

    except Exception as e:
        logger.error("Error guardando preferencias: %s", e)
```

### REVIEW GATE 5

- [ ] `PARSER_PREFERENCE=code` → exact same regex extraction as current.
- [ ] `PARSER_PREFERENCE=hybrid` → LLM extracts quantitative + qualitative prefs. Falls back to regex.
- [ ] LLM output is validated: must be valid JSON with at least one non-empty field.
- [ ] `qualitative_prefs` is a new field in Redis context, does not break existing schema.
- [ ] Background task errors never propagate to user response.
- [ ] Logs show `PARSER_METRIC | component=PREFERENCE`.

---

## Phase 6: Date Parser Migration (Wrap Existing)

### Context
The date parser already has `parse_datetime_llm()` in `app/utils/date_parser.py` (added in commit `21dd200`). But it's called directly from `tools.py:774-779` — not through the hybrid infrastructure.

This phase wraps the existing implementation into a `HybridParser` so it's consistent with the other parsers, and extends the same pattern to `reschedule_appointment_tool`.

### Task 6.1 — Create `app/core/hybrid/date.py`

```python
"""Date/time parsing: wrap existing parse_datetime_llm into HybridParser pattern."""
from datetime import datetime
from typing import Optional
from .base import HybridParser, ParseResult


class DateParser(HybridParser):
    """Spanish date/time expression → timezone-aware datetime.
    Wraps existing parse_datetime_llm + parse_spanish_datetime."""

    def __init__(self):
        super().__init__(component="DATE", default_strategy="hybrid")

    async def parse_llm(self, raw: str, ctx: dict) -> ParseResult:
        from app.utils.date_parser import parse_datetime_llm, get_argentina_now

        date_str = ctx.get("date_str", raw)
        time_str = ctx.get("time_str")
        now = ctx.get("reference_dt", get_argentina_now())

        parsed_dt, error = await parse_datetime_llm(date_str, time_str, now)

        if error:
            return ParseResult(None, 0.0, "llm", error=error)
        if parsed_dt:
            return ParseResult(
                value=parsed_dt,
                confidence=0.95,
                parser_used="llm",
            )
        return ParseResult(None, 0.0, "llm")

    def parse_code(self, raw: str, ctx: dict) -> ParseResult:
        from app.utils.date_parser import parse_spanish_datetime, get_argentina_now

        date_str = ctx.get("date_str", raw)
        time_str = ctx.get("time_str")
        combined = f"{date_str} {time_str or ''}".strip()
        now = ctx.get("reference_dt", get_argentina_now())

        parsed_dt, error = parse_spanish_datetime(combined)

        if error:
            return ParseResult(None, 0.0, "code", error=error)
        if parsed_dt:
            return ParseResult(
                value=parsed_dt,
                confidence=0.9,
                parser_used="code",
            )
        return ParseResult(None, 0.0, "code")


# Singleton
date_parser = DateParser()
```

### Task 6.2 — Wire into `schedule_visit()` in tools.py

Replace lines 773-779:

```python
# === REPLACE THIS ===
# --- Paso 1: LLM parser (primario) ---
parsed_dt, parse_error = await parse_datetime_llm(date_str, time_str, get_argentina_now())
# --- Paso 2: Fallback a regex si el LLM falló técnicamente ---
if parsed_dt is None and parse_error is None:
    logger.info("[schedule_visit] LLM parser sin resultado, fallback a regex")
    parsed_dt, parse_error = parse_spanish_datetime(combined_input)

# === WITH THIS ===
from app.core.hybrid.date import date_parser as hybrid_date_parser

ctx = {"date_str": date_str, "time_str": time_str}
parse_ctx = {"date_str": date_str, "time_str": time_str, "reference_dt": get_argentina_now()}
date_result = await hybrid_date_parser.parse(combined_input, parse_ctx)
parsed_dt = date_result.value
parse_error = date_result.error
```

### Task 6.3 — Wire into `reschedule_appointment_tool()` in tools.py

Currently uses only `parse_spanish_datetime` at line 1046. Replace with:

```python
# === REPLACE ===
parsed_dt, error_msg = parse_spanish_datetime(new_date_str)

# === WITH ===
from app.core.hybrid.date import date_parser as hybrid_date_parser
date_result = await hybrid_date_parser.parse(
    new_date_str,
    {"date_str": new_date_str, "time_str": new_time_str},
)
parsed_dt = date_result.value
error_msg = date_result.error
```

### REVIEW GATE 6

- [ ] `PARSER_DATE=code` → pure regex `parse_spanish_datetime()` (same as before LLM was added).
- [ ] `PARSER_DATE=hybrid` → LLM first, regex fallback (same as current `schedule_visit` behavior).
- [ ] `PARSER_DATE=llm` → pure LLM. If LLM is down, scheduling fails with technical error.
- [ ] `reschedule_appointment_tool` now uses the same hybrid pattern as `schedule_visit`.
- [ ] All metrics go through `PARSER_METRIC | component=DATE`.
- [ ] The `import parse_datetime_llm` in tools.py can remain as a fallback, but the primary path goes through `hybrid_date_parser.parse()`.

---

## Phase 7: Final Code Audit

### Context
Before shipping to production, every component must pass these audits.

### Audit 7.1 — Safety Audit (Every Component)

```
Checklist:
[ ] All LLM parser calls use temperature=0
[ ] All LLM parser calls use max_tokens ≤ 200 (DATE ≤ 20, NAME ≤ 15, LOCATION ≤ 20)
[ ] All LLM outputs are validated (strptime, json.loads, int-cast, etc.)
[ ] All parse_code() methods are pure functions — no IO, no awaits, no exceptions
[ ] All parse_llm() methods catch exceptions and return (None, error) never raise
[ ] No API key or secret is passed to any LLM prompt
[ ] User PII (name, phone) is never logged in plain text in _emit_metric
[ ] Background parsers (NAME, PREFERENCE) never block the user response path
```

### Audit 7.2 — Regression Audit

```
Checklist:
[ ] PARSER_NAME=code → bot behavior is IDENTICAL to pre-refactor
[ ] PARSER_LOCATION=code → same
[ ] PARSER_REFERENCE=code → same
[ ] PARSER_BUDGET=code → same
[ ] PARSER_PREFERENCE=code → same
[ ] PARSER_DATE=code → same regex date parsing as before parse_datetime_llm was added
```

Test each with `PARSER_*=code` against the full Monte Carlo test suite:

```bash
cd tests/massive_test && PARSER_NAME=code PARSER_LOCATION=code \
  PARSER_REFERENCE=code PARSER_BUDGET=code PARSER_PREFERENCE=code \
  PARSER_DATE=code python3 -u run_full_test.py
```

### Audit 7.3 — Migration Audit

```
Checklist:
[ ] Every parser has a unique env var (PARSER_{NAME})
[ ] Every parser defaults to 'code' (zero behavior change out of the box)
[ ] Every parser has a singleton instance registered in registry
[ ] registry.list_parsers() returns all 6 parsers + their strategies
[ ] Env vars are documented in Render dashboard
[ ] Setting all env vars to 'code' reproduces pre-refactor behavior exactly
[ ] Switching any single parser to 'hybrid' or 'llm' only affects that component
```

### Audit 7.4 — Performance Audit

Run 100 iterations of each parser, measure:

```bash
# Can be added as a standalone test script:
# tests/benchmark_parsers.py

Parser       | Strategy    | p50(ms) | p99(ms) | Success% | Code fallback%
-------------|-------------|---------|---------|----------|---------------
PARSER_DATE  | code        |    0.01 |    0.02 |   100.0% |        100.0%
PARSER_DATE  | llm         |  450.00 |  920.00 |    98.5% |          0.0%
PARSER_DATE  | hybrid      |   0.01* |   0.02* |   100.0%*|        *see note
PARSER_NAME  | code        |    0.01 |    0.02 |    45.0% |        100.0%
PARSER_NAME  | llm         |  380.00 |  850.00 |    92.0% |          0.0%
PARSER_NAME  | hybrid      |  380.00 |  850.00 |    92.0% |          8.0%
PARSER_LOCAT | code        |    0.01 |    0.02 |    55.0% |        100.0%
PARSER_LOCAT | llm         |  350.00 |  800.00 |    95.0% |          0.0%
...
```

*Note: `hybrid` latency is min(LLM latency, code latency in fallback case). In the 98.5% case where LLM succeeds, hybrid = LLM latency. In the 1.5% fallback case, hybrid = LLM latency + code latency.

### Audit 7.5 — Token Budget Audit

```python
# Maximum tokens consumed per user interaction in "hybrid" mode:

# Name extraction: max 15 tokens (background)
# Location parsing: max 20 tokens (during search_properties)
# Reference resolution: max 10 + options (during turn, conditional)
# Budget tier: max 50 tokens (during search_properties)
# Preference extraction: max 120 tokens (background)
# Date parsing: max 20 tokens (during schedule_visit)

# WORST CASE (user schedules a visit): NAME(15) + DATE(20) + main agent loop
#  = ~35 additional tokens per scheduling interaction

# COST: 35 tokens × ~$0.15/1M tokens × 1000 scheduling attempts/month
#  = $0.00525/month in additional LLM costs. Negligible.
```

### Audit 7.6 — Integration Test

```python
"""
test_hybrid_parsers.py — Full integration test.

Tests every parser in every strategy mode:
1. Set env var to 'code' — verify behavior matches pre-refactor
2. Set env var to 'llm' — verify LLM output format is valid
3. Set env var to 'hybrid' — verify fallback path when LLM fails
4. Verify _emit_metric output format for log aggregation

Run with:
  pytest tests/test_hybrid_parsers.py -v
"""
```

### REVIEW GATE 7 (Final)

- [ ] All 6 audits pass with no failures.
- [ ] Monte Carlo test suite passes with all `PARSER_*=code` (regression check).
- [ ] Monte Carlo test suite passes with all `PARSER_*=hybrid` (new behavior check).
- [ ] Render env vars documented in `render.yaml` or deploy docs.
- [ ] README.md or BOT_DOCUMENTATION.md updated with hybrid architecture section.
- [ ] AGENTS.md updated with new components for Claude Code handoff.

---

## Appendix: Env Var Reference

| Env Var | Default | Options | Component | Background? |
|---------|---------|---------|-----------|-------------|
| `PARSER_DATE` | `hybrid` | `code`, `llm`, `hybrid` | Date/time parsing | No (inline in schedule_visit) |
| `PARSER_NAME` | `hybrid` | `code`, `llm`, `hybrid` | User name extraction | Yes (post-response) |
| `PARSER_LOCATION` | `hybrid` | `code`, `llm`, `hybrid` | City name normalization | No (inline in search) |
| `PARSER_REFERENCE` | `hybrid` | `code`, `llm`, `hybrid` | Property reference resolution | No (inline in agent loop) |
| `PARSER_BUDGET` | `hybrid` | `code`, `llm`, `hybrid` | Budget tier → numeric range | No (inline in search) |
| `PARSER_PREFERENCE` | `hybrid` | `code`, `llm`, `hybrid` | Preference extraction | Yes (post-response) |

## Appendix: File Map

```
app/
├── core/
│   ├── hybrid/
│   │   ├── __init__.py          # Phase 0 — Package exports
│   │   ├── base.py              # Phase 0 — HybridParser ABC, ParseResult, ParserConfig
│   │   ├── registry.py          # Phase 0 — ParserRegistry
│   │   ├── name.py              # Phase 1 — NameExtractor
│   │   ├── location.py          # Phase 2 — LocationParser
│   │   ├── reference.py         # Phase 3 — PropertyReferenceParser
│   │   ├── budget.py            # Phase 4 — BudgetTierParser
│   │   ├── preference.py        # Phase 5 — PreferenceExtractor
│   │   └── date.py              # Phase 6 — DateParser (wrap existing)
│   ├── memory.py                # Phase 1 — Add get_user_name, save_user_name
│   └── ...
├── agents/
│   ├── real_estate_agent.py     # Phase 1, 2, 3, 5 — Wire parsers into agent loop
│   ├── tools.py                 # Phase 2, 4, 6 — Wire into search_properties, schedule_visit, reschedule
│   └── ...
├── main.py                      # Phase 2 — Add refresh_known_cities to lifespan
└── ...
```

## Appendix: Deploy Sequence (Render)

```
Step 1: Deploy Phase 0 (infrastructure only)
  → `git push origin main`
  → Render auto-deploys
  → No behavior change (no parser uses it yet)

Step 2: Deploy Phase 1 (name extraction)
  → PARSER_NAME=hybrid by default (background, zero risk)
  → Monitor logs for PARSER_METRIC | component=NAME

Step 3: Deploy Phase 2 (location normalization)
  → PARSER_LOCATION=code initially
  → After 24h, switch to PARSER_LOCATION=hybrid via Render env var
  → Compare search success rate via logs

Step 4: Deploy Phase 3 (reference resolution)
  → PARSER_REFERENCE=code initially
  → A/B test by toggling env var for specific phone numbers
  → Monitor confidence distribution

Step 5: Deploy Phase 4 (budget tiers)
  → PARSER_BUDGET=code initially
  → Toggle to hybrid after validation

Step 6: Deploy Phase 5 (preference extraction)
  → PARSER_PREFERENCE=hybrid by default (background, zero risk)
  → Monitor qualitative_prefs field in Redis

Step 7: Deploy Phase 6 (date parser wrap)
  → PARSER_DATE=hybrid (already current behavior)
  → reschedule_appointment now also benefits from LLM
```
