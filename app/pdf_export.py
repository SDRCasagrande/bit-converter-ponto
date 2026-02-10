"""
Gerador de relatórios PDF — Folha de Ponto.
Header personalizado com dados da empresa + relatório por colaborador.
"""
import os
from datetime import date, time
from typing import List, Optional
from fpdf import FPDF
from app.models import MonthlyReport, Employee, WorkDay, Company


class PontoPDF(FPDF):
    """PDF customizado para relatório de ponto."""
    
    def __init__(self, company: Company, period: str):
        super().__init__('P', 'mm', 'A4')
        self.company = company
        self.period = period
        self.set_auto_page_break(auto=True, margin=20)
        # Usa fonte padrão que suporta bem caracteres latinos
        self.add_font('DejaVu', '', os.path.join(os.path.dirname(__file__), '..', 'assets', 'DejaVuSans.ttf'), uni=True)
        self.add_font('DejaVu', 'B', os.path.join(os.path.dirname(__file__), '..', 'assets', 'DejaVuSans-Bold.ttf'), uni=True)
    
    def header(self):
        """Cabeçalho com dados da empresa em cada página."""
        # Fundo do header
        self.set_fill_color(25, 25, 112)  # Navy blue
        self.rect(10, 10, 190, 24, 'F')
        
        # Logo (se existir)
        x_text = 15
        if self.company.logo_path and os.path.exists(self.company.logo_path):
            try:
                self.image(self.company.logo_path, 12, 11, 22, 22)
                x_text = 38
            except Exception:
                pass
        
        # Nome da empresa
        self.set_xy(x_text, 12)
        self.set_text_color(255, 255, 255)
        self.set_font('DejaVu', 'B', 12)
        self.cell(0, 6, self.company.name or 'Empresa', ln=True)
        
        # CNPJ e endereço
        self.set_x(x_text)
        self.set_font('DejaVu', '', 7)
        info_parts = []
        if self.company.cnpj:
            info_parts.append(f"CNPJ: {self.company.cnpj}")
        if self.company.address:
            info_parts.append(self.company.address)
        if self.company.city:
            city_state = self.company.city
            if self.company.state:
                city_state += f"/{self.company.state}"
            info_parts.append(city_state)
        self.cell(0, 4, " | ".join(info_parts) if info_parts else '', ln=True)
        
        # Período / título do relatório
        self.set_x(x_text)
        self.set_font('DejaVu', 'B', 8)
        self.cell(0, 5, f"Relatório de Ponto — {self.period}", ln=True)
        
        self.set_text_color(0, 0, 0)
        self.ln(4)
    
    def footer(self):
        """Rodapé com número da página, data e branding."""
        self.set_y(-15)
        self.set_font('DejaVu', '', 7)
        self.set_text_color(128, 128, 128)
        self.cell(95, 10, 'Powered By BitKaiser Solution - Xinguara - PA', align='L')
        self.cell(95, 10, f'Página {self.page_no()}/{{nb}}', align='R')


