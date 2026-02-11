"""
Calculador de jornada de trabalho — CLT.
Agrupa marcações por dia, calcula horas trabalhadas,
horas extras, atrasos e faltas baseado na escala configurada.
"""
from datetime import datetime, date, time, timedelta
from typing import Dict, List, Optional, Tuple
from calendar import monthrange
from app.models import (
    Punch, Employee, WorkDay, ScheduleConfig, 
    ScheduleType, MonthlyReport, Company
)


class WorkCalculator:
    """Calcula horas trabalhadas, extras e faltas baseado em regras CLT."""
    
    def __init__(self, default_schedule: Optional[ScheduleConfig] = None):
        self.default_schedule = default_schedule or ScheduleConfig()
    
    def process_employee(
        self, 
        employee: Employee, 
        punches: List[Punch],
        month: int, 
        year: int
    ) -> Employee:
        """
        Processa todas as marcações de um funcionário para um mês.
        Retorna o Employee com workdays calculados.
        """
        schedule = employee.schedule or self.default_schedule
        
        # Agrupa marcações por dia
        punches_by_day: Dict[date, List[Punch]] = {}
        for punch in punches:
            if punch.datetime.month == month and punch.datetime.year == year:
                day = punch.date
                if day not in punches_by_day:
                    punches_by_day[day] = []
                punches_by_day[day].append(punch)
        
        # Ordena marcações dentro de cada dia
        for day in punches_by_day:
            punches_by_day[day].sort(key=lambda p: p.datetime)
        
        # Gera WorkDays para todos os dias do mês
        _, days_in_month = monthrange(year, month)
        employee.workdays = []
        
        for day_num in range(1, days_in_month + 1):
            current_date = date(year, month, day_num)
            day_punches = punches_by_day.get(current_date, [])
            
            workday = self._calculate_workday(
                current_date, 
                day_punches, 
                schedule
            )
            employee.workdays.append(workday)
        
        return employee
    
    def _calculate_workday(
        self, 
        current_date: date, 
        punches: List[Punch],
        schedule: ScheduleConfig
    ) -> WorkDay:
        """Calcula as horas de um dia específico."""
        weekday = current_date.weekday()  # 0=segunda, 6=domingo
        is_workday = self._is_workday(weekday, schedule)
        expected = self._expected_hours(weekday, schedule)
        
        workday = WorkDay(
            date=current_date,
            punches=punches,
            is_workday=is_workday,
            expected_hours=expected
        )
        
        if not punches:
            # Sem marcações
            if is_workday:
                workday.is_absent = True
                workday.deficit_hours = expected
                workday.observation = "Sem marcações"
            return workday
        
        # === Validação de marcações incompletas ===
        num_punches = len(punches)
        
        if num_punches == 1:
            # Apenas 1 marcação — esqueceu de bater saída (ou entrada)
            workday.worked_hours = 0.0
            workday.deficit_hours = expected if is_workday else 0.0
            workday.observation = "Marcação incompleta (1 batida — falta entrada ou saída)"
            workday.is_incomplete = True
            if is_workday:
                workday.is_absent = True
            return workday
        
        if num_punches % 2 != 0:
            # 3, 5 marcações — uma batida sem par
            workday.observation = f"Marcação ímpar ({num_punches} batidas — falta 1 registro)"
            workday.is_incomplete = True
        
        if num_punches == 2 and is_workday and expected > 6:
            # Jornada > 6h com apenas 2 marcações — não registrou intervalo
            workday.observation = "Jornada contínua (sem intervalo registrado)"
        
        if not is_workday and punches:
            # Trabalhou em dia de folga — tudo é hora extra
            worked = self._calc_worked_hours(punches, schedule)
            workday.worked_hours = worked
            workday.overtime_hours = worked
            if not workday.observation:
                workday.observation = "Trabalho em dia de folga"
            return workday
        
        # Dia normal de trabalho
        worked = self._calc_worked_hours(punches, schedule)
        workday.worked_hours = worked
        
        # Verifica atraso (primeira entrada vs horário esperado)
        entry_time = punches[0].time
        expected_entry = schedule.entry_time
        
        if schedule.schedule_type == ScheduleType.STANDARD and weekday == 5:
            expected_entry = schedule.saturday_entry
        
        late_minutes = self._time_diff_minutes(expected_entry, entry_time)
        
        if late_minutes > schedule.tolerance_minutes:
            workday.is_late = True
            workday.late_minutes = late_minutes
        
        # Calcula horas extras e déficit
        if worked > expected + (schedule.tolerance_minutes / 60):
            overtime = worked - expected
            # Limita a 2h extras/dia (CLT)
            workday.overtime_hours = min(overtime, schedule.max_daily_overtime_hours)
            if overtime > schedule.max_daily_overtime_hours:
                workday.observation = f"Excedeu limite de {schedule.max_daily_overtime_hours}h extras"
        elif worked < expected - (schedule.tolerance_minutes / 60):
            workday.deficit_hours = expected - worked
        
        # Calcula intervalo realizado
        workday.break_minutes = self._calc_break_minutes(punches)
        
        # Verifica se intervalo mínimo foi respeitado (CLT: 1h para jornada > 6h)
        if expected > 6 and workday.break_minutes < 60:
            if workday.break_minutes > 0:
                workday.observation = (
                    f"Intervalo insuficiente: {workday.break_minutes:.0f}min "
                    f"(mínimo 60min)"
                )
        
        return workday
    
    def _calc_worked_hours(
        self, punches: List[Punch], schedule: ScheduleConfig
    ) -> float:
        """
        Calcula horas trabalhadas a partir dos pares entrada/saída.
        Para 4 marcações: (E1→S1) + (E2→S2), descontando intervalo.
        Para 2 marcações: (E1→S1), intervalo não descontado.
        Para número ímpar: usa as que conseguir parear.
        """
        if len(punches) < 2:
            return 0.0
        
        total_minutes = 0.0
        
        # Agrupa em pares (entrada, saída)
        for i in range(0, len(punches) - 1, 2):
            entry = punches[i].datetime
            exit_p = punches[i + 1].datetime
            diff = (exit_p - entry).total_seconds() / 60
            if diff > 0:
                total_minutes += diff
        
        # Se tem 2 marcações: respeitar o registro real.
        # NÃO descontar intervalo automaticamente — o funcionário
        # pode ter trabalhado direto sem almoço.
        # O intervalo só é calculado quando há 4 marcações (E1→S1 + E2→S2).
        
        return max(0, total_minutes / 60)
    
    def _calc_break_minutes(self, punches: List[Punch]) -> float:
        """Calcula o intervalo entre a 2ª e 3ª marcação (saída almoço → volta)."""
        if len(punches) >= 4:
            exit_break = punches[1].datetime
            return_break = punches[2].datetime
            diff = (return_break - exit_break).total_seconds() / 60
            return max(0, diff)
        return 0.0
    
    def _is_workday(self, weekday: int, schedule: ScheduleConfig) -> bool:
        """Verifica se o dia da semana é dia de trabalho na escala."""
        stype = schedule.schedule_type
        
        if stype == ScheduleType.STANDARD:
            # Seg-Sex + Sáb meio período
            return weekday <= 5
        elif stype == ScheduleType.SCALE_5X2:
            return weekday in schedule.workdays
        elif stype == ScheduleType.SCALE_6X1:
            # 6 dias, 1 folga (domingo padrão)
            return weekday <= 5
        elif stype == ScheduleType.SCALE_12X36:
            # 12x36 não segue semana fixa — precisa de lógica especial
            return True  # Sempre calculado pelo padrão de marcações
        elif stype in (ScheduleType.PARTIAL_30, ScheduleType.PARTIAL_26):
            return weekday in schedule.workdays
        elif stype == ScheduleType.CUSTOM:
            return weekday in schedule.workdays
        
        return weekday in schedule.workdays
    
    def _expected_hours(self, weekday: int, schedule: ScheduleConfig) -> float:
        """Retorna as horas esperadas para um dia da semana na escala."""
        stype = schedule.schedule_type
        
        if stype == ScheduleType.STANDARD:
            if weekday <= 4:  # Seg-Sex
                return schedule.daily_hours if schedule.daily_hours else 8.0
            elif weekday == 5:  # Sábado
                return schedule.saturday_hours
            return 0.0
        
        elif stype == ScheduleType.SCALE_5X2:
            if weekday in schedule.workdays:
                return schedule.daily_hours  # Usa configuração (padrão 8h)
            return 0.0
        
        elif stype == ScheduleType.SCALE_6X1:
            if weekday <= 4:
                return schedule.daily_hours if schedule.daily_hours else 8.0
            elif weekday == 5:
                return schedule.saturday_hours
            return 0.0
        
        elif stype == ScheduleType.SCALE_12X36:
            return 12.0
        
        elif stype == ScheduleType.PARTIAL_30:
            if weekday in schedule.workdays:
                return schedule.daily_hours
            return 0.0
        
        elif stype == ScheduleType.PARTIAL_26:
            if weekday in schedule.workdays:
                return schedule.daily_hours
            return 0.0
        
        elif stype == ScheduleType.CUSTOM:
            if weekday in schedule.workdays:
                return schedule.daily_hours
            return 0.0
        
        return schedule.daily_hours if weekday in schedule.workdays else 0.0
    
    def _time_diff_minutes(self, expected: time, actual: time) -> float:
        """Calcula diferença em minutos entre dois horários (positivo = atraso)."""
        expected_min = expected.hour * 60 + expected.minute
        actual_min = actual.hour * 60 + actual.minute
        return actual_min - expected_min
    
    def generate_report(
        self,
        employees: Dict[str, Employee],
        punches: List[Punch],
        company: Company,
        month: int,
        year: int
    ) -> MonthlyReport:
        """Gera o relatório mensal completo para todos os funcionários."""
        report = MonthlyReport(
            company=company,
            month=month,
            year=year,
            employees=[],
            generated_at=datetime.now()
        )
        
        for pis, employee in employees.items():
            emp_punches = [p for p in punches if p.pis == pis]
            processed = self.process_employee(employee, emp_punches, month, year)
            report.employees.append(processed)
        
        # Ordena por nome
        report.employees.sort(key=lambda e: e.display_name)
        
        return report
