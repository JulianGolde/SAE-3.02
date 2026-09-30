"""
Projet Esk-2718 — SAÉ 3.02
Simulation 2D de régulation intelligente de carrefours
pour véhicules prioritaires (V2X / V2I).

Point d'entrée principal de l'application.
"""

import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QHBoxLayout, QWidget, QGraphicsView
from PyQt6.QtGui import QPainter
from PyQt6.QtCore import Qt

from gui.carrefour_scene import CarrefourScene
from gui.dashboard import DashboardPanel


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
        main_layout.addWidget(self.view, stretch=1)
        main_layout.addWidget(self.dashboard)

        # ==========================================
        # INITIALISATION DU MOTEUR DE SIMULATION (MVP)
        # ==========================================
        from simulation.moteur import MoteurSimulation
        from simulation.vehicules import Vehicule, TypeVehicule
        import uuid # Pour générer des ID uniques
        
        self.moteur = MoteurSimulation()
        # On branche le signal physique -> affichage visuel
        self.moteur.tick_simulation.connect(self.scene.mettre_a_jour_entites)
        
        # --- Câblage des boutons du Dashboard ---
        def toggle_simulation():
            if self.moteur.isRunning():
                self.moteur.arreter()
                self.dashboard.btn_toggle_sim.setText("▶️ Démarrer Simulation")
                self.dashboard.btn_toggle_sim.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; margin-top: 10px; padding: 5px;")
            else:
                self.moteur.demarrer()
                self.dashboard.btn_toggle_sim.setText("⏸️ Mettre en Pause")
                self.dashboard.btn_toggle_sim.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold; margin-top: 10px; padding: 5px;")
                
        self.dashboard.btn_toggle_sim.clicked.connect(toggle_simulation)
        
        # Fonction générique de spawn
        def spawner_entite(v_type):
            nouvelle_entite = Vehicule(id_vehicule=str(uuid.uuid4())[:8], v_type=v_type)
            nouvelle_entite.vitesse_kmh = 50.0 if v_type not in (TypeVehicule.PIETON, TypeVehicule.CYCLISTE) else 5.0
            nouvelle_entite.position = (-400, 0) # Apparaît à gauche de la route
            self.moteur.ajouter_entite(nouvelle_entite)
            
        self.dashboard.btn_spawn_voiture.clicked.connect(lambda: spawner_entite(TypeVehicule.VOITURE))
        self.dashboard.btn_spawn_pl.clicked.connect(lambda: spawner_entite(TypeVehicule.POIDS_LOURD))
        self.dashboard.btn_spawn_vta.clicked.connect(lambda: spawner_entite(TypeVehicule.VIG_VTA))
        self.dashboard.btn_spawn_pieton.clicked.connect(lambda: spawner_entite(TypeVehicule.PIETON))
        self.dashboard.btn_spawn_cycliste.clicked.connect(lambda: spawner_entite(TypeVehicule.CYCLISTE))

    def closeEvent(self, event):
        """Assure la fermeture propre du QThread à la fermeture de la fenêtre."""
        if hasattr(self, 'moteur') and self.moteur.isRunning():
            self.moteur.arreter()
        event.accept()


def main():
    """Lance l'application PyQt6."""
    app = QApplication(sys.argv)
    app.setApplicationName("Esk-2718")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