class PDFExporter:
    """Exportador de relatórios em PDF."""
    
    def __init__(self):
        self._ensure_fonts()
    
    def _ensure_fonts(self):
        """Verifica se as fontes DejaVu existem, senão cria fallback."""
        assets_dir = os.path.join(os.path.dirname(__file__), '..', 'assets')
        os.makedirs(assets_dir, exist_ok=True)
        
        # As fontes serão baixadas no setup ou embarcadas
        self.fonts_available = (
            os.path.exists(os.path.join(assets_dir, 'DejaVuSans.ttf')) and
            os.path.exists(os.path.join(assets_dir, 'DejaVuSans-Bold.ttf'))
        )
    
    def export_individual(
        self, 
        report: MonthlyReport, 
        output_dir: str
    ) -> List[str]:
        """Exporta um PDF para cada colaborador. Retorna lista de caminhos."""
        os.makedirs(output_dir, exist_ok=True)
        generated = []
        
        for employee in report.employees:
            filename = self._safe_filename(employee.display_name)
            filepath = os.path.join(
                output_dir, 
                f"Ponto_{filename}_{report.period_label.replace('/', '_')}.pdf"
            )
            
            self._generate_employee_pdf(
                report.company, 
                report.period_label, 
                employee, 
                filepath
            )
            generated.append(filepath)
        
        return generated
    
    def export_consolidated(
        self, 
        report: MonthlyReport, 
        output_path: str
    ) -> str:
        """Exporta um PDF consolidado com todos os colaboradores."""
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        
        if self.fonts_available:
            pdf = PontoPDF(report.company, report.period_label)
        else:
            pdf = FPDF('P', 'mm', 'A4')
            pdf.set_auto_page_break(auto=True, margin=20)
        
        pdf.alias_nb_pages()
        
        for i, employee in enumerate(report.employees):
            self._add_employee_pages(pdf, report.company, report.period_label, employee)
        
        pdf.output(output_path)
        return output_path
    
    def _generate_employee_pdf(
        self, 
        company: Company, 
        period: str, 
        employee: Employee, 
        filepath: str
    ):
        """Gera PDF individual para um colaborador."""
        if self.fonts_available:
            pdf = PontoPDF(company, period)
        else:
            pdf = FPDF('P', 'mm', 'A4')
            pdf.set_auto_page_break(auto=True, margin=20)
        
        pdf.alias_nb_pages()
        self._add_employee_pages(pdf, company, period, employee)
        pdf.output(filepath)
    
    def _add_employee_pages(
        self, 
        pdf: FPDF, 
        company: Company, 
        period: str, 
        employee: Employee
    ):
        """Adiciona as páginas de um colaborador ao PDF."""
        pdf.add_page()
        use_dejavu = self.fonts_available and isinstance(pdf, PontoPDF)
        
        # --- Dados do Colaborador ---
        if use_dejavu:
            pdf.set_font('DejaVu', 'B', 11)
        else:
            pdf.set_font('Helvetica', 'B', 11)
        
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(0, 7, f"  {employee.display_name}", ln=True, fill=True)
        
        if use_dejavu:
            pdf.set_font('DejaVu', '', 8)
        else:
            pdf.set_font('Helvetica', '', 8)
        
        info_line = f"  PIS: {employee.pis}"
        if employee.employee_id:
            info_line += f"  |  ID: {employee.employee_id}"
        pdf.cell(0, 5, info_line, ln=True)
        pdf.ln(2)
        
        # --- Tabela de Marcações ---
        self._draw_table_header(pdf, use_dejavu)
        
        for workday in employee.workdays:
            self._draw_table_row(pdf, workday, use_dejavu)
        
        pdf.ln(3)
        
        # --- Resumo do Mês ---
        self._draw_summary(pdf, employee, use_dejavu)
    
    def _draw_table_header(self, pdf: FPDF, use_dejavu: bool):
        """Desenha o cabeçalho da tabela de ponto."""
        if use_dejavu:
            pdf.set_font('DejaVu', 'B', 8)
        else:
            pdf.set_font('Helvetica', 'B', 8)
        
        pdf.set_fill_color(25, 25, 112)
        pdf.set_text_color(255, 255, 255)
        
        cols = [
            ('Data', 18),
            ('Dia', 12),
            ('Ent. 1', 16),
            ('Sai. 1', 16),
            ('Ent. 2', 16),
            ('Sai. 2', 16),
            ('Trab.', 16),
            ('Prev.', 16),
            ('Extra', 16),
            ('Obs.', 48),
        ]
        
        for label, width in cols:
            pdf.cell(width, 5, label, border=1, align='C', fill=True)
        pdf.ln()
        
        pdf.set_text_color(0, 0, 0)
    
    def _draw_table_row(self, pdf: FPDF, wd: WorkDay, use_dejavu: bool):
        """Desenha uma linha da tabela."""
        if use_dejavu:
            pdf.set_font('DejaVu', '', 7)
        else:
            pdf.set_font('Helvetica', '', 7)
        
        # Cores alternadas
        weekday = wd.date.weekday()
        day_names = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
        day_name = day_names[weekday] if weekday < 7 else ''
        
        # Background
        if wd.is_incomplete:
            pdf.set_fill_color(255, 235, 180)  # Laranja claro (marcação incompleta)
            fill = True
        elif wd.is_absent and wd.is_workday:
            pdf.set_fill_color(255, 220, 220)  # Vermelho claro (falta)
            fill = True
        elif weekday >= 5:
            pdf.set_fill_color(230, 230, 250)  # Lavanda (fim de semana)
            fill = True
        elif wd.overtime_hours > 0:
            pdf.set_fill_color(220, 255, 220)  # Verde claro (extra)
            fill = True
        else:
            fill = False
        
        ROW_H = 4.5
        
        # Data
        date_str = wd.date.strftime('%d/%m')
        pdf.cell(18, ROW_H, date_str, border=1, align='C', fill=fill)
        pdf.cell(12, ROW_H, day_name, border=1, align='C', fill=fill)
        
        # Marcações
        punches = wd.punches
        entries = [
            punches[0].time.strftime('%H:%M') if len(punches) > 0 else '',
            punches[1].time.strftime('%H:%M') if len(punches) > 1 else '',
            punches[2].time.strftime('%H:%M') if len(punches) > 2 else '',
            punches[3].time.strftime('%H:%M') if len(punches) > 3 else '',
        ]
        
        for entry in entries:
            pdf.cell(16, ROW_H, entry, border=1, align='C', fill=fill)
        
        # Horas trabalhadas
        worked_str = self._format_hours(wd.worked_hours) if wd.worked_hours > 0 else ''
        pdf.cell(16, ROW_H, worked_str, border=1, align='C', fill=fill)
        
        # Horas previstas
        expected_str = self._format_hours(wd.expected_hours) if wd.expected_hours > 0 else ''
        pdf.cell(16, ROW_H, expected_str, border=1, align='C', fill=fill)
        
        # Horas extras
        if wd.overtime_hours > 0:
            pdf.set_text_color(0, 128, 0)
            extra_str = f"+{self._format_hours(wd.overtime_hours)}"
        elif wd.deficit_hours > 0:
            pdf.set_text_color(200, 0, 0)
            extra_str = f"-{self._format_hours(wd.deficit_hours)}"
        else:
            extra_str = ''
        pdf.cell(16, ROW_H, extra_str, border=1, align='C', fill=fill)
        pdf.set_text_color(0, 0, 0)
        
        # Observação
        obs = wd.observation
        if wd.is_late:
            obs = f"Atraso {wd.late_minutes:.0f}min" + (f" | {obs}" if obs else '')
        pdf.cell(48, ROW_H, obs[:30] if obs else '', border=1, align='L', fill=fill)
        
        pdf.ln()
    
    def _draw_summary(self, pdf: FPDF, employee: Employee, use_dejavu: bool):
        """Desenha o resumo mensal do colaborador."""
        if use_dejavu:
            pdf.set_font('DejaVu', 'B', 9)
        else:
            pdf.set_font('Helvetica', 'B', 9)
        
        pdf.set_fill_color(25, 25, 112)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 6, '  RESUMO DO MÊS', ln=True, fill=True)
        
        pdf.set_text_color(0, 0, 0)
        if use_dejavu:
            pdf.set_font('DejaVu', '', 8)
        else:
            pdf.set_font('Helvetica', '', 8)
        
        pdf.set_fill_color(245, 245, 245)
        
        total_expected = sum(wd.expected_hours for wd in employee.workdays)
        
        incomplete_days = sum(1 for wd in employee.workdays if wd.is_incomplete)
        
        rows = [
            ('Total Horas Trabalhadas', self._format_hours(employee.total_worked_hours)),
            ('Total Horas Previstas', self._format_hours(total_expected)),
            ('Horas Extras', f"+{self._format_hours(employee.total_overtime_hours)}" if employee.total_overtime_hours > 0 else '0h00'),
            ('Horas em Déficit', f"-{self._format_hours(employee.total_deficit_hours)}" if employee.total_deficit_hours > 0 else '0h00'),
            ('Dias com Atraso', str(employee.total_late_days)),
            ('Total Min Atraso', f"{employee.total_late_minutes:.0f} min"),
            ('Faltas', str(employee.total_absent_days)),
            ('Marc. Incompletas', str(incomplete_days)),
        ]
        
        SUM_H = 5
        for i, (label, value) in enumerate(rows):
            fill = i % 2 == 0
            pdf.cell(95, SUM_H, f"  {label}", border=1, fill=fill)
            
            # Cor para extras/déficit/problemas
            if 'Extra' in label and employee.total_overtime_hours > 0:
                pdf.set_text_color(0, 128, 0)
            elif 'Déficit' in label and employee.total_deficit_hours > 0:
                pdf.set_text_color(200, 0, 0)
            elif 'Falta' in label and employee.total_absent_days > 0:
                pdf.set_text_color(200, 0, 0)
            elif 'Incompletas' in label and incomplete_days > 0:
                pdf.set_text_color(210, 140, 0)
            
            pdf.cell(95, SUM_H, f"  {value}", border=1, fill=fill, ln=True)
            pdf.set_text_color(0, 0, 0)
    
    @staticmethod
    def _format_hours(hours: float) -> str:
        """Formata horas decimal em HHhMM (ex: 8.5 → 8h30)."""
        h = int(hours)
        m = int((hours - h) * 60)
        return f"{h}h{m:02d}"
    
    @staticmethod
    def _safe_filename(name: str) -> str:
        """Remove caracteres inválidos para nome de arquivo."""
        import re
        safe = re.sub(r'[^\w\s\-]', '', name)
        return safe.strip().replace(' ', '_')
