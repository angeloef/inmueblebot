#!/bin/bash
# Production-mode entrypoint (Phase 0a). NOT --reload (that spawns a reloader
# subprocess — wrong for a Render web service). The real Render deploy uses the
# Dockerfile CMD; this script is the local-prod / non-Docker equivalent.
#
# Schema is owned by Alembic: apply migrations BEFORE starting the app. On Render
# the same step runs as the service `preDeployCommand` in render.yaml.
set -e

alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
