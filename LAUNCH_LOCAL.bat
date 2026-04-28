@echo off
setlocal enabledelayedexpansion

echo ================================================
echo InmuebleBot - Local Launcher
echo ================================================
echo.

REM Start Redis if not running (try without Docker)
echo Step 1: Checking Redis...
redis-cli ping >nul 2>&1
if %errorlevel% neq 0 (
    echo Starting Redis...
    start /b redis-server --port 6379
    timeout /t 2 /nobreak >nul
)

echo Step 2: Starting FastAPI on port 8000...
start "InmuebleBot-API" cmd /k "cd /d %~dp0inmueblebot && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

echo.
echo Waiting for FastAPI to start...
timeout /t 5 /nobreak >nul

echo Step 3: Starting Streamlit Chat on port 8501...
start "InmuebleBot-Chat" cmd /k "cd /d %~dp0inmueblebot && streamlit run frontend/chat_ui.py --server.port 8501"

echo.
echo ================================================
echo READY!
echo ================================================
echo.
echo FastAPI:    http://localhost:8000
echo Streamlit: http://localhost:8501
echo.
echo Press any key to open browser...
pause >nul

start http://localhost:8501

endlocal