# =============================================================================
# Dockerfile - Single-stage build for InmuebleBot
# Simpler and more reliable than multi-stage
# =============================================================================
FROM python:3.12-slim

WORKDIR /app

# =========================================================================
# Step 1: Install dependencies FIRST (before copying code)
# =========================================================================
COPY requirements.txt ./

# Install dependencies with explicit verification
RUN pip install --no-cache-dir -r requirements.txt

# =========================================================================
# Step 2: Verify critical dependencies are installed
# This will FAIL the build if dependencies are missing
# =========================================================================
RUN python -c "from google_auth_oauthlib.flow import InstalledAppFlow; print('OAuth dependencies OK')"

# =========================================================================
# Step 3: Copy application code
# =========================================================================
COPY . .

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose ports
EXPOSE 8000 8080

# Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]