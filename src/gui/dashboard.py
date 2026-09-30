"""
Panneau latéral regroupant les contrôles manuels et le tableau de bord (statistiques).
Prêt pour l'intégration avec SQLite et PyQtGraph.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QPushButton, 
    QLabel, QFormLayout, QComboBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt

class DashboardPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(300)
        
        # Layout principal du panneau
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # --- 1. ZONE ENVIRONNEMENT (Physique de la route) ---
        env_group = QGroupBox("🌤️ Environnement & Adhérence")
        env_layout = QFormLayout()
        
        self.combo_meteo = QComboBox()
        self.combo_meteo.addItems(["Dégagé", "Pluie", "Gel"])
        
        self.spin_temp = QDoubleSpinBox()
        self.spin_temp.setRange(-20.0, 50.0)
        self.spin_temp.setValue(20.0)
        self.spin_temp.setSuffix(" °C")
        
        env_layout.addRow("Météo :", self.combo_meteo)
        env_layout.addRow("Température :", self.spin_temp)
        env_group.setLayout(env_layout)
        
        # --- 2. ZONE STATISTIQUES (Base de données) ---
        stats_group = QGroupBox("📊 Tableau de Bord (Métriques BDD)")
        stats_layout = QFormLayout()
        
        self.lbl_vehicules = QLabel("0")
        self.lbl_temps_attente = QLabel("0.0 s")
        self.lbl_incidents = QLabel("0")
        
        stats_layout.addRow("Véhicules passés :", self.lbl_vehicules)
        stats_layout.addRow("Temps d'attente moy :", self.lbl_temps_attente)
        stats_layout.addRow("Incidents / Freinages :", self.lbl_incidents)
        stats_group.setLayout(stats_layout)
        
        # Placeholder pour pyqtgraph
        self.graph_placeholder = QLabel("[ Graphique PyqtGraph ]")
        self.graph_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.graph_placeholder.setStyleSheet("background-color: #222; color: #777; border-radius: 5px;")
        self.graph_placeholder.setMinimumHeight(120)
        
        # --- 3. ZONE CONTRÔLES (Simulation & Usagers) ---
        controls_group = QGroupBox("🎮 Contrôles Opérateur")
        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(5)
        
        self.btn_spawn_voiture = QPushButton("🚗 Ajouter Voiture")
        self.btn_spawn_pl = QPushButton("🚛 Ajouter Poids Lourd")
        self.btn_spawn_convoi = QPushButton("⚠️ Ajouter Convoi Exceptionnel")
        
        self.btn_spawn_vta = QPushButton("🚑 Ajouter VTA (Priorité)")
        self.btn_spawn_vta.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
        
        self.btn_spawn_pieton = QPushButton("🚶 Ajouter Piéton")
        self.btn_spawn_pieton.setStyleSheet("background-color: #9C27B0; color: white; font-weight: bold;")
        
        self.btn_spawn_cycliste = QPushButton("🚲 Ajouter Cycliste")
        self.btn_spawn_cycliste.setStyleSheet("background-color: #00BCD4; color: white; font-weight: bold;")
        
        self.btn_toggle_sim = QPushButton("▶️ Démarrer Simulation")
        self.btn_toggle_sim.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; margin-top: 10px; padding: 5px;")
        
        controls_layout.addWidget(self.btn_spawn_voiture)
        controls_layout.addWidget(self.btn_spawn_pl)
        controls_layout.addWidget(self.btn_spawn_convoi)
        controls_layout.addWidget(self.btn_spawn_vta)
        controls_layout.addWidget(self.btn_spawn_pieton)
        controls_layout.addWidget(self.btn_spawn_cycliste)
        controls_layout.addWidget(self.btn_toggle_sim)
        controls_group.setLayout(controls_layout)
        
        # Assemblage final
        layout.addWidget(env_group)
        layout.addWidget(stats_group)
        layout.addWidget(self.graph_placeholder)
        layout.addWidget(controls_group)
        layout.addStretch()
