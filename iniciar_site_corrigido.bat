@echo off
REM Este arquivo e apenas um atalho para iniciar o site localmente no Windows.
REM Ele configura a porta 8001 para evitar conflito com uma instancia antiga
REM que possa estar usando a porta 8000 e depois executa o run_8001.py.
REM Tambem e possivel iniciar o site manualmente com: python run_8001.py
REM Este arquivo nao e necessario em um ambiente de producao.
REM
REM Vai para a pasta onde este arquivo esta salvo.
cd /d "%~dp0"
REM Define as configuracoes da instancia local antes de iniciar o Python.
set FLASK_DEBUG=False
set PORT=8001
echo Iniciando o Posto Nova Rota corrigido em http://127.0.0.1:8001/
echo.
echo Use esta porta para evitar a instancia antiga presa em 8000.
echo Pressione CTRL+C para encerrar o servidor.
echo.
REM Inicia o pequeno arquivo Python responsavel por ligar o site.
python run_8001.py
REM Mantem a janela aberta para que seja possivel ler eventuais mensagens.
pause
