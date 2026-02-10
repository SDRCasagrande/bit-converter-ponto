"""
Janela principal do AFD Parser.
Interface moderna com CustomTkinter para importar AFD,
selecionar período, visualizar colaboradores e exportar PDF.
"""
import os
import sys
import json
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
from typing import Optional, Dict, List

from app.parser import AFDParser
from app.calculator import WorkCalculator
from app.pdf_export import PDFExporter
from app.models import (
    Employee, Company, ScheduleConfig, ScheduleType, MonthlyReport
)
from app.updater import (
    APP_VERSION, check_for_update, download_update,
    apply_update, format_size, UpdateInfo
)


# Mapeamento de escalas para exibição
SCHEDULE_LABELS = {
    ScheduleType.STANDARD: "Padrão CLT (8h seg-sex + 4h sáb = 44h/sem)",
    ScheduleType.SCALE_5X2: "5x2 (8h48/dia seg-sex = 44h/sem)",
    ScheduleType.SCALE_6X1: "6x1 (7h20/dia média, 6 dias = 44h/sem)",
    ScheduleType.SCALE_12X36: "12x36 (12h trabalho / 36h descanso)",
    ScheduleType.PARTIAL_30: "Parcial 30h (até 30h/sem, sem extra)",
    ScheduleType.PARTIAL_26: "Parcial 26h (até 26h/sem, até 6h extra)",
    ScheduleType.CUSTOM: "Personalizada",
}

SCHEDULE_FROM_LABEL = {v: k for k, v in SCHEDULE_LABELS.items()}

CONFIG_FILE = os.path.join(os.path.dirname(__file__), '..', 'config.json')


