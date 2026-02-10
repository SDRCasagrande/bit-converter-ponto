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
        
        for proto, port in attempts:
            try:
                self.device.protocol = proto
                self.device.port = port
                self._update_base_url()
                
                body = json.dumps({
                    "login": self.device.login,
                    "password": self.device.password
                }).encode('utf-8')
                
                req = urllib.request.Request(
                    f"{self.base_url}/login.fcgi",
                    data=body,
                    headers={
                        'Content-Type': 'application/json',
                        'Content-Length': str(len(body)),
                    },
                    method='POST'
                )
                
                ctx = self._ssl_ctx if proto == 'https' else None
                
                with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
                    content = resp.read().decode('utf-8')
                    result = json.loads(content)
                    if "session" in result:
                        self.device.session = result["session"]
                        return True, f"Conectado via {proto.upper()}:{port}"
                        
            except Exception:
                continue
        
        return False, "Nenhum protocolo funcionou"
    
    def connect(self) -> bool:
        """
        Autentica no relógio e obtém sessão.
        Tenta auto-detecção de protocolo se a primeira tentativa falhar.
        Retorna True se conectou com sucesso.
        """
        # Tenta com as configurações atuais primeiro
        try:
            result = self._request("login.fcgi", {
                "login": self.device.login,
                "password": self.device.password
            })
            
            if "session" in result:
                self.device.session = result["session"]
                return True
            else:
                # Tenta auto-detecção
                ok, msg = self._auto_detect_protocol()
                if ok:
                    return True
                raise ConnectionError("Login falhou — verifique usuario e senha.")
                
        except ConnectionError as e:
            # Se deu erro de conexão, tenta outros protocolos
            if "HTTP" in str(e) or "conectar" in str(e):
                ok, msg = self._auto_detect_protocol()
                if ok:
                    return True
            raise
        except Exception as e:
            # Tenta auto-detecção como fallback
            ok, msg = self._auto_detect_protocol()
            if ok:
                return True
            raise ConnectionError(f"Erro ao conectar: {e}")
    
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
