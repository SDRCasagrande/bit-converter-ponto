@echo off
chcp 65001 >nul
title AFD Parser - Setup Completo
color 0A
echo.
echo ============================================
echo   AFD Parser - Instalação Automática
echo ============================================
echo.

:: 1. Verifica se Python está instalado
where python >nul 2>&1
if %errorlevel%==0 (
    echo [OK] Python encontrado!
    python --version
    goto :setup_venv
)

:: Tenta py launcher
where py >nul 2>&1
if %errorlevel%==0 (
    echo [OK] Python encontrado via py launcher!
    py --version
    goto :setup_venv_py
)

:: 2. Python não encontrado — instala automaticamente
echo [!!] Python não encontrado. Instalando via winget...
echo.
winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if %errorlevel% neq 0 (
    echo.
    echo [ERRO] Não conseguiu instalar automaticamente.
    echo Por favor instale manualmente em: https://www.python.org/downloads/
    echo Marque "Add Python to PATH" na instalação!
    echo.
    pause
    exit /b 1
)

:: Atualiza PATH para a sessão atual
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
echo [OK] Python instalado com sucesso!

:setup_venv
:: 3. Cria ambiente virtual
echo.
echo [..] Criando ambiente virtual...
if not exist "venv" (
    python -m venv venv
) else (
    echo [OK] Ambiente virtual já existe.
)

:: 4. Ativa e instala dependências
echo [..] Instalando dependências...
call venv\Scripts\activate.bat
pip install --quiet -r requirements.txt
pip install --quiet pyinstaller

:: 5. Baixa fontes DejaVu se não existem
if not exist "assets\DejaVuSans.ttf" (
    echo [..] Baixando fontes para PDF...
    mkdir assets 2>nul
    curl -sL "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip" -o assets\dejavu.zip
    powershell -Command "Expand-Archive -Path 'assets\dejavu.zip' -DestinationPath 'assets\dejavu_tmp' -Force" 2>nul
    copy "assets\dejavu_tmp\dejavu-fonts-ttf-2.37\ttf\DejaVuSans.ttf" "assets\" >nul 2>&1
    copy "assets\dejavu_tmp\dejavu-fonts-ttf-2.37\ttf\DejaVuSans-Bold.ttf" "assets\" >nul 2>&1
    rmdir /s /q "assets\dejavu_tmp" 2>nul
    del "assets\dejavu.zip" 2>nul
    echo [OK] Fontes instaladas!
)

echo.
echo ============================================
echo   TUDO PRONTO!
echo ============================================
echo.
echo   Para RODAR o programa:    Dê dois cliques em RODAR.bat
echo   Para GERAR o .exe:        Dê dois cliques em GERAR_EXE.bat
echo   Para TESTAR o parser:     Dê dois cliques em TESTAR.bat
echo.
pause
goto :eof

:setup_venv_py
:: Fallback com py launcher
echo.
echo [..] Criando ambiente virtual...
if not exist "venv" (
    py -m venv venv
)
call venv\Scripts\activate.bat
pip install --quiet -r requirements.txt
pip install --quiet pyinstaller

if not exist "assets\DejaVuSans.ttf" (
    echo [..] Baixando fontes para PDF...
    mkdir assets 2>nul
    curl -sL "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip" -o assets\dejavu.zip
    powershell -Command "Expand-Archive -Path 'assets\dejavu.zip' -DestinationPath 'assets\dejavu_tmp' -Force" 2>nul
    copy "assets\dejavu_tmp\dejavu-fonts-ttf-2.37\ttf\DejaVuSans.ttf" "assets\" >nul 2>&1
    copy "assets\dejavu_tmp\dejavu-fonts-ttf-2.37\ttf\DejaVuSans-Bold.ttf" "assets\" >nul 2>&1
    rmdir /s /q "assets\dejavu_tmp" 2>nul
    del "assets\dejavu.zip" 2>nul
)

echo.
echo ============================================
echo   TUDO PRONTO!
echo ============================================
echo.
pause