class MainWindow(ctk.CTk):
    """Janela principal do aplicativo."""
    
    def __init__(self):
        super().__init__()
        
        # Configuração da janela
        self.title("Bit-Converter — Conversor de AFD Relógio de Ponto para PDF | BitKaiser Solution")
        self.geometry("960x680")
        self.minsize(800, 600)
        
        # Tema
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # State
        self.parser: Optional[AFDParser] = None
        self.report: Optional[MonthlyReport] = None
        self.company = Company()
        self.schedule = ScheduleConfig()
        self.afd_filepath: str = ""
        self.selected_month: int = 0
        self.selected_year: int = 0
        
        # Carrega config salva
        self._load_config()
        
        # Update state
        self._update_info: Optional[UpdateInfo] = None
        
        # Build UI
        self._build_ui()
        
        # Verifica atualização em background (adiado 2s para evitar conflito com CTk)
        self.after(2000, lambda: self._check_update_background())
    
    def _build_ui(self):
        """Constrói toda a interface."""
        # === Barra Superior ===
        self.top_bar = ctk.CTkFrame(self, height=50, fg_color=("#1a1a2e", "#1a1a2e"))
        self.top_bar.pack(fill='x', padx=0, pady=0)
        self.top_bar.pack_propagate(False)
        
        ctk.CTkLabel(
            self.top_bar, text="Bit-Converter — Conversor de AFD para PDF",
            font=("Segoe UI", 16, "bold"), text_color="white"
        ).pack(side='left', padx=20, pady=10)
        
        # Versão
        self.lbl_version = ctk.CTkLabel(
            self.top_bar, text=f"v{APP_VERSION}",
            font=("Segoe UI", 10), text_color="#888"
        )
        self.lbl_version.pack(side='left', padx=(5, 0), pady=10)
        
        self.btn_help = ctk.CTkButton(
            self.top_bar, text="? Ajuda", width=80,
            command=self._open_help,
            fg_color="#3d3d5c", hover_color="#4d4d6c"
        )
        self.btn_help.pack(side='right', padx=(0, 5), pady=10)
        
        # Botão de atualização (inicialmente oculto)
        self.btn_update = ctk.CTkButton(
            self.top_bar, text="Atualizar", width=110,
            command=lambda: self._open_update_dialog(),
            fg_color="#e67e22", hover_color="#d35400"
        )
        # Não faz pack aqui — só aparece quando houver update
        
        self.btn_settings = ctk.CTkButton(
            self.top_bar, text="Configuracoes", width=130,
            command=self._open_settings,
            fg_color="#3d3d5c", hover_color="#4d4d6c"
        )
        self.btn_settings.pack(side='right', padx=(0, 5), pady=10)
        
        # === Container Principal (2 colunas) ===
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill='both', expand=True, padx=10, pady=10)
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(1, weight=2)
        self.main_container.grid_rowconfigure(0, weight=1)
        
        # --- Painel Esquerdo: Controles ---
        self.left_panel = ctk.CTkFrame(self.main_container, width=300)
        self.left_panel.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        self.left_panel.grid_propagate(False)
        
        self._build_left_panel()
        
        # --- Painel Direito: Resultados ---
        self.right_panel = ctk.CTkFrame(self.main_container)
        self.right_panel.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        
        self._build_right_panel()
        
        # === Barra de Status ===
        self.status_bar = ctk.CTkFrame(self, height=30, fg_color=("#1a1a2e", "#1a1a2e"))
        self.status_bar.pack(fill='x', padx=0, pady=0)
        self.status_bar.pack_propagate(False)
        
        self.status_label = ctk.CTkLabel(
            self.status_bar, text="Pronto. Importe um arquivo AFD para começar.",
            font=("Segoe UI", 11), text_color="#aaa"
        )
        self.status_label.pack(side='left', padx=15, pady=5)
    
    def _build_left_panel(self):
        """Painel esquerdo com controles de importação e seleção."""
        # Importação
        section_import = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        section_import.pack(fill='x', padx=10, pady=(10, 5))
        
        ctk.CTkLabel(
            section_import, text="ARQUIVO AFD",
            font=("Segoe UI", 12, "bold"), anchor='w'
        ).pack(fill='x', pady=(0, 5))
        
        self.btn_import = ctk.CTkButton(
            section_import, text="Selecionar Arquivo AFD...",
            command=self._import_file, height=36
        )
        self.btn_import.pack(fill='x')
        
        self.btn_from_clock = ctk.CTkButton(
            section_import, text="Puxar do Relogio (ControlID)",
            command=self._open_clock_dialog, height=34,
            fg_color="#e07c24", hover_color="#c96a1a"
        )
        self.btn_from_clock.pack(fill='x', pady=(5, 0))
        
        self.lbl_filename = ctk.CTkLabel(
            section_import, text="Nenhum arquivo selecionado",
            font=("Segoe UI", 10), text_color="#888", wraplength=260
        )
        self.lbl_filename.pack(fill='x', pady=5)
        
        # Info do arquivo
        self.info_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.info_frame.pack(fill='x', padx=10, pady=5)
        
        self.lbl_company = ctk.CTkLabel(
            self.info_frame, text="",
            font=("Segoe UI", 10), anchor='w', wraplength=260
        )
        self.lbl_company.pack(fill='x')
        
        self.lbl_stats = ctk.CTkLabel(
            self.info_frame, text="",
            font=("Segoe UI", 10), anchor='w', text_color="#aaa"
        )
        self.lbl_stats.pack(fill='x')
        
        # Seleção de mês
        section_month = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        section_month.pack(fill='x', padx=10, pady=10)
        
        ctk.CTkLabel(
            section_month, text="📅 PERÍODO",
            font=("Segoe UI", 12, "bold"), anchor='w'
        ).pack(fill='x', pady=(0, 5))
        
        self.month_var = ctk.StringVar(value="Selecione o mês...")
        self.month_dropdown = ctk.CTkOptionMenu(
            section_month, variable=self.month_var,
            values=["Importe um AFD primeiro"],
            command=self._on_month_selected
        )
        self.month_dropdown.pack(fill='x')
        
        # Escala
        section_schedule = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        section_schedule.pack(fill='x', padx=10, pady=10)
        
        ctk.CTkLabel(
            section_schedule, text="⏰ ESCALA DE TRABALHO",
            font=("Segoe UI", 12, "bold"), anchor='w'
        ).pack(fill='x', pady=(0, 5))
        
        self.schedule_var = ctk.StringVar(
            value=SCHEDULE_LABELS.get(self.schedule.schedule_type, "5x2")
        )
        self.schedule_dropdown = ctk.CTkOptionMenu(
            section_schedule, variable=self.schedule_var,
            values=list(SCHEDULE_LABELS.values()),
            command=self._on_schedule_changed
        )
        self.schedule_dropdown.pack(fill='x')
        
        # Botão processar
        self.btn_process = ctk.CTkButton(
            self.left_panel, text="▶ Processar Ponto",
            command=self._process, height=40,
            state='disabled', font=("Segoe UI", 13, "bold"),
            fg_color="#2d6a4f", hover_color="#40916c"
        )
        self.btn_process.pack(fill='x', padx=10, pady=10)
        
        # Botões de exportação
        export_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        export_frame.pack(fill='x', padx=10, pady=5)
        
        self.btn_export_individual = ctk.CTkButton(
            export_frame, text="📄 Exportar Individual",
            command=self._export_individual, height=34,
            state='disabled', fg_color="#7b2cbf", hover_color="#9d4edd"
        )
        self.btn_export_individual.pack(fill='x', pady=(0, 5))
        
        self.btn_export_consolidated = ctk.CTkButton(
            export_frame, text="📑 Exportar Consolidado",
            command=self._export_consolidated, height=34,
            state='disabled', fg_color="#7b2cbf", hover_color="#9d4edd"
        )
        self.btn_export_consolidated.pack(fill='x')
    
    def _build_right_panel(self):
        """Painel direito com lista de colaboradores e preview."""
        ctk.CTkLabel(
            self.right_panel, text="👥 COLABORADORES",
            font=("Segoe UI", 12, "bold"), anchor='w'
        ).pack(fill='x', padx=10, pady=(10, 5))
        
        # Scrollable list
        self.employees_scroll = ctk.CTkScrollableFrame(
            self.right_panel, fg_color="transparent"
        )
        self.employees_scroll.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.lbl_no_data = ctk.CTkLabel(
            self.employees_scroll,
            text="Importe um arquivo AFD e processe\npara ver os colaboradores aqui.",
            font=("Segoe UI", 13), text_color="#666", justify='center'
        )
        self.lbl_no_data.pack(expand=True, pady=50)
    
    # ========= AÇÕES =========
    
    def _import_file(self):
        """Abre diálogo para selecionar arquivo AFD."""
        filepath = filedialog.askopenfilename(
            title="Selecione o arquivo AFD",
            filetypes=[
                ("Arquivo AFD", "*.txt *.afd *.AFD"),
                ("Todos os arquivos", "*.*")
            ]
        )
        
        if not filepath:
            return
        
        self.afd_filepath = filepath
        self.lbl_filename.configure(text=os.path.basename(filepath))
        self.status_label.configure(text="Lendo arquivo AFD...")
        self.update()
        
        # Parse
        self.parser = AFDParser()
        employees, company = self.parser.parse_file(filepath)
        
        # Atualiza dados da empresa (mantém config manual se houver)
        if company.name and not self.company.name:
            self.company.name = company.name
        if company.cnpj and not self.company.cnpj:
            self.company.cnpj = company.cnpj
        
        # Atualiza info
        summary = self.parser.get_summary()
        self.lbl_company.configure(
            text=f"🏢 {summary['company_name'] or 'Empresa não identificada'}\n"
                 f"📋 CNPJ: {summary['company_cnpj'] or 'N/A'}"
        )
        self.lbl_stats.configure(
            text=f"📊 {summary['total_punches']} marcações | "
                 f"{summary['total_employees']} colaboradores | "
                 f"Formato: {summary['format'].upper()}"
        )
        
        # Atualiza dropdown de meses
        months = summary['months_available']
        month_labels = []
        month_names = [
            '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
            'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
        ]
        
        for m, y in months:
            month_labels.append(f"{month_names[m]} / {y}")
        
        if month_labels:
            self.month_dropdown.configure(values=month_labels)
            self.month_var.set(month_labels[-1])  # Último mês disponível
            # Parse o mês selecionado
            last_month, last_year = months[-1]
            self.selected_month = last_month
            self.selected_year = last_year
            self.btn_process.configure(state='normal')
        
        if summary['errors'] > 0:
            self.status_label.configure(
                text=f"Arquivo lido com {summary['errors']} avisos. Processando..."
            )
        else:
            self.status_label.configure(
                text=f"Arquivo lido com sucesso! Processando..."
            )
        self.update()
        
        # Auto-processa o ultimo mes disponivel
        if self.selected_month and self.parser:
            self._process()
    
    def _on_month_selected(self, value: str):
        """Callback quando o mês é selecionado."""
        month_names = [
            '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
            'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
        ]
        
        try:
            parts = value.split(' / ')
            month_name = parts[0].strip()
            year = int(parts[1].strip())
            month = month_names.index(month_name)
            self.selected_month = month
            self.selected_year = year
            
            # Auto-processa ao trocar de mes
            if self.parser:
                self._process()
        except (ValueError, IndexError):
            pass
    
    def _on_schedule_changed(self, value: str):
        """Callback quando a escala é alterada."""
        stype = SCHEDULE_FROM_LABEL.get(value, ScheduleType.SCALE_5X2)
        self.schedule.schedule_type = stype
        
        # Ajusta parâmetros conforme escala
        if stype == ScheduleType.STANDARD:
            self.schedule.workdays = [0, 1, 2, 3, 4, 5]
            self.schedule.daily_hours = 8.0
            self.schedule.saturday_hours = 4.0
        elif stype == ScheduleType.SCALE_5X2:
            self.schedule.workdays = [0, 1, 2, 3, 4]
            self.schedule.daily_hours = 8.8
        elif stype == ScheduleType.SCALE_6X1:
            self.schedule.workdays = [0, 1, 2, 3, 4, 5]
            self.schedule.daily_hours = 8.0
            self.schedule.saturday_hours = 4.0
        elif stype == ScheduleType.SCALE_12X36:
            self.schedule.daily_hours = 12.0
        elif stype == ScheduleType.PARTIAL_30:
            self.schedule.workdays = [0, 1, 2, 3, 4]
            self.schedule.daily_hours = 6.0
            self.schedule.weekly_hours = 30.0
        elif stype == ScheduleType.PARTIAL_26:
            self.schedule.workdays = [0, 1, 2, 3, 4]
            self.schedule.daily_hours = 5.2
            self.schedule.weekly_hours = 26.0
        
        self._save_config()
    
    def _process(self):
        """Processa o arquivo AFD com a escala selecionada."""
        if not self.parser or not self.selected_month:
            messagebox.showwarning("Aviso", "Selecione um arquivo AFD e mês primeiro.")
            return
        
        self.status_label.configure(text="⏳ Processando marcações...")
        self.update()
        
        calculator = WorkCalculator(default_schedule=self.schedule)
        self.report = calculator.generate_report(
            employees=self.parser.employees,
            punches=self.parser.punches,
            company=self.company,
            month=self.selected_month,
            year=self.selected_year
        )
        
        # Atualiza lista de colaboradores
        self._update_employee_list()
        
        # Habilita exportação
        self.btn_export_individual.configure(state='normal')
        self.btn_export_consolidated.configure(state='normal')
        
        total_extra = sum(e.total_overtime_hours for e in self.report.employees)
        total_faltas = sum(e.total_absent_days for e in self.report.employees)
        
        self.status_label.configure(
            text=f"✅ Processado! {len(self.report.employees)} colaboradores | "
                 f"Extras: {total_extra:.1f}h | Faltas: {total_faltas} dias"
        )
    
    def _update_employee_list(self):
        """Atualiza a lista visual de colaboradores no painel direito."""
        # Limpa lista atual
        for widget in self.employees_scroll.winfo_children():
            widget.destroy()
        
        if not self.report or not self.report.employees:
            ctk.CTkLabel(
                self.employees_scroll,
                text="Nenhum colaborador encontrado.",
                font=("Segoe UI", 13), text_color="#666"
            ).pack(expand=True, pady=50)
            return
        
        for emp in self.report.employees:
            card = ctk.CTkFrame(self.employees_scroll, height=80)
            card.pack(fill='x', pady=3)
            card.pack_propagate(False)
            
            # Nome e PIS
            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(fill='both', expand=True, padx=10, pady=5)
            
            ctk.CTkLabel(
                info_frame, text=f"👤 {emp.display_name}",
                font=("Segoe UI", 13, "bold"), anchor='w'
            ).pack(fill='x')
            
            ctk.CTkLabel(
                info_frame, text=f"PIS: {emp.pis}",
                font=("Segoe UI", 10), text_color="#aaa", anchor='w'
            ).pack(fill='x')
            
            # Stats
            stats_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
            stats_frame.pack(fill='x')
            
            total_expected = sum(wd.expected_hours for wd in emp.workdays)
            
            stats_text = (
                f"Trabalhadas: {emp.total_worked_hours:.1f}h  |  "
                f"Previstas: {total_expected:.1f}h  |  "
                f"Extras: +{emp.total_overtime_hours:.1f}h  |  "
                f"Faltas: {emp.total_absent_days}"
            )
            
            # Cor baseada no status
            if emp.total_absent_days > 3:
                stats_color = "#e63946"
            elif emp.total_overtime_hours > 10:
                stats_color = "#f4a261"
            else:
                stats_color = "#2a9d8f"
            
            ctk.CTkLabel(
                stats_frame, text=stats_text,
                font=("Segoe UI", 10), text_color=stats_color, anchor='w'
            ).pack(fill='x')
    
    def _export_individual(self):
        """Exporta PDFs individuais."""
        if not self.report:
            return
        
        output_dir = filedialog.askdirectory(title="Selecione a pasta de destino")
        if not output_dir:
            return
        
        self.status_label.configure(text="⏳ Gerando PDFs individuais...")
        self.update()
        
        try:
            exporter = PDFExporter()
            files = exporter.export_individual(self.report, output_dir)
            
            self.status_label.configure(
                text=f"✅ {len(files)} PDFs gerados em {output_dir}"
            )
            
            # Abre a pasta
            os.startfile(output_dir)
            
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao gerar PDFs:\n{str(e)}")
            self.status_label.configure(text=f"❌ Erro na exportação: {str(e)}")
    
    def _export_consolidated(self):
        """Exporta PDF consolidado."""
        if not self.report:
            return
        
        filepath = filedialog.asksaveasfilename(
            title="Salvar PDF Consolidado",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=f"Ponto_Consolidado_{self.report.period_label.replace('/', '_')}.pdf"
        )
        
        if not filepath:
            return
        
        self.status_label.configure(text="⏳ Gerando PDF consolidado...")
        self.update()
        
        try:
            exporter = PDFExporter()
            exporter.export_consolidated(self.report, filepath)
            
            self.status_label.configure(text=f"✅ PDF consolidado salvo: {filepath}")
            
            # Abre o PDF
            os.startfile(filepath)
            
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao gerar PDF:\n{str(e)}")
            self.status_label.configure(text=f"❌ Erro na exportação: {str(e)}")
    
    def _open_clock_dialog(self):
        """Abre diálogo para puxar AFD do relógio ControlID."""
        dialog = ClockDialog(self)
        dialog.grab_set()
        self.wait_window(dialog)
        
        # Se o diálogo retornou um arquivo AFD, importa automaticamente
        if hasattr(dialog, 'afd_filepath') and dialog.afd_filepath:
            self.afd_filepath = dialog.afd_filepath
            self.lbl_filename.configure(text=f"(Relogio) {os.path.basename(dialog.afd_filepath)}")
            self.status_label.configure(text="AFD recebido do relogio! Processando...")
            self.update()
            
            # Parse o arquivo
            self.parser = AFDParser()
            employees, company = self.parser.parse_file(dialog.afd_filepath)
            
            if company.name and not self.company.name:
                self.company.name = company.name
            if company.cnpj and not self.company.cnpj:
                self.company.cnpj = company.cnpj
            
            summary = self.parser.get_summary()
            self.lbl_company.configure(
                text=f"{summary['company_name'] or 'Empresa nao identificada'}\n"
                     f"CNPJ: {summary['company_cnpj'] or 'N/A'}"
            )
            self.lbl_stats.configure(
                text=f"{summary['total_punches']} marcacoes | "
                     f"{summary['total_employees']} colaboradores | "
                     f"Formato: {summary['format'].upper()}"
            )
            
            months = summary['months_available']
            month_names = [
                '', 'Janeiro', 'Fevereiro', 'Marco', 'Abril', 'Maio', 'Junho',
                'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
            ]
            month_labels = [f"{month_names[m]} / {y}" for m, y in months]
            
            if month_labels:
                self.month_dropdown.configure(values=month_labels)
                self.month_var.set(month_labels[-1])
                last_month, last_year = months[-1]
                self.selected_month = last_month
                self.selected_year = last_year
                self.btn_process.configure(state='normal')
            
            # Auto-processa
            if self.selected_month and self.parser:
                self._process()
    
    def _open_settings(self):
        """Abre a janela de configurações."""
        settings = SettingsWindow(self, self.company, self.schedule)
        settings.grab_set()
        self.wait_window(settings)
        
        # Atualiza dados da empresa após fechar
        self.company = settings.company
        self.schedule = settings.schedule
        self._save_config()
    
    def _open_help(self):
        """Abre a janela de ajuda/FAQ."""
        help_win = HelpDialog(self)
        help_win.grab_set()
    
    # ========= CONFIG PERSISTÊNCIA =========
    
    def _save_config(self):
        """Salva configurações em JSON local."""
        try:
            config = {
                'company': {
                    'name': self.company.name,
                    'cnpj': self.company.cnpj,
                    'address': self.company.address,
                    'city': self.company.city,
                    'state': self.company.state,
                    'phone': self.company.phone,
                    'logo_path': self.company.logo_path,
                },
                'schedule': {
                    'type': self.schedule.schedule_type.value,
                    'entry_time': self.schedule.entry_time.strftime('%H:%M'),
                    'exit_time': self.schedule.exit_time.strftime('%H:%M'),
                    'break_start': self.schedule.break_start.strftime('%H:%M'),
                    'break_end': self.schedule.break_end.strftime('%H:%M'),
                    'break_duration': self.schedule.break_duration_minutes,
                    'tolerance': self.schedule.tolerance_minutes,
                    'weekly_hours': self.schedule.weekly_hours,
                    'daily_hours': self.schedule.daily_hours,
                    'saturday_hours': self.schedule.saturday_hours,
                    'workdays': self.schedule.workdays,
                }
            }
            
            config_path = os.path.abspath(CONFIG_FILE)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    
    def _load_config(self):
        """Carrega configurações do JSON local."""
        try:
            config_path = os.path.abspath(CONFIG_FILE)
            if not os.path.exists(config_path):
                return
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Company
            c = config.get('company', {})
            self.company.name = c.get('name', '')
            self.company.cnpj = c.get('cnpj', '')
            self.company.address = c.get('address', '')
            self.company.city = c.get('city', '')
            self.company.state = c.get('state', '')
            self.company.phone = c.get('phone', '')
            self.company.logo_path = c.get('logo_path', '')
            
            # Schedule
            s = config.get('schedule', {})
            stype = s.get('type', '5x2')
            for st in ScheduleType:
                if st.value == stype:
                    self.schedule.schedule_type = st
                    break
            
            if 'entry_time' in s:
                h, m = s['entry_time'].split(':')
                from datetime import time
                self.schedule.entry_time = time(int(h), int(m))
            if 'exit_time' in s:
                h, m = s['exit_time'].split(':')
                from datetime import time
                self.schedule.exit_time = time(int(h), int(m))
            
            self.schedule.tolerance_minutes = s.get('tolerance', 10)
            self.schedule.daily_hours = s.get('daily_hours', 8.8)
            self.schedule.weekly_hours = s.get('weekly_hours', 44.0)
            self.schedule.saturday_hours = s.get('saturday_hours', 4.0)
            self.schedule.workdays = s.get('workdays', [0, 1, 2, 3, 4])
            
        except Exception:
            pass


