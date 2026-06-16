# Skill: implementador-loop

Implementador secuencial autónomo (patrón **Ralph loop**) para los planes de
`ImplementacionesWIP/`. Lee el próximo plan pendiente, lo implementa, lo verifica
con gates y —con todo en verde— commitea y pushea a `main` (deploy Render).

## Archivos
- `SKILL.md` — protocolo del agente por iteración (un plan por pasada).
- `pick-next.sh` — selector del próximo plan (menor `id` pendiente con `depends_on` cumplidas).
- `run-loop.sh` — runner externo Ralph: reinvoca Claude Code con **contexto fresco** por plan.

## Instalación (una vez)
La carpeta `.claude/` no se pudo escribir desde esta sesión, así que el skill quedó
acá. Movelo a donde Claude Code lo descubre:

```bash
cd C:\Users\angelo\Documents\alemai\inmueblebot     # raíz del repo
mkdir -p .claude/skills
cp -r ImplementacionesWIP/loop-skill .claude/skills/implementador-loop
chmod +x .claude/skills/implementador-loop/*.sh
```

Verificá que Claude Code lo ve: en la CLI escribí `/` y debería aparecer
`implementador-loop` (o invocalo por nombre).

## Uso

### Modo human-in-the-loop (recomendado para empezar)
```bash
bash .claude/skills/implementador-loop/run-loop.sh --once     # un plan
# o desde la CLI de Claude Code:
/implementador-loop            # próximo plan
/implementador-loop 01         # forzar un plan
/implementador-loop --plan-only
```

### Modo autónomo (loop completo)
```bash
MAX_ITERS=5 MAX_MINUTES=180 bash .claude/skills/implementador-loop/run-loop.sh
```
Parada: `ALL_PLANS_COMPLETE`, `BLOCKED:`, archivo `STOP`, o budgets agotados.
Para frenar a mano: `touch ImplementacionesWIP/.loop-logs/STOP`.

## Quality gates (definición de "done", en orden)
1. Lint/format (`npm run lint`, `ruff`, `black --check`)
2. Tests (`pytest`) si toca `app/`
3. Build + run local en **Docker** (contenedor vivo entre iteraciones)
4. **Chrome MCP**: navegar el flujo, screenshot, consola/red sin errores, pulir UX
5. Review por subagente (`react-reviewer` / `security-reviewer`)

Solo si pasan los 5 → `commit` + `push origin main` (Render auto-deploy) y se marca
el plan `status: completed` + Bitácora.

## Requisitos
- Claude Code CLI en PATH (`claude`).
- Docker / docker-compose para el gate 3.
- Extensión **Claude in Chrome** conectada para el gate 4.
- `PyYAML` (ya en el venv del proyecto) o fallback del parser incluido.
