"""Point d'entrée principal du client de simulation et interface graphique (IHM).

Ce module initialise l'application Qt, orchestre la scène 2D du carrefour (`CarrefourScene`),
la vue adaptée haute performance (`CarrefourView`), le tableau de bord de commande (`DashboardPanel`),
le fil de calcul cinématique (`MoteurSimulation`) ainsi que le nœud réseau V2X (`ClientNode`).
Il assure également l'auto-scale intégral, le zoom interactif, le HUD télémétrique et l'analyse CLI.
"""

import json
import logging
import math
import os
import socket
import sys
import time
import traceback
import uuid

# Assurer la résolution des imports internes quel que soit le répertoire d'appel
repertoire_src = os.path.abspath(os.path.dirname(__file__))
if repertoire_src not in sys.path:
    sys.path.insert(0, repertoire_src)

from PyQt6.QtCore import QMutexLocker, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QKeyEvent,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QWidget,
)

from gui.carrefour_scene import CarrefourScene, CarrefourView
from gui.dashboard import DashboardPanel
from simulation.environnement import ConditionsMeteo
from simulation.intersection import IntersectionManager
from simulation.moteur import MoteurSimulation
from simulation.vehicules import TypeVehicule, Vehicule

try:
    from network.client_node import ClientNode
except ImportError:
    ClientNode = None

try:
    from network.server_node import ServerNode
except ImportError:
    ServerNode = None

logger = logging.getLogger(__name__)


def parse_arguments(argv: list) -> dict:
    """Analyse les arguments passés en ligne de commande via sys.argv.

    Arguments pris en charge :
        --ip <ip> ou --ip=<ip> : Adresse IP du serveur de régulation.
        --tcp-port <port> ou --tcp-port=<port> : Port TCP du serveur.
        --udp-port <port> ou --udp-port=<port> : Port UDP du serveur (alertes VTA).
        --client-udp-port <port> ou --client-udp-port=<port> : Port UDP d'écoute local du client.
        --windowed : Lancement en mode fenêtré plutôt qu'en plein écran.
        -h ou --help : Affiche l'aide d'utilisation et quitte.

    Args:
        argv (list): Liste des arguments passés en ligne de commande (ex: sys.argv[1:]).

    Returns:
        dict: Dictionnaire associant les paramètres identifiés à leurs valeurs typées.
    """
    cli_params = {}
    idx = 0
    total = len(argv)

    try:
        while idx < total:
            arg = argv[idx]

            if arg in ("-h", "--help"):
                print("Usage: python client_main.py [OPTIONS]")
                print("Options réseau et affichage :")
                print("  --ip <IP>                  Adresse IP du serveur distant (défaut: 127.0.0.1)")
                print("  --tcp-port <PORT>          Port TCP de commande du serveur (défaut: 5000)")
                print("  --udp-port <PORT>          Port UDP d'urgence VTA du serveur (défaut: 5001)")
                print("  --client-udp-port <PORT>   Port UDP local d'écoute du client (défaut: 5002)")
                print("  --windowed                 Ouvre l'application en mode fenêtré au lieu du plein écran")
                sys.exit(0)

            elif arg.startswith("--ip="):
                cli_params["server_ip"] = arg.split("=", 1)[1]
            elif arg == "--ip" and idx + 1 < total:
                idx += 1
                cli_params["server_ip"] = argv[idx]

            elif arg.startswith("--tcp-port=") or arg.startswith("--tcp_port="):
                try:
                    cli_params["server_tcp_port"] = int(arg.split("=", 1)[1])
                except ValueError:
                    logger.warning(f"[CLI] Port TCP invalide spécifié dans {arg}")
            elif arg in ("--tcp-port", "--tcp_port") and idx + 1 < total:
                idx += 1
                try:
                    cli_params["server_tcp_port"] = int(argv[idx])
                except ValueError:
                    logger.warning(f"[CLI] Port TCP invalide : {argv[idx]}")

            elif arg.startswith("--udp-port=") or arg.startswith("--udp_port="):
                try:
                    cli_params["server_udp_port"] = int(arg.split("=", 1)[1])
                except ValueError:
                    logger.warning(f"[CLI] Port UDP invalide spécifié dans {arg}")
            elif arg in ("--udp-port", "--udp_port") and idx + 1 < total:
                idx += 1
                try:
                    cli_params["server_udp_port"] = int(argv[idx])
                except ValueError:
                    logger.warning(f"[CLI] Port UDP invalide : {argv[idx]}")

            elif arg.startswith("--client-udp-port=") or arg.startswith("--client_udp_port="):
                try:
                    cli_params["client_udp_port"] = int(arg.split("=", 1)[1])
                except ValueError:
                    logger.warning(f"[CLI] Port UDP client invalide spécifié dans {arg}")
            elif arg in ("--client-udp-port", "--client_udp_port") and idx + 1 < total:
                idx += 1
                try:
                    cli_params["client_udp_port"] = int(argv[idx])
                except ValueError:
                    logger.warning(f"[CLI] Port UDP client invalide : {argv[idx]}")

            elif arg == "--windowed":
                cli_params["windowed"] = True

            else:
                logger.debug(f"[CLI] Argument non reconnu ou ignoré : {arg}")

            idx += 1

    except Exception as e:
        logger.error(f"[CLI] Erreur lors de l'analyse des arguments : {e}", exc_info=True)

    return cli_params


