"""
AFD Parser — Controle de Ponto
Programa para importar arquivos AFD de relógios ControlID,
calcular horas extras/faltas e exportar relatórios em PDF.
"""
from ui.main_window import MainWindow


def main():
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