class SettingsWindow(ctk.CTkToplevel):
    """Janela de configurações da empresa e escala."""
    
    # Horas/dia padrão por escala
    SCHEDULE_DEFAULTS = {
        ScheduleType.STANDARD: {"daily": 8.0, "sat": 4.0, "days": [0,1,2,3,4,5], "label": "8h seg-sex + 4h sáb = 44h/sem"},
        ScheduleType.SCALE_5X2: {"daily": 8.8, "sat": 0, "days": [0,1,2,3,4], "label": "8h48/dia seg-sex = 44h/sem"},
        ScheduleType.SCALE_6X1: {"daily": 7.33, "sat": 7.33, "days": [0,1,2,3,4,5], "label": "7h20/dia média, 6 dias = 44h/sem"},
        ScheduleType.SCALE_12X36: {"daily": 12.0, "sat": 0, "days": [0,1,2,3,4,5,6], "label": "12h on / 36h off"},
        ScheduleType.PARTIAL_30: {"daily": 6.0, "sat": 0, "days": [0,1,2,3,4], "label": "6h/dia = 30h/sem"},
        ScheduleType.PARTIAL_26: {"daily": 5.2, "sat": 0, "days": [0,1,2,3,4], "label": "5h12/dia = 26h/sem"},
        ScheduleType.CUSTOM: {"daily": 8.0, "sat": 0, "days": [0,1,2,3,4], "label": "Configurável"},
    }
    
    def __init__(self, parent, company: Company, schedule: ScheduleConfig):
        super().__init__(parent)
        
        self.title("Configurações")
        self.geometry("500x550")
        self.minsize(450, 500)
        
        self.company = Company(
            name=company.name, cnpj=company.cnpj,
            address=company.address, city=company.city,
            state=company.state, phone=company.phone,
            logo_path=company.logo_path,
            default_schedule=company.default_schedule
        )
        self.schedule = schedule
        
        self._build_ui()
    
    def _build_ui(self):
        """Constrói a interface de configurações."""
        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill='both', expand=True, padx=10, pady=10)
        
        # === Dados da Empresa ===
        ctk.CTkLabel(
            scroll, text="DADOS DA EMPRESA",
            font=("Segoe UI", 14, "bold")
        ).pack(fill='x', pady=(0, 10))
        
        self.entry_name = self._add_field(scroll, "Nome / Razão Social", self.company.name)
        self.entry_cnpj = self._add_field(scroll, "CNPJ", self.company.cnpj)
        self.entry_address = self._add_field(scroll, "Endereço", self.company.address)
        self.entry_city = self._add_field(scroll, "Cidade", self.company.city)
        self.entry_state = self._add_field(scroll, "Estado (UF)", self.company.state)
        self.entry_phone = self._add_field(scroll, "Telefone", self.company.phone)
        
        # Logo
        logo_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        logo_frame.pack(fill='x', pady=5)
        ctk.CTkLabel(logo_frame, text="Logo:", font=("Segoe UI", 11)).pack(side='left')
        self.lbl_logo = ctk.CTkLabel(
            logo_frame, 
            text=os.path.basename(self.company.logo_path) if self.company.logo_path else "Nenhuma",
            font=("Segoe UI", 10), text_color="#aaa"
        )
        self.lbl_logo.pack(side='left', padx=10)
        ctk.CTkButton(
            logo_frame, text="Selecionar", width=80,
            command=self._select_logo
        ).pack(side='right')
        
        # Separador
        ctk.CTkFrame(scroll, height=2, fg_color="#444").pack(fill='x', pady=15)
        
        # === Escala de Trabalho ===
        ctk.CTkLabel(
            scroll, text="ESCALA DE TRABALHO",
            font=("Segoe UI", 14, "bold")
        ).pack(fill='x', pady=(0, 5))
        
        # Nota explicativa
        ctk.CTkLabel(
            scroll,
            text="A escala define quantas horas/dia são esperadas.\nOs horários reais vêm do relógio de ponto (arquivo AFD).",
            font=("Segoe UI", 10), text_color="#888",
            justify='left'
        ).pack(fill='x', pady=(0, 10))
        
        # Seletor de escala
        self.settings_schedule_var = ctk.StringVar(
            value=SCHEDULE_LABELS.get(self.schedule.schedule_type, "5x2")
        )
        ctk.CTkLabel(scroll, text="Tipo de Escala", font=("Segoe UI", 11)).pack(anchor='w')
        self.settings_schedule_dropdown = ctk.CTkOptionMenu(
            scroll, variable=self.settings_schedule_var,
            values=list(SCHEDULE_LABELS.values()),
            command=self._on_schedule_type_changed
        )
        self.settings_schedule_dropdown.pack(fill='x', pady=(0, 10))
        
        # Horas/dia (auto-preenchido pela escala, editável)
        self.entry_daily_hours = self._add_field(
            scroll, "Horas esperadas por dia",
            str(self.schedule.daily_hours)
        )
        
        # Tolerância
        self.entry_tolerance = self._add_field(
            scroll, "Tolerância para atraso (minutos — CLT art. 58)", 
            str(self.schedule.tolerance_minutes)
        )
        
        # Info da escala selecionada
        self.lbl_schedule_info = ctk.CTkLabel(
            scroll, text="",
            font=("Segoe UI", 10), text_color="#2a9d8f",
            justify='left'
        )
        self.lbl_schedule_info.pack(fill='x', pady=5)
        self._update_schedule_info()
        
        # Botão salvar
        ctk.CTkButton(
            scroll, text="Salvar Configurações",
            command=self._save, height=40,
            font=("Segoe UI", 13, "bold"),
            fg_color="#2d6a4f", hover_color="#40916c"
        ).pack(fill='x', pady=15)
    
    def _on_schedule_type_changed(self, value: str):
        """Atualiza horas/dia quando muda a escala."""
        stype = SCHEDULE_FROM_LABEL.get(value, ScheduleType.SCALE_5X2)
        defaults = self.SCHEDULE_DEFAULTS.get(stype, {})
        daily = defaults.get("daily", 8.0)
        
        # Atualiza campo de horas
        self.entry_daily_hours.delete(0, 'end')
        self.entry_daily_hours.insert(0, str(daily))
        
        self._update_schedule_info()
    
    def _update_schedule_info(self):
        """Mostra info resumida da escala."""
        value = self.settings_schedule_var.get()
        stype = SCHEDULE_FROM_LABEL.get(value, ScheduleType.SCALE_5X2)
        defaults = self.SCHEDULE_DEFAULTS.get(stype, {})
        label = defaults.get("label", "")
        days = defaults.get("days", [])
        day_names = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]
        day_str = ", ".join(day_names[d] for d in days if d < 7)
        self.lbl_schedule_info.configure(
            text=f"Jornada: {label}\nDias de trabalho: {day_str}"
        )
    
    def _add_field(self, parent, label: str, value: str = "") -> ctk.CTkEntry:
        """Adiciona um campo de texto com label."""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill='x', pady=3)
        
        ctk.CTkLabel(frame, text=label, font=("Segoe UI", 11)).pack(anchor='w')
        entry = ctk.CTkEntry(frame, height=32)
        entry.pack(fill='x')
        if value:
            entry.insert(0, value)
        
        return entry
    
    def _select_logo(self):
        """Seleciona imagem da logo."""
        filepath = filedialog.askopenfilename(
            title="Selecione a logo",
            filetypes=[("Imagens", "*.png *.jpg *.jpeg *.bmp")]
        )
        if filepath:
            self.company.logo_path = filepath
            self.lbl_logo.configure(text=os.path.basename(filepath))
    
    def _save(self):
        """Salva as configurações e fecha."""
        self.company.name = self.entry_name.get().strip()
        self.company.cnpj = self.entry_cnpj.get().strip()
        self.company.address = self.entry_address.get().strip()
        self.company.city = self.entry_city.get().strip()
        self.company.state = self.entry_state.get().strip()
        self.company.phone = self.entry_phone.get().strip()
        
        # Escala
        stype = SCHEDULE_FROM_LABEL.get(
            self.settings_schedule_var.get(), ScheduleType.SCALE_5X2
        )
        self.schedule.schedule_type = stype
        defaults = self.SCHEDULE_DEFAULTS.get(stype, {})
        self.schedule.workdays = defaults.get("days", [0,1,2,3,4])
        self.schedule.saturday_hours = defaults.get("sat", 0)
        
        try:
            self.schedule.daily_hours = float(self.entry_daily_hours.get().strip())
        except ValueError:
            pass
        
        try:
            self.schedule.tolerance_minutes = int(self.entry_tolerance.get().strip())
        except ValueError:
            pass
        
        self.destroy()


