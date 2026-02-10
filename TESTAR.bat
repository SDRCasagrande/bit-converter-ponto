@echo off
chcp 65001 >nul
title AFD Parser - Teste
color 0E

if not exist "venv\Scripts\activate.bat" (
    echo [!!] Execute INSTALAR.bat primeiro!
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
echo.
echo Testando parser com arquivos AFD...
echo.
python test_parser.py
echo.
pause
