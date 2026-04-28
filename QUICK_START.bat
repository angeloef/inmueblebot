@echo off
echo ================================================
echo InmuebleBot - Quick Start
echo ================================================
echo.

echo [1/3] Changing to project directory...
cd /d %~dp0inmueblebot

echo [2/3] Starting FastAPI (API at http://localhost:8000)...
start "FastAPI" cmd /k "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

echo.
echo [3/3] Starting Streamlit Chat (at http://localhost:8501)...
start "Streamlit" cmd /k "streamlit run frontend/chat_ui.py --server.port 8501"

echo.
echo ================================================
echo DONE - Both services should open
echo ================================================
echo.
echo If you see errors about Redis, that's OK - the AI will still work!
echo.
echo Open your browser to: http://localhost:8501
echo.

timeout /t 3 /nobreak
start http://localhost:8501