"""
Projet Esk-2718 — SAÉ 3.02
Simulation 2D de régulation intelligente de carrefours
pour véhicules prioritaires (V2X / V2I).

Point d'entrée principal de l'application.
"""

import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QHBoxLayout, QWidget, QGraphicsView
from PyQt6.QtCore import Qt

from gui.carrefour_scene import CarrefourScene
from gui.dashboard import DashboardPanel


from PyQt6.QtGui import QPainter

class MainWindow(QMainWindow):
    """Fenêtre principale de l'application Esk-2718."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Esk-2718 — Simulation Carrefour V2X/V2I")
        self.setMinimumSize(1200, 850)

        # Widget central et layout horizontal
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Vue Graphique 2D (Gauche)
        self.scene = CarrefourScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing) # Lissage
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag) # Permet de bouger la carte avec la souris
        
        # 2. Panneau latéral (Droite)
        self.dashboard = DashboardPanel(self)

        # Assemblage
        main_layout.addWidget(self.view, stretch=1) # Prend un max de place
        main_layout.addWidget(self.dashboard)       # Taille fixe (définie à 300px dans le dashboard)


def main():
    """Lance l'application PyQt6."""
    app = QApplication(sys.argv)
    app.setApplicationName("Esk-2718")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
