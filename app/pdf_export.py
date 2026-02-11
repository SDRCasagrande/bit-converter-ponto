"""
Gerador de relatórios PDF — Cartão de Ponto.
Layout inspirado no ControlID RHiD com cabeçalho vermelho,
bloco de dados da empresa, horário de trabalho e tabela detalhada.
"""
import os
from datetime import date, time, datetime
from typing import List, Optional
from fpdf import FPDF
from app.models import MonthlyReport, Employee, WorkDay, Company, ScheduleConfig


# Cores do tema ControlID
RED = (180, 30, 30)
DARK_RED = (140, 20, 20)
LIGHT_GRAY = (245, 245, 245)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY_TEXT = (100, 100, 100)
BLUE_HEADER = (25, 25, 112)


class PontoPDF(FPDF):
    """PDF customizado — Cartão de Ponto estilo ControlID."""
    
    def __init__(self, company: Company, period: str, schedule: ScheduleConfig = None):
        super().__init__('P', 'mm', 'A4')
        self.company = company
        self.period = period
        self.schedule = schedule or ScheduleConfig()
        self.set_auto_page_break(auto=True, margin=15)
        
        # Fontes
        assets = os.path.join(os.path.dirname(__file__), '..', 'assets')
        font_reg = os.path.join(assets, 'DejaVuSans.ttf')
        font_bold = os.path.join(assets, 'DejaVuSans-Bold.ttf')
        
        if os.path.exists(font_reg) and os.path.exists(font_bold):
            self.add_font('DejaVu', '', font_reg, uni=True)
            self.add_font('DejaVu', 'B', font_bold, uni=True)
            self.has_dejavu = True
        else:
            self.has_dejavu = False
    
    def _font(self, style='', size=8):
        if self.has_dejavu:
            self.set_font('DejaVu', style, size)
        else:
            self.set_font('Helvetica', style, size)
    
    def header(self):
        """Cabeçalho: Cartão de Ponto vermelho + período."""
        # Barra vermelha
        self.set_fill_color(*RED)
        self.rect(10, 8, 190, 12, 'F')
        
        # Logo da empresa (se existir)
        x_logo = 12
        if self.company.logo_path and os.path.exists(self.company.logo_path):
            try:
                self.image(self.company.logo_path, x_logo, 8.5, 11, 11)
                x_logo = 25
            except Exception:
                pass
        
        # Título "Cartão de Ponto"
        self.set_xy(x_logo, 9)
        self.set_text_color(*WHITE)
        self._font('B', 13)
        self.cell(60, 5, 'Cartão de Ponto', align='L')
        
        # Período centralizado
        self.set_xy(70, 9)
        self._font('B', 9)
        self.cell(70, 5, self.period, align='C')
        
        # Página
        self.set_xy(150, 9)
        self._font('', 7)
        self.cell(50, 4, f'Página {self.page_no()}/{{nb}}', align='R')
        
        # Data de emissão
        self.set_xy(150, 14)
        self._font('', 6)
        now = datetime.now().strftime('%d/%m/%Y às %H:%M')
        self.cell(50, 3, f'Emitido em {now}', align='R')
        
        self.set_text_color(*BLACK)
        self.set_y(22)
    
    def footer(self):
        """Rodapé com branding."""
        self.set_y(-10)
        self._font('', 6)
        self.set_text_color(150, 150, 150)
        self.cell(95, 5, 'Bit-Converter — BitKaiser Solution', align='L')
        self.cell(95, 5, 'www.bitkaiser.com.br', align='R')
        self.set_text_color(*BLACK)


