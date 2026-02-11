"""
Modelos de dados para o sistema AFD Parser.
Dataclasses para Employee, Punch, WorkDay, Company e Schedule.
"""
from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta
from typing import Optional, List
from enum import Enum


class ScheduleType(Enum):
    """Tipos de escala CLT suportados."""
    STANDARD = "padrao"       # 8h/dia seg-sex + 4h sáb = 44h/sem
    SCALE_5X2 = "5x2"         # 5 dias 8h48/dia, 2 folgas = 44h/sem
    SCALE_6X1 = "6x1"         # 6 dias até 8h/dia, 1 folga = 44h/sem
    SCALE_12X36 = "12x36"     # 12h trabalho / 36h descanso
    PARTIAL_30 = "parcial_30" # Até 30h/sem, sem hora extra
    PARTIAL_26 = "parcial_26" # Até 26h/sem, até 6h extras
    CUSTOM = "personalizada"


@dataclass
class ScheduleConfig:
    """Configuração de escala de trabalho."""
    schedule_type: ScheduleType = ScheduleType.SCALE_6X1
    # Horários padrão
    entry_time: time = field(default_factory=lambda: time(8, 0))
    exit_time: time = field(default_factory=lambda: time(18, 0))
    # Intervalo
    break_start: time = field(default_factory=lambda: time(13, 0))
    break_end: time = field(default_factory=lambda: time(15, 0))
    break_duration_minutes: int = 120
    # Tolerância (CLT art. 58 — até 10 min não descontam/pagam)
    tolerance_minutes: int = 10
    # Jornada parcial
    weekly_hours: float = 44.0
    daily_hours: float = 8.0  # 8h para 6x1 seg-sex (+ 4h sáb = 44h/sem)
    # Sábado (para escala padrão/6x1)
    saturday_hours: float = 4.0
    saturday_entry: time = field(default_factory=lambda: time(8, 0))
    saturday_exit: time = field(default_factory=lambda: time(12, 0))
    # Hora extra
    overtime_premium: float = 0.50  # 50% mínimo CLT
    max_daily_overtime_hours: float = 2.0  # Limite CLT: 2h extras/dia
    # Dias de trabalho (0=segunda, 6=domingo)
    workdays: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5])  # seg-sáb


@dataclass
class Company:
    """Dados da empresa para o cabeçalho do relatório."""
    name: str = ""
    cnpj: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    phone: str = ""
    logo_path: str = ""
    default_schedule: ScheduleConfig = field(default_factory=ScheduleConfig)


@dataclass
class Punch:
    """Uma marcação de ponto individual."""
    datetime: datetime = field(default_factory=datetime.now)
    nsr: str = ""          # Número Sequencial de Registro
    pis: str = ""          # PIS do empregado
    
    @property
    def date(self) -> date:
        return self.datetime.date()
    
    @property
    def time(self) -> time:
        return self.datetime.time()


@dataclass
class WorkDay:
    """Resumo de um dia de trabalho de um colaborador."""
    date: date = field(default_factory=date.today)
    punches: List[Punch] = field(default_factory=list)
    # Calculados
    worked_hours: float = 0.0       # Horas efetivamente trabalhadas
    expected_hours: float = 0.0     # Horas esperadas pela escala
    overtime_hours: float = 0.0     # Horas extras
    deficit_hours: float = 0.0      # Horas faltantes
    break_minutes: float = 0.0      # Intervalo realizado
    is_late: bool = False           # Chegou atrasado
    late_minutes: float = 0.0       # Minutos de atraso
    is_absent: bool = False         # Faltou
    is_incomplete: bool = False     # Marcação incompleta (ímpar)
    is_workday: bool = True         # Era dia de trabalho
    is_holiday: bool = False        # Feriado
    observation: str = ""           # Observações (falta justificada, etc.)
    
    @property
    def first_entry(self) -> Optional[time]:
        if self.punches:
            return self.punches[0].time
        return None
    
    @property
    def last_exit(self) -> Optional[time]:
        if len(self.punches) >= 2:
            return self.punches[-1].time
        return None
    
    @property
    def entry_exit_pairs(self) -> List[tuple]:
        """Retorna pares (entrada, saída) das marcações."""
        pairs = []
        for i in range(0, len(self.punches) - 1, 2):
            entry = self.punches[i]
            exit_p = self.punches[i + 1] if i + 1 < len(self.punches) else None
            pairs.append((entry, exit_p))
        return pairs


@dataclass
class Employee:
    """Dados de um colaborador."""
    pis: str = ""
    name: str = ""
    employee_id: str = ""
    cargo: str = ""        # Cargo / função
    department: str = ""    # Departamento
    schedule: Optional[ScheduleConfig] = None  # Override da escala padrão
    workdays: List[WorkDay] = field(default_factory=list)
    
    @property
    def display_name(self) -> str:
        return self.name if self.name else f"PIS {self.pis}"
    
    @property
    def total_worked_hours(self) -> float:
        return sum(wd.worked_hours for wd in self.workdays)
    
    @property
    def total_overtime_hours(self) -> float:
        return sum(wd.overtime_hours for wd in self.workdays)
    
    @property
    def total_deficit_hours(self) -> float:
        return sum(wd.deficit_hours for wd in self.workdays)
    
    @property
    def total_late_days(self) -> int:
        return sum(1 for wd in self.workdays if wd.is_late)
    
    @property
    def total_absent_days(self) -> int:
        return sum(1 for wd in self.workdays if wd.is_absent)
    
    @property
    def total_late_minutes(self) -> float:
        return sum(wd.late_minutes for wd in self.workdays)


@dataclass
class MonthlyReport:
    """Relatório mensal consolidado."""
    company: Company = field(default_factory=Company)
    month: int = 1
    year: int = 2026
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    employees: List[Employee] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    
    @property
    def period_label(self) -> str:
        if self.start_date and self.end_date:
            return (
                f"DE {self.start_date.strftime('%d/%m/%Y')} "
                f"ATÉ {self.end_date.strftime('%d/%m/%Y')}"
            )
        months = [
            '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
            'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
        ]
        return f"{months[self.month]}/{self.year}"

