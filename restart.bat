@echo off
setlocal EnableDelayedExpansion

echo.
echo ============================================
echo   Restarting InmuebleBot Docker Services
echo ============================================

echo.
echo [1/4] Stopping containers...
docker compose down
timeout /t 2 /nobreak >nul

echo.
echo [2/4] Starting containers...
docker compose up -d
if errorlevel 1 (
    echo.
    echo [2b/4] Port 8051 in use, switching to port 9000...
    docker compose down
    powershell -Command "(Get-Content docker-compose.yml) -replace '8051:8000', '9000:8000' | Set-Content docker-compose.yml"
    docker compose up -d
)

echo.
echo [3/4] Waiting for services...
timeout /t 10 /nobreak >nul

echo.
echo [4/4] Checking health...
docker compose ps

echo.
echo ============================================
echo   Done! Services should be running
echo ============================================
echo.
echo   FastAPI: http://localhost:9000
echo   Health:  http://localhost:9000/health
echo ============================================