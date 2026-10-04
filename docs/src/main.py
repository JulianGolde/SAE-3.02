import sys
import uuid
import math
import json
import os
from PyQt6.QtWidgets import QApplication, QMainWindow, QHBoxLayout, QWidget, QGraphicsView
from PyQt6.QtGui import QPainter, QIcon, QPixmap, QColor
from PyQt6.QtCore import Qt

from gui.carrefour_scene import CarrefourScene
from gui.dashboard import DashboardPanel
from simulation.moteur import MoteurSimulation
from simulation.vehicules import Vehicule, TypeVehicule

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Esk-2718 — Simulation Totale VPI/VPO")
        self.setMinimumSize(1300, 850)
        self.id_selectionne = None
        self.type_a_placer = None 
        
        icon_pixmap = QPixmap(64, 64)
        icon_pixmap.fill(QColor("#4CAF50"))
        painter = QPainter(icon_pixmap)
        painter.setBrush(QColor("#333"))
        painter.drawRect(24, 0, 16, 64)
        painter.drawRect(0, 24, 64, 16)
        painter.setBrush(QColor("#F44336"))
        painter.drawEllipse(28, 28, 8, 8)
        painter.end()
        self.setWindowIcon(QIcon(icon_pixmap))

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scene = CarrefourScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.dashboard = DashboardPanel(self)

        layout.addWidget(self.view, stretch=1)
        layout.addWidget(self.dashboard)

        self.moteur = MoteurSimulation()
        
        def rafraichir_interface(entites, inter):
            self.scene.mettre_a_jour_entites(entites, inter)
            if self.id_selectionne:
                entite = next((e for e in entites if e.id_entite == self.id_selectionne), None)
                if entite:
                    ec = 0.5 * entite.masse_kg * (entite.vitesse**2)
                    texte = f"ID: {entite.id_entite} | {entite.type_entite.name}\n"
                    texte += f"Vitesse: {entite.vitesse_kmh:.1f} km/h\n"
                    texte += f"Masse: {entite.masse_kg:.1f} kg\n"
                    texte += f"Énergie Cinétique: {ec/1000:.1f} kJ\n"
                    if entite.freinage_mecanique:
                        texte += f"Accél: {entite.commande_acceleration:.1f} m/s² [FREIN MÉC.]\n"
                    else:
                        texte += f"Accél: {entite.commande_acceleration:.1f} m/s² [frein mot.]\n"
                    texte += f"ABS: {'Oui' if entite.possede_abs else 'Non'}"
                    texte += f" | Pneus: {entite.age_pneus:.0f}ans ({entite.usure_pneus*100:.0f}%)\n"
                    texte += f"Cap: {math.degrees(entite.cap):.0f}°"
                    if entite.action_intersection is not None:
                        texte += f" [VIRAGE PRÉVU]"
                    self.dashboard.text_hud.setText(texte)
                else:
                    self.dashboard.text_hud.setText("Entité perdue ou hors zone.")

        self.moteur.tick_simulation.connect(rafraichir_interface)
        
        def change_vitesse(val):
            self.moteur.multiplicateur_temps = val/10.0
            self.dashboard.lbl_temps_valeur.setText(f"{val/10.0:.1f}x")
            
        self.dashboard.slider_temps.valueChanged.connect(change_vitesse)
        self.dashboard.btn_feux_ns.clicked.connect(self.moteur.intersection.forcer_vert_ns)
        self.dashboard.btn_feux_eo.clicked.connect(self.moteur.intersection.forcer_vert_eo)
        
        def change_meteo(etat):
            self.scene.set_meteo(etat)
            if etat == "Tempête": self.moteur.densite_air_rho = 2.5
            elif etat == "Pluie": self.moteur.densite_air_rho = 1.5
            else: self.moteur.densite_air_rho = 1.225
                
        self.dashboard.combo_meteo.currentTextChanged.connect(change_meteo)
        
        def toggle_simulation():
            if self.moteur.isRunning():
                self.moteur.arreter()
                self.dashboard.btn_toggle_sim.setText("▶️ Démarrer Simulation")
                self.dashboard.btn_toggle_sim.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
            else:
                self.moteur.demarrer()
                self.dashboard.btn_toggle_sim.setText("⏸️ Mettre en Pause")
                self.dashboard.btn_toggle_sim.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold;")
        self.dashboard.btn_toggle_sim.clicked.connect(toggle_simulation)
        
        def selectionner_entite(entite_id): 
            self.id_selectionne = entite_id
        self.scene.signal_entite_selectionnee.connect(selectionner_entite)
        
        def spawn_clic(x, y):
            if self.type_a_placer is None:
                return
            try:
                nouvelle = Vehicule(id_vehicule=str(uuid.uuid4())[:8], v_type=self.type_a_placer)
                voie = self.dashboard.combo_voie_spawn.currentText()
                
                if voie == "Passage Piéton" or self.type_a_placer == TypeVehicule.PIETON:
                    nouvelle.pos_x = x
                    nouvelle.pos_y = y
                    nouvelle.cap = math.pi/2 if y < 0 else -math.pi/2
                elif voie == "Nord -> Sud":
                    nouvelle.pos_x = -2.0
                    nouvelle.pos_y = y
                    nouvelle.cap = math.pi/2
                elif voie == "Sud -> Nord":
                    nouvelle.pos_x = 2.0
                    nouvelle.pos_y = y
                    nouvelle.cap = -math.pi/2
                elif voie == "Est -> Ouest":
                    nouvelle.pos_y = -2.0
                    nouvelle.pos_x = x
                    nouvelle.cap = math.pi
                elif voie == "Ouest -> Est":
                    nouvelle.pos_y = 2.0
                    nouvelle.pos_x = x
                    nouvelle.cap = 0.0
                else:
                    if abs(y) < abs(x):
                        nouvelle.pos_x = x
                        nouvelle.pos_y = 2.0 if y > 0 else -2.0
                        nouvelle.cap = 0.0 if nouvelle.pos_y > 0 else math.pi
                    else:
                        nouvelle.pos_y = y
                        nouvelle.pos_x = 2.0 if x < 0 else -2.0
                        nouvelle.cap = math.pi/2 if nouvelle.pos_x < 0 else -math.pi/2
                    
                nouvelle.vitesse = 0.0
                self.moteur.ajouter_entite(nouvelle)
                set_type_a_placer(None)
            except Exception as e:
                print(f"Erreur de placement : {e}")
                
        self.scene.signal_clic_vide.connect(spawn_clic)
        
        def set_type_a_placer(t): 
            self.type_a_placer = t
            if t is not None:
                self.dashboard.lbl_mode_placement.setText(f"Prêt à placer : {t.name}")
            else:
                self.dashboard.lbl_mode_placement.setText("Mode : Sélection")
            
        self.dashboard.btn_spawn_voiture.clicked.connect(lambda: set_type_a_placer(TypeVehicule.VOITURE))
        self.dashboard.btn_spawn_pl.clicked.connect(lambda: set_type_a_placer(TypeVehicule.POIDS_LOURD))
        self.dashboard.btn_spawn_vta.clicked.connect(lambda: set_type_a_placer(TypeVehicule.VIG_VTA))
        self.dashboard.btn_spawn_pieton.clicked.connect(lambda: set_type_a_placer(TypeVehicule.PIETON))
        self.dashboard.btn_spawn_cycliste.clicked.connect(lambda: set_type_a_placer(TypeVehicule.CYCLISTE))
        
        def prevoir_virage(angle):
            if self.id_selectionne:
                ent = next((e for e in self.moteur.entites if e.id_entite == self.id_selectionne), None)
                if ent: ent.action_intersection = angle
                
        self.dashboard.btn_dir_nord.clicked.connect(lambda: prevoir_virage(-math.pi/2))
        self.dashboard.btn_dir_sud.clicked.connect(lambda: prevoir_virage(math.pi/2))
        self.dashboard.btn_dir_est.clicked.connect(lambda: prevoir_virage(0.0))
        self.dashboard.btn_dir_ouest.clicked.connect(lambda: prevoir_virage(math.pi))

        def charger_scenario():
            choix = self.dashboard.combo_scenario.currentText()
            self.moteur.entites.clear()
            fichier = ""
            if choix == "Heure de Pointe": fichier = "heure_de_pointe.json"
            elif choix == "Urgences (VTA)": fichier = "urgences.json"
            if fichier:
                chemin = os.path.join(os.path.dirname(__file__), "..", "data", "scenarios", fichier)
                try:
                    with open(chemin, "r", encoding="utf-8") as f:
                        donnees = json.load(f)
                    for item in donnees:
                        v_type_str = item.get("type", "VOITURE")
                        v_type = getattr(TypeVehicule, v_type_str, TypeVehicule.VOITURE)
                        v = Vehicule(id_vehicule=item.get("id", str(uuid.uuid4())[:8]), v_type=v_type)
                        v.pos_x = item.get("pos_x", 0.0)
                        v.pos_y = item.get("pos_y", 0.0)
                        v.cap = item.get("cap", 0.0)
                        v.vitesse = item.get("vitesse", 0.0)
                        self.moteur.ajouter_entite(v)
                except Exception as e:
                    print(f"Erreur chargement {fichier}: {e}")
                    
        self.dashboard.btn_load_scenario.clicked.connect(charger_scenario)

    def closeEvent(self, event):
        if hasattr(self, 'moteur') and self.moteur.isRunning(): self.moteur.arreter()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Esk-2718")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
