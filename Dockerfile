# =============================================================================
# Dockerfile - Multi-stage build
# Stage 1: Build the React Dashboard SPA
# Stage 2: Python runtime with FastAPI + dashboard SPA
# =============================================================================

# ── Stage 1: Dashboard builder ──────────────────────────────────────────────
FROM node:20-alpine AS dashboard-builder

WORKDIR /app

# Copy package files first (Docker layer cache)
COPY dashboard/package*.json ./dashboard/
RUN cd dashboard && npm install

# Copy dashboard source and build
COPY dashboard/ ./dashboard/
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
# Login canónico (la landing): usuarios anónimos del dashboard se redirigen acá.
# Default = landing de producción; overridable por env var en Render. En dev local
# (npm run dev, sin la env) el dashboard muestra su form de login propio.
ARG VITE_LOGIN_URL="https://viviendapp-web.onrender.com/login"
ENV VITE_LOGIN_URL=$VITE_LOGIN_URL
RUN cd dashboard && npm run build
# Result: dashboard/dist/

# ── Stage 2: Python runtime ─────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# =========================================================================
# Step 1: Install Python dependencies FIRST
# =========================================================================
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# =========================================================================
# Step 2: Verify critical dependencies
# =========================================================================
RUN python -c "from google_auth_oauthlib.flow import InstalledAppFlow; print('OAuth dependencies OK')"

# =========================================================================
# Step 3: Copy application code
# =========================================================================
COPY . .

# =========================================================================
# Step 4: Copy dashboard SPA from builder stage
# =========================================================================
COPY --from=dashboard-builder /app/dashboard/dist /app/dashboard/dist

# =========================================================================
# Step 5: Create non-root user
# =========================================================================
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Ensure run.sh is executable
RUN chmod +x /app/run.sh

EXPOSE 8000 8080
# run.sh runs `alembic upgrade head` then `exec uvicorn` — schema is always
# up to date before the app starts accepting traffic. Alembic is a no-op when
# already at head (~1s), and row-level locks keep concurrent starts safe.
CMD ["/app/run.sh"]
