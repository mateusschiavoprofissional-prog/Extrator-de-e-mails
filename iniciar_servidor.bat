@echo off
:: Garante que o script execute na pasta onde ele está localizado
cd /d "%~dp0"
title Radar de Reenvios - Inicializador
cls
echo ======================================================
echo   🛠️  Verificando ambiente e dependencias...
echo ======================================================
echo.

:: Instala ou atualiza as dependencias necessarias automaticamente
python -m pip install fastapi uvicorn google-auth-oauthlib google-api-python-client pydantic python-multipart --quiet

echo 🚀 Tentando iniciar o servidor...
echo 🔗 Link para acessar: http://localhost:5210
echo.

:: Executa o servidor e verifica se há erros
python app.py || (
    echo.
    echo ❌ Erro: O servidor falhou ao iniciar. 
    echo Certifique-se de que o Python esta no PATH e que a porta 5210 nao esta em uso.
    pause
)