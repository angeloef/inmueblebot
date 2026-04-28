@echo off
setlocal enabledelayedexpansion

echo ================================================
echo InmuebleBot - Full Stack Launcher
echo ================================================
echo.

REM Check if Docker is running
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not running!
    echo Please start Docker Desktop first
    pause
    exit /b 1
)

echo Step 1: Starting Redis...
docker run -d --name temp-redis -p 6379:6379 redis:7-alpine >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Redis started on port 6379
) else (
    echo [OK] Redis container already running
)

echo Step 2: Starting PostgreSQL...
docker run -d --name temp-postgres -p 5432:5432 -e POSTGRES_USER=user -e POSTGRES_PASSWORD=pass -e POSTGRES_DB=inmueblebot postgres:16 >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] PostgreSQL started on port 5432
) else (
    echo [OK] PostgreSQL container already running
)

echo.
echo Waiting for services to be ready...
timeout /t 3 /nobreak >nul

echo.
echo ================================================
echo Starting FastAPI App on port 8000...
echo ================================================
start "InmuebleBot-API" cmd /k "cd /d %~dp0inmueblebot && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 5 /nobreak >nul

echo.
echo ================================================
echo Starting Streamlit Chat UI on port 8501...
echo ================================================
start "InmuebleBot-Chat" cmd /k "cd /d %~dp0inmueblebot && streamlit run frontend/chat_ui.py --server.port 8501"

echo.
echo ================================================
echo READY!
echo ================================================
echo.
echo FastAPI:    http://localhost:8000
echo Streamlit:  http://localhost:8501
echo API Docs:   http://localhost:8000/docs
echo.
echo Press any key to open Streamlit in browser...
pause >nul

start http://localhost:8501

endlocal