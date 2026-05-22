"""
Tests for modular prompt architecture — frontmatter validation,
capability coverage, and assembly correctness.

Run with: pytest tests/test_prompts_modular.py -v
"""

import sys
import types
from pathlib import Path

# ── Bootstrap: mock app deps to import loader without full app init ─────
_mock_prompts = types.ModuleType('app.agents.prompts')
_mock_prompts._get_cached_bot_settings = lambda: {}
_mock_prompts.get_system_prompt = lambda ctx=None: "LEGACY FALLBACK"
_mock_config = types.ModuleType('app.core.config')
_mock_config.get_settings = lambda: types.SimpleNamespace(COMPANY_NAME=None)
sys.modules['app.agents.prompts'] = _mock_prompts
sys.modules['app.core.config'] = _mock_config

import importlib.util
_spec = importlib.util.spec_from_file_location(
    'prompt_loader',
    str(Path(__file__).resolve().parent.parent / 'app' / 'agents' / 'prompt_files' / 'loader.py')
)
_loader_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_loader_mod)

PromptLibrary = _loader_mod.PromptLibrary
assemble_system_prompt = _loader_mod.assemble_system_prompt
get_plan_b_prompt = _loader_mod.get_plan_b_prompt

# ── Fixtures ─────────────────────────────────────────────────────────────

def _get_lib():
    lib = PromptLibrary.get_instance()
    lib.load_all(force=True)
    return lib


# ── Tests: Frontmatter Validation ───────────────────────────────────────

def test_all_prompts_have_frontmatter():
    """Every .md file has --- delimited frontmatter with required keys."""
    lib = _get_lib()
    errors = []
    for path_key, entry in lib._by_path.items():
        meta = entry['metadata']
        has_id = 'capability' in meta or 'tool' in meta
        if not has_id:
            errors.append(f"{path_key}: missing capability/tool key")
        if 'version' not in meta:
            errors.append(f"{path_key}: missing version")
        if 'description' not in meta:
            errors.append(f"{path_key}: missing description")
    assert not errors, "\n".join(errors)


def test_all_capabilities_covered():
    """Router capabilities match prompt library capabilities."""
    lib = _get_lib()
    lib_caps = set(lib.list_capabilities())
    # Expected from router
    expected = {'search', 'detail', 'schedule', 'appointment', 'faq', 'greeting', 'general'}
    missing = expected - lib_caps
    extra = lib_caps - expected
    assert not missing, f"Prompts missing for: {missing}"
    assert not extra, f"Unexpected capabilities: {extra}"


def test_example_counts():
    """Examples are correctly attached to their parent capability."""
    lib = _get_lib()
    assert len(lib.get_examples('search')) == 2  # search.md + no-results.md
    assert len(lib.get_examples('schedule')) == 1  # schedule.md (Ej2 + Ej4)
    assert len(lib.get_examples('faq')) == 1       # faq.md (Ej3)
    assert len(lib.get_examples('detail')) == 0
    assert len(lib.get_examples('appointment')) == 0
    assert len(lib.get_examples('greeting')) == 0
    assert len(lib.get_examples('general')) == 0


def test_no_duplicate_examples():
    """No example is double-counted."""
    lib = _get_lib()
    for cap in lib.list_capabilities():
        exs = lib.get_examples(cap)
        # Check for exact duplicates
        unique = set(exs)
        assert len(unique) == len(exs), f"Duplicate examples in {cap}"
        # Check each example has content
        for ex in exs:
            assert len(ex) > 20, f"Example too short in {cap}"


# ── Tests: Assembly Correctness ──────────────────────────────────────────

def test_assemble_search_prompt():
    """Search assembly includes shared + search rules + no schedule instructions."""
    r = assemble_system_prompt('search', 'BUSQUEDA', {
        'name': 'Juan', 'budget_max': 150000,
        '_raw_message': 'busco casa',
    })
    _assert_all_in(r, ['Personalidad', 'Alcance', 'property_type',
                       'NO_RESULTS_ASK_MORE', 'BUSQUEDA', 'Juan'])
    _assert_none_in(r, ['Flujo de Agendamiento', 'Reprogramación'])


def test_assemble_schedule_prompt():
    """Schedule assembly includes scheduling rules + active property + pending info."""
    r = assemble_system_prompt('schedule', 'AGENDANDO', {
        '_raw_message': 'quiero agendar',
        'selected_property_id': '5',
        'selected_property_title': 'Test',
        'pending_scheduling_info': {'active': True, 'date_str': 'martes', 'property_id': '5'},
    })
    _assert_all_in(r, ['Flujo de Agendamiento', 'ACTIVE PROPERTY', 'PENDING SCHEDULING'])
    _assert_none_in(r, ['property_type', 'NO_RESULTS_ASK_MORE'])