def load_configuration(cli_args: dict | None = None) -> dict:
    """Charge la configuration depuis config.json et applique les surcharges de la ligne de commande.

    Args:
        cli_args (dict | None, optional): Paramètres extraits de la ligne de commande. Par défaut None.

    Returns:
        dict: Configuration complète résolue pour le nœud client.
    """
    chemins_possibles = [
        os.path.join(os.path.dirname(__file__), "..", "config.json"),
        os.path.join(os.getcwd(), "config.json"),
        "config.json"
    ]

    config = {
        "server_ip": "127.0.0.1",
        "server_tcp_port": 5000,
        "server_udp_port": 5001,
        "client_udp_port": 5002,
        "windowed": False
    }

    fichier_trouve = None
    for p in chemins_possibles:
        if os.path.exists(p):
            fichier_trouve = p
            break

    try:
        if fichier_trouve:
            with open(fichier_trouve, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                config.update(loaded)
                logger.info(f"[Config] Configuration chargée depuis {os.path.abspath(fichier_trouve)}")
        else:
            logger.warning("[Config] config.json introuvable. Valeurs par défaut utilisées.")
    except Exception as e:
        logger.error(
            f"[Config] Erreur lors de la lecture de config.json : {e}. Valeurs par défaut conservées.",
            exc_info=True
        )

    # Application des surcharges CLI (prioritaires sur les valeurs du fichier)
    if cli_args:
        for k, v in cli_args.items():
            config[k] = v
            logger.info(f"[Config] Surcharge CLI appliquée : {k} = {v}")

    return config


class MainWindow(QMainWindow):
    """Fenêtre principale orchestrant la vue graphique, le tableau de bord et la simulation.

    Attributes:
        config (dict): Paramètres de configuration réseau et applicative.
        id_selectionne (str | None): Identifiant du véhicule actuellement suivi dans le HUD.
        type_a_placer (TypeVehicule | None): Outil d'insertion d'usager actuellement actif.
        scene (CarrefourScene): Scène vectorielle 2D du carrefour.
        view (CarrefourView): Vue d'affichage avec auto-scale intégral et zoom molette.
        dashboard (DashboardPanel): Panneau latéral de contrôle Cyber-SCADA en 3 onglets.
        moteur (MoteurSimulation): Thread dédié à l'intégration physique d'Euler.
        client_node (ClientNode | None): Nœud de communication réseau V2X/V2I.
    """

    def __init__(self, config: dict | None = None):
        """Initialise la fenêtre principale, l'interface graphique et le moteur de calcul."""
        super().__init__()
        self.config = config if config is not None else {}
        self.setWindowTitle("Esk-2718 — Simulation Totale VPI/VPO")
        self.setMinimumSize(1280, 800)

        self.id_selectionne = None
        self.type_a_placer = None

        # Construction de l'icône vectorielle de l'application (feu tricolore stylisé)
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

        # Disposition centrale : 72% Scène 2D du carrefour | 28% Dashboard
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scene = CarrefourScene(self)
        self.view = CarrefourView(self.scene, self)
        self.dashboard = DashboardPanel(self)

        layout.addWidget(self.view, stretch=72)
        layout.addWidget(self.dashboard, stretch=28)

        # Bouton flottant de recadrage rapide sur la vue
        self.btn_overlay_reset = QPushButton("🔍 Recadrer Vue (100%) [R]", self.view)
        self.btn_overlay_reset.setStyleSheet("""
            QPushButton {
                background-color: rgba(24, 26, 32, 220);
                color: #00E5FF;
                border: 1px solid #00E5FF;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(0, 229, 255, 40);
            }
        """)
        self.btn_overlay_reset.move(14, 14)
        self.btn_overlay_reset.clicked.connect(self.view.fit_scene)

        # Force une police globale explicite en points (Segoe UI, 9) pour éradiquer tout setPointSize <= 0
        if QApplication.instance():
            default_font = QFont("Segoe UI", 9)
            default_font.setPointSize(9)
            QApplication.instance().setFont(default_font)

        # Moteur cinématique et initialisation réseau V2X
        self.moteur = MoteurSimulation()

        # Innovation Chef d'Orchestre : Auto-serveur local embarqué en fallback
        self.embedded_server = None
        server_ip = str(self.config.get("server_ip", "127.0.0.1"))
        server_tcp_port = int(self.config.get("server_tcp_port", 5000))

        if server_ip in ("127.0.0.1", "localhost"):
            serveur_present = False
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.15)
                    s.connect((server_ip, server_tcp_port))
                    serveur_present = True
            except (ConnectionRefusedError, TimeoutError, OSError):
                serveur_present = False

            if not serveur_present and ServerNode is not None:
                try:
                    self.embedded_server = ServerNode(self.config)
                    self.embedded_server.daemon = True
                    self.embedded_server.start()
                    logger.info(
                        f"[MainWindow] Auto-serveur local démarré en fallback sur {server_ip}:{server_tcp_port}"
                    )
                    time.sleep(0.05)
                except Exception as e_srv:
                    logger.warning(f"[MainWindow] Impossible de démarrer le serveur local en fallback : {e_srv}")
                    self.embedded_server = None

        if ClientNode is not None:
            try:
                self.client_node = ClientNode(self.config, self.moteur)
                self.moteur.network_client = self.client_node
                if hasattr(self.client_node, 'trame_reseau_log'):
                    self.client_node.trame_reseau_log.connect(self.dashboard.ajouter_log_trame)
                if hasattr(self.client_node, 'connexion_statut'):
                    self.client_node.connexion_statut.connect(self.dashboard.set_serveur_connecte)
                self.client_node.start()
            except Exception as e:
                logger.error(f"[MainWindow] Erreur d'initialisation du réseau : {e}", exc_info=True)
                self.client_node = None
                self.moteur.network_client = None

        # Connexions des signaux et slots
        self.moteur.tick_simulation.connect(self.rafraichir_interface)

        self.dashboard.slider_temps.valueChanged.connect(self.change_vitesse)
        self.dashboard.combo_meteo.currentTextChanged.connect(self.change_meteo)
        self.dashboard.btn_toggle_sim.clicked.connect(self.toggle_simulation)
        self.scene.signal_entite_selectionnee.connect(self.selectionner_entite)
        self.scene.signal_clic_vide.connect(self.spawn_clic)

        # Connexions des clics directs sur la carte 2D (exactement comme les boutons du dashboard)
        if hasattr(self.dashboard, 'btn_feux_ns'):
            self.scene.signal_forcer_feux_ns.connect(self.dashboard.btn_feux_ns.click)
        else:
            self.scene.signal_forcer_feux_ns.connect(self.moteur.intersection.forcer_vert_ns)

        if hasattr(self.dashboard, 'btn_feux_eo'):
            self.scene.signal_forcer_feux_eo.connect(self.dashboard.btn_feux_eo.click)
        else:
            self.scene.signal_forcer_feux_eo.connect(self.moteur.intersection.forcer_vert_eo)
        self.scene.signal_toggle_preemption_v2i.connect(self.toggle_preemption_v2i)

        if hasattr(self.dashboard, 'chk_preemption_v2i'):
            self.dashboard.chk_preemption_v2i.toggled.connect(
                lambda chk: (setattr(self.moteur, 'preemption_v2i_active', chk), self.scene.set_preemption_v2i_active(chk))
            )

        if hasattr(self.dashboard, 'btn_recadrer_vue'):
            self.dashboard.btn_recadrer_vue.clicked.connect(self.view.fit_scene)

        self.dashboard.btn_spawn_voiture.clicked.connect(lambda: self.set_type_a_placer(TypeVehicule.VOITURE))
        self.dashboard.btn_spawn_pl.clicked.connect(lambda: self.set_type_a_placer(TypeVehicule.POIDS_LOURD))
        self.dashboard.btn_spawn_vta.clicked.connect(lambda: self.set_type_a_placer(TypeVehicule.VIG_VTA))
        self.dashboard.btn_spawn_pieton.clicked.connect(lambda: self.set_type_a_placer(TypeVehicule.PIETON))
        self.dashboard.btn_spawn_cycliste.clicked.connect(lambda: self.set_type_a_placer(TypeVehicule.CYCLISTE))

        self.dashboard.btn_dir_nord.clicked.connect(lambda: self.prevoir_virage(-math.pi / 2))
        self.dashboard.btn_dir_sud.clicked.connect(lambda: self.prevoir_virage(math.pi / 2))
        self.dashboard.btn_dir_est.clicked.connect(lambda: self.prevoir_virage(0.0))
        self.dashboard.btn_dir_ouest.clicked.connect(lambda: self.prevoir_virage(math.pi))

        self.dashboard.btn_load_scenario.clicked.connect(self.charger_scenario)

        if hasattr(self.dashboard, 'btn_feux_ns'):
            self.dashboard.btn_feux_ns.clicked.connect(self.moteur.intersection.forcer_vert_ns)
        if hasattr(self.dashboard, 'btn_feux_eo'):
            self.dashboard.btn_feux_eo.clicked.connect(self.moteur.intersection.forcer_vert_eo)
        if hasattr(self.dashboard, 'btn_feux_auto'):
            self.dashboard.btn_feux_auto.clicked.connect(self.moteur.intersection.reprendre_mode_automatique)

        # Lancement différé automatique après initialisation complète de la boucle d'événements Qt
        QTimer.singleShot(100, self._startup_routine)

    def toggle_preemption_v2i(self):
        """Bascule l'état de la préemption V2I lors d'un clic direct sur l'antenne RSU."""
        if hasattr(self.dashboard, 'chk_preemption_v2i'):
            nouvel_etat = not self.dashboard.chk_preemption_v2i.isChecked()
            self.dashboard.chk_preemption_v2i.setChecked(nouvel_etat)
            self.scene.set_preemption_v2i_active(nouvel_etat)

    def resizeEvent(self, event):
        """Garantit l'auto-fit de la vue lors de tout redimensionnement de la fenêtre."""
        super().resizeEvent(event)
        if hasattr(self, 'view'):
            self.view.fit_scene()

    def showEvent(self, event):
        """Garantit l'auto-fit initial dès l'affichage de la fenêtre."""
        super().showEvent(event)
        if hasattr(self, 'view'):
            QTimer.singleShot(0, self.view.fit_scene)

    def _startup_routine(self):
        """Exécute la routine de démarrage automatique (chargement du trafic et lancement)."""
        try:
            # Sélection et chargement automatique du scénario 'Heure de Pointe'
            idx = self.dashboard.combo_scenario.findText("Heure de Pointe")
            if idx >= 0:
                self.dashboard.combo_scenario.setCurrentIndex(idx)
            self.charger_scenario()

            # Démarrage effectif du thread de simulation physique
            if not self.moteur.isRunning():
                self.toggle_simulation()

            # Ajustement optimal de l'échelle
            self.view.fit_scene()
        except Exception as e:
            logger.error(f"[MainWindow] Erreur lors de la routine de démarrage : {e}", exc_info=True)

    def rafraichir_interface(self, entites: list, inter: IntersectionManager):
        """Réceptionne l'instantané physique du moteur et actualise la vue et le HUD.

        Args:
            entites (list[EntiteSnapshot]): Liste des instantanés des véhicules actifs.
            inter (IntersectionManager): Copie de l'état des feux tricolores.
        """
        try:
            self.scene.mettre_a_jour_entites(entites, inter, id_selectionne=self.id_selectionne)

            # Mise à jour des informations télémétriques de l'entité sélectionnée dans le HUD
            if self.id_selectionne:
                entite = next((e for e in entites if e.id_entite == self.id_selectionne), None)
                if entite:
                    ec = 0.5 * entite.masse_kg * (entite.vitesse ** 2)
                    texte = f"ID: {entite.id_entite} | {entite.type_entite.name}\n"
                    texte += f"Vitesse: {entite.vitesse_kmh:.1f} km/h\n"
                    texte += f"Masse: {entite.masse_kg:.1f} kg\n"
                    texte += f"Énergie Cinétique: {ec / 1000.0:.1f} kJ\n"
                    if entite.freinage_mecanique:
                        texte += f"Accél: {entite.commande_acceleration:.1f} m/s² [FREIN MÉC.]\n"
                    else:
                        texte += f"Accél: {entite.commande_acceleration:.1f} m/s² [frein mot.]\n"
                    texte += f"ABS: {'Oui' if entite.possede_abs else 'Non'}"
                    texte += f" | Pneus: {entite.age_pneus:.0f} ans ({entite.usure_pneus * 100:.0f}%)\n"
                    texte += f"Cap: {math.degrees(entite.cap):.0f}°"
                    if entite.action_intersection is not None:
                        texte += " [VIRAGE PRÉVU]"
                    self.dashboard.text_hud.setText(texte)
                    if hasattr(self.dashboard, 'update_inspection'):
                        self.dashboard.update_inspection(entite)
                else:
                    self.dashboard.text_hud.setText("Entité perdue ou hors zone.")
                    if hasattr(self.dashboard, 'update_inspection'):
                        self.dashboard.update_inspection(None)
            else:
                if hasattr(self.dashboard, 'update_inspection'):
                    self.dashboard.update_inspection(None)
        except Exception as e:
            logger.error(f"[MainWindow] Erreur lors du rafraîchissement de l'interface : {e}", exc_info=True)

    def change_vitesse(self, val: int):
        """Modifie le multiplicateur de vitesse de la simulation physique.

        Args:
            val (int): Valeur brute du curseur (10 = 1.0x, 20 = 2.0x, etc.).
        """
        try:
            facteur = val / 10.0
            self.moteur.multiplicateur_temps = facteur
            self.dashboard.lbl_temps_valeur.setText(f"{facteur:.1f}x")
        except Exception as e:
            logger.error(f"[MainWindow] Erreur lors du changement de vitesse : {e}", exc_info=True)

    def change_meteo(self, etat: str):
        """Applique une nouvelle condition météo et ajuste l'environnement physique et l'air.

        Args:
            etat (str): Libellé météo sélectionné ("Dégagé", "Pluie", "Tempête", "Gel").
        """
        try:
            self.scene.set_meteo(etat)
            if etat == "Tempête":
                self.moteur.densite_air_rho = 2.5
                if hasattr(self.moteur, 'environnement'):
                    self.moteur.environnement.meteo = ConditionsMeteo.PLUIE
                    self.moteur.environnement.hauteur_eau_mm = 5.0
                    self.moteur.environnement.temperature = 10.0
            elif etat == "Pluie":
                self.moteur.densite_air_rho = 1.5
                if hasattr(self.moteur, 'environnement'):
                    self.moteur.environnement.meteo = ConditionsMeteo.PLUIE
                    self.moteur.environnement.hauteur_eau_mm = 2.5
                    self.moteur.environnement.temperature = 14.0
            elif etat == "Gel":
                self.moteur.densite_air_rho = 1.3
                if hasattr(self.moteur, 'environnement'):
                    self.moteur.environnement.meteo = ConditionsMeteo.GEL
                    self.moteur.environnement.hauteur_eau_mm = 0.0
                    self.moteur.environnement.temperature = -4.0
            else:
                self.moteur.densite_air_rho = 1.225
                if hasattr(self.moteur, 'environnement'):
                    self.moteur.environnement.meteo = ConditionsMeteo.DEGAGE
                    self.moteur.environnement.hauteur_eau_mm = 0.0
                    self.moteur.environnement.temperature = 20.0
        except Exception as e:
            logger.error(f"[MainWindow] Erreur lors du changement météo : {e}", exc_info=True)

    def toggle_simulation(self):
        """Bascule l'état d'exécution du moteur physique entre Marche et Pause."""
        try:
            if self.moteur.isRunning():
                self.moteur.arreter()
                self.dashboard.btn_toggle_sim.setText("▶️ Démarrer Simulation")
                self.dashboard.btn_toggle_sim.setStyleSheet(
                    "background-color: #00E676; color: #181A20; font-weight: bold;"
                )
            else:
                self.moteur.demarrer()
                self.dashboard.btn_toggle_sim.setText("⏸️ Mettre en Pause")
                self.dashboard.btn_toggle_sim.setStyleSheet(
                    "background-color: #F59E0B; color: #181A20; font-weight: bold;"
                )
        except Exception as e:
            logger.error(f"[MainWindow] Erreur lors du basculement de la simulation : {e}", exc_info=True)

    def selectionner_entite(self, entite_id: str):
        """Mémorise l'identifiant de l'entité sélectionnée pour focaliser le suivi télémétrique.

        Args:
            entite_id (str): Identifiant unique de l'entité ciblée.
        """
        self.id_selectionne = entite_id
        # Bascule automatique vers l'onglet inspection pour un confort optimal
        if hasattr(self.dashboard, 'tabs'):
            self.dashboard.tabs.setCurrentIndex(1)

    def spawn_clic(self, x: float, y: float):
        """Insère manuellement un véhicule aux coordonnées cliquées selon la voie sélectionnée.

        Args:
            x (float): Coordonnée cartésienne X du clic en mètres.
            y (float): Coordonnée cartésienne Y du clic en mètres.
        """
        if self.type_a_placer is None:
            return
        try:
            nouvelle = Vehicule(id_vehicule=str(uuid.uuid4())[:8], v_type=self.type_a_placer)
            voie = self.dashboard.combo_voie_spawn.currentText()

            # Positionnement et orientation cinématique selon le profil de la voie
            if voie == "Passage Piéton" or self.type_a_placer == TypeVehicule.PIETON:
                if abs(x) > abs(y):
                    nouvelle.pos_x = 9.0 if x > 0 else -9.0
                    nouvelle.pos_y = max(-4.0, min(4.0, y))
                    nouvelle.cap = math.pi / 2 if y < 0 else -math.pi / 2
                else:
                    nouvelle.pos_x = max(-4.0, min(4.0, x))
                    nouvelle.pos_y = 9.0 if y > 0 else -9.0
                    nouvelle.cap = 0.0 if x < 0 else math.pi
            elif voie == "Nord -> Sud":
                nouvelle.pos_x = -3.6 if self.type_a_placer == TypeVehicule.CYCLISTE else -2.0
                nouvelle.pos_y = y
                nouvelle.cap = math.pi / 2
            elif voie == "Sud -> Nord":
                nouvelle.pos_x = 3.6 if self.type_a_placer == TypeVehicule.CYCLISTE else 2.0
                nouvelle.pos_y = y
                nouvelle.cap = -math.pi / 2
            elif voie == "Est -> Ouest":
                nouvelle.pos_y = -3.6 if self.type_a_placer == TypeVehicule.CYCLISTE else -2.0
                nouvelle.pos_x = x
                nouvelle.cap = math.pi
            elif voie == "Ouest -> Est":
                nouvelle.pos_y = 3.6 if self.type_a_placer == TypeVehicule.CYCLISTE else 2.0
                nouvelle.pos_x = x
                nouvelle.cap = 0.0
            else:
                lat = 3.6 if self.type_a_placer == TypeVehicule.CYCLISTE else 2.0
                if abs(y) < abs(x):
                    nouvelle.pos_x = x
                    nouvelle.pos_y = lat if y > 0 else -lat
                    nouvelle.cap = 0.0 if nouvelle.pos_y > 0 else math.pi
                else:
                    nouvelle.pos_y = y
                    nouvelle.pos_x = lat if x > 0 else -lat
                    nouvelle.cap = math.pi / 2 if nouvelle.pos_x < 0 else -math.pi / 2

            if self.type_a_placer == TypeVehicule.CYCLISTE:
                nouvelle.action_intersection = None
                nouvelle.en_virage_bezier = False
            nouvelle.vitesse = 0.0
            self.moteur.ajouter_entite(nouvelle)

            # Désélectionne l'outil de placement sauf si la touche Majuscule (Shift) est maintenue
            modifiers = QApplication.keyboardModifiers()
            if not (modifiers & Qt.KeyboardModifier.ShiftModifier):
                self.set_type_a_placer(None)

        except Exception as e:
            logger.error(f"[MainWindow] Erreur lors du placement manuel de l'entité : {e}", exc_info=True)

    def prevoir_virage(self, angle: float):
        """Assigne une consigne de virage à l'entité actuellement sélectionnée.

        Args:
            angle (float): Cap consigne en radians à adopter au franchissement du carrefour.
        """
        try:
            if self.id_selectionne:
                with QMutexLocker(self.moteur.mutex):
                    ent = next((e for e in self.moteur.entites if e.id_entite == self.id_selectionne), None)
                    if ent and getattr(ent, 'type_entite', None) not in (TypeVehicule.CYCLISTE, TypeVehicule.VIG_VTA):
                        ent.action_intersection = angle
        except Exception as e:
            logger.error(f"[MainWindow] Erreur lors de la programmation du virage : {e}", exc_info=True)

    def charger_scenario(self):
        """Charge un fichier scénario JSON décrivant une disposition initiale de trafic."""
        try:
            choix = self.dashboard.combo_scenario.currentText()
            self.moteur.vider_entites()
            fichier = ""
            if choix == "Heure de Pointe":
                fichier = "heure_de_pointe.json"
            elif choix == "Urgences (VTA)":
                fichier = "urgences.json"

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
                        if v_type == TypeVehicule.CYCLISTE:
                            v.action_intersection = None
                            v.en_virage_bezier = False
                            if abs(math.cos(v.cap)) > 0.5:
                                v.pos_y = 3.6 if math.cos(v.cap) > 0 else -3.6
                            else:
                                v.pos_x = -3.6 if math.sin(v.cap) > 0 else 3.6
                        self.moteur.ajouter_entite(v)

        except Exception as e:
            logger.error(f"[MainWindow] Erreur lors du chargement du scénario : {e}", exc_info=True)

    def set_type_a_placer(self, t: TypeVehicule | None):
        """Active ou désactive l'outil d'insertion pour une catégorie d'usager donnée.

        Args:
            t (TypeVehicule | None): Catégorie d'usager à placer, ou None pour repasser en mode sélection.
        """
        try:
            self.type_a_placer = t
            if t is not None:
                self.dashboard.lbl_mode_placement.setText(f"Prêt à placer : {t.name}")
            else:
                self.dashboard.lbl_mode_placement.setText("Mode : Sélection")

            if t is None:
                self.scene.supprimer_hologramme()
        except Exception as e:
            logger.error(f"[MainWindow] Erreur lors du paramétrage de l'outil de placement : {e}", exc_info=True)

    def keyPressEvent(self, event: QKeyEvent):
        """Assure le traitement des raccourcis clavier numériques et de contrôle.

        Raccourcis :
            - Touche 1 : Voiture
            - Touche 2 : Poids lourd
            - Touche 3 : Véhicule prioritaire VTA
            - Touche 4 : Piéton
            - Touche 5 : Cycliste
            - Touche R : Recadrer la vue (100% fit)
            - Échap     : Annulation du mode placement

        Args:
            event (QKeyEvent): Événement clavier Qt.
        """
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
            elif event.key() == Qt.Key.Key_R:
                self.view.fit_scene()
            elif event.key() == Qt.Key.Key_Escape:
                self.set_type_a_placer(None)
            super().keyPressEvent(event)
        except Exception as e:
            logger.error(f"[MainWindow] Erreur lors du traitement des raccourcis clavier : {e}", exc_info=True)

    def closeEvent(self, event):
        """Intercepte la fermeture de la fenêtre pour arrêter proprement les threads et connexions.

        Args:
            event (QCloseEvent): Événement de fermeture Qt.
        """
        try:
            if hasattr(self, 'moteur') and self.moteur.isRunning():
                self.moteur.arreter()
            if hasattr(self, 'client_node') and self.client_node is not None:
                self.client_node.stop()
            if hasattr(self, 'embedded_server') and self.embedded_server is not None:
                self.embedded_server.stop()
            event.accept()
        except Exception as e:
            logger.error(f"[MainWindow] Erreur lors de la fermeture de l'application : {e}", exc_info=True)
            event.accept()


