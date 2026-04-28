@echo off
cd /d "%~dp0inmueblebot"
streamlit run frontend\chat_ui.py --server.port 5000 --server.address 127.0.0.1