def test_assemble_faq_prompt():
    """FAQ assembly includes faq rules only."""
    r = assemble_system_prompt('faq', 'CONSULTA', {'_raw_message': 'horarios?'})
    _assert_all_in(r, ['get_faq_answer', 'request_human_assistance'])
    _assert_none_in(r, ['property_type', 'Flujo de Agendamiento', 'Reprogramación'])


def test_assemble_without_capability():
    """Unknown capability returns shared base without crashing."""
    r = assemble_system_prompt('nonexistent_cap', 'GENERAL', {'_raw_message': 'test'})
    assert r and len(r) > 100
    assert 'Personalidad' in r


def test_assemble_empty_context():
    """Empty context doesn't crash."""
    r = assemble_system_prompt('search', '', {})
    assert r and len(r) > 100


def test_assemble_max_context():
    """All dynamic blocks render correctly with maximum context."""
    r = assemble_system_prompt('schedule', 'AGENDANDO', {
        'name': 'Test User',
        'budget_max': 300000,
        'location_preferences': 'Posadas',
        'selected_property_id': '42',
        'selected_property_title': 'Depto Centro',
        'pending_scheduling_info': {
            'active': True, 'date_str': 'viernes', 'time_str': '15:00', 'property_id': '42'
        },
        'is_returning': True,
        'last_reference': 'casas',
        '_raw_message': 'quiero agendar',
        '_sentiment': 'URGENTE',
    })
    _assert_all_in(r, [
        'Test User', '$300,000', 'Posadas',
        'ACTIVE PROPERTY', 'ID=42',
        'PENDING SCHEDULING', 'viernes', '15:00',
        'USUARIO RECURRENTE',
        'URGENTE', 'AGENDANDO',
    ])


def test_returning_user_block():
    """Returning user block includes last reference."""
    r = assemble_system_prompt('search', 'BUSQUEDA', {
        '_raw_message': 'hola',
        'is_returning': True,
        'last_reference': 'departamentos',
    })
    assert 'USUARIO RECURRENTE' in r
    assert 'departamentos' in r


def test_sentiment_block():
    """Sentiment block injects tone tag."""
    r = assemble_system_prompt('search', 'BUSQUEDA', {
        '_raw_message': 'test',
        '_sentiment': 'URGENTE',
    })
    assert 'TONO: URGENTE' in r


# ── Tests: Plan B Guidance ───────────────────────────────────────────────

def test_plan_b_all_tools():
    """All 7 plan_b tools return success + failure prompts."""
    tools = ['search_properties', 'get_property_details', 'schedule_visit',
             'reschedule_appointment', 'cancel_appointment', 'get_faq_answer',
             'get_property_images']
    for tool in tools:
        s = get_plan_b_prompt(tool, 'success')
        f = get_plan_b_prompt(tool, 'failure')
        assert s, f"{tool} success missing"
        assert f, f"{tool} failure missing"


def test_plan_b_unknown_tool():
    """Unknown tool returns None without crashing."""
    assert get_plan_b_prompt('unknown_tool', 'success') is None


# ── Tests: File Integrity ────────────────────────────────────────────────

def test_no_missing_depends_on():
    """depends_on references are valid file paths."""
    lib = _get_lib()
    errors = []
    for path_key, entry in lib._by_path.items():
        deps = entry['metadata'].get('depends_on', [])
        if isinstance(deps, str):
            deps = [deps]
        for dep in deps:
            dep_path = dep if dep.endswith('.md') else f"{dep}.md"
            if dep_path not in lib._by_path:
                errors.append(f"{path_key} depends on missing: {dep_path}")
    assert not errors, "\n".join(errors[:10])


def test_placeholder_resolution():
    """All {company_name} placeholders are resolvable."""
    lib = _get_lib()
    for path_key, entry in lib._by_path.items():
        content = entry['content']
        if '{company_name}' in content or '{_saludo_hora}' in content:
            # These are resolved by _replace_variables at assembly time
            # Verify the placeholders use valid variable names
            import re
            for match in re.findall(r'\{(\w+)\}', content):
                assert match in ('company_name', '_saludo_hora'), (
                    f"{path_key}: unknown placeholder {{{match}}}"
                )


# ── Helpers ──────────────────────────────────────────────────────────────

def _assert_all_in(text: str, keywords: list):
    for kw in keywords:
        assert kw in text, f"Missing: '{kw}'"


def _assert_none_in(text: str, keywords: list):
    for kw in keywords:
        assert kw not in text, f"Unexpected: '{kw}'"
