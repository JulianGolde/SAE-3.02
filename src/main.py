"""
Projet Esk-2718 — SAÉ 3.02
Simulation 2D de régulation intelligente de carrefours
pour véhicules prioritaires (V2X / V2I).

Point d'entrée principal de l'application.
"""

import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel
from PyQt6.QtCore import Qt


class MainWindow(QMainWindow):
    """Fenêtre principale de l'application Esk-2718."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Esk-2718 — Simulation Carrefour V2X/V2I")
        self.setMinimumSize(1024, 768)

        # Label temporaire — sera remplacé par QGraphicsView
        label = QLabel("🚦 Esk-2718 — Simulation en cours de développement")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 24px; color: #333;")
        self.setCentralWidget(label)


def main():
    """Lance l'application PyQt6."""
    app = QApplication(sys.argv)
    app.setApplicationName("Esk-2718")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
