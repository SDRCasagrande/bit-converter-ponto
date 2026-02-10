"""
Script de teste rapido - sem emojis para Windows.
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.parser import AFDParser
from app.calculator import WorkCalculator
from app.models import ScheduleConfig, ScheduleType


def test_file(filepath):
    print(f"\n{'='*60}")
    print(f"Testando: {os.path.basename(filepath)}")
    print(f"{'='*60}")
    
    parser = AFDParser()
    employees, company = parser.parse_file(filepath)
    summary = parser.get_summary()
    
    print(f"Formato detectado: {summary['format'].upper()}")
    print(f"Empresa: {summary['company_name']}")
    print(f"CNPJ: {summary['company_cnpj']}")
    print(f"Linhas: {summary['total_lines']} | Marcacoes: {summary['total_punches']} | Colaboradores: {summary['total_employees']}")
    
    if summary['date_start']:
        print(f"Periodo: {summary['date_start']} a {summary['date_end']}")
    print(f"Meses disponiveis: {summary['months_available']}")
    
    if summary['errors'] > 0:
        print(f"Avisos: {summary['errors']}")
        for err in parser.errors[:3]:
            print(f"  -> {err}")
    
    print(f"\nColaboradores:")
    for pis, emp in employees.items():
        n = len(parser.get_punches_by_pis(pis))
        print(f"  * {emp.display_name} (PIS:{pis}) = {n} marcacoes")
    
    # Calcula ultimo mes disponivel
    if summary['months_available']:
        month, year = summary['months_available'][-1]
        print(f"\n--- CALCULO {month}/{year} (Escala 5x2) ---")
        
        schedule = ScheduleConfig(schedule_type=ScheduleType.SCALE_5X2)
        calculator = WorkCalculator(default_schedule=schedule)
        report = calculator.generate_report(
            employees=employees,
            punches=parser.punches,
            company=company,
            month=month,
            year=year
        )
        
        for emp in report.employees:
            total_exp = sum(wd.expected_hours for wd in emp.workdays)
            worked_days = sum(1 for wd in emp.workdays if wd.worked_hours > 0)
            
            print(f"\n  {emp.display_name}:")
            print(f"    Dias trabalhados: {worked_days}")
            print(f"    Horas trabalhadas: {emp.total_worked_hours:.1f}h")
            print(f"    Horas previstas: {total_exp:.1f}h")
            print(f"    Extras: +{emp.total_overtime_hours:.1f}h")
            print(f"    Deficit: -{emp.total_deficit_hours:.1f}h")
            print(f"    Atrasos: {emp.total_late_days} dias ({emp.total_late_minutes:.0f} min total)")
            print(f"    Faltas: {emp.total_absent_days}")
            
            # Mostra primeiros 5 dias com marcacao
            shown = 0
            for wd in emp.workdays:
                if wd.punches and shown < 5:
                    ps = " -> ".join([x.time.strftime("%H:%M") for x in wd.punches])
                    extra = ""
                    if wd.overtime_hours > 0:
                        extra = f" [+{wd.overtime_hours:.1f}h extra]"
                    elif wd.is_late:
                        extra = f" [Atraso {wd.late_minutes:.0f}min]"
                    elif wd.deficit_hours > 0:
                        extra = f" [-{wd.deficit_hours:.1f}h deficit]"
                    day_names = ["Seg","Ter","Qua","Qui","Sex","Sab","Dom"]
                    dn = day_names[wd.date.weekday()]
                    print(f"      {wd.date.strftime('%d/%m')} ({dn}): {ps} = {wd.worked_hours:.1f}h{extra}")
                    shown += 1


def main():
    print("AFD Parser - Teste Automatizado")
    print("=" * 60)
    
    search_dirs = [
        os.path.dirname(os.path.abspath(__file__)),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."),
    ]
    
    afd_files = []
    for d in search_dirs:
        try:
            for f in os.listdir(d):
                if f.lower().endswith((".txt", ".afd")) and "afd" in f.lower():
                    full = os.path.join(d, f)
                    if os.path.isfile(full):
                        afd_files.append(full)
        except Exception:
            pass
    
    if not afd_files:
        print("Nenhum arquivo AFD encontrado.")
        return
    
    print(f"Encontrados {len(afd_files)} arquivo(s) AFD")
    
    for fp in afd_files:
        try:
            test_file(fp)
        except Exception as e:
            print(f"\nErro ao testar {fp}: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*60}")
    print("Teste concluido!")


if __name__ == "__main__":
    main()
