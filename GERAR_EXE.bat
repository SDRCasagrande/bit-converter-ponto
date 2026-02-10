@echo off
chcp 65001 >nul
title Bit-Converter - Gerando .EXE
color 0D

if not exist "venv\Scripts\activate.bat" (
    echo [!!] Execute INSTALAR.bat primeiro!
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo.
echo ============================================
echo   Gerando Bit-Converter.exe ...
echo   Isso pode levar 1-2 minutos.
echo ============================================
echo.

:: Limpa builds anteriores
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

:: Gera o .exe
pyinstaller --onefile --windowed --name "Bit-Converter" --add-data "assets\DejaVuSans.ttf;assets" --add-data "assets\DejaVuSans-Bold.ttf;assets" main.py

if exist "dist\Bit-Converter.exe" (
    echo.
    echo ============================================
    echo   SUCESSO! .exe gerado em:
    echo   dist\Bit-Converter.exe
    echo ============================================
    echo.
    echo   O cliente so precisa desse arquivo!
    echo   Abrindo a pasta...
    explorer dist
) else (
    echo.
    echo [ERRO] Falha ao gerar o .exe
    echo Verifique os erros acima.
)

echo.
pause