def global_exception_hook(exctype, value, tb):
    """Gestionnaire global des exceptions non interceptées (sys.excepthook)."""
    error_msg = "".join(traceback.format_exception(exctype, value, tb))
    logger.critical(f"Arrêt d'urgence du système - Crash non intercepté : {error_msg}")

    try:
        with open("fatal_crash.log", "a", encoding="utf-8") as f:
            f.write(error_msg + "\n")
    except Exception as log_err:
        logger.error(f"Impossible d'écrire dans fatal_crash.log : {log_err}", exc_info=True)

    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setWindowTitle("Arrêt d'urgence du système")
    msg_box.setText("Une erreur critique non interceptée est survenue dans l'application.")
    msg_box.setInformativeText(str(value))
    msg_box.setDetailedText(error_msg)
    msg_box.exec()
    sys.exit(1)


sys.excepthook = global_exception_hook


def main():
    """Point d'entrée d'exécution du client simulateur."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )

    cli_params = parse_arguments(sys.argv[1:])
    config = load_configuration(cli_params)

    app = QApplication(sys.argv)
    app.setApplicationName("Esk-2718")
    default_font = QFont("Segoe UI", 9)
    default_font.setPointSize(9)
    app.setFont(default_font)
    w = MainWindow(config)

    if config.get("windowed", False):
        w.resize(1300, 850)
        w.show()
    else:
        w.showFullScreen()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
