import logging
logger = logging.getLogger(__name__)

import sys
import traceback
import uuid
import math
import json
import os

from PyQt6.QtWidgets import QApplication, QMainWindow, QHBoxLayout, QWidget, QGraphicsView, QMessageBox
from PyQt6.QtGui import QPainter, QIcon, QPixmap, QColor, QPen, QLinearGradient
from PyQt6.QtCore import Qt, QMutexLocker, QTimer

from gui.carrefour_scene import CarrefourScene
from gui.dashboard import DashboardPanel
from simulation.moteur import MoteurSimulation
from simulation.vehicules import Vehicule, TypeVehicule

try:
    from network.client_node import ClientNode
except ImportError:
    ClientNode = None

class MainWindow(QMainWindow):
    def __init__(self, config=None):
        super().__init__()
        self.config = config if config is not None else {}
        self.setWindowTitle("Esk-2718 — Simulation Totale VPI/VPO")
        self.setMinimumSize(1300, 850)
        
        self.id_selectionne = None
        self.type_a_placer = None 
        
        icon_pixmap = QPixmap(256, 256)
        icon_pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(icon_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        road_gradient = QLinearGradient(0, 0, 256, 256)
        road_gradient.setColorAt(0.0, QColor("#3a3a3a"))
        road_gradient.setColorAt(1.0, QColor("#1f1f1f"))
        painter.setBrush(road_gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(16, 16, 224, 224, 32, 32)
        
        painter.setPen(QPen(QColor("#ffffff"), 12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(128, 16, 128, 96)
        painter.drawLine(128, 160, 128, 240)
        painter.drawLine(16, 128, 96, 128)
        painter.drawLine(160, 128, 240, 128)
        
        painter.setBrush(QColor("#222222"))
        painter.setPen(QPen(QColor("#555555"), 4))
        painter.drawRoundedRect(96, 64, 64, 128, 16, 16)
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#F44336"))
        painter.drawEllipse(112, 76, 32, 32)
        painter.setBrush(QColor("#4CAF50"))
        painter.drawEllipse(112, 148, 32, 32)
        
        gloss = QLinearGradient(96, 64, 160, 192)
        gloss.setColorAt(0.0, QColor(255, 255, 255, 40))
        gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(gloss)
        painter.drawRoundedRect(96, 64, 64, 128, 16, 16)
        
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
        self.view.setMouseTracking(True)
        
        self.dashboard = DashboardPanel(self)

        layout.addWidget(self.view, stretch=1)
        layout.addWidget(self.dashboard)

        self.moteur = MoteurSimulation()
        
        if ClientNode is not None:
            try:
                self.client_node = ClientNode(self.config, self.moteur)
                self.moteur.network_client = self.client_node
                self.client_node.start()
            except Exception as e:
                logger.error(f"Erreur d'initialisation du réseau : {e}", exc_info=True)
                self.client_node = None
                self.moteur.network_client = None

        # Connections
        self.moteur.tick_simulation.connect(self.rafraichir_interface)
        
        self.dashboard.slider_temps.valueChanged.connect(self.change_vitesse)
        self.dashboard.combo_meteo.currentTextChanged.connect(self.change_meteo)
        self.dashboard.btn_toggle_sim.clicked.connect(self.toggle_simulation)
        self.scene.signal_entite_selectionnee.connect(self.selectionner_entite)
        self.scene.signal_clic_vide.connect(self.spawn_clic)
        
        self.dashboard.btn_spawn_voiture.clicked.connect(lambda: self.set_type_a_placer(TypeVehicule.VOITURE))
        self.dashboard.btn_spawn_pl.clicked.connect(lambda: self.set_type_a_placer(TypeVehicule.POIDS_LOURD))
        self.dashboard.btn_spawn_vta.clicked.connect(lambda: self.set_type_a_placer(TypeVehicule.VIG_VTA))
        self.dashboard.btn_spawn_pieton.clicked.connect(lambda: self.set_type_a_placer(TypeVehicule.PIETON))
        self.dashboard.btn_spawn_cycliste.clicked.connect(lambda: self.set_type_a_placer(TypeVehicule.CYCLISTE))
        
        self.dashboard.btn_dir_nord.clicked.connect(lambda: self.prevoir_virage(-math.pi/2))
        self.dashboard.btn_dir_sud.clicked.connect(lambda: self.prevoir_virage(math.pi/2))
        self.dashboard.btn_dir_est.clicked.connect(lambda: self.prevoir_virage(0.0))
        self.dashboard.btn_dir_ouest.clicked.connect(lambda: self.prevoir_virage(math.pi))

        self.dashboard.btn_load_scenario.clicked.connect(self.charger_scenario)
        
        if hasattr(self.dashboard, 'btn_feux_ns'):
            self.dashboard.btn_feux_ns.clicked.connect(self.moteur.intersection.forcer_vert_ns)
        if hasattr(self.dashboard, 'btn_feux_eo'):
            self.dashboard.btn_feux_eo.clicked.connect(self.moteur.intersection.forcer_vert_eo)

        # Automatic startup with QTimer to ensure the event loop is running
        QTimer.singleShot(100, self._startup_routine)

    def _startup_routine(self):
        try:
            # Set a default scenario to show traffic immediately
            idx = self.dashboard.combo_scenario.findText("Heure de Pointe")
            if idx >= 0:
                self.dashboard.combo_scenario.setCurrentIndex(idx)
            self.charger_scenario()
            # Start simulation
            if not self.moteur.isRunning():
                self.toggle_simulation()
        except Exception as e:
            logger.error(f"Error during startup routine: {e}")

    def rafraichir_interface(self, entites, inter):
        try:
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
        except Exception as e:
            logger.error(f"Erreur rafraîchissement interface: {e}", exc_info=True)

    def change_vitesse(self, val):
        try:
            self.moteur.multiplicateur_temps = val/10.0
            self.dashboard.lbl_temps_valeur.setText(f"{val/10.0:.1f}x")
        except Exception as e:
            logger.error(f"Erreur change_vitesse: {e}", exc_info=True)

    def change_meteo(self, etat):
        try:
            self.scene.set_meteo(etat)
            if etat == "Tempête": self.moteur.densite_air_rho = 2.5
            elif etat == "Pluie": self.moteur.densite_air_rho = 1.5
            else: self.moteur.densite_air_rho = 1.225
        except Exception as e:
            logger.error(f"Erreur change_meteo: {e}", exc_info=True)

    def toggle_simulation(self):
        try:
            if self.moteur.isRunning():
                self.moteur.arreter()
                self.dashboard.btn_toggle_sim.setText("▶️ Démarrer Simulation")
                self.dashboard.btn_toggle_sim.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
            else:
                self.moteur.demarrer()
                self.dashboard.btn_toggle_sim.setText("⏸️ Mettre en Pause")
                self.dashboard.btn_toggle_sim.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold;")
        except Exception as e:
            logger.error(f"Erreur toggle_simulation: {e}", exc_info=True)

    def selectionner_entite(self, entite_id):
        self.id_selectionne = entite_id

    def spawn_clic(self, x, y):
        if self.type_a_placer is None:
            return
        try:
            nouvelle = Vehicule(id_vehicule=str(uuid.uuid4())[:8], v_type=self.type_a_placer)
            voie = self.dashboard.combo_voie_spawn.currentText()
            
            if voie == "Passage Piéton" or self.type_a_placer == TypeVehicule.PIETON:
                if abs(x) > abs(y):
                    nouvelle.pos_x = 9.0 if x > 0 else -9.0
                    nouvelle.pos_y = max(-4.0, min(4.0, y))
                    nouvelle.cap = math.pi/2 if y < 0 else -math.pi/2
                else:
                    nouvelle.pos_x = max(-4.0, min(4.0, x))
                    nouvelle.pos_y = 9.0 if y > 0 else -9.0
                    nouvelle.cap = 0.0 if x < 0 else math.pi
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
                    nouvelle.pos_x = 2.0 if x > 0 else -2.0
                    nouvelle.cap = math.pi/2 if nouvelle.pos_x < 0 else -math.pi/2
                
            nouvelle.vitesse = 0.0
            self.moteur.ajouter_entite(nouvelle)
            
            modifiers = QApplication.keyboardModifiers()
            if not (modifiers & Qt.KeyboardModifier.ShiftModifier):
                self.set_type_a_placer(None)
        except Exception as e:
            logger.error(f"Erreur de placement : {e}", exc_info=True)

    def prevoir_virage(self, angle):
        try:
            if self.id_selectionne:
                with QMutexLocker(self.moteur.mutex):
                    ent = next((e for e in self.moteur.entites if e.id_entite == self.id_selectionne), None)
                    if ent: ent.action_intersection = angle
        except Exception as e:
            logger.error(f"Erreur prevoir_virage: {e}", exc_info=True)

    def charger_scenario(self):
        try:
            choix = self.dashboard.combo_scenario.currentText()
            self.moteur.vider_entites()
            fichier = ""
            if choix == "Heure de Pointe": fichier = "heure_de_pointe.json"
            elif choix == "Urgences (VTA)": fichier = "urgences.json"
            if fichier:
                chemin = os.path.join(os.path.dirname(__file__), "..", "data", "scenarios", fichier)
                if os.path.exists(chemin):
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
            logger.error(f"Erreur chargement scenario: {e}", exc_info=True)

    def set_type_a_placer(self, t):
        try:
            self.type_a_placer = t
            if t is not None:
                self.dashboard.lbl_mode_placement.setText(f"Prêt à placer : {t.name}")
            else:
                self.dashboard.lbl_mode_placement.setText("Mode : Sélection")
                
            if t is None and self.scene.hologramme is not None:
                self.scene.removeItem(self.scene.hologramme)
                self.scene.hologramme = None
                self.scene.type_hologramme = None
        except Exception as e:
            logger.error(f"Erreur set_type_a_placer: {e}", exc_info=True)

    def keyPressEvent(self, event):
        try:
            if event.key() == Qt.Key.Key_1:
                self.dashboard.btn_spawn_voiture.click()
            elif event.key() == Qt.Key.Key_2:
                self.dashboard.btn_spawn_pl.click()
            elif event.key() == Qt.Key.Key_3:
                self.dashboard.btn_spawn_vta.click()
            elif event.key() == Qt.Key.Key_4:
                self.dashboard.btn_spawn_pieton.click()
            elif event.key() == Qt.Key.Key_5:
                self.dashboard.btn_spawn_cycliste.click()
            elif event.key() == Qt.Key.Key_Escape:
                self.set_type_a_placer(None)
            super().keyPressEvent(event)
        except Exception as e:
            logger.error(f"Erreur raccourcis clavier: {e}", exc_info=True)

    def closeEvent(self, event):
        try:
            if hasattr(self, 'moteur') and self.moteur.isRunning(): 
                self.moteur.arreter()
            if hasattr(self, 'client_node') and self.client_node is not None: 
                self.client_node.stop()
            event.accept()
        except Exception as e:
            logger.error(f"Erreur closeEvent: {e}", exc_info=True)
            event.accept()

def global_exception_hook(exctype, value, tb):
    error_msg = "".join(traceback.format_exception(exctype, value, tb))
    try:
        with open("fatal_crash.log", "a", encoding="utf-8") as f:
            f.write(error_msg + "\n")
    except:
        pass
    
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setWindowTitle("Fatal Crash")
    msg_box.setText("A fatal error occurred.")
    msg_box.setInformativeText(str(value))
    msg_box.setDetailedText(error_msg)
    msg_box.exec()
    sys.exit(1)

sys.excepthook = global_exception_hook

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        config = {}
        
    app = QApplication(sys.argv)
    app.setApplicationName("Esk-2718")
    w = MainWindow(config)
    w.showFullScreen()
    sys.exit(app.exec())
