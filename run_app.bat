@echo off
cd /d "%~dp0inmueblebot"
echo Starting InmuebleBot FastAPI...
echo.
echo The app will open at: http://localhost:8000
echo.
echo To start Streamlit chat UI, open a new terminal and run:
echo   streamlit run frontend\chat_ui.py
echo.
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause