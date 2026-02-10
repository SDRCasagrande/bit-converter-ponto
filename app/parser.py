"""
Parser de arquivos AFD (Arquivo-Fonte de Dados).
Suporta dois formatos:
  - Portaria 671 REP-C (padrão oficial): posições fixas ddmmaaaa + hhmm
  - ControlID proprietário (legado): datetime ISO 8601

Detecta automaticamente o formato ao ler o arquivo.

Layout Portaria 671:
  Tipo 3 (ponto):  NSR(9) + "3"(1) + data(8) + hora(4) + PIS(12)
  Tipo 5 (funcionário): NSR(9) + "5"(1) + data(8) + hora(4) + op(1) + PIS(12) + nome(52)
  
Layout ControlID proprietário (ISO):
  Tipo 3 (ponto):  NSR(9) + "3"(1) + datetime(25 ISO8601) + PIS(12)
  Tipo 5 (funcionário): NSR(9) + "5"(1) + datetime(25 ISO8601) + op(1) + PIS(12) + nome(52)
"""
import re
from datetime import datetime, date, time
from typing import Dict, List, Tuple, Optional
from app.models import Punch, Employee, Company


class AFDParser:
    """
    Parse de arquivo AFD com auto-detecção de formato.
    
    Tipos de registro:
    1 - Cabeçalho (dados do REP e empresa)
    2 - Alteração de empresa no REP
    3 - Marcação de ponto (PRINCIPAL)
    4 - Ajuste de relógio
    5 - Cadastro de funcionário
    6 - Evento do sistema (ControlID)
    9 - Trailer/rodapé
    """
    
    # Regex para ISO datetime usado no formato ControlID proprietário
    ISO_DT_PATTERN = re.compile(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})([+-]\d{4})')
    
    def __init__(self):
        self.punches: List[Punch] = []
        self.employees: Dict[str, Employee] = {}  # PIS -> Employee
        self.company = Company()
        self.errors: List[str] = []
        self.total_lines = 0
        self.parsed_lines = 0
        self.format_detected: str = "unknown"  # "portaria671" ou "controlid_iso"
    
    def parse_file(self, filepath: str) -> Tuple[Dict[str, Employee], Company]:
        """Lê e processa um arquivo AFD completo."""
        self.punches = []
        self.employees = {}
        self.company = Company()
        self.errors = []
        self.total_lines = 0
        self.parsed_lines = 0
        self.format_detected = "unknown"
        
        content = self._read_file(filepath)
        if content is None:
            return self.employees, self.company
        
        self.total_lines = len(content)
        
        # Auto-detecção do formato
        self._detect_format(content)
        
        for line_num, line in enumerate(content, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                self._parse_line(line, line_num)
                self.parsed_lines += 1
            except Exception as e:
                self.errors.append(f"Linha {line_num}: {str(e)}")
        
        # Ordena marcações por data/hora
        self.punches.sort(key=lambda p: p.datetime)
        
        return self.employees, self.company
    
    def _read_file(self, filepath: str) -> Optional[List[str]]:
        """Lê o arquivo tentando diferentes encodings."""
        for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    return f.readlines()
            except UnicodeDecodeError:
                continue
            except FileNotFoundError:
                self.errors.append(f"Arquivo não encontrado: {filepath}")
                return None
            except Exception as e:
                self.errors.append(f"Erro ao ler arquivo: {str(e)}")
                return None
        
        # Fallback
        try:
            with open(filepath, 'r', encoding='latin-1', errors='replace') as f:
                return f.readlines()
        except Exception as e:
            self.errors.append(f"Erro ao ler arquivo: {str(e)}")
            return None
    
    def _detect_format(self, lines: List[str]):
        """
        Detecta se é formato Portaria 671 (padrão) ou ControlID proprietário (ISO).
        
        Regra:
        - Se a primeira linha contém "REP_C" ou "REP-C" → Portaria 671
        - Se encontra ISO datetime (yyyy-mm-ddT...) nos registros tipo 3 → ControlID ISO
        - Caso contrário → Portaria 671 (padrão)
        """
        # Checa se o cabeçalho (primeira linha) indica REP-C
        if lines:
            first_line = lines[0].strip().upper()
            if 'REP_C' in first_line or 'REP-C' in first_line:
                self.format_detected = "portaria671"
                return
        
        # Procura pela primeira linha de marcação (tipo 3)
        for line in lines:
            line = line.strip()
            if len(line) < 20:
                continue
            
            record_type = line[9] if len(line) > 9 else ''
            
            if record_type == '3':
                # Verifica se após o tipo '3' tem ISO datetime (ControlID proprietário)
                after_type = line[10:35]
                if self.ISO_DT_PATTERN.match(after_type):
                    self.format_detected = "controlid_iso"
                else:
                    # Verifica se parece ter data compacta ddmmaaaa
                    date_part = line[10:18]
                    if date_part.isdigit() and len(date_part) == 8:
                        self.format_detected = "portaria671"
                    else:
                        self.format_detected = "portaria671"
                return
        
        # Default
        self.format_detected = "portaria671"
    
    def _parse_line(self, line: str, line_num: int):
        """Identifica o tipo de registro e delega o parse."""
        if len(line) < 10:
            return
        
        # Trailer/rodapé
        if line.startswith('999999999'):
            return
        
        # Linha de assinatura/checksum
        if '==' in line and len(line) < 120:
            return
        
        nsr = line[:9].strip()
        record_type = line[9] if len(line) > 9 else ''
        
        if record_type == '1':
            self._parse_header(line)
        elif record_type == '2':
            self._parse_company_change(line)
        elif record_type == '3':
            self._parse_punch(line, nsr)
        elif record_type == '4':
            pass  # Ajuste de relógio — apenas auditoria
        elif record_type == '5':
            self._parse_employee(line, nsr)
        elif record_type == '6':
            pass  # Evento de sistema ControlID — ignorar
    
    def _parse_header(self, line: str):
        """
        Registro Tipo 1 — Cabeçalho.
        
        Portaria 671:
        NSR(9) + "1"(1) + TipoId(1) + CNPJ/CPF(14) + CEI(12) + razaoSocial(150) + ...
        Posição 10: tipo ID (1=CNPJ, 2=CPF)
        Posição 11-24: CNPJ (14 dígitos)
        Posição 25-36: CEI (12 dígitos)  
        Posição 37-186: Razão Social (150 chars)
        
        ControlID ISO:
        NSR(9) + "1"(1) + CNPJ(14) + zeros(14) + razão(150) + ...
        """
        try:
            if self.format_detected == "controlid_iso":
                cnpj_raw = line[10:24].strip()
                razao = line[38:188].strip() if len(line) > 38 else ''
            else:
                # Portaria 671 standard
                # Posição 10: tipo ID (1 char)
                # Posição 11-24: CNPJ (14 chars)
                # Posição 25-36: CEI (12 chars)
                # Posição 37-186: Razão Social (150 chars)
                tipo_id = line[10] if len(line) > 10 else ''
                cnpj_raw = line[11:25].strip()
                razao = line[37:187].strip() if len(line) > 37 else ''
                
                # Se não achou razão na posição padrão, tenta buscar texto
                if not razao:
                    rest = line[25:]
                    match = re.search(r'([A-ZÀ-Ú][A-ZÀ-Ú\s\.\-\&]{3,})', rest)
                    if match:
                        razao = match.group(1).strip()
            
            if cnpj_raw:
                digits = re.sub(r'\D', '', cnpj_raw)[:14]
                if len(digits) == 14:
                    self.company.cnpj = (
                        f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/"
                        f"{digits[8:12]}-{digits[12:14]}"
                    )
            
            if razao:
                self.company.name = razao.strip()
                
        except Exception:
            pass
    
    def _parse_company_change(self, line: str):
        """Registro Tipo 2 — Alteração de empresa."""
        pass
    
    def _parse_punch(self, line: str, nsr: str):
        """
        Registro Tipo 3 — Marcação de Ponto.
        
        Portaria 671 (34+ chars):
        NSR(9) + "3"(1) + data(8 ddmmaaaa) + hora(4 hhmm) + PIS(12)
        Posição 10-17: data
        Posição 18-21: hora
        Posição 22-33: PIS
        
        ControlID ISO (47+ chars):
        NSR(9) + "3"(1) + datetime(25 ISO8601) + PIS(12)
        Posição 10-34: datetime
        Posição 35-46: PIS
        """
        try:
            if self.format_detected == "controlid_iso":
                # ControlID proprietário: ISO datetime
                dt_str = line[10:35]
                match = self.ISO_DT_PATTERN.match(dt_str)
                if not match:
                    return
                
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3))
                hour = int(match.group(4))
                minute = int(match.group(5))
                
                pis = line[35:47].strip()
            else:
                # Portaria 671: posições fixas
                date_str = line[10:18]   # ddmmaaaa (8 chars)
                time_str = line[18:22]   # hhmm (4 chars)
                pis = line[22:34].strip()  # PIS (12 chars)
                
                day = int(date_str[0:2])
                month = int(date_str[2:4])
                year = int(date_str[4:8])
                hour = int(time_str[0:2])
                minute = int(time_str[2:4])
            
            if not pis:
                return
            
            # Validações
            if not (1 <= day <= 31 and 1 <= month <= 12 and 2000 <= year <= 2100):
                return
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return
            
            punch = Punch(
                datetime=datetime(year, month, day, hour, minute),
                nsr=nsr,
                pis=pis
            )
            
            self.punches.append(punch)
            
            if pis not in self.employees:
                self.employees[pis] = Employee(pis=pis)
                
        except (ValueError, IndexError) as e:
            self.errors.append(f"Registro tipo 3 (NSR {nsr}): {e}")
    
    def _parse_employee(self, line: str, nsr: str):
        """
        Registro Tipo 5 — Cadastro de Funcionário.
        
        Portaria 671:
        NSR(9) + "5"(1) + data(8) + hora(4) + op(1) + PIS(12) + Nome(52)
        Posição 10-17: data (8 chars)
        Posição 18-21: hora (4 chars)
        Posição 22: operação (1 char: I/A/E)
        Posição 23-34: PIS (12 chars)
        Posição 35-86: Nome (52 chars)
        
        ControlID ISO:
        NSR(9) + "5"(1) + datetime(25) + op(1) + PIS(12) + Nome(52)
        Posição 35: operação
        Posição 36-47: PIS
        Posição 48-99: Nome
        """
        try:
            if self.format_detected == "controlid_iso":
                op = line[35] if len(line) > 35 else ''
                pis = line[36:48].strip()
                name = line[48:100].strip() if len(line) > 48 else ''
            else:
                # Portaria 671: posições fixas oficiais
                op = line[22] if len(line) > 22 else ''
                pis = line[23:35].strip()
                name = line[35:87].strip() if len(line) > 35 else ''
            
            if pis:
                if pis not in self.employees:
                    self.employees[pis] = Employee(pis=pis)
                if name:
                    self.employees[pis].name = name
                    
        except (ValueError, IndexError) as e:
            self.errors.append(f"Registro tipo 5 (NSR {nsr}): {e}")
    
    def get_punches_by_pis(self, pis: str) -> List[Punch]:
        """Retorna todas as marcações de um PIS, ordenadas por data/hora."""
        result = [p for p in self.punches if p.pis == pis]
        result.sort(key=lambda p: p.datetime)
        return result
    
    def get_date_range(self) -> Tuple[Optional[date], Optional[date]]:
        """Retorna a data mais antiga e mais recente das marcações."""
        if not self.punches:
            return None, None
        dates = [p.date for p in self.punches]
        return min(dates), max(dates)
    
    def get_month_year_options(self) -> List[Tuple[int, int]]:
        """Retorna lista de (mês, ano) disponíveis nas marcações."""
        if not self.punches:
            return []
        months = set()
        for p in self.punches:
            months.add((p.datetime.month, p.datetime.year))
        return sorted(months, key=lambda x: (x[1], x[0]))
    
    def get_summary(self) -> dict:
        """Retorna resumo do arquivo parseado."""
        date_start, date_end = self.get_date_range()
        return {
            'total_lines': self.total_lines,
            'parsed_lines': self.parsed_lines,
            'total_punches': len(self.punches),
            'total_employees': len(self.employees),
            'date_start': date_start,
            'date_end': date_end,
            'company_name': self.company.name,
            'company_cnpj': self.company.cnpj,
            'errors': len(self.errors),
            'months_available': self.get_month_year_options(),
            'format': self.format_detected,
            'employees': {
                pis: emp.display_name 
                for pis, emp in self.employees.items()
            }
        }
