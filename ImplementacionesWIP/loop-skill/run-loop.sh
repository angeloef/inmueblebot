#!/usr/bin/env bash
# run-loop.sh — Runner Ralph externo: reinvoca Claude Code con CONTEXTO FRESCO
# por cada plan de ImplementacionesWIP/. Una iteración = un plan completo.
#
# Por qué externo: el contexto fresco por iteración evita la degradación de
# atención en sesiones largas (principio central del patrón Ralph). El estado
# persiste en el frontmatter `status:` de cada plan y en sus Bitácoras, no en
# la ventana de contexto.
#
# Uso:
#   bash run-loop.sh                 # loop autónomo hasta terminar/bloquear
#   bash run-loop.sh --once          # una sola iteración (human-in-the-loop)
#   bash run-loop.sh --dry-run       # corre gates, NO commitea ni pushea
#   MAX_ITERS=5 MAX_MINUTES=180 bash run-loop.sh
#
# Parada: ALL_PLANS_COMPLETE (éxito) · BLOCKED (review humano) ·
#   archivo STOP presente · budget de iteraciones o tiempo agotado.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

MODEL="${MODEL:-opus}"
MAX_ITERS="${MAX_ITERS:-10}"
MAX_MINUTES="${MAX_MINUTES:-240}"
LOG_DIR="${LOG_DIR:-$REPO_ROOT/ImplementacionesWIP/.loop-logs}"
STOP_FILE="$REPO_ROOT/ImplementacionesWIP/.loop-logs/STOP"
EXTRA_FLAGS=""
PROMPT_SUFFIX=""

for arg in "$@"; do
  case "$arg" in
    --once)    MAX_ITERS=1 ;;
    --dry-run) PROMPT_SUFFIX=" Modo --dry-run: NO commitees ni pushees." ;;
    *)         echo "Flag desconocido: $arg" ;;
  esac
done

mkdir -p "$LOG_DIR"
START_EPOCH=$(date +%s)

# Prompt de iteración. El skill se autodescubre por su descripción; lo nombramos
# explícito para forzar el protocolo.
read -r -d '' PROMPT <<EOF || true
Usá el skill "implementador-loop". Procesá EXACTAMENTE el próximo plan pendiente
de ImplementacionesWIP/ siguiendo su protocolo completo (select → explore → plan →
implement → verify gates → ship → log). Procesá UN solo plan y terminá la pasada.
Al final imprimí una de estas señales en una línea propia:
PLAN_DONE: <id>  |  BLOCKED: <motivo>  |  ALL_PLANS_COMPLETE.${PROMPT_SUFFIX}
EOF

iter=0
while :; do
  iter=$((iter+1))

  if [[ -f "$STOP_FILE" ]]; then
    echo "⏹  STOP file presente ($STOP_FILE). Deteniendo."; break
  fi
  if (( iter > MAX_ITERS )); then
    echo "⏹  Budget de iteraciones agotado (MAX_ITERS=$MAX_ITERS)."; break
  fi
  elapsed_min=$(( ( $(date +%s) - START_EPOCH ) / 60 ))
  if (( elapsed_min >= MAX_MINUTES )); then
    echo "⏹  Budget de tiempo agotado (${elapsed_min}m ≥ ${MAX_MINUTES}m)."; break
  fi

  ts="$(date +%Y%m%d-%H%M%S)"
  log="$LOG_DIR/iter-${iter}-${ts}.log"
  echo "▶  Iteración $iter — $(date) — log: $log"

  # CONTEXTO FRESCO: cada llamada a `claude -p` arranca limpio.
  # --permission-mode acceptEdits para autonomía controlada (Edits/Bash sin prompt).
  # Para autonomía total usar --dangerously-skip-permissions bajo tu responsabilidad.
  claude -p "$PROMPT" \
    --model "$MODEL" \
    --permission-mode acceptEdits \
    $EXTRA_FLAGS 2>&1 | tee "$log"

  if grep -q "ALL_PLANS_COMPLETE" "$log"; then
    echo "✅  Todos los planes completados. Fin del loop."; break
  fi
  if grep -q "^BLOCKED:" "$log"; then
    echo "🛑  Plan bloqueado — requiere review humano. Deteniendo el loop."
    grep "^BLOCKED:" "$log"; break
  fi
  if ! grep -q "^PLAN_DONE:" "$log"; then
    echo "⚠️   La iteración no emitió PLAN_DONE/ALL_PLANS_COMPLETE/BLOCKED."
    echo "    Revisá $log antes de re-lanzar. Deteniendo por seguridad."; break
  fi

  echo "✔  $(grep '^PLAN_DONE:' "$log" | head -1) — siguiente iteración con contexto fresco."
  sleep 2
done

echo "—— Loop finalizado tras $iter iteración(es). Logs en $LOG_DIR ——"
