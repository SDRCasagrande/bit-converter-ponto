"""
Cliente API para relógios de ponto ControlID.
Conecta via rede local (HTTPS ou HTTP) para puxar o AFD diretamente.

Endpoints usados:
- POST /login.fcgi         → Autentica e retorna sessão
- POST /get_afd.fcgi       → Baixa o arquivo AFD
- POST /system_information.fcgi → Info do equipamento (opcional)

Referência: https://www.controlid.com.br/suporte/api/
"""
import json
import urllib.request
import urllib.error
import urllib.parse
import ssl
import tempfile
import os
from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass
class ControlIDDevice:
    """Representa um relógio ControlID na rede."""
    ip: str
    port: int = 443
    login: str = "admin"
    password: str = "admin"
    session: str = ""
    device_name: str = ""
    serial: str = ""
    protocol: str = "https"  # https ou http


class ControlIDClient:
    """Cliente para API REST dos relógios ControlID (iDClass/iDFlex)."""
    
    def __init__(self, device: ControlIDDevice):
        self.device = device
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE
        self._update_base_url()
    
    def _update_base_url(self):
        """Atualiza a URL base com protocolo e porta corretos."""
        self.base_url = f"{self.device.protocol}://{self.device.ip}:{self.device.port}"
    
    def _request(self, endpoint: str, data: dict = None, params: str = "") -> dict:
        """Faz requisição POST para o equipamento."""
        url = f"{self.base_url}/{endpoint}"
        if params:
            url += f"?{params}"
        
        body = json.dumps(data).encode('utf-8') if data else b'{}'
        
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                'Content-Type': 'application/json',
                'Content-Length': str(len(body)),
            },
            method='POST'
        )
        
        ctx = self._ssl_ctx if self.device.protocol == 'https' else None
        
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
                content = resp.read().decode('utf-8')
                if content.strip():
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return {"raw": content}
                return {}
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode('utf-8', errors='replace')[:200]
            except Exception:
                pass
            raise ConnectionError(
                f"Erro HTTP {e.code} do relogio ({self.device.ip}): {e.reason}\n{error_body}"
            )
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Nao foi possivel conectar ao relogio ({self.device.ip}): {e}"
            )
        except Exception as e:
            raise ConnectionError(f"Erro na comunicacao: {e}")
    
    def _request_raw(self, endpoint: str, data: dict = None, params: str = "") -> str:
        """Faz requisição POST e retorna resposta como texto bruto."""
        url = f"{self.base_url}/{endpoint}"
        if params:
            url += f"?{params}"
        
        body = json.dumps(data).encode('utf-8') if data else b'{}'
        
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                'Content-Type': 'application/json',
                'Content-Length': str(len(body)),
            },
            method='POST'
        )
        
        ctx = self._ssl_ctx if self.device.protocol == 'https' else None
        
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                return resp.read().decode('utf-8', errors='replace')
        except urllib.error.HTTPError as e:
            raise ConnectionError(f"Erro HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Nao foi possivel conectar ao relogio ({self.device.ip}): {e}"
            )
    
    def _auto_detect_protocol(self):
        """
        Tenta detectar automaticamente se o relógio usa HTTPS ou HTTP.
        Testa HTTPS:443 primeiro, depois HTTP:80.
        """
        attempts = [
            ("https", 443),
            ("http", 80),
            ("https", 4370),
            ("http", 4370),
        ]
        
        content_types = ["json", "form"]
        
        for proto, port in attempts:
            self.device.protocol = proto
            self.device.port = port
            self._update_base_url()
            
            for ct in content_types:
                try:
                    result = self._login_request(ct)
                    if "session" in result:
                        self.device.session = result["session"]
                        return True, f"Conectado via {proto.upper()}:{port} ({ct})"
                except Exception:
                    continue
        
        return False, "Nenhum protocolo funcionou"
    
    def _login_request(self, content_type: str = "json") -> dict:
        """
        Tenta login com o tipo de conteúdo especificado.
        content_type: 'json' ou 'form'
        """
        url = f"{self.base_url}/login.fcgi"
        login_data = {
            "login": self.device.login,
            "password": self.device.password
        }
        
        if content_type == "form":
            body = urllib.parse.urlencode(login_data).encode('utf-8')
            ct_header = 'application/x-www-form-urlencoded'
        else:
            body = json.dumps(login_data).encode('utf-8')
            ct_header = 'application/json'
        
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                'Content-Type': ct_header,
                'Content-Length': str(len(body)),
            },
            method='POST'
        )
        
        ctx = self._ssl_ctx if self.device.protocol == 'https' else None
        
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            content = resp.read().decode('utf-8')
            if content.strip():
                return json.loads(content)
            return {}
    
    def connect(self) -> bool:
        """
        Autentica no relógio e obtém sessão.
        Tenta JSON primeiro, depois form-urlencoded, depois auto-detecção.
        Retorna True se conectou com sucesso.
        """
        # 1) Tenta JSON (padrão)
        try:
            result = self._login_request("json")
            if "session" in result:
                self.device.session = result["session"]
                return True
        except urllib.error.HTTPError as e:
            if e.code == 400:
                # Firmware pode não aceitar JSON, tenta form-urlencoded
                pass
            else:
                pass
        except Exception:
            pass
        
        # 2) Tenta form-urlencoded (firmware antigo do iDClass)
        try:
            result = self._login_request("form")
            if "session" in result:
                self.device.session = result["session"]
                return True
        except Exception:
            pass
        
        # 3) Auto-detecção de protocolo/porta com ambos os formatos
        ok, msg = self._auto_detect_protocol()
        if ok:
            return True
        
        raise ConnectionError(
            "Não foi possível conectar ao relógio.\n"
            "Verifique:\n"
            "• IP correto (visível no display do relógio)\n"
            "• Usuário e senha da API (padrão: admin/admin)\n"
            "• Relógio ligado e na mesma rede"
        )
    
    def get_device_info(self) -> dict:
        """Obtém informações do equipamento."""
        if not self.device.session:
            raise ConnectionError("Nao autenticado. Chame connect() primeiro.")
        
        try:
            result = self._request(
                "system_information.fcgi",
                params=f"session={self.device.session}"
            )
            
            self.device.device_name = result.get("name", "")
            self.device.serial = result.get("serial", "")
            
            return result
        except Exception:
            # Alguns modelos não suportam este endpoint
            return {"name": "ControlID", "serial": "N/A"}
    
    def download_afd(self, save_path: Optional[str] = None, mode: str = "671") -> str:
        """
        Baixa o arquivo AFD do relógio.
        
        Args:
            save_path: Caminho para salvar o arquivo. Se None, salva em temp.
            mode: Modo do AFD ("671" para Portaria 671, padrão).
            
        Returns:
            Caminho do arquivo AFD salvo.
        """
        if not self.device.session:
            raise ConnectionError("Nao autenticado. Chame connect() primeiro.")
        
        params = f"session={self.device.session}"
        if mode:
            params += f"&mode={mode}"
        
        afd_content = self._request_raw("get_afd.fcgi", params=params)
        
        if not afd_content or len(afd_content.strip()) < 10:
            raise ValueError("AFD vazio — o relogio pode nao ter marcacoes.")
        
        # Salva em arquivo
        if not save_path:
            save_path = os.path.join(
                tempfile.gettempdir(),
                f"AFD_ControlID_{self.device.ip.replace('.', '_')}.txt"
            )
        
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(afd_content)
        
        return save_path
    
    def get_employees(self) -> list:
        """Obtém lista de funcionários cadastrados no relógio."""
        if not self.device.session:
            raise ConnectionError("Nao autenticado. Chame connect() primeiro.")
        
        result = self._request("load_objects.fcgi", {
            "object": "users"
        }, params=f"session={self.device.session}")
        
        return result.get("users", [])
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        Testa a conexão com o relógio.
        Retorna (sucesso, mensagem).
        """
        try:
            self.connect()
            proto = self.device.protocol.upper()
            port = self.device.port
            
            info = self.get_device_info()
            name = info.get("name", "Desconhecido")
            serial = info.get("serial", "N/A")
            return True, (
                f"Conectado! ({proto}:{port})\n"
                f"Equipamento: {name}\n"
                f"Serial: {serial}"
            )
        except ConnectionError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Erro: {e}"
