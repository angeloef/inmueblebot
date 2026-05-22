"""
Prompt Library — Loader + Assembly Engine.

Loads prompt files from app/agents/prompt_files/ directory,
resolves frontmatter metadata, and assembles per-turn system prompts
by combining shared + capability-specific + dynamic blocks.

No external dependencies (no PyYAML, no LangChain).
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Dict, Any, Optional, List


# ── Path resolution ────────────────────────────────────────────────────────

_PROMPTS_DIR = Path(__file__).resolve().parent


def _get_prompts_dir() -> Path:
    """Return the prompts/ directory (resolved once)."""
    return _PROMPTS_DIR


# ── Frontmatter parser ────────────────────────────────────────────────────

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """
    Parse minimal YAML frontmatter (--- delimited) from a .md file.

    Returns (metadata_dict, body_text).
    Handles simple key: value pairs only (no nested YAML).
    """
    metadata: Dict[str, Any] = {}
    body = text

    if text.lstrip().startswith("---"):
        # Find the closing ---
        lines = text.split("\n")
        end_idx = None
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_idx = i
                break

        if end_idx is not None:
            front_lines = lines[1:end_idx]
            for line in front_lines:
                line = line.strip()
                if ":" in line:
                    key, _, val = line.partition(":")
                    metadata[key.strip().lower()] = val.strip().strip('"').strip("'")
            body = "\n".join(lines[end_idx + 1:]).strip()

    # Normalize depends_on to list
    deps = metadata.get("depends_on")
    if isinstance(deps, str):
        # Handle YAML-style lists: "[a, b]" or "a, b"
        deps_clean = deps.strip().strip("[]")
        metadata["depends_on"] = [d.strip() for d in deps_clean.split(",") if d.strip()]

    return metadata, body


# ── Prompt Library ─────────────────────────────────────────────────────────

class PromptLibrary:
    """
    Loads and caches all prompt files from the prompts/ directory tree.

    Files are indexed by capability (from frontmatter) and by path for
    dependency resolution.
    """

    _instance: Optional["PromptLibrary"] = None

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}  # capability -> {content, metadata, source}
        self._by_path: Dict[str, Dict[str, Any]] = {}  # relative_path -> entry
        self._loaded = False
        self._load_error: Optional[str] = None

    @classmethod
    def get_instance(cls) -> "PromptLibrary":
        """Singleton: shared cache across all agent turns."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load_all(self, force: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        Scan prompts/ directory, parse all .md files, build index by capability.

        Returns {capability_name: {content, metadata, source}}.
        """
        if self._loaded and not force:
            return self._cache

        self._cache = {}
        self._by_path = {}
        prompts_dir = _get_prompts_dir()

        if not prompts_dir.exists():
            self._load_error = f"Prompts dir not found: {prompts_dir}"
            return self._cache

        md_files = sorted(prompts_dir.rglob("*.md"))
        # Exclude INVENTORY.md and README.md
        md_files = [f for f in md_files
                    if f.name not in ("INVENTORY.md", "README.md")]

        for filepath in md_files:
            try:
                text = filepath.read_text(encoding="utf-8")
            except Exception as exc:
                continue

            metadata, body = _parse_frontmatter(text)
            rel_path = str(filepath.relative_to(prompts_dir))

            entry = {
                "content": body,
                "metadata": metadata,
                "source": rel_path,
                "path": str(filepath),
            }
            self._by_path[rel_path] = entry

            # Index by capability
            capability = metadata.get("capability")
            if capability:
                # If multiple files share a capability, merge examples
                if capability in self._cache:
                    existing = self._cache[capability]
                    if metadata.get("description", "").startswith("Ejemplo"):
                        # Append to existing examples list
                        existing.setdefault("examples", [])
                        existing["examples"].append(body)
                    else:
                        # Main file for this capability
                        existing["content"] = body
                        existing["metadata"] = metadata
                        existing["source"] = rel_path
                else:
                    self._cache[capability] = {
                        "content": body,
                        "metadata": metadata,
                        "source": rel_path,
                        "examples": [],
                    }

        self._loaded = True
        return self._cache

    def get_shared_prompt(self) -> str:
        """Return the combined shared prompts (persona + alcance + condiciones)."""
        self.load_all()
        parts = []
        for name in ("shared/persona.md", "shared/alcance.md", "shared/condiciones.md"):
            entry = self._by_path.get(name)
            if entry:
                parts.append(entry["content"])
        return "\n\n".join(parts)

    def get_capability_prompt(self, capability: str) -> Optional[str]:
        """Return the main content for a capability (without examples)."""
        self.load_all()
        entry = self._cache.get(capability)
        if entry:
            return entry.get("content")
        return None

    def get_examples(self, capability: str) -> List[str]:
        """Return example conversations for a capability."""
        self.load_all()
        entry = self._cache.get(capability)
        if entry:
            return entry.get("examples", [])
        return []

    def list_capabilities(self) -> List[str]:
        """Return all registered capability names."""
        self.load_all()
        return [k for k in self._cache.keys() if k != "shared"]

    def get_all_entries(self) -> Dict[str, Dict[str, Any]]:
        """Return full cache (for debugging/testing)."""
        self.load_all()
        return self._cache


# ── Assembly Engine ────────────────────────────────────────────────────────

def _resolve_company_name() -> str:
    """Read company_name from DB cache or env var."""
    try:
        from app.agents.prompts import _get_cached_bot_settings
        db_settings = _get_cached_bot_settings()
        if db_settings.get("company_name"):
            return db_settings["company_name"]
    except Exception:
        pass
    try:
        from app.core.config import get_settings
        return get_settings().COMPANY_NAME or "la inmobiliaria"
    except Exception:
        return "la inmobiliaria"


def _resolve_time_of_day() -> str:
    """Return current Argentina time-of-day greeting."""
    try:
        from datetime import datetime
        import pytz
        ar_tz = pytz.timezone("America/Argentina/Buenos_Aires")
        hour = datetime.now(ar_tz).hour
        if 6 <= hour < 12:
            return "buenos días"
        elif 12 <= hour < 20:
            return "buenas tardes"
        else:
            return "buenas noches"
    except Exception:
        return "buenas"


def _replace_variables(text: str, **kwargs: Any) -> str:
    """Resolve {variable} placeholders in prompt text."""
    for key, val in kwargs.items():
        text = text.replace(f"{{{key}}}", str(val) if val is not None else "")
    return text


def assemble_system_prompt(
    capability: str,
    stage: str,
    context: Dict[str, Any],
    library: Optional[PromptLibrary] = None,
) -> str:
    """
    Build the per-turn system prompt by combining:

    1. SHARED (persona + alcance + condiciones)
    2. CAPABILITY-specific instructions
    3. CAPABILITY-specific examples
    4. ### User Context (name, preferences)
    5. ### ACTIVE PROPERTY CONTEXT
    6. ### PENDING SCHEDULING INFO
    7. ### ETAPA: {stage}
    8. ### TONO: {sentiment}
    9. ### USUARIO RECURRENTE

    Falls back to legacy get_system_prompt() if loader is unavailable.
    """
    if library is None:
        library = PromptLibrary.get_instance()

    # Resolve variables
    company_name = _resolve_company_name()
    time_of_day = _resolve_time_of_day()

    # ── 1. SHARED base ────────────────────────────────────────────────────
    shared = library.get_shared_prompt()
    if not shared:
        # Fallback to legacy
        from app.agents.prompts import get_system_prompt as legacy
        return legacy(context)

    # Resolve {company_name} and {_saludo_hora} in shared
    shared = _replace_variables(shared, company_name=company_name)
    # Time-of-day hint in shared
    shared = shared.replace(
        "# Colaboración",
        f"# Colaboración\nHora actual en Argentina: {time_of_day}. Usá este saludo cuando no se especifique otro."
    )

    parts = [shared]

    # ── 2. CAPABILITY-specific instructions ──────────────────────────────
    cap_content = library.get_capability_prompt(capability)
    if cap_content:
        cap_content = _replace_variables(cap_content, company_name=company_name)
        parts.append(cap_content)

    # ── 3. CAPABILITY-specific examples ──────────────────────────────────
    examples = library.get_examples(capability)
    if examples:
        parts.append("# Ejemplos de Conversación")
        parts.extend(examples)

    # ── 4. User Context ──────────────────────────────────────────────────
    user_parts = []
    user_name = context.get("name") or context.get("user_name") or ""
    if user_name:
        user_parts.append(f"Nombre: {user_name}")
    if context.get("location_preferences"):
        user_parts.append(f"Ubicacion: {context['location_preferences']}")
    if context.get("budget_max"):
        try:
            bv = int(float(str(context['budget_max'])))
            user_parts.append(f"Presupuesto: ${bv:,}")
        except (ValueError, TypeError):
            pass
    if context.get("property_type"):
        user_parts.append(f"Tipo: {context['property_type']}")
    if context.get("operation_type"):
        user_parts.append(f"Operacion: {context['operation_type']}")
    if context.get("bedrooms"):
        user_parts.append(f"Dormitorios: {context['bedrooms']}")

    if user_parts:
        parts.append("### User Context\n" + " | ".join(user_parts))

    # ── 5. Active Property Context ───────────────────────────────────────
    selected_id = context.get("selected_property_id")
    selected_title = context.get("selected_property_title") or "propiedad"
    if selected_id:
        prop_ctx = (
            f"### ACTIVE PROPERTY CONTEXT\n"
            f"Propiedad activa: [{selected_title}] (ID={selected_id}).\n"
            f"SIEMPRE que el usuario mencione 'esa', 'la misma', 'esa propiedad', "
            f"'el departamento que vimos', 'esa casa' → referite a [{selected_title}] ID={selected_id}.\n"
            f"Para schedule_visit usa property_id={selected_id} (NO uses otro ID).\n"
        )
        # Check if user is asking about scheduling
        _user_message = context.get("_raw_message", "").lower()
        _sched_kws = ["visita", "agendar", "agend", "coordinar", "turno", "cita",
                       "puedo ir", "ir a ver", "conocer", "verla", "visitarla"]
        if any(kw in _user_message for kw in _sched_kws):
            prop_ctx += (
                f"PROHIBIDO preguntar '¿Te referís a {selected_title}?' — "
                f"la propiedad ya está identificada. "
                f"Pasá DIRECTAMENTE a preguntar el día de la visita.\n"
            )
        parts.append(prop_ctx)

    # ── 6. Pending Scheduling Info ───────────────────────────────────────
    pending = context.get("pending_scheduling_info")
    if pending and isinstance(pending, dict) and pending.get("active"):
        saved_date = pending.get("date_str", "")
        saved_pid = pending.get("property_id", "")
        saved_time = pending.get("time_str", "")
        schedule_ctx = (
            "### PENDING SCHEDULING INFO\n"
            "El usuario ya mencionó querer agendar una visita y se guardó esta información:\n"
        )
        if saved_pid:
            schedule_ctx += f"- Propiedad: ID={saved_pid}\n"
        if saved_date:
            schedule_ctx += f"- Fecha mencionada: {saved_date}\n"
        if saved_time:
            schedule_ctx += f"- Horario mencionado: {saved_time}\n"
        schedule_ctx += (
            "- Si el usuario confirma, llamá schedule_visit con estos datos.\n"
            "- Si el usuario da un dato nuevo (fecha/hora diferente), actualizalo.\n"
            "- NO preguntes todo de nuevo — solo lo que falta.\n"
        )
        parts.append(schedule_ctx)

    # ── 7. Stage tag ─────────────────────────────────────────────────────
    if stage:
        parts.append(f"### ETAPA: {stage}")

    # ── 8. Sentiment ─────────────────────────────────────────────────────
    sentiment = context.get("_sentiment")
    if sentiment:
        parts.append(f"### TONO: {sentiment}")

    # ── 9. Returning user ────────────────────────────────────────────────
    if context.get("is_returning"):
        last_ref = context.get("last_reference", "propiedades")
        returning_msg = (
            f"### USUARIO RECURRENTE\n"
            f"Este usuario ya ha conversado antes. "
            f"Su última referencia fue: {last_ref}\n"
            f"Saludalo con un mensaje cálido tipo: '¡Bienvenido de nuevo! La última vez viste [referencia]...'\n"
        )
        parts.append(returning_msg)

    return "\n\n".join(parts)


def get_fallback_prompt(context: Dict[str, Any]) -> str:
    """
    Fallback to legacy system prompt generator.
    Used when the modular loader is not available or fails.
    """
    from app.agents.prompts import get_system_prompt as legacy
    return legacy(context)


# ── Plan B (post-tool guidance) ─────────────────────────────────────────────

def get_plan_b_prompt(tool_name: str, outcome: str) -> Optional[str]:
    """
    Load post-tool guidance for a specific tool and outcome.

    Args:
        tool_name: e.g. "search_properties", "schedule_visit"
        outcome: "success" or "failure"

    Returns prompt text or None if not found.
    """
    library = PromptLibrary.get_instance()
    library.load_all()

    # Look in plan_b/ directory
    file_name = f"plan_b/{tool_name}.md"
    entry = library._by_path.get(file_name)
    if entry is None:
        return None

    content = entry["content"]

    # If file has frontmatter, body is already stripped
    # Look for outcome sections by heading
    if outcome == "success":
        # Return content after # Success or full content if no split
        parts = content.split("# Success", 1)
        if len(parts) > 1:
            success_text = parts[1].split("# Failure", 1)[0]
            return success_text.strip()
    elif outcome == "failure":
        parts = content.split("# Failure", 1)
        if len(parts) > 1:
            return parts[1].strip()

    return content.strip()
