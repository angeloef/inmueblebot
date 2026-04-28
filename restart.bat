@echo off
setlocal EnableDelayedExpansion

echo.
echo ============================================
echo   Restarting InmuebleBot Docker Services
echo ============================================
echo.

echo [1/4] Stopping containers...
docker compose down

echo.
echo [2/4] Starting containers...
docker compose up -d

echo.
echo [3/4] Waiting for database to be ready...
ping -n 10 127.0.0.1 >nul

echo.
echo [4/4] Populating database...

REM Run seed_properties using docker compose exec with inline Python
docker compose exec -T app python -c "import sys;sys.path.insert(0,'/app');import asyncio;from app.db.seed import seed_properties;asyncio.run(seed_properties())"

REM Run populate_test_images
docker compose exec -T app python populate_test_images.py

echo Done!

echo.
echo ============================================
echo   Done! Services are running
echo ============================================
echo.
docker compose ps