class ClockDialog(ctk.CTkToplevel):
    """Diálogo para conectar ao relógio de ponto ControlID via rede."""
    
    def __init__(self, parent):
        super().__init__(parent)
        
        self.title("Puxar AFD do Relogio - ControlID")
        self.geometry("450x400")
        self.minsize(400, 350)
        
        self.afd_filepath = ""  # Resultado: caminho do AFD baixado
        self._parent = parent
        
        # Carrega configurações salvas do relógio
        self._saved_ip = ""
        self._saved_login = "admin"
        self._saved_password = "admin"
        self._load_clock_config()
        
        self._build_ui()
    
    def _build_ui(self):
        """Constrói a interface do diálogo."""
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill='both', expand=True, padx=15, pady=15)
        
        # Título
        ctk.CTkLabel(
            main, text="Conexao com Relogio de Ponto",
            font=("Segoe UI", 15, "bold")
        ).pack(fill='x', pady=(0, 5))
        
        ctk.CTkLabel(
            main,
            text="Conecte ao relogio ControlID pela rede local\npara baixar o AFD automaticamente.",
            font=("Segoe UI", 10), text_color="#888", justify='left'
        ).pack(fill='x', pady=(0, 15))
        
        # IP do relógio
        ctk.CTkLabel(main, text="IP do Relogio", font=("Segoe UI", 11)).pack(anchor='w')
        self.entry_ip = ctk.CTkEntry(main, height=34, placeholder_text="Ex: 192.168.18.228")
        self.entry_ip.pack(fill='x', pady=(0, 8))
        if self._saved_ip:
            self.entry_ip.insert(0, self._saved_ip)
        
        # Login e senha lado a lado
        cred_frame = ctk.CTkFrame(main, fg_color="transparent")
        cred_frame.pack(fill='x', pady=(0, 8))
        cred_frame.grid_columnconfigure(0, weight=1)
        cred_frame.grid_columnconfigure(1, weight=1)
        
        # Login
        left = ctk.CTkFrame(cred_frame, fg_color="transparent")
        left.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        ctk.CTkLabel(left, text="Usuario", font=("Segoe UI", 11)).pack(anchor='w')
        self.entry_login = ctk.CTkEntry(left, height=32)
        self.entry_login.pack(fill='x')
        self.entry_login.insert(0, self._saved_login)
        
        # Senha
        right = ctk.CTkFrame(cred_frame, fg_color="transparent")
        right.grid(row=0, column=1, sticky='ew', padx=(5, 0))
        ctk.CTkLabel(right, text="Senha", font=("Segoe UI", 11)).pack(anchor='w')
        self.entry_password = ctk.CTkEntry(right, height=32, show="*")
        self.entry_password.pack(fill='x')
        self.entry_password.insert(0, self._saved_password)
        
        # Status
        self.lbl_status = ctk.CTkLabel(
            main, text="",
            font=("Segoe UI", 10), text_color="#888",
            wraplength=400, justify='left'
        )
        self.lbl_status.pack(fill='x', pady=8)
        
        # Botões
        btn_frame = ctk.CTkFrame(main, fg_color="transparent")
        btn_frame.pack(fill='x', pady=(5, 0))
        
        self.btn_test = ctk.CTkButton(
            btn_frame, text="Testar Conexao",
            command=self._test_connection, height=36,
            fg_color="#3d3d5c", hover_color="#4d4d6c"
        )
        self.btn_test.pack(fill='x', pady=(0, 5))
        
        self.btn_download = ctk.CTkButton(
            btn_frame, text="Baixar AFD do Relogio",
            command=self._download_afd, height=40,
            font=("Segoe UI", 13, "bold"),
            fg_color="#2d6a4f", hover_color="#40916c"
        )
        self.btn_download.pack(fill='x')
    
    def _test_connection(self):
        """Testa a conexão com o relógio."""
        ip = self.entry_ip.get().strip()
        if not ip:
            self.lbl_status.configure(text="Informe o IP do relogio.", text_color="#e63946")
            return
        
        self.lbl_status.configure(text="Conectando...", text_color="#f4a261")
        self.update()
        
        try:
            from app.controlid_api import ControlIDClient, ControlIDDevice
            
            device = ControlIDDevice(
                ip=ip,
                login=self.entry_login.get().strip(),
                password=self.entry_password.get().strip()
            )
            client = ControlIDClient(device)
            success, msg = client.test_connection()
            
            if success:
                self.lbl_status.configure(text=f"Conectado! {msg}", text_color="#2a9d8f")
                self._save_clock_config()
            else:
                self.lbl_status.configure(text=f"Falha: {msg}", text_color="#e63946")
                
        except Exception as e:
            self.lbl_status.configure(text=f"Erro: {e}", text_color="#e63946")
    
    def _download_afd(self):
        """Baixa o AFD do relógio."""
        ip = self.entry_ip.get().strip()
        if not ip:
            self.lbl_status.configure(text="Informe o IP do relogio.", text_color="#e63946")
            return
        
        self.lbl_status.configure(text="Conectando e baixando AFD...", text_color="#f4a261")
        self.btn_download.configure(state='disabled')
        self.update()
        
        try:
            from app.controlid_api import ControlIDClient, ControlIDDevice
            
            device = ControlIDDevice(
                ip=ip,
                login=self.entry_login.get().strip(),
                password=self.entry_password.get().strip()
            )
            client = ControlIDClient(device)
            client.connect()
            
            # Baixa o AFD
            filepath = client.download_afd()
            
            self.afd_filepath = filepath
            self._save_clock_config()
            
            self.lbl_status.configure(
                text=f"AFD baixado com sucesso!\n{filepath}",
                text_color="#2a9d8f"
            )
            
            # Fecha o diálogo após 1 segundo
            self.after(1000, self.destroy)
            
        except Exception as e:
            self.lbl_status.configure(text=f"Erro: {e}", text_color="#e63946")
            self.btn_download.configure(state='normal')
    
    def _save_clock_config(self):
        """Salva configurações do relógio."""
        try:
            config_path = os.path.abspath(CONFIG_FILE)
            config = {}
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            
            config['clock'] = {
                'ip': self.entry_ip.get().strip(),
                'login': self.entry_login.get().strip(),
                'password': self.entry_password.get().strip(),
            }
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    
    def _load_clock_config(self):
        """Carrega configurações salvas do relógio."""
        try:
            config_path = os.path.abspath(CONFIG_FILE)
            if not os.path.exists(config_path):
                return
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            clock = config.get('clock', {})
            self._saved_ip = clock.get('ip', '')
            self._saved_login = clock.get('login', 'admin')
            self._saved_password = clock.get('password', 'admin')
        except Exception:
            pass


class HelpDialog(ctk.CTkToplevel):
    """Janela de ajuda e FAQ do Bit-Converter."""
    
    FAQ_ITEMS = [
        {
            "titulo": "Como importar um arquivo AFD?",
            "resposta": (
                "1. Clique em 'Selecionar Arquivo AFD...'\n"
                "2. Escolha o arquivo .txt gerado pelo relogio de ponto\n"
                "3. O programa detecta automaticamente o formato\n"
                "4. Os dados serao processados e os colaboradores aparecerao na tela\n\n"
                "O arquivo AFD e gerado pelo relogio de ponto e contem todas as marcacoes. "
                "Geralmente voce encontra esse arquivo no software do relogio ou "
                "copiando de um pendrive conectado ao equipamento."
            )
        },
        {
            "titulo": "Como puxar o AFD direto do relogio?",
            "resposta": (
                "1. Clique no botao laranja 'Puxar do Relogio (ControlID)'\n"
                "2. Digite o IP do relogio na rede (ex: 192.168.18.228)\n"
                "3. Digite o usuario e senha\n"
                "4. Clique em 'Testar Conexao' para verificar\n"
                "5. Clique em 'Baixar AFD do Relogio'\n\n"
                "O AFD sera baixado e processado automaticamente!\n\n"
                "IMPORTANTE: O computador precisa estar na mesma rede "
                "que o relogio de ponto (mesma rede Wi-Fi ou cabo)."
            )
        },
        {
            "titulo": "Qual o usuario e senha do relogio?",
            "resposta": (
                "E a SENHA WEB do relogio de ponto — a mesma usada para "
                "acessar o painel do relogio pelo navegador (digitando o IP "
                "na barra de endereco).\n\n"
                "Senha padrao de fabrica da ControlID:\n"
                "  Usuario: admin\n"
                "  Senha: admin\n\n"
                "Se a senha foi alterada, use a nova senha. "
                "Voce pode verificar/alterar a senha web diretamente "
                "no menu do relogio de ponto."
            )
        },
        {
            "titulo": "Como descubro o IP do relogio?",
            "resposta": (
                "No proprio relogio de ponto:\n"
                "1. Acesse o menu do relogio (tecla Menu ou engrenagem)\n"
                "2. Va em 'Rede' ou 'Configuracoes de Rede'\n"
                "3. O IP aparecera na tela (ex: 192.168.18.228)\n\n"
                "Voce tambem pode ver o IP acessando o painel web "
                "do roteador e verificando os dispositivos conectados."
            )
        },
        {
            "titulo": "Como selecionar o mes?",
            "resposta": (
                "Apos importar o AFD, o programa detecta automaticamente "
                "todos os meses disponiveis no arquivo.\n\n"
                "O dropdown 'PERIODO' mostra os meses encontrados. "
                "Ao selecionar um mes diferente, o programa reprocessa "
                "automaticamente os dados daquele mes.\n\n"
                "O ultimo mes disponivel e selecionado por padrao."
            )
        },
        {
            "titulo": "Como exportar o PDF?",
            "resposta": (
                "Apos processar os dados, dois botoes ficam disponiveis:\n\n"
                "EXPORTAR INDIVIDUAL:\n"
                "Gera um PDF separado para cada colaborador. "
                "Voce escolhe a pasta onde salvar e todos os PDFs "
                "sao gerados automaticamente.\n\n"
                "EXPORTAR CONSOLIDADO:\n"
                "Gera um unico PDF com todos os colaboradores. "
                "Ideal para arquivo geral ou contabilidade."
            )
        },
        {
            "titulo": "O que significa cada cor no PDF?",
            "resposta": (
                "VERDE = Hora extra (trabalhou mais que o esperado)\n"
                "VERMELHO = Falta (nao compareceu no dia)\n"
                "LARANJA = Marcacao incompleta (esqueceu de bater ponto)\n"
                "CINZA CLARO = Final de semana / dia de folga\n"
                "BRANCO = Dia normal"
            )
        },
        {
            "titulo": "O que e 'marcacao incompleta'?",
            "resposta": (
                "Uma marcacao incompleta acontece quando o colaborador "
                "nao bateu todos os pontos do dia. Exemplos:\n\n"
                "- So 1 batida: esqueceu de bater a saida\n"
                "- So 2 batidas em dia cheio: nao registrou o intervalo\n"
                "- 3 batidas: faltou uma entrada ou saida\n\n"
                "Esses dias aparecem em LARANJA no PDF e sao contados "
                "no resumo mensal como 'Marcacoes Incompletas'."
            )
        },
        {
            "titulo": "Como configuro a escala de trabalho?",
            "resposta": (
                "Em 'Configuracoes', selecione o tipo de escala:\n\n"
                "5x2: 5 dias trabalho, 2 folgas (8h48/dia = 44h/sem)\n"
                "6x1: 6 dias trabalho, 1 folga (7h20/dia = 44h/sem)\n"
                "12x36: 12h trabalho, 36h descanso\n"
                "Padrao CLT: 8h seg-sex + 4h sabado = 44h/sem\n\n"
                "A escala define quantas horas/dia sao ESPERADAS. "
                "Os horarios reais vem do relogio de ponto (arquivo AFD).\n\n"
                "Voce pode ajustar as 'Horas esperadas por dia' "
                "manualmente se a escala padrao nao corresponder "
                "ao contrato dos colaboradores."
            )
        },
        {
            "titulo": "Precisa instalar algo no computador do cliente?",
            "resposta": (
                "NAO! O Bit-Converter e um executavel standalone (.exe).\n"
                "Basta copiar o arquivo Bit-Converter.exe para o computador "
                "e dar dois cliques. Nao precisa instalar Python, "
                "bibliotecas ou qualquer outro programa.\n\n"
                "Requisitos minimos:\n"
                "- Windows 10 ou superior\n"
                "- 100MB de espaco em disco"
            )
        },
        {
            "titulo": "O programa precisa de internet?",
            "resposta": (
                "NAO! O programa funciona 100% offline.\n\n"
                "Para importar arquivo AFD: funciona sem internet.\n"
                "Para puxar do relogio: precisa apenas estar na mesma "
                "rede local (Wi-Fi ou cabo) que o relogio de ponto. "
                "Nao precisa de internet."
            )
        },
    ]
    
    def __init__(self, parent):
        super().__init__(parent)
        
        self.title("Ajuda - Bit-Converter")
        self.geometry("600x550")
        self.minsize(500, 450)
        
        self._build_ui()
    
    def _build_ui(self):
        """Constrói a interface de ajuda."""
        # Header
        header = ctk.CTkFrame(self, height=50, fg_color=("#1a1a2e", "#1a1a2e"))
        header.pack(fill='x')
        header.pack_propagate(False)
        
        ctk.CTkLabel(
            header, text="Perguntas Frequentes (FAQ)",
            font=("Segoe UI", 16, "bold"), text_color="white"
        ).pack(side='left', padx=15, pady=10)
        
        # Scroll area
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill='both', expand=True, padx=10, pady=10)
        
        for i, item in enumerate(self.FAQ_ITEMS):
            self._add_faq_item(scroll, i + 1, item["titulo"], item["resposta"])
        
        # Footer
        footer = ctk.CTkFrame(self, height=35, fg_color=("#1a1a2e", "#1a1a2e"))
        footer.pack(fill='x')
        footer.pack_propagate(False)
        ctk.CTkLabel(
            footer,
            text=f"Powered By BitKaiser Solution - Xinguara - PA  |  v{APP_VERSION}",
            font=("Segoe UI", 9), text_color="#888"
        ).pack(pady=8)
    
    def _add_faq_item(self, parent, num: int, titulo: str, resposta: str):
        """Adiciona um item de FAQ."""
        card = ctk.CTkFrame(parent, fg_color=("#2a2a3e", "#2a2a3e"), corner_radius=8)
        card.pack(fill='x', pady=4)
        
        # Titulo
        ctk.CTkLabel(
            card, text=f"{num}. {titulo}",
            font=("Segoe UI", 12, "bold"), anchor='w',
            text_color="#e0e0ff"
        ).pack(fill='x', padx=12, pady=(10, 4))
        
        # Resposta
        ctk.CTkLabel(
            card, text=resposta,
            font=("Segoe UI", 11), anchor='w', justify='left',
            text_color="#bbb", wraplength=530
        ).pack(fill='x', padx=12, pady=(0, 10))
    
    # ==========================================
    # AUTO-UPDATE
    # ==========================================
    
    def _check_update_background(self):
        """Verifica atualização disponível em background."""
        def _check():
            try:
                has_update, info, msg = check_for_update()
                if has_update and info:
                    self._update_info = info
                    # Atualiza UI na thread principal
                    self.after(0, self._show_update_available, info)
            except Exception:
                pass  # Silencioso — não interrompe o app
        
        thread = threading.Thread(target=_check, daemon=True)
        thread.start()
    
    def _show_update_available(self, info: UpdateInfo):
        """Mostra o botão de atualização quando disponível."""
        self.btn_update.configure(
            text=f"Atualizar v{info.version}"
        )
        self.btn_update.pack(side='right', padx=(0, 5), pady=10)
    
    def _open_update_dialog(self):
        """Abre o diálogo de atualização."""
        if self._update_info:
            dialog = UpdateDialog(self, self._update_info)
            dialog.grab_set()
            self.wait_window(dialog)
        else:
            # Verifica manualmente
            self._check_update_manual()
    
    def _check_update_manual(self):
        """Verificação manual de atualização."""
        has_update, info, msg = check_for_update()
        if has_update and info:
            self._update_info = info
            self._show_update_available(info)
            dialog = UpdateDialog(self, info)
            dialog.grab_set()
            self.wait_window(dialog)
        else:
            messagebox.showinfo("Atualização", msg)


