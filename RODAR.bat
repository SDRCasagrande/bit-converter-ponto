@echo off
chcp 65001 >nul
title AFD Parser
color 0B

if not exist "venv\Scripts\activate.bat" (
    echo [!!] Execute INSTALAR.bat primeiro!
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python main.py
