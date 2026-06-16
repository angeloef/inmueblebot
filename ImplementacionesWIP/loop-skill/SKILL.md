---
name: implementador-loop
description: >
  Implementador secuencial autónomo (Ralph loop) para los planes de
  ImplementacionesWIP/. Selecciona el próximo plan pendiente cuyas dependencias
  estén cumplidas, lo implementa leyendo solo el contexto relevante, lo verifica
  con gates (lint → tests → Docker local → Chrome MCP UX → review de subagente) y,
  recién con todo en verde, commitea y pushea a main (deploy Render). Usar cuando
  el usuario pida "implementar los planes", "correr el loop", "seguir con la
  siguiente implementación" o invoque /implementador-loop.
argument-hint: "[id del plan opcional, ej. 01 | --dry-run | --plan-only]"
allowed-tools: Read, Edit, Write, Grep, Glob, Bash, Task, TodoWrite
---

# Implementador-loop — agente de implementación secuencial

Sos el **implementador**. Tu fuente de verdad son los planes en `ImplementacionesWIP/`.
Cada invocación procesa **un (1) plan completo** de principio a fin y luego termina
(el contexto fresco entre planes lo da `run-loop.sh`). Si te invocan in-session sin
runner, al terminar un plan ofrecé continuar con el siguiente.

> Diseño basado en el patrón **Ralph loop** (spec-driven autonomous development):
> leer specs → tomar la primera tarea pendiente con deps cumplidas → implementar →
> quality gates → actualizar progreso → señal de fin. Principios aplicados:
> contexto se construye, no se vuelca; presupuestos (pasos/tiempo/tool-calls) son
> parte del producto; **toda salida se verifica** (los agentes generan ~1.75× más
> errores lógicos que un humano — nada se da por bueno sin gate).

## Presupuestos (budgets) por iteración
- **Tiempo:** ~45 min de pared por plan. Si lo superás, parás y registrás en bitácora.
- **Reintentos por gate:** máx. 3 ciclos fix→re-verificar. Si no pasa, NO completes el plan.
- **Alcance:** tocá **solo** los archivos del bloque `files:`/Contexto del plan. Si
  necesitás otro archivo, registrá por qué en la bitácora.
- **Sin scope creep:** no implementes cosas de otros planes "de paso".

## Protocolo (una pasada = un plan)

### 0. Preflight
- Leé `AGENTS.md` y las reglas del proyecto (rules ECC) que apliquen al área del plan.
- Confirmá que el entorno de test corre: contenedor Docker levantado (ver §Gates).
  Si no está, levantalo y **dejalo corriendo** (no lo bajes entre iteraciones).
- `git status` limpio. Si hay cambios sin commitear ajenos al loop, parar y avisar.

### 1. SELECT — elegir el próximo plan
- Ejecutá el picker: `bash .claude/skills/implementador-loop/pick-next.sh`
  (devuelve el path del próximo plan: menor `id` con `status: pending|in_progress`
  y todos sus `depends_on` en `completed`). Si te pasaron un id como argumento, usá ese.
- Si devuelve `ALL_PLANS_COMPLETE`, imprimí exactamente esa cadena y terminá.
- Marcá el plan `status: in_progress` en su frontmatter y anotá inicio en la Bitácora.

### 2. EXPLORE — contexto mínimo verdadero
- Leé **solo** los archivos/líneas que lista la sección "Contexto necesario" del plan.
- Si el mapa es ambiguo (p. ej. orquestación de navegación), usá el subagente
  **Explore** ("medium") en vez de leer medio repo. Traé conclusiones, no volcados.

### 3. PLAN — expandir a checklist ejecutable
- Convertí "Plan secuencial" del `.md` en tareas con **TodoWrite**.
- Para el plan transversal (03), arrancá con el subagente **Plan** para fijar
  contrato de endpoint / modelo / migración antes de codear.

### 4. IMPLEMENT
- Implementá tarea por tarea, marcando TodoWrite. Seguí las reglas de estilo ECC
  (React/TS/Python). Inmutabilidad, sin `console.log`/`print`, props tipadas.
- Si el plan sugiere refactor compartido (01↔02: `LinkClientProperty`), hacelo una vez.

### 5. VERIFY — quality gates (orden estricto, todo en local primero)
Definición de "done" (basada en elite implementations; ejecutar **en este orden**):

1. **Lint/format**
   - Frontend: `cd dashboard && npm run lint`
   - Backend: `ruff check app/ && black --check app/`
2. **Tests unitarios/integración** (si el plan toca `app/`)
   - `pytest -q` (y los tests nuevos que el plan exija para el log/endpoints).
3. **Build + run local en Docker** (mantener el contenedor vivo entre iteraciones)
   - Levantar/usar `docker-compose` para servir API + dashboard.
   - Healthcheck antes de seguir (esperar cold start si aplica).
4. **Verificación UX con Chrome MCP** (gold standard para los planes de frontend)
   - Con las tools `mcp__Claude_in_Chrome__*`: navegar al dashboard local, ejecutar
     el flujo del plan (p. ej. abrir cliente → vincular propiedad → verla listada),
     **capturar screenshot**, leer la consola (`read_console_messages`) y la red.
   - Criterio: cero errores en consola, el flujo funciona, y el resultado visual
     cumple el estándar (estados vacío/cargando/error, foco, teclado, responsive).
     Iterar sobre la UI hasta que quede "perfecta" dentro del budget.
5. **Review por subagente** sobre el diff (`git diff`)
   - Frontend → **react-reviewer**. Backend/datos → **security-reviewer** (PII,
     tenant-scoping/RLS, sin secretos). Resolver findings antes de cerrar.
- **Si algún gate falla:** fix y re-correr (máx 3). Si no pasa, dejá el plan en
  `in_progress`, anotá el blocker concreto en la Bitácora y terminá con `BLOCKED:`.

### 6. SHIP — solo con TODO en verde
- `git add -A && git commit` con mensaje convencional: `feat(<área>): <plan id> <resumen>`.
- `git push origin main` (dispara auto-deploy en Render).
- Verificá el deploy como en `loop-optimize-report.md` (endpoint `/version` vs SHA).
- Marcá el plan `status: completed`, agregá entrada en su **Bitácora** (qué se hizo,
  gates pasados, SHA, link de deploy) y actualizá la tabla de `ImplementacionesWIP/README.md`.

### 7. NEXT
- Imprimí un resumen de 3–5 líneas y la señal `PLAN_DONE: <id>`. Si no quedan planes,
  imprimí `ALL_PLANS_COMPLETE` (el runner reinvoca con contexto fresco entre planes).

## Señales de control (para el runner)
- `ALL_PLANS_COMPLETE` → no quedan planes ejecutables; el loop para.
- `BLOCKED: <motivo>` → un plan no pudo cerrarse; el loop para para review humano.
- `PLAN_DONE: <id>` → un plan se completó y pusheó; el runner sigue (contexto fresco).

## Modos
- `--plan-only`: ejecutá pasos 0–3 y mostrá el plan detallado; no implementes.
- `--dry-run`: corré gates sin commitear ni pushear (paso 6 deshabilitado).
- `[id]`: forzá un plan específico en lugar del picker.

## Notas de seguridad / riesgo
- Push a `main` **únicamente** tras pasar los 5 gates. Nada de "push and pray".
- Acciones destructivas (migraciones, borrados) requieren downgrade probado en el
  gate 2/3 (ver plan 03). Ante duda, `BLOCKED`.