class PDFExporter:
    """Exportador de relatórios em PDF — Cartão de Ponto."""
    
    def __init__(self):
        self._ensure_fonts()
    
    def _ensure_fonts(self):
        assets_dir = os.path.join(os.path.dirname(__file__), '..', 'assets')
        os.makedirs(assets_dir, exist_ok=True)
        self.fonts_available = (
            os.path.exists(os.path.join(assets_dir, 'DejaVuSans.ttf')) and
            os.path.exists(os.path.join(assets_dir, 'DejaVuSans-Bold.ttf'))
        )
    
    def export_individual(
        self, 
        report: MonthlyReport, 
        output_dir: str
    ) -> List[str]:
        """Exporta um PDF para cada colaborador."""
        os.makedirs(output_dir, exist_ok=True)
        generated = []
        schedule = report.company.default_schedule
        
        for employee in report.employees:
            filename = self._safe_filename(employee.display_name)
            filepath = os.path.join(
                output_dir, 
                f"Ponto_{filename}_{report.month:02d}_{report.year}.pdf"
            )
            
            pdf = PontoPDF(report.company, report.period_label, schedule)
            pdf.alias_nb_pages()
            self._add_employee_pages(pdf, report, employee)
            pdf.output(filepath)
            generated.append(filepath)
        
        return generated
    
    def export_employee(
        self,
        report: MonthlyReport,
        employee,
        output_path: str
    ) -> str:
        """Exporta PDF de um único colaborador."""
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        schedule = report.company.default_schedule
        pdf = PontoPDF(report.company, report.period_label, schedule)
        pdf.alias_nb_pages()
        self._add_employee_pages(pdf, report, employee)
        pdf.output(output_path)
        return output_path
    
    def export_consolidated(
        self, 
        report: MonthlyReport, 
        output_path: str
    ) -> str:
        """Exporta um PDF consolidado com todos os colaboradores."""
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        schedule = report.company.default_schedule
        
        pdf = PontoPDF(report.company, report.period_label, schedule)
        pdf.alias_nb_pages()
        
        for employee in report.employees:
            self._add_employee_pages(pdf, report, employee)
        
        pdf.output(output_path)
        return output_path
    
    # ==========================================
    # BLOCOS DO RELATÓRIO
    # ==========================================
    
    def _add_employee_pages(self, pdf: PontoPDF, report: MonthlyReport, employee: Employee):
        """Adiciona as páginas de um colaborador."""
        pdf.add_page()
        
        # 1) Bloco empresa + funcionário
        self._draw_info_block(pdf, report, employee)
        
        # 2) Quadro "Horário de Trabalho"
        self._draw_schedule_box(pdf, report.company.default_schedule)
        
        pdf.ln(3)
        
        # 3) Tabela de marcações
        self._draw_table_header(pdf)
        for wd in employee.workdays:
            # Verifica se precisa de nova página
            if pdf.get_y() > 265:
                pdf.add_page()
                self._draw_table_header(pdf)
            self._draw_table_row(pdf, wd)
        
        pdf.ln(3)
        
        # 4) Resumo do período
        self._draw_summary(pdf, employee)
        
        # 5) Linhas de assinatura
        self._draw_signatures(pdf, employee)
    
    def _draw_signatures(self, pdf: PontoPDF, employee: Employee):
        """Linhas de assinatura do funcionário e responsável."""
        # Verifica se cabe na página (precisa de ~25mm)
        if pdf.get_y() > 255:
            pdf.add_page()
        
        pdf.ln(12)
        
        y = pdf.get_y()
        line_w = 80
        
        # Assinatura Funcionário (esquerda)
        x1 = 15
        pdf.set_draw_color(0, 0, 0)
        pdf.line(x1, y, x1 + line_w, y)
        pdf._font('', 7)
        pdf.set_xy(x1, y + 1)
        pdf.cell(line_w, 4, employee.display_name, align='C')
        pdf.set_xy(x1, y + 4)
        pdf._font('', 6)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(line_w, 3, 'Assinatura do Funcionário', align='C')
        
        # Assinatura Responsável (direita)
        x2 = 110
        pdf.line(x2, y, x2 + line_w, y)
        pdf._font('', 7)
        pdf.set_text_color(*BLACK)
        pdf.set_xy(x2, y + 1)
        pdf.cell(line_w, 4, pdf.company.name or 'Empresa', align='C')
        pdf.set_xy(x2, y + 4)
        pdf._font('', 6)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(line_w, 3, 'Responsável / RH', align='C')
        
        pdf.set_text_color(*BLACK)
    
    def _draw_info_block(self, pdf: PontoPDF, report: MonthlyReport, employee: Employee):
        """Bloco de dados da empresa e funcionário (estilo ControlID)."""
        y = pdf.get_y()
        ROW = 4.5
        
        pdf._font('', 7)
        
        # Empresa
        pdf.set_xy(10, y)
        pdf._font('B', 7)
        pdf.cell(30, ROW, 'NOME DA EMPRESA:', border=0)
        pdf._font('', 7)
        pdf.cell(70, ROW, pdf.company.name or '-', border=0)
        
        pdf.set_xy(110, y)
        pdf._font('B', 7)
        pdf.cell(20, ROW, 'CNPJ:', border=0)
        pdf._font('', 7)
        pdf.cell(60, ROW, pdf.company.cnpj or '-', border=0)
        pdf.ln(ROW)
        
        # Endereço + Cidade/UF
        pdf.set_x(10)
        pdf._font('B', 7)
        pdf.cell(30, ROW, 'ENDEREÇO:', border=0)
        pdf._font('', 7)
        addr = pdf.company.address or '-'
        if pdf.company.city:
            addr += f" — {pdf.company.city}"
            if pdf.company.state:
                addr += f"/{pdf.company.state}"
        pdf.cell(160, ROW, addr, border=0)
        pdf.ln(ROW)
        
        # Linha separadora
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(1)
        
        # Funcionário — Linha 1 (Nome + PIS)
        y2 = pdf.get_y()
        pdf.set_xy(10, y2)
        pdf._font('B', 7)
        pdf.cell(38, ROW, 'NOME DO FUNCIONÁRIO:', border=0)
        pdf._font('B', 8)
        pdf.cell(72, ROW, employee.display_name, border=0)
        
        pdf.set_xy(120, y2)
        pdf._font('B', 7)
        pdf.cell(10, ROW, 'PIS:', border=0)
        pdf._font('', 7)
        pdf.cell(60, ROW, employee.pis or '-', border=0)
        pdf.ln(ROW + 1)
        
        # Linha separadora
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(2)
    
    def _draw_schedule_box(self, pdf: PontoPDF, schedule: ScheduleConfig):
        """Quadro lateral de horários de trabalho (estilo ControlID)."""
        y = pdf.get_y()
        
        # Título do quadro
        pdf.set_fill_color(*RED)
        pdf.set_text_color(*WHITE)
        pdf._font('B', 7)
        pdf.set_xy(10, y)
        pdf.cell(60, 4, '  HORÁRIO DE TRABALHO', fill=True)
        pdf.set_text_color(*BLACK)
        pdf.ln(4)
        
        # Cabeçalho da mini-tabela
        pdf._font('B', 6)
        pdf.set_fill_color(*LIGHT_GRAY)
        x0 = 10
        w_day = 12
        w_ent = 12
        w_sai = 12
        
        pdf.set_xy(x0, pdf.get_y())
        pdf.cell(w_day, 3.5, '', border=1, align='C', fill=True)
        pdf.cell(w_ent, 3.5, 'ENT.', border=1, align='C', fill=True)
        pdf.cell(w_sai, 3.5, 'SAÍ.', border=1, align='C', fill=True)
        pdf.cell(w_ent, 3.5, 'ENT.', border=1, align='C', fill=True)
        pdf.cell(w_sai, 3.5, 'SAÍ.', border=1, align='C', fill=True)
        pdf.ln()
        
        # Dias da semana
        days = ['SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SÁB', 'DOM']
        pdf._font('', 6)
        
        entry = schedule.entry_time.strftime('%H:%M')
        exit_t = schedule.exit_time.strftime('%H:%M')
        
        # Horários de almoço flexíveis (dois turnos possíveis)
        brk_s_h = schedule.break_start.hour
        brk_e_h = schedule.break_end.hour
        flex_sai = f"{brk_s_h - 2} ou {brk_s_h}h"
        flex_ent = f"{brk_e_h - 2} ou {brk_e_h}h"
        
        sat_entry = schedule.saturday_entry.strftime('%H:%M')
        sat_exit = schedule.saturday_exit.strftime('%H:%M')
        
        for i, day in enumerate(days):
            pdf.set_x(x0)
            pdf._font('B', 6)
            pdf.cell(w_day, 3.5, day, border=1, align='C')
            pdf._font('', 6)
            
            if i <= 4 and i in schedule.workdays:
                # Seg-Sex com almoço flexível
                pdf.cell(w_ent, 3.5, entry, border=1, align='C')
                pdf._font('', 5)
                pdf.cell(w_sai, 3.5, flex_sai, border=1, align='C')
                pdf.cell(w_ent, 3.5, flex_ent, border=1, align='C')
                pdf._font('', 6)
                pdf.cell(w_sai, 3.5, exit_t, border=1, align='C')
            elif i == 5 and 5 in schedule.workdays:
                # Sábado
                pdf.cell(w_ent, 3.5, sat_entry, border=1, align='C')
                pdf.cell(w_sai, 3.5, sat_exit, border=1, align='C')
                pdf.cell(w_ent, 3.5, '', border=1, align='C')
                pdf.cell(w_sai, 3.5, '', border=1, align='C')
            else:
                # Folga
                pdf.cell(w_ent, 3.5, '', border=1, align='C')
                pdf.cell(w_sai, 3.5, '', border=1, align='C')
                pdf.cell(w_ent, 3.5, '', border=1, align='C')
                pdf.cell(w_sai, 3.5, '', border=1, align='C')
            pdf.ln()
    
    def _draw_table_header(self, pdf: PontoPDF):
        """Cabeçalho da tabela de marcações."""
        pdf._font('B', 6.5)
        pdf.set_fill_color(*RED)
        pdf.set_text_color(*WHITE)
        
        cols = [
            ('DIA', 20),
            ('PREVISTO', 24),
            ('ENT. 1', 14),
            ('SAÍ. 1', 14),
            ('ENT. 2', 14),
            ('SAÍ. 2', 14),
            ('TRAB.', 14),
            ('FALTA/ATRASO', 24),
            ('EXTRA', 14),
            ('BANCO', 14),
            ('OBS.', 34),
        ]
        
        for label, w in cols:
            pdf.cell(w, 4.5, label, border=1, align='C', fill=True)
        pdf.ln()
        
        pdf.set_text_color(*BLACK)
    
    def _draw_table_row(self, pdf: PontoPDF, wd: WorkDay):
        """Desenha uma linha da tabela de ponto."""
        pdf._font('', 6.5)
        
        weekday = wd.date.weekday()
        day_names = ['SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SÁB', 'DOM']
        day_str = f"{wd.date.strftime('%d/%m/%y')} - {day_names[weekday]}"
        
        # Background
        fill = False
        if wd.is_absent and wd.is_workday:
            pdf.set_fill_color(255, 230, 230)  # Vermelho claro
            fill = True
        elif not wd.is_workday and not wd.punches:
            pdf.set_fill_color(240, 240, 240)  # Cinza claro (folga)
            fill = True
        elif wd.is_incomplete:
            pdf.set_fill_color(255, 245, 210)  # Laranja claro
            fill = True
        
        ROW_H = 4
        
        # DIA (data + dia da semana)
        pdf.cell(20, ROW_H, day_str, border=1, align='C', fill=fill)
        
        # PREVISTO (horas esperadas)
        if wd.is_workday and wd.expected_hours > 0:
            prev_str = self._format_hours(wd.expected_hours)
        else:
            prev_str = ''
        pdf.cell(24, ROW_H, prev_str, border=1, align='C', fill=fill)
        
        # Marcações (ENT.1, SAÍ.1, ENT.2, SAÍ.2)
        punches = wd.punches
        
        if not wd.is_workday and not punches:
            # Folga
            pdf.set_text_color(120, 120, 120)
            pdf.cell(56, ROW_H, 'Folga', border=1, align='C', fill=fill)
            pdf.set_text_color(*BLACK)
        elif wd.is_absent and wd.is_workday and not punches:
            # Falta
            pdf.set_text_color(200, 0, 0)
            for _ in range(4):
                pdf.cell(14, ROW_H, 'Falta', border=1, align='C', fill=fill)
            pdf.set_text_color(*BLACK)
        else:
            if len(punches) >= 4:
                entries = [
                    punches[0].time.strftime('%H:%M'),
                    punches[1].time.strftime('%H:%M'),
                    punches[2].time.strftime('%H:%M'),
                    punches[3].time.strftime('%H:%M'),
                ]
            elif len(punches) == 2 and punches[0].time.hour >= 11:
                entries = ['', '', punches[0].time.strftime('%H:%M'), punches[1].time.strftime('%H:%M')]
            elif len(punches) == 2:
                entries = [punches[0].time.strftime('%H:%M'), '', '', punches[1].time.strftime('%H:%M')]
            else:
                # Fallback para 1, 3, 5+ marcações
                entries = [
                    punches[i].time.strftime('%H:%M') if i < len(punches) else ''
                    for i in range(4)
                ]
            
            for e in entries:
                pdf.cell(14, ROW_H, e, border=1, align='C', fill=fill)
        
        # TRAB. (horas trabalhadas)
        worked_str = self._format_hours(wd.worked_hours) if wd.worked_hours > 0 else ''
        pdf.cell(14, ROW_H, worked_str, border=1, align='C', fill=fill)
        
        # FALTA/ATRASO
        falta_str = ''
        if wd.is_absent and wd.is_workday:
            falta_str = self._format_hours(wd.expected_hours)
            pdf.set_text_color(200, 0, 0)
        elif wd.is_late:
            falta_str = f"{wd.late_minutes:.0f}min"
            pdf.set_text_color(200, 120, 0)
        pdf.cell(24, ROW_H, falta_str, border=1, align='C', fill=fill)
        pdf.set_text_color(*BLACK)
        
        # EXTRA
        extra_str = ''
        if wd.overtime_hours > 0:
            extra_str = f"+{self._format_hours(wd.overtime_hours)}"
            pdf.set_text_color(0, 128, 0)
        pdf.cell(14, ROW_H, extra_str, border=1, align='C', fill=fill)
        pdf.set_text_color(*BLACK)
        
        # BANCO (saldo do dia: extra - déficit)
        banco_str = ''
        if wd.overtime_hours > 0:
            banco_str = f"+{self._format_hours(wd.overtime_hours)}"
            pdf.set_text_color(0, 128, 0)
        elif wd.deficit_hours > 0:
            banco_str = f"-{self._format_hours(wd.deficit_hours)}"
            pdf.set_text_color(200, 0, 0)
        pdf.cell(14, ROW_H, banco_str, border=1, align='C', fill=fill)
        pdf.set_text_color(*BLACK)
        
        # OBS
        obs = wd.observation or ''
        if wd.is_late and wd.observation:
            obs = f"Atraso {wd.late_minutes:.0f}min | {obs}"
        elif wd.is_late:
            obs = f"Atraso {wd.late_minutes:.0f}min"
        pdf._font('', 5.5)
        pdf.cell(34, ROW_H, obs[:30] if obs else '', border=1, align='L', fill=fill)
        pdf._font('', 6.5)
        
        pdf.ln()
    
    def _draw_summary(self, pdf: PontoPDF, employee: Employee):
        """Resumo do período."""
        # Título
        pdf._font('B', 8)
        pdf.set_fill_color(*RED)
        pdf.set_text_color(*WHITE)
        pdf.cell(0, 5, '  RESUMO DO PERÍODO', ln=True, fill=True)
        pdf.set_text_color(*BLACK)
        
        pdf._font('', 7)
        pdf.set_fill_color(*LIGHT_GRAY)
        
        total_expected = sum(wd.expected_hours for wd in employee.workdays)
        incomplete = sum(1 for wd in employee.workdays if wd.is_incomplete)
        
        # Saldo banco de horas
        bank_balance = employee.total_overtime_hours - employee.total_deficit_hours
        
        rows = [
            ('Total Horas Trabalhadas', self._format_hours(employee.total_worked_hours)),
            ('Total Horas Previstas', self._format_hours(total_expected)),
            ('Horas Extras', f"+{self._format_hours(employee.total_overtime_hours)}" if employee.total_overtime_hours > 0 else '0h00'),
            ('Horas em Déficit', f"-{self._format_hours(employee.total_deficit_hours)}" if employee.total_deficit_hours > 0 else '0h00'),
            ('Banco de Horas (Saldo)', f"{'+' if bank_balance >= 0 else '-'}{self._format_hours(abs(bank_balance))}"),
            ('Dias com Atraso', f"{employee.total_late_days} dias ({employee.total_late_minutes:.0f} min total)"),
            ('Faltas', f"{employee.total_absent_days} dias"),
            ('Marcações Incompletas', f"{incomplete} dias"),
        ]
        
        H = 4.5
        for i, (label, value) in enumerate(rows):
            f = i % 2 == 0
            pdf.cell(95, H, f"  {label}", border=1, fill=f)
            
            # Colorir valores
            if 'Extra' in label and employee.total_overtime_hours > 0:
                pdf.set_text_color(0, 128, 0)
            elif 'Déficit' in label and employee.total_deficit_hours > 0:
                pdf.set_text_color(200, 0, 0)
            elif 'Banco' in label:
                pdf.set_text_color(0, 128, 0) if bank_balance >= 0 else pdf.set_text_color(200, 0, 0)
            elif 'Falta' in label and employee.total_absent_days > 0:
                pdf.set_text_color(200, 0, 0)
            elif 'Incompletas' in label and incomplete > 0:
                pdf.set_text_color(210, 140, 0)
            
            pdf.cell(95, H, f"  {value}", border=1, fill=f, ln=True)
            pdf.set_text_color(*BLACK)
    
    @staticmethod
    def _format_hours(hours: float) -> str:
        """Formata horas decimal em HhMM (ex: 8.5 → 8h30)."""
        h = int(abs(hours))
        m = int((abs(hours) - h) * 60)
        return f"{h}h{m:02d}"
    
    @staticmethod
    def _safe_filename(name: str) -> str:
        """Remove caracteres inválidos para nome de arquivo."""
        import re
        safe = re.sub(r'[^\w\s\-]', '', name)
        return safe.strip().replace(' ', '_')
