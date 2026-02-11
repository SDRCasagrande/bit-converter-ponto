"""
Sistema de atualização automática via GitHub Releases.
Verifica a última release do repositório e permite download + instalação.

Repositório: https://github.com/SDRCasagrande/bit-converter-ponto
"""
import json
import os
import sys
import subprocess
import tempfile
import urllib.request
import urllib.error
import ssl
from dataclasses import dataclass
from typing import Optional, Tuple, Callable


# =====================================================
# VERSÃO ATUAL DO APLICATIVO
# Atualize aqui antes de cada nova release
# =====================================================
APP_VERSION = "1.1.0"

GITHUB_OWNER = "SDRCasagrande"
GITHUB_REPO = "bit-converter-ponto"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"


@dataclass
class UpdateInfo:
    """Informações sobre uma atualização disponível."""
    version: str
    download_url: str
    changelog: str
    date: str
    size: int = 0  # bytes


def get_current_version() -> str:
    """Retorna a versão atual do aplicativo."""
    return APP_VERSION


def _parse_version(version: str) -> tuple:
    """Converte '1.2.3' em (1, 2, 3) para comparação."""
    try:
        parts = version.strip().lstrip('v').split('.')
        return tuple(int(p) for p in parts)
    except (ValueError, AttributeError):
        return (0, 0, 0)


def check_for_update() -> Tuple[bool, Optional[UpdateInfo], str]:
    """
    Verifica se há atualização disponível no GitHub Releases.
    
    Returns:
        (has_update, update_info, message)
    """
    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': f'Bit-Converter/{APP_VERSION}'
            }
        )
        
        # GitHub usa HTTPS válido, não precisa ignorar cert
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        
        remote_version = data.get('tag_name', '').lstrip('v')
        changelog = data.get('body', 'Sem detalhes.')
        published = data.get('published_at', '')[:10]  # YYYY-MM-DD
        
        # Procura o .exe nos assets
        download_url = ""
        file_size = 0
        for asset in data.get('assets', []):
            name = asset.get('name', '').lower()
            if name.endswith('.exe'):
                download_url = asset.get('browser_download_url', '')
                file_size = asset.get('size', 0)
                break
        
        if not download_url:
            return False, None, "Release encontrada mas sem .exe anexado."
        
        # Compara versões
        local = _parse_version(APP_VERSION)
        remote = _parse_version(remote_version)
        
        if remote > local:
            info = UpdateInfo(
                version=remote_version,
                download_url=download_url,
                changelog=changelog,
                date=published,
                size=file_size
            )
            return True, info, f"Nova versao disponivel: v{remote_version}"
        else:
            return False, None, f"Voce ja esta na versao mais recente (v{APP_VERSION})"
    
    except urllib.error.URLError as e:
        return False, None, f"Sem conexao com internet: {e}"
    except Exception as e:
        return False, None, f"Erro ao verificar: {e}"


def download_update(
    update_info: UpdateInfo,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> Tuple[bool, str]:
    """
    Baixa o novo .exe do GitHub.
    
    Args:
        update_info: Informações da atualização
        progress_callback: Função chamada com (bytes_baixados, total_bytes)
        
    Returns:
        (sucesso, caminho_do_arquivo_ou_mensagem_erro)
    """
    try:
        req = urllib.request.Request(
            update_info.download_url,
            headers={'User-Agent': f'Bit-Converter/{APP_VERSION}'}
        )
        
        # Cria arquivo temporário
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, "Bit-Converter_update.exe")
        
        with urllib.request.urlopen(req, timeout=120) as resp:
            total_size = int(resp.headers.get('Content-Length', 0))
            downloaded = 0
            chunk_size = 65536  # 64KB
            
            with open(temp_path, 'wb') as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if progress_callback and total_size > 0:
                        progress_callback(downloaded, total_size)
        
        # Verifica se o download foi completo
        actual_size = os.path.getsize(temp_path)
        if total_size > 0 and actual_size < total_size * 0.95:
            os.remove(temp_path)
            return False, "Download incompleto. Tente novamente."
        
        return True, temp_path
    
    except Exception as e:
        return False, f"Erro no download: {e}"


def apply_update(new_exe_path: str) -> bool:
    """
    Aplica a atualização substituindo o .exe atual.
    Cria um script .bat que:
    1. Espera o app fechar
    2. Substitui o .exe
    3. Reinicia o app
    
    Returns:
        True se o script foi criado e executado com sucesso
    """
    try:
        # Caminho do .exe atual (funciona tanto em dev quanto empacotado)
        if getattr(sys, 'frozen', False):
            current_exe = sys.executable
        else:
            # Em modo dev, não faz sentido substituir
            return False
        
        # Cria script batch para substituição
        bat_content = f"""@echo off
chcp 65001 >nul
title Atualizando Bit-Converter...
echo.
echo ============================================
echo   Atualizando Bit-Converter...
echo   Aguarde, nao feche esta janela.
echo ============================================
echo.

:: Espera o app fechar (máximo 30 segundos)
set /a count=0
:wait_loop
tasklist /fi "PID eq {os.getpid()}" 2>nul | find "{os.getpid()}" >nul
if %errorlevel% equ 0 (
    set /a count+=1
    if %count% geq 30 (
        echo [ERRO] Timeout esperando o programa fechar.
        pause
        exit /b 1
    )
    timeout /t 1 /nobreak >nul
    goto wait_loop
)

:: Pequeno delay extra para liberar o arquivo
timeout /t 2 /nobreak >nul

:: Faz backup do atual (por segurança)
if exist "{current_exe}.bak" del /f /q "{current_exe}.bak"
copy /y "{current_exe}" "{current_exe}.bak" >nul 2>&1

:: Substitui pelo novo
copy /y "{new_exe_path}" "{current_exe}" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao copiar o novo arquivo.
    echo Restaurando backup...
    copy /y "{current_exe}.bak" "{current_exe}" >nul 2>&1
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Atualizacao concluida com sucesso!
echo   Reiniciando o programa...
echo ============================================
echo.

:: Limpa temporários
del /f /q "{new_exe_path}" >nul 2>&1

:: Reinicia o app
start "" "{current_exe}"

:: Remove este script (auto-limpeza)
del /f /q "%~f0"
exit
"""
        
        bat_path = os.path.join(tempfile.gettempdir(), "bit_converter_update.bat")
        with open(bat_path, 'w', encoding='utf-8') as f:
            f.write(bat_content)
        
        # Executa o script e fecha o app
        subprocess.Popen(
            ['cmd', '/c', bat_path],
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        
        return True
    
    except Exception as e:
        print(f"Erro ao aplicar atualização: {e}")
        return False


def format_size(bytes_val: int) -> str:
    """Formata bytes para exibição legível."""
    if bytes_val < 1024:
        return f"{bytes_val} B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    else:
        return f"{bytes_val / (1024 * 1024):.1f} MB"
