#!/usr/bin/env bash
# pick-next.sh — selecciona el próximo plan ejecutable de ImplementacionesWIP/.
# Regla: menor `id` con status ∈ {pending, in_progress} y todos sus depends_on
# en status `completed`. Imprime el path del .md, o "ALL_PLANS_COMPLETE".
set -euo pipefail

# Raíz del repo (este script vive en .claude/skills/implementador-loop/)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
WIP_DIR="${WIP_DIR:-$REPO_ROOT/ImplementacionesWIP}"

python3 - "$WIP_DIR" <<'PY'
import sys, os, glob, re

wip = sys.argv[1]
try:
    import yaml  # PyYAML suele estar en el venv del proyecto
    HAVE_YAML = True
except Exception:
    HAVE_YAML = False

def parse_frontmatter(text):
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.S)
    if not m:
        return {}
    block = m.group(1)
    if HAVE_YAML:
        try:
            return yaml.safe_load(block) or {}
        except Exception:
            pass
    # Fallback mínimo: id, status, depends_on (lista inline o de bloque)
    fm, key = {}, None
    for line in block.splitlines():
        if re.match(r'^\s*-\s', line) and key == 'depends_on':
            fm.setdefault('depends_on', []).append(
                line.strip().lstrip('-').strip().strip('"\''))
            continue
        mm = re.match(r'^(\w+):\s*(.*)$', line)
        if not mm:
            continue
        key, val = mm.group(1), mm.group(2).strip()
        if key == 'depends_on':
            if val.startswith('['):
                items = [x.strip().strip('"\'') for x in val.strip('[]').split(',') if x.strip()]
                fm['depends_on'] = items
            elif val:
                fm['depends_on'] = [val.strip('"\'')]
            else:
                fm['depends_on'] = []
        else:
            fm[key] = val.strip('"\'')
    return fm

plans = {}
for path in glob.glob(os.path.join(wip, '*.md')):
    if os.path.basename(path).lower() == 'readme.md':
        continue
    with open(path, encoding='utf-8') as f:
        fm = parse_frontmatter(f.read())
    pid = str(fm.get('id', '')).strip()
    if not pid:
        continue
    plans[pid] = {
        'path': path,
        'status': str(fm.get('status', 'pending')).strip(),
        'deps': [str(d).strip() for d in (fm.get('depends_on') or [])],
    }

def deps_ok(p):
    return all(plans.get(d, {}).get('status') == 'completed' for d in p['deps'])

candidates = [
    (pid, p) for pid, p in plans.items()
    if p['status'] in ('pending', 'in_progress') and deps_ok(p)
]
if not candidates:
    print("ALL_PLANS_COMPLETE")
    sys.exit(0)

# menor id (orden natural por string con zero-pad ya en los nombres: 01,02,03)
candidates.sort(key=lambda kv: kv[0])
print(candidates[0][1]['path'])
PY
