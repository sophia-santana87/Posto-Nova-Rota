@echo off
cd /d "%~dp0"
set FLASK_DEBUG=False
set PORT=8001
echo Iniciando o Posto Nova Rota corrigido em http://127.0.0.1:8001/
echo.
echo Use esta porta para evitar a instancia antiga presa em 8000.
echo Pressione CTRL+C para encerrar o servidor.
echo.
python run_8001.py
pause