class UpdateDialog(ctk.CTkToplevel):
    """Diálogo de atualização do aplicativo."""
    
    def __init__(self, parent, update_info: UpdateInfo):
        super().__init__(parent)
        self.update_info = update_info
        self.parent_app = parent
        self._downloading = False
        
        self.title(f"Atualização Disponível — v{update_info.version}")
        self.geometry("500x400")
        self.resizable(False, False)
        
        # Centraliza na tela
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 500) // 2
        y = (self.winfo_screenheight() - 400) // 2
        self.geometry(f"500x400+{x}+{y}")
        
        self._build_ui()
    
    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, height=60, fg_color=("#e67e22", "#e67e22"))
        header.pack(fill='x')
        header.pack_propagate(False)
        
        ctk.CTkLabel(
            header, text=f"Nova Versão Disponível!",
            font=("Segoe UI", 18, "bold"), text_color="white"
        ).pack(side='left', padx=20, pady=15)
        
        ctk.CTkLabel(
            header, text=f"v{APP_VERSION} → v{self.update_info.version}",
            font=("Segoe UI", 14), text_color="#fff8"
        ).pack(side='right', padx=20, pady=15)
        
        # Corpo
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill='both', expand=True, padx=20, pady=15)
        
        # Info
        info_frame = ctk.CTkFrame(body, fg_color=("#2a2a3e", "#2a2a3e"), corner_radius=10)
        info_frame.pack(fill='x', pady=(0, 10))
        
        details = f"Data: {self.update_info.date}"
        if self.update_info.size > 0:
            details += f"  |  Tamanho: {format_size(self.update_info.size)}"
        
        ctk.CTkLabel(
            info_frame, text=details,
            font=("Segoe UI", 11), text_color="#aaa"
        ).pack(padx=15, pady=8)
        
        # Changelog
        ctk.CTkLabel(
            body, text="O que mudou:",
            font=("Segoe UI", 12, "bold"), anchor='w'
        ).pack(fill='x', pady=(5, 5))
        
        changelog_frame = ctk.CTkFrame(body, fg_color=("#1e1e30", "#1e1e30"), corner_radius=8)
        changelog_frame.pack(fill='both', expand=True)
        
        self.changelog_text = ctk.CTkTextbox(
            changelog_frame, font=("Segoe UI", 11),
            fg_color="transparent", wrap='word'
        )
        self.changelog_text.pack(fill='both', expand=True, padx=10, pady=10)
        self.changelog_text.insert('1.0', self.update_info.changelog or 'Sem detalhes disponíveis.')
        self.changelog_text.configure(state='disabled')
        
        # Barra de progresso (inicialmente oculta)
        self.progress_frame = ctk.CTkFrame(body, fg_color="transparent")
        
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, height=12)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill='x', pady=(5, 2))
        
        self.lbl_progress = ctk.CTkLabel(
            self.progress_frame, text="Baixando...",
            font=("Segoe UI", 10), text_color="#aaa"
        )
        self.lbl_progress.pack()
        
        # Botões
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill='x', padx=20, pady=(0, 15))
        
        self.btn_cancel = ctk.CTkButton(
            btn_frame, text="Depois", width=120,
            fg_color="#555", hover_color="#666",
            command=self.destroy
        )
        self.btn_cancel.pack(side='left')
        
        self.btn_update = ctk.CTkButton(
            btn_frame, text="Atualizar Agora", width=180,
            fg_color="#27ae60", hover_color="#219a52",
            font=("Segoe UI", 13, "bold"),
            command=self._start_download
        )
        self.btn_update.pack(side='right')
    
    def _start_download(self):
        """Inicia o download da atualização."""
        if self._downloading:
            return
        self._downloading = True
        
        self.btn_update.configure(state='disabled', text="Baixando...")
        self.btn_cancel.configure(state='disabled')
        self.progress_frame.pack(fill='x', pady=(10, 0))
        
        def _download():
            def _progress(downloaded, total):
                pct = downloaded / total if total > 0 else 0
                self.after(0, self._update_progress, pct, downloaded, total)
            
            success, result = download_update(self.update_info, _progress)
            
            if success:
                self.after(0, self._download_complete, result)
            else:
                self.after(0, self._download_failed, result)
        
        thread = threading.Thread(target=_download, daemon=True)
        thread.start()
    
    def _update_progress(self, pct: float, downloaded: int, total: int):
        """Atualiza barra de progresso."""
        self.progress_bar.set(pct)
        self.lbl_progress.configure(
            text=f"Baixando... {format_size(downloaded)} / {format_size(total)} ({pct*100:.0f}%)"
        )
    
    def _download_complete(self, new_exe_path: str):
        """Download concluído — aplica atualização."""
        self.progress_bar.set(1.0)
        self.lbl_progress.configure(text="Download concluído! Aplicando...")
        
        # Aplica a atualização (substitui o .exe)
        if getattr(sys, 'frozen', False):
            # Modo empacotado — aplica de verdade
            success = apply_update(new_exe_path)
            if success:
                self.lbl_progress.configure(text="Reiniciando...")
                self.after(1000, lambda: sys.exit(0))
            else:
                messagebox.showerror(
                    "Erro",
                    "Não foi possível aplicar a atualização.\n"
                    f"O arquivo foi salvo em:\n{new_exe_path}\n\n"
                    "Substitua manualmente o Bit-Converter.exe."
                )
                self.btn_cancel.configure(state='normal')
                self._downloading = False
        else:
            # Modo desenvolvimento — só avisa
            messagebox.showinfo(
                "Atualização (Dev Mode)",
                f"Em modo desenvolvimento, a atualização não é aplicada automaticamente.\n"
                f"Novo .exe salvo em:\n{new_exe_path}"
            )
            self.btn_cancel.configure(state='normal')
            self._downloading = False
    
    def _download_failed(self, error_msg: str):
        """Falha no download."""
        self.progress_bar.set(0)
        self.lbl_progress.configure(text=f"Erro: {error_msg}")
        self.btn_update.configure(state='normal', text="Tentar Novamente")
        self.btn_cancel.configure(state='normal')
        self._downloading = False
