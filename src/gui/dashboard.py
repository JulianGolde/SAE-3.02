import logging
logger = logging.getLogger(__name__)

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QPushButton, 
    QLabel, QFormLayout, QComboBox, QSlider, QTextEdit, QHBoxLayout
)
from PyQt6.QtCore import Qt

class DashboardPanel(QWidget):
    """Panneau latéral contenant les contrôles de la simulation."""
    def __init__(self, parent=None):
        """Initialise l'objet avec les paramètres requis.
        
        Args:
            *args: Arguments divers.
            **kwargs: Paramètres nommés.
        """
        super().__init__(parent)
        self.setFixedWidth(340)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        style_btn = """
            QPushButton { background-color: #333; color: white; border-radius: 4px; padding: 5px; }
            QPushButton:hover { background-color: #555; }
        """
        self.setStyleSheet(style_btn)
        
        env_group = QGroupBox("🌤️ Météo & Temps")
        env_layout = QFormLayout()
        
        self.combo_meteo = QComboBox()
        self.combo_meteo.addItems(["Dégagé", "Pluie", "Tempête", "Gel"])
        
        self.slider_temps = QSlider(Qt.Orientation.Horizontal)
        self.slider_temps.setRange(1, 30)
        self.slider_temps.setValue(10)
        self.lbl_temps_valeur = QLabel("1.0x")
        
        env_layout.addRow("Météo :", self.combo_meteo)
        env_layout.addRow("Vitesse Simu :", self.slider_temps)
        env_layout.addRow("", self.lbl_temps_valeur)
        env_group.setLayout(env_layout)
        
        feux_group = QGroupBox("🚦 Contrôle & Scénarios")
        feux_layout = QVBoxLayout()
        self.btn_feux_ns = QPushButton("Passer Axe N/S au Vert")
        self.btn_feux_eo = QPushButton("Passer Axe E/O au Vert")
        self.combo_scenario = QComboBox()
        self.combo_scenario.addItems(["-- Scénarios JSON --", "Heure de Pointe", "Urgences (VTA)"])
        self.btn_load_scenario = QPushButton("Charger Scénario")
        feux_layout.addWidget(self.btn_feux_ns)
        feux_layout.addWidget(self.btn_feux_eo)
        feux_layout.addWidget(self.combo_scenario)
        feux_layout.addWidget(self.btn_load_scenario)
        feux_group.setLayout(feux_layout)
        
        hud_group = QGroupBox("🔍 HUD et Pilotage")
        hud_layout = QVBoxLayout()
        self.text_hud = QTextEdit()
        self.text_hud.setReadOnly(True)
        self.text_hud.setText("Cliquez sur un usager...")
        self.text_hud.setMaximumHeight(130)
        self.text_hud.setStyleSheet("background-color: #1e1e1e; color: #00FF00; font-family: monospace; font-size: 11px;")
        
        dir_layout = QHBoxLayout()
        self.btn_dir_nord = QPushButton("⬆️ Tourner N")
        self.btn_dir_sud = QPushButton("⬇️ Tourner S")
        self.btn_dir_ouest = QPushButton("⬅️ Tourner O")
        self.btn_dir_est = QPushButton("➡️ Tourner E")
        dir_layout.addWidget(self.btn_dir_nord)
        dir_layout.addWidget(self.btn_dir_sud)
        dir_layout.addWidget(self.btn_dir_ouest)
        dir_layout.addWidget(self.btn_dir_est)
        
        hud_layout.addWidget(self.text_hud)
        hud_layout.addLayout(dir_layout)
        hud_group.setLayout(hud_layout)
        
        controls_group = QGroupBox("🎮 Générateur d'Usagers")
        controls_layout = QVBoxLayout()
        self.lbl_mode_placement = QLabel("Prêt (Cliquez sur la scène)")
        self.lbl_mode_placement.setStyleSheet("color: #FFC107; font-size: 11px;")
        
        self.combo_voie_spawn = QComboBox()
        self.combo_voie_spawn.addItems(["Auto (proche)", "Nord -> Sud", "Sud -> Nord", "Est -> Ouest", "Ouest -> Est", "Passage Piéton"])
        
        self.btn_spawn_voiture = QPushButton("🚗 Voiture")
        self.btn_spawn_pl = QPushButton("🚛 Poids Lourd")
        self.btn_spawn_vta = QPushButton("🚑 VTA (Priorité)")
        self.btn_spawn_vta.setStyleSheet("background-color: #f44336; color: white;")
        self.btn_spawn_pieton = QPushButton("🚶 Piéton")
        self.btn_spawn_cycliste = QPushButton("🚲 Cycliste")
        
        self.btn_toggle_sim = QPushButton("▶️ Démarrer Simulation")
        self.btn_toggle_sim.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        
        controls_layout.addWidget(QLabel("Choix de la voie :"))
        controls_layout.addWidget(self.combo_voie_spawn)
        controls_layout.addWidget(self.btn_spawn_voiture)
        controls_layout.addWidget(self.btn_spawn_pl)
        controls_layout.addWidget(self.btn_spawn_vta)
        controls_layout.addWidget(self.btn_spawn_pieton)
        controls_layout.addWidget(self.btn_spawn_cycliste)
        controls_layout.addWidget(self.lbl_mode_placement)
        controls_layout.addWidget(self.btn_toggle_sim)
        controls_group.setLayout(controls_layout)
        
        stats_group = QGroupBox("📊 Analyse de Données")
        stats_layout = QFormLayout()
        self.lbl_veh_count = QLabel("0")
        self.lbl_avg_speed = QLabel("0.0 km/h")
        stats_layout.addRow("Véhicules Actifs :", self.lbl_veh_count)
        stats_layout.addRow("Vitesse Moyenne :", self.lbl_avg_speed)
        stats_group.setLayout(stats_layout)
        
        layout.addWidget(env_group)
        layout.addWidget(feux_group)
        layout.addWidget(hud_group)
        layout.addWidget(controls_group)
        layout.addWidget(stats_group)
        layout.addStretch()

    def showEvent(self, event):
        super().showEvent(event)
        if not hasattr(self, '_connected_stats'):
            p = self.parent()
            while p is not None:
                if hasattr(p, 'moteur') and hasattr(p.moteur, 'tick_simulation'):
                    p.moteur.tick_simulation.connect(self.update_from_tick)
                    self._connected_stats = True
                    break
                p = p.parent()

    def update_from_tick(self, entites, inter):
        try:
            nb = len(entites)
            s = sum(e.vitesse_kmh for e in entites if hasattr(e, 'vitesse_kmh'))
            avg = s / nb if nb > 0 else 0.0
            self.lbl_veh_count.setText(str(nb))
            self.lbl_avg_speed.setText(f"{avg:.1f} km/h")
        except Exception as e:
            logger.error(f"Erreur update_from_tick: {e}")
