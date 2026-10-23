"""Panneau latéral de contrôle et tableau de bord statistique Cyber-SCADA pour Esk-2718.

Fournit l'ensemble des commandes de simulation (météo, feux tricolores, insertion d'usagers,
sélection de scénarios) ainsi que la restitution statistique en temps réel
(cartes KPIs 2x2 permanentes, 3 onglets compacts, inspection usager avec barres de progression,
courbes pyqtgraph et persistance SQLite relationnelle).
Conforme aux spécifications de la SAÉ 3.02 (Esk-2718).
"""

import logging
import os
import time
from datetime import datetime

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from database.db_manager import DBManager
from gui.graphiques import FenetreGraphiques

try:
    from simulation.vehicules import TypeVehicule
except ImportError:
    TypeVehicule = None

logger = logging.getLogger(__name__)


class DialogHistorique(QDialog):
    """Boîte de dialogue modale affichant l'historique des simulations passées stockées en BDD."""

    def __init__(self, db_manager: DBManager, parent: QWidget | None = None):
        """Initialise la boîte de dialogue d'historique.

        Args:
            db_manager (DBManager): Instance active du gestionnaire de base de données.
            parent (QWidget | None): Widget parent Qt.
        """
        super().__init__(parent)
        self.db = db_manager
        self.setWindowTitle("📜 Historique des Simulations — Esk-2718")
        self.setMinimumSize(720, 440)
        self.setStyleSheet("""
            QDialog { background-color: #181A20; color: #FFFFFF; }
            QTableWidget {
                background-color: #222630;
                color: #FFFFFF;
                gridline-color: #333947;
                selection-background-color: #0284C7;
                border: 1px solid #333947;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #181A20;
                color: #00E5FF;
                font-weight: bold;
                padding: 6px;
                border: 1px solid #333947;
            }
            QPushButton {
                background-color: #222630;
                color: #FFFFFF;
                border: 1px solid #333947;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2D3342; border-color: #00E5FF; }
        """)

        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "ID",
            "Date de Début",
            "Scénario",
            "Durée (s)",
            "Nb Métriques",
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(lambda row, col: self._visualiser_selection())
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.btn_exporter = QPushButton("📁 Exporter la sélection en CSV")
        self.btn_exporter.setStyleSheet("background-color: #10B981; color: white; border: none;")
        self.btn_exporter.clicked.connect(self._exporter_selection)

        self.btn_visualiser = QPushButton("📈 Visualiser les Courbes")
        self.btn_visualiser.setStyleSheet("background-color: #0284C7; color: white; border: none;")
        self.btn_visualiser.clicked.connect(self._visualiser_selection)

        self.btn_rafraichir = QPushButton("🔄 Rafraîchir")
        self.btn_rafraichir.clicked.connect(self.charger_donnees)

        btn_fermer = QPushButton("Fermer")
        btn_fermer.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_exporter)
        btn_layout.addWidget(self.btn_visualiser)
        btn_layout.addWidget(self.btn_rafraichir)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_fermer)
        layout.addLayout(btn_layout)

        self.charger_donnees()

    def charger_donnees(self):
        """Charge l'ensemble des simulations passées depuis la base SQLite."""
        try:
            simulations = self.db.get_historique_simulations()
            self.table.setRowCount(len(simulations))
            for row_idx, sim in enumerate(simulations):
                sim_id = sim["id"]
                nb_mets = sim.get("nb_metriques", 0)
                duree = float(sim.get("duree_secondes") or 0.0)

                self.table.setItem(row_idx, 0, QTableWidgetItem(str(sim_id)))
                self.table.setItem(row_idx, 1, QTableWidgetItem(str(sim.get("date_debut", ""))))
                self.table.setItem(row_idx, 2, QTableWidgetItem(str(sim.get("scenario", ""))))
                self.table.setItem(row_idx, 3, QTableWidgetItem(f"{duree:.1f}"))
                self.table.setItem(row_idx, 4, QTableWidgetItem(str(nb_mets)))
        except Exception as e:
            logger.error(f"[DialogHistorique] Erreur lors du chargement des simulations: {e}", exc_info=True)

    def _exporter_selection(self):
        """Exporte les métriques de la simulation sélectionnée vers un fichier CSV."""
        ligne_sel = self.table.currentRow()
        if ligne_sel < 0:
            QMessageBox.warning(self, "Sélection requise", "Veuillez sélectionner une simulation dans la liste.")
            return

        item_id = self.table.item(ligne_sel, 0)
        if not item_id:
            return
        sim_id = int(item_id.text())

        mets = self.db.get_metriques_simulation(sim_id)
        if not mets:
            QMessageBox.information(
                self,
                "Données Absentes",
                f"Aucune métrique n'est enregistrée pour la simulation {sim_id}.",
            )
            return

        chemin, _ = QFileDialog.getSaveFileName(
            self,
            f"Exporter la simulation {sim_id}",
            f"simulation_{sim_id}.csv",
            "Fichiers CSV (*.csv)",
        )
        if chemin:
            if self.db.exporter_csv(sim_id, chemin):
                QMessageBox.information(
                    self,
                    "Export Réussi",
                    f"Les {len(mets)} métriques de la simulation {sim_id} ont été exportées dans :\n{chemin}",
                )
            else:
                QMessageBox.critical(
                    self,
                    "Erreur",
                    "Impossible d'exporter les données de la simulation.",
                )

    def _visualiser_selection(self):
        """Affiche les graphiques détaillés pour la simulation passée sélectionnée."""
        ligne_sel = self.table.currentRow()
        if ligne_sel < 0:
            QMessageBox.warning(self, "Sélection requise", "Veuillez sélectionner une simulation dans la liste.")
            return

        item_id = self.table.item(ligne_sel, 0)
        if not item_id:
            return
        sim_id = int(item_id.text())
        metriques = self.db.get_metriques_simulation(sim_id)
        if not metriques:
            QMessageBox.information(
                self,
                "Données Absentes",
                f"Aucune métrique n'a été enregistrée pour la simulation {sim_id}.",
            )
            return

        scenario = self.table.item(ligne_sel, 2).text() if self.table.item(ligne_sel, 2) else ""
        fenetre = FenetreGraphiques(self)
        fenetre.setWindowTitle(f"📈 Métriques de la Simulation #{sim_id} ({scenario})")
        fenetre.charger_metriques(metriques)
        fenetre.exec()


class DashboardPanel(QWidget):
    """Panneau latéral Cyber-SCADA contenant les cartes KPIs permanentes et 3 onglets thématiques."""

    def __init__(self, parent: QWidget | None = None, db: DBManager | None = None):
        """Initialise l'ensemble des composants graphiques et le moteur de métriques.

        Args:
            parent (QWidget | None): Widget parent Qt.
            db (DBManager | None): Gestionnaire BDD partagé ou nouvellement instancié.
        """
        super().__init__(parent)
        self.setMinimumWidth(360)
        self.setMaximumWidth(420)

        # Base de données et métriques d'exécution
        self.db = db if db is not None else DBManager()
        self.simulation_id = None
        self.temps_debut_sim = None
        self._dernier_insert_db = 0.0
        self._dernier_point_graph = 0.0
        self._dernier_etat_feux = None

        # Suivi des incidents et des temps de passage
        self._total_incidents = 0
        self._vehicules_en_freinage = set()
        self._vehicules_entree = {}  # eid -> timestamp entrée
        self._temps_passages = []  # durées réelles de franchissement
        self.fenetre_graphiques = None

        # Séries pour la fenêtre glissante pyqtgraph de 60 points
        self.historique_temps = []
        self.historique_vitesse = []
        self.historique_vehicules = []

        # Sniffer Mini-Wireshark et compteurs V2X
        self._compteur_tcp = 0
        self._compteur_udp = 0
        self._lignes_mini_wireshark = []

        # Usager sélectionné
        self._entite_inspectee = None

        # Configuration de la feuille de style globale Cyber-SCADA
        self.setStyleSheet("""
            QWidget {
                background-color: #181A20;
                color: #F8FAFC;
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            }
            QGroupBox {
                border: 1px solid #333947;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
                font-size: 11px;
                color: #00E5FF;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QPushButton {
                background-color: #222630;
                color: #FFFFFF;
                border: 1px solid #333947;
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2D3342;
                border-color: #00E5FF;
            }
            QPushButton:pressed {
                background-color: #1E232E;
            }
            QComboBox {
                background-color: #222630;
                color: #FFFFFF;
                border: 1px solid #333947;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QComboBox QAbstractItemView {
                background-color: #222630;
                color: #FFFFFF;
                selection-background-color: #0284C7;
                border: 1px solid #333947;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #222630;
                border-radius: 3px;
                border: 1px solid #333947;
            }
            QSlider::sub-page:horizontal {
                background: #00E5FF;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                border: 2px solid #00E5FF;
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }
            QProgressBar {
                background-color: #222630;
                border: 1px solid #333947;
                border-radius: 4px;
                text-align: center;
                color: #FFFFFF;
                font-size: 10px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #00E5FF;
                border-radius: 3px;
            }
            QTabWidget::pane {
                border: 1px solid #333947;
                border-radius: 8px;
                background: #181A20;
                top: -1px;
            }
            QTabBar::tab {
                background: #222630;
                color: #94A3B8;
                border: 1px solid #333947;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 7px 10px;
                font-weight: bold;
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background: #181A20;
                color: #00E5FF;
                border-bottom: 2px solid #00E5FF;
            }
            QTabBar::tab:hover:!selected {
                background: #282D3A;
                color: #FFFFFF;
            }
        """)

        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(8, 8, 8, 8)
        layout_principal.setSpacing(8)

        # -------------------------------------------------------------
        # ZONE 1 : EN-TÊTE PERMANENT - GRILLE 2X2 DE 4 CARTES KPI
        # -------------------------------------------------------------
        kpi_container = QFrame()
        kpi_container.setStyleSheet("""
            QFrame {
                background-color: #222630;
                border: 1px solid #333947;
                border-radius: 8px;
            }
        """)
        grid_kpi = QGridLayout(kpi_container)
        grid_kpi.setContentsMargins(8, 8, 8, 8)
        grid_kpi.setSpacing(8)

        # Helper pour créer une carte KPI Cyber-SCADA
        def creer_carte_kpi(titre: str, val_widget: QLabel, sub_widget: QLabel, bg_color="#181A20"):
            carte = QFrame()
            carte.setStyleSheet(f"""
                QFrame {{
                    background-color: {bg_color};
                    border: 1px solid #333947;
                    border-radius: 6px;
                    padding: 4px;
                }}
            """)
            c_layout = QVBoxLayout(carte)
            c_layout.setContentsMargins(6, 4, 6, 4)
            c_layout.setSpacing(2)

            lbl_titre = QLabel(titre)
            lbl_titre.setStyleSheet("color: #94A3B8; font-size: 9px; font-weight: bold; border: none;")

            val_widget.setStyleSheet(val_widget.styleSheet() + " border: none;")
            sub_widget.setStyleSheet("color: #64748B; font-size: 9px; border: none;")

            c_layout.addWidget(lbl_titre)
            c_layout.addWidget(val_widget)
            c_layout.addWidget(sub_widget)
            return carte

        # Carte 1 : Trafic Actif
        self.lbl_veh_count = QLabel("0")
        self.lbl_veh_count.setStyleSheet("color: #00E5FF; font-size: 20pt; font-weight: bold;")
        self.lbl_kpi_pietons = QLabel("0 véh. | 0 piét.")
        carte_1 = creer_carte_kpi("🚗 TRAFIC ACTIF", self.lbl_veh_count, self.lbl_kpi_pietons)

        # Carte 2 : Vitesse Moyenne
        self.lbl_avg_speed = QLabel("0.0 km/h")
        self.lbl_avg_speed.setStyleSheet("color: #00E676; font-size: 20pt; font-weight: bold;")
        self.lbl_kpi_vitesse_sub = QLabel("Fluidité nominale")
        carte_2 = creer_carte_kpi("⚡ VITESSE MOY.", self.lbl_avg_speed, self.lbl_kpi_vitesse_sub)

        # Carte 3 : Temps Franchissement VTA
        self.lbl_temps_vta = QLabel("0.0s")
        self.lbl_temps_vta.setStyleSheet("color: #FF9100; font-size: 20pt; font-weight: bold;")
        self.lbl_kpi_vta_sub = QLabel("Gain V2I: -45%")
        carte_3 = creer_carte_kpi("⏱️ FRANCHISSEMENT VTA", self.lbl_temps_vta, self.lbl_kpi_vta_sub)

        # Carte 4 : Adhérence Chaussée mu
        self.lbl_adherence_mu = QLabel("µ = 0.85")
        self.lbl_adherence_mu.setStyleSheet("color: #FFD54F; font-size: 20pt; font-weight: bold;")
        self.lbl_kpi_meteo_sub = QLabel("Chaussée Sèche")
        carte_4 = creer_carte_kpi("🌧️ ADHÉRENCE µ", self.lbl_adherence_mu, self.lbl_kpi_meteo_sub)

        # Attributs requis par les tests unitaires existants
        self.lbl_incidents = QLabel("0")
        self.lbl_temps_passage = QLabel("0.0 s")
        self.lbl_vehicules_franchis = QLabel("0")

        grid_kpi.addWidget(carte_1, 0, 0)
        grid_kpi.addWidget(carte_2, 0, 1)
        grid_kpi.addWidget(carte_3, 1, 0)
        grid_kpi.addWidget(carte_4, 1, 1)

        layout_principal.addWidget(kpi_container)

        # -------------------------------------------------------------
        # ZONE 2 : CORPS ORGANISÉ EN 3 ONGLETS (POUR NE JAMAIS SCROLLER)
        # -------------------------------------------------------------
        self.tabs = QTabWidget()

        # =============================================================
        # ONGLET 1 : PILOTAGE & TRAFIC
        # =============================================================
        tab_pilotage = QWidget()
        lay_tab1 = QVBoxLayout(tab_pilotage)
        lay_tab1.setContentsMargins(6, 6, 6, 6)
        lay_tab1.setSpacing(6)

        # Contrôles de simulation
        grp_sim = QGroupBox("🎮 Contrôles Simulation")
        sim_layout = QVBoxLayout(grp_sim)
        sim_layout.setContentsMargins(8, 8, 8, 8)
        sim_layout.setSpacing(6)

        self.btn_toggle_sim = QPushButton("▶️ Démarrer Simulation")
        self.btn_toggle_sim.setStyleSheet(
            "background-color: #00E676; color: #181A20; font-weight: bold; font-size: 12px; padding: 7px;"
        )

        row_vitesse = QHBoxLayout()
        row_vitesse.addWidget(QLabel("Vitesse :"))
        self.slider_temps = QSlider(Qt.Orientation.Horizontal)
        self.slider_temps.setRange(5, 50)
        self.slider_temps.setValue(10)
        self.lbl_temps_valeur = QLabel("1.0x")
        self.lbl_temps_valeur.setStyleSheet("color: #00E5FF; font-weight: bold; min-width: 32px;")
        row_vitesse.addWidget(self.slider_temps)
        row_vitesse.addWidget(self.lbl_temps_valeur)

        row_meteo = QHBoxLayout()
        row_meteo.addWidget(QLabel("Météo :"))
        self.combo_meteo = QComboBox()
        self.combo_meteo.addItems(["Dégagé", "Pluie", "Tempête", "Gel"])
        row_meteo.addWidget(self.combo_meteo)

        row_scen = QHBoxLayout()
        self.combo_scenario = QComboBox()
        self.combo_scenario.addItems(["-- Scénarios JSON --", "Heure de Pointe", "Urgences (VTA)"])
        self.btn_load_scenario = QPushButton("Charger")
        self.btn_load_scenario.setStyleSheet("background-color: #0284C7; color: white;")
        row_scen.addWidget(self.combo_scenario, stretch=2)
        row_scen.addWidget(self.btn_load_scenario, stretch=1)

        sim_layout.addWidget(self.btn_toggle_sim)
        sim_layout.addLayout(row_vitesse)
        sim_layout.addLayout(row_meteo)
        sim_layout.addLayout(row_scen)
        lay_tab1.addWidget(grp_sim)

        # Insertion d'usagers
        grp_spawn = QGroupBox("🚗 Insertion d'Usagers")
        spawn_layout = QVBoxLayout(grp_spawn)
        spawn_layout.setContentsMargins(8, 8, 8, 8)
        spawn_layout.setSpacing(6)

        row_spawn_ctrl = QHBoxLayout()
        self.combo_voie_spawn = QComboBox()
        self.combo_voie_spawn.addItems([
            "Auto (proche)",
            "Nord -> Sud",
            "Sud -> Nord",
            "Est -> Ouest",
            "Ouest -> Est",
            "Passage Piéton",
        ])
        self.lbl_mode_placement = QLabel("Sélection active")
        self.lbl_mode_placement.setStyleSheet("color: #FBBF24; font-size: 10px;")
        row_spawn_ctrl.addWidget(self.combo_voie_spawn, stretch=1)
        row_spawn_ctrl.addWidget(self.lbl_mode_placement, stretch=1)

        grid_spawn = QGridLayout()
        grid_spawn.setSpacing(4)
        self.btn_spawn_voiture = QPushButton("🚗 Voiture [1]")
        self.btn_spawn_pl = QPushButton("🚛 Poids Lourd [2]")
        self.btn_spawn_vta = QPushButton("🚑 VTA Urgence [3]")
        self.btn_spawn_vta.setStyleSheet("background-color: #EF4444; color: white; font-weight: bold;")
        self.btn_spawn_pieton = QPushButton("🚶 Piéton [4]")
        self.btn_spawn_cycliste = QPushButton("🚲 Cycliste [5]")

        grid_spawn.addWidget(self.btn_spawn_voiture, 0, 0)
        grid_spawn.addWidget(self.btn_spawn_pl, 0, 1)
        grid_spawn.addWidget(self.btn_spawn_vta, 1, 0)
        grid_spawn.addWidget(self.btn_spawn_pieton, 1, 1)
        grid_spawn.addWidget(self.btn_spawn_cycliste, 2, 0, 1, 2)

        spawn_layout.addLayout(row_spawn_ctrl)
        spawn_layout.addLayout(grid_spawn)
        lay_tab1.addWidget(grp_spawn)

        # Contrôle des Feux & Préemption V2I
        grp_feux = QGroupBox("🚦 Contrôle Feux & V2I")
        feux_layout = QVBoxLayout(grp_feux)
        feux_layout.setContentsMargins(8, 8, 8, 8)
        feux_layout.setSpacing(6)

        grid_feux = QGridLayout()
        grid_feux.setSpacing(4)
        self.btn_feux_ns = QPushButton("🟢 Vert Nord-Sud")
        self.btn_feux_eo = QPushButton("🟢 Vert Est-Ouest")
        self.btn_feux_auto = QPushButton("🔄 Auto Adaptatif")
        self.btn_recadrer_vue = QPushButton("🔍 Recadrer Vue (100%)")
        self.btn_recadrer_vue.setStyleSheet("background-color: #1E293B; border-color: #00E5FF; color: #00E5FF;")

        grid_feux.addWidget(self.btn_feux_ns, 0, 0)
        grid_feux.addWidget(self.btn_feux_eo, 0, 1)
        grid_feux.addWidget(self.btn_feux_auto, 1, 0)
        grid_feux.addWidget(self.btn_recadrer_vue, 1, 1)

        self.chk_preemption_v2i = QCheckBox("📡 Préemption V2I Active (Ondes & Feux)")
        self.chk_preemption_v2i.setChecked(True)
        self.chk_preemption_v2i.setStyleSheet("color: #00E5FF; font-weight: bold; font-size: 11px;")
        self.chk_preemption_v2i.toggled.connect(self._sur_toggle_v2i)

        feux_layout.addLayout(grid_feux)
        feux_layout.addWidget(self.chk_preemption_v2i)
        lay_tab1.addWidget(grp_feux)
        lay_tab1.addStretch()

        # =============================================================
        # ONGLET 2 : INSPECTION USAGER
        # =============================================================
        tab_inspection = QWidget()
        lay_tab2 = QVBoxLayout(tab_inspection)
        lay_tab2.setContentsMargins(6, 6, 6, 6)
        lay_tab2.setSpacing(6)

        grp_inspect = QGroupBox("🎯 Télémétrie Usager Sélectionné")
        inspect_layout = QVBoxLayout(grp_inspect)
        inspect_layout.setContentsMargins(8, 8, 8, 8)
        inspect_layout.setSpacing(6)

        self.lbl_inspect_title = QLabel("Cliquez sur un usager pour l'inspecter")
        self.lbl_inspect_title.setStyleSheet("color: #00E5FF; font-size: 11px; font-weight: bold;")
        inspect_layout.addWidget(self.lbl_inspect_title)

        # Barres de progression télémétriques
        # Vitesse
        self.lbl_vitesse_bar = QLabel("Vitesse : 0.0 / 50.0 km/h")
        self.lbl_vitesse_bar.setStyleSheet("font-size: 10px; color: #CBD5E1;")
        self.pbar_vitesse = QProgressBar()
        self.pbar_vitesse.setRange(0, 130)
        self.pbar_vitesse.setValue(0)
        self.pbar_vitesse.setStyleSheet("QProgressBar::chunk { background-color: #00E5FF; }")

        # Énergie cinétique
        self.lbl_energie_bar = QLabel("Énergie Cinétique : 0.0 kJ")
        self.lbl_energie_bar.setStyleSheet("font-size: 10px; color: #CBD5E1;")
        self.pbar_energie = QProgressBar()
        self.pbar_energie.setRange(0, 500)
        self.pbar_energie.setValue(0)
        self.pbar_energie.setStyleSheet("QProgressBar::chunk { background-color: #F59E0B; }")

        # Distance obstacle
        self.lbl_distance_bar = QLabel("Distance Obstacle : Voie Libre")
        self.lbl_distance_bar.setStyleSheet("font-size: 10px; color: #CBD5E1;")
        self.pbar_distance = QProgressBar()
        self.pbar_distance.setRange(0, 50)
        self.pbar_distance.setValue(50)
        self.pbar_distance.setStyleSheet("QProgressBar::chunk { background-color: #10B981; }")

        # Freinage & Pneus
        row_pneus = QHBoxLayout()
        self.lbl_freinage_badge = QLabel("FREINAGE : AUCUN")
        self.lbl_freinage_badge.setStyleSheet(
            "background-color: #1E293B; color: #10B981; border: 1px solid #333947; "
            "border-radius: 4px; padding: 2px 6px; font-size: 9px; font-weight: bold;"
        )
        self.lbl_pneus_info = QLabel("ABS: Oui | Pneus: 100%")
        self.lbl_pneus_info.setStyleSheet("font-size: 10px; color: #94A3B8;")
        row_pneus.addWidget(self.lbl_freinage_badge)
        row_pneus.addStretch()
        row_pneus.addWidget(self.lbl_pneus_info)

        inspect_layout.addWidget(self.lbl_vitesse_bar)
        inspect_layout.addWidget(self.pbar_vitesse)
        inspect_layout.addWidget(self.lbl_energie_bar)
        inspect_layout.addWidget(self.pbar_energie)
        inspect_layout.addWidget(self.lbl_distance_bar)
        inspect_layout.addWidget(self.pbar_distance)
        inspect_layout.addLayout(row_pneus)

        # Moniteur HUD texte (requis par les tests)
        self.text_hud = QTextEdit()
        self.text_hud.setReadOnly(True)
        self.text_hud.setMaximumHeight(85)
        self.text_hud.setStyleSheet(
            "background-color: #0F172A; color: #38BDF8; font-family: Consolas, monospace; "
            "font-size: 10px; border: 1px solid #1E293B; border-radius: 6px;"
        )
        self.text_hud.setText("Cliquez sur un usager...")
        inspect_layout.addWidget(self.text_hud)
        lay_tab2.addWidget(grp_inspect)

        # Actions interactives sur l'usager sélectionné
        grp_actions = QGroupBox("⚡ Actions sur l'Usager Sélectionné")
        actions_layout = QVBoxLayout(grp_actions)
        actions_layout.setContentsMargins(8, 8, 8, 8)
        actions_layout.setSpacing(6)

        actions_layout.addWidget(QLabel("Programmer virage :"))
        dir_layout = QHBoxLayout()
        self.btn_dir_nord = QPushButton("⬆️ Nord")
        self.btn_dir_sud = QPushButton("⬇️ Sud")
        self.btn_dir_ouest = QPushButton("⬅️ Ouest")
        self.btn_dir_est = QPushButton("➡️ Est")
        dir_layout.addWidget(self.btn_dir_nord)
        dir_layout.addWidget(self.btn_dir_sud)
        dir_layout.addWidget(self.btn_dir_ouest)
        dir_layout.addWidget(self.btn_dir_est)
        actions_layout.addLayout(dir_layout)

        row_interventions = QHBoxLayout()
        self.btn_simuler_panne = QPushButton("⚠️ Simuler Arrêt / Panne")
        self.btn_simuler_panne.setStyleSheet("background-color: #D97706; color: white;")
        self.btn_simuler_panne.clicked.connect(self._action_simuler_panne)

        self.btn_supprimer_usager = QPushButton("🗑️ Supprimer Usager")
        self.btn_supprimer_usager.setStyleSheet("background-color: #DC2626; color: white;")
        self.btn_supprimer_usager.clicked.connect(self._action_supprimer_usager)

        row_interventions.addWidget(self.btn_simuler_panne)
        row_interventions.addWidget(self.btn_supprimer_usager)
        actions_layout.addLayout(row_interventions)

        lay_tab2.addWidget(grp_actions)
        lay_tab2.addStretch()

        # =============================================================
        # ONGLET 3 : RÉSEAU V2X & STATS
        # =============================================================
        tab_v2x = QWidget()
        lay_tab3 = QVBoxLayout(tab_v2x)
        lay_tab3.setContentsMargins(6, 6, 6, 6)
        lay_tab3.setSpacing(6)

        # Mini-Wireshark
        grp_sniffer = QGroupBox("📡 Supervision Réseau V2X (Mini-Wireshark)")
        sniffer_layout = QVBoxLayout(grp_sniffer)
        sniffer_layout.setContentsMargins(8, 8, 8, 8)
        sniffer_layout.setSpacing(4)

        row_sniff_hdr = QHBoxLayout()
        self.lbl_status_serveur = QLabel("[LOCAL] AUTONOME")
        self.lbl_status_serveur.setStyleSheet("color: #F59E0B; font-weight: bold; font-size: 10px;")
        self.lbl_compteur_paquets = QLabel("TCP: 0 | UDP: 0")
        self.lbl_compteur_paquets.setStyleSheet("color: #94A3B8; font-size: 10px;")
        row_sniff_hdr.addWidget(self.lbl_status_serveur)
        row_sniff_hdr.addStretch()
        row_sniff_hdr.addWidget(self.lbl_compteur_paquets)
        sniffer_layout.addLayout(row_sniff_hdr)

        self.list_trames_v2x = QTextEdit()
        self.list_trames_v2x.setReadOnly(True)
        self.list_trames_v2x.setMaximumHeight(85)
        self.list_trames_v2x.setStyleSheet(
            "background-color: #0F172A; color: #38BDF8; font-family: Consolas, monospace; "
            "font-size: 9px; border: 1px solid #1E293B; border-radius: 4px;"
        )
        self.list_trames_v2x.setText("En attente de trames V2X/V2I...")
        sniffer_layout.addWidget(self.list_trames_v2x)
        lay_tab3.addWidget(grp_sniffer)

        # Graphique pyqtgraph temps réel
        grp_graph = QGroupBox("📈 Vitesse Moyenne en Temps Réel")
        graph_layout = QVBoxLayout(grp_graph)
        graph_layout.setContentsMargins(4, 4, 4, 4)
        graph_layout.setSpacing(4)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#181A20")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.setLabel("bottom", "Temps (s)", color="#94A3B8")
        self.plot_widget.setLabel("left", "Vitesse (km/h)", color="#94A3B8")
        self.plot_widget.setMinimumHeight(120)
        self.plot_widget.setMaximumHeight(150)

        pen_vitesse = pg.mkPen(color="#00E5FF", width=2.5)
        self.courbe_vitesse = self.plot_widget.plot(pen=pen_vitesse, name="Vitesse Moyenne")
        graph_layout.addWidget(self.plot_widget)

        self.btn_graphiques_detailles = QPushButton("🔍 Graphiques Détaillés (Double)")
        self.btn_graphiques_detailles.setStyleSheet("background-color: #0284C7; color: white;")
        self.btn_graphiques_detailles.clicked.connect(self.ouvrir_graphiques_detailles)
        graph_layout.addWidget(self.btn_graphiques_detailles)
        lay_tab3.addWidget(grp_graph)

        # Synthèse et BDD
        grp_db = QGroupBox("💾 Persistance & Export")
        db_layout = QVBoxLayout(grp_db)
        db_layout.setContentsMargins(8, 8, 8, 8)
        db_layout.setSpacing(6)

        row_db_kpi = QHBoxLayout()
        lbl_inc_title = QLabel("Incidents :")
        lbl_inc_title.setStyleSheet("color: #94A3B8; font-size: 10px;")
        self.lbl_incidents.setStyleSheet("color: #EF4444; font-weight: bold; font-size: 11px;")

        lbl_pass_title = QLabel("Passage :")
        lbl_pass_title.setStyleSheet("color: #94A3B8; font-size: 10px;")
        self.lbl_temps_passage.setStyleSheet("color: #F59E0B; font-weight: bold; font-size: 11px;")

        lbl_franchis_title = QLabel("Franchis :")
        lbl_franchis_title.setStyleSheet("color: #94A3B8; font-size: 10px;")
        self.lbl_vehicules_franchis.setStyleSheet("color: #10B981; font-weight: bold; font-size: 11px;")

        row_db_kpi.addWidget(lbl_inc_title)
        row_db_kpi.addWidget(self.lbl_incidents)
        row_db_kpi.addSpacing(10)
        row_db_kpi.addWidget(lbl_pass_title)
        row_db_kpi.addWidget(self.lbl_temps_passage)
        row_db_kpi.addSpacing(10)
        row_db_kpi.addWidget(lbl_franchis_title)
        row_db_kpi.addWidget(self.lbl_vehicules_franchis)
        db_layout.addLayout(row_db_kpi)

        row_db_btns = QHBoxLayout()
        self.btn_export_csv = QPushButton("💾 Exporter CSV")
        self.btn_export_csv.setStyleSheet("background-color: #10B981; color: white;")
        self.btn_historique = QPushButton("📜 Historique")
        self.btn_historique.setStyleSheet("background-color: #4F46E5; color: white;")
        self.btn_export_csv.clicked.connect(self.exporter_csv_courant)
        self.btn_historique.clicked.connect(self.ouvrir_historique)
        row_db_btns.addWidget(self.btn_export_csv)
        row_db_btns.addWidget(self.btn_historique)
        db_layout.addLayout(row_db_btns)

        lay_tab3.addWidget(grp_db)
        lay_tab3.addStretch()

        # Ajout des 3 onglets
        self.tabs.addTab(tab_pilotage, "🎮 Pilotage & Trafic")
        self.tabs.addTab(tab_inspection, "🎯 Inspection Usager")
        self.tabs.addTab(tab_v2x, "📊 Réseau V2X & Stats")

        layout_principal.addWidget(self.tabs)

        # Connexions d'événements pour la persistance en base de données
        self.btn_load_scenario.clicked.connect(self._reinitialiser_session_scenario)
        self.combo_meteo.currentTextChanged.connect(self._sur_changement_meteo)
        self.btn_spawn_vta.clicked.connect(self._sur_spawn_vta)
        self.btn_feux_ns.clicked.connect(lambda: self._enregistrer_evt("FEUX_MANUEL", "Axe N/S forcé au vert"))
        self.btn_feux_eo.clicked.connect(lambda: self._enregistrer_evt("FEUX_MANUEL", "Axe E/O forcé au vert"))
        self.btn_feux_auto.clicked.connect(lambda: self._enregistrer_evt("FEUX_AUTO", "Reprise du cycle automatique"))

    def _action_simuler_panne(self):
        """Force l'arrêt ou le redémarrage du véhicule actuellement sélectionné."""
        p = self.parent()
        while p is not None:
            if hasattr(p, "moteur") and hasattr(p, "id_selectionne") and p.id_selectionne:
                from PyQt6.QtCore import QMutexLocker
                with QMutexLocker(p.moteur.mutex):
                    ent = next((e for e in p.moteur.entites if e.id_entite == p.id_selectionne), None)
                    if ent:
                        if getattr(ent, "vitesse", 0.0) > 0.1:
                            ent._vitesse_avant_panne = ent.vitesse
                            ent.vitesse = 0.0
                            ent.en_panne = True
                            self.btn_simuler_panne.setText("▶️ Relancer Véhicule")
                            self.btn_simuler_panne.setStyleSheet("background-color: #10B981; color: white;")
                        else:
                            ent.vitesse = getattr(ent, "_vitesse_avant_panne", 8.0)
                            ent.en_panne = False
                            self.btn_simuler_panne.setText("⚠️ Simuler Arrêt / Panne")
                            self.btn_simuler_panne.setStyleSheet("background-color: #D97706; color: white;")
                break
            p = p.parent()

    def _action_supprimer_usager(self):
        """Retire proprement l'usager sélectionné du moteur de simulation."""
        p = self.parent()
        while p is not None:
            if hasattr(p, "moteur") and hasattr(p, "id_selectionne") and p.id_selectionne:
                from PyQt6.QtCore import QMutexLocker
                with QMutexLocker(p.moteur.mutex):
                    p.moteur.entites = [e for e in p.moteur.entites if e.id_entite != p.id_selectionne]
                p.id_selectionne = None
                self.reset_inspection()
                break
            p = p.parent()

    def reset_inspection(self):
        """Réinitialise les indicateurs de l'onglet inspection."""
        self.lbl_inspect_title.setText("Cliquez sur un usager pour l'inspecter")
        self.pbar_vitesse.setValue(0)
        self.lbl_vitesse_bar.setText("Vitesse : 0.0 / 50.0 km/h")
        self.pbar_energie.setValue(0)
        self.lbl_energie_bar.setText("Énergie Cinétique : 0.0 kJ")
        self.pbar_distance.setValue(50)
        self.lbl_distance_bar.setText("Distance Obstacle : Voie Libre")
        self.lbl_freinage_badge.setText("FREINAGE : AUCUN")
        self.lbl_freinage_badge.setStyleSheet(
            "background-color: #1E293B; color: #10B981; border: 1px solid #333947; "
            "border-radius: 4px; padding: 2px 6px; font-size: 9px; font-weight: bold;"
        )
        self.lbl_pneus_info.setText("ABS: Oui | Pneus: 100%")
        self.text_hud.setText("Cliquez sur un usager...")
        self.btn_simuler_panne.setText("⚠️ Simuler Arrêt / Panne")
        self.btn_simuler_panne.setStyleSheet("background-color: #D97706; color: white;")

    def update_inspection(self, entite):
        """Actualise les jauges et badges de l'usager sélectionné.

        Args:
            entite: EntiteSnapshot ou Vehicule sélectionné.
        """
        if entite is None:
            self.reset_inspection()
            return

        eid = getattr(entite, "id_entite", "N/A")
        t_name = getattr(getattr(entite, "type_entite", None), "name", str(getattr(entite, "type_entite", "")))
        self.lbl_inspect_title.setText(f"Véhicule #{eid} [{t_name}]")

        v_kmh = float(getattr(entite, "vitesse_kmh", 0.0))
        v_max = float(getattr(entite, "vitesse_max_kmh", 50.0)) or 50.0
        self.pbar_vitesse.setMaximum(int(v_max * 1.2))
        self.pbar_vitesse.setValue(int(v_kmh))
        self.lbl_vitesse_bar.setText(f"Vitesse : {v_kmh:.1f} / {v_max:.0f} km/h")

        masse = float(getattr(entite, "masse_kg", 1200.0))
        v_ms = float(getattr(entite, "vitesse", 0.0))
        ec_kj = (0.5 * masse * (v_ms ** 2)) / 1000.0
        self.pbar_energie.setValue(min(500, int(ec_kj)))
        self.lbl_energie_bar.setText(f"Énergie Cinétique : {ec_kj:.1f} kJ ({masse:.0f} kg)")

        # Distance obstacle
        dist_obs = getattr(entite, "distance_obstacle", None)
        if dist_obs is not None and dist_obs < 100.0:
            self.pbar_distance.setValue(min(50, int(dist_obs)))
            self.lbl_distance_bar.setText(f"Distance Obstacle : {dist_obs:.1f} m")
            if dist_obs < 15.0:
                self.pbar_distance.setStyleSheet("QProgressBar::chunk { background-color: #EF4444; }")
            else:
                self.pbar_distance.setStyleSheet("QProgressBar::chunk { background-color: #10B981; }")
        else:
            self.pbar_distance.setValue(50)
            self.lbl_distance_bar.setText("Distance Obstacle : Voie Libre")
            self.pbar_distance.setStyleSheet("QProgressBar::chunk { background-color: #10B981; }")

        # Freinage badge
        is_frein_mec = getattr(entite, "freinage_mecanique", False)
        is_panne = getattr(entite, "en_panne", False)
        accel = float(getattr(entite, "commande_acceleration", 0.0))

        if is_panne:
            self.lbl_freinage_badge.setText("ÉTAT : EN PANNE")
            self.lbl_freinage_badge.setStyleSheet(
                "background-color: #7F1D1D; color: #FCA5A5; border: 1px solid #DC2626; "
                "border-radius: 4px; padding: 2px 6px; font-size: 9px; font-weight: bold;"
            )
        elif is_frein_mec:
            self.lbl_freinage_badge.setText("FREINAGE : MÉCANIQUE (ABS)")
            self.lbl_freinage_badge.setStyleSheet(
                "background-color: #7F1D1D; color: #F87171; border: 1px solid #EF4444; "
                "border-radius: 4px; padding: 2px 6px; font-size: 9px; font-weight: bold;"
            )
        elif accel < -0.5:
            self.lbl_freinage_badge.setText("FREINAGE : MOTEUR")
            self.lbl_freinage_badge.setStyleSheet(
                "background-color: #1E3A8A; color: #60A5FA; border: 1px solid #2563EB; "
                "border-radius: 4px; padding: 2px 6px; font-size: 9px; font-weight: bold;"
            )
        else:
            self.lbl_freinage_badge.setText("PROPULSION : NOMINALE")
            self.lbl_freinage_badge.setStyleSheet(
                "background-color: #064E3B; color: #34D399; border: 1px solid #059669; "
                "border-radius: 4px; padding: 2px 6px; font-size: 9px; font-weight: bold;"
            )

        # Pneus & ABS
        abs_ok = "Oui" if getattr(entite, "possede_abs", True) else "Non"
        usure = getattr(entite, "usure_pneus", 0.1)
        age = getattr(entite, "age_pneus", 1.0)
        sante = max(0, int((1.0 - usure) * 100))
        self.lbl_pneus_info.setText(f"ABS: {abs_ok} | Pneus: {sante}% ({age:.0f} ans)")

    def _enregistrer_evt(
        self,
        type_evt: str,
        description: str,
        pos_x: float = 0.0,
        pos_y: float = 0.0,
    ):
        """Enregistre un événement discret en BDD en garantissant l'existence d'une simulation active."""
        try:
            if self.simulation_id is None:
                scen = self.combo_scenario.currentText()
                if scen.startswith("--"):
                    scen = "Standard"
                self.simulation_id = self.db.creer_simulation(scen)
            self.db.insert_evenement(self.simulation_id, type_evt, description, pos_x, pos_y)
        except Exception as e:
            logger.error(f"Erreur enregistrement événement: {e}", exc_info=True)

    def _sur_changement_meteo(self, meteo: str):
        """Enregistre l'événement de changement de météo."""
        self._enregistrer_evt("METEO", f"Météo passée à '{meteo}'")

    def _sur_spawn_vta(self):
        """Enregistre l'apparition d'un véhicule prioritaire VTA."""
        self._enregistrer_evt("ALERTE_VTA", "Demande de priorité véhicule d'urgence (VTA)")

    def _reinitialiser_session_scenario(self):
        """Réinitialise la session de simulation et les courbes lors d'un changement de scénario."""
        try:
            scenario_nom = self.combo_scenario.currentText()
            if scenario_nom.startswith("--"):
                scenario_nom = "Standard"

            self.simulation_id = self.db.creer_simulation(scenario_nom)
            self.temps_debut_sim = time.time()
            self._total_incidents = 0
            self._vehicules_en_freinage.clear()
            self._vehicules_entree.clear()
            self._temps_passages.clear()
            self.historique_temps.clear()
            self.historique_vitesse.clear()
            self.historique_vehicules.clear()
            self._dernier_etat_feux = None

            self.courbe_vitesse.setData([], [])
            self.lbl_veh_count.setText("0")
            self.lbl_avg_speed.setText("0.0 km/h")
            self.lbl_incidents.setText("0")
            self.lbl_temps_passage.setText("0.0 s")
            self.lbl_vehicules_franchis.setText("0")
            self.lbl_kpi_pietons.setText("0 véh. | 0 piét.")
            self.reset_inspection()

            if self.fenetre_graphiques is not None:
                self.fenetre_graphiques.graphique.reinitialiser()

            self.db.insert_evenement(self.simulation_id, "SCENARIO", f"Chargement du scénario '{scenario_nom}'")
        except Exception as e:
            logger.error(f"Erreur réinitialisation scénario: {e}", exc_info=True)

    def showEvent(self, event):
        """Connecte automatiquement le signal de tick du moteur lors de l'affichage."""
        super().showEvent(event)
        if not hasattr(self, "_connected_stats"):
            p = self.parent()
            while p is not None:
                if hasattr(p, "moteur") and hasattr(p.moteur, "tick_simulation"):
                    p.moteur.tick_simulation.connect(self.update_from_tick)
                    self._connected_stats = True
                    break
                p = p.parent()

    def update_from_tick(self, entites, inter):
        """Met à jour les métriques, KPIs, graphiques et la base SQLite lors de chaque tick.

        Args:
            entites (list): Liste des entités physiques de la simulation.
            inter (IntersectionManager): Gestionnaire des feux de signalisation.
        """
        try:
            now = time.time()
            if self.temps_debut_sim is None:
                self.temps_debut_sim = now

            nb = len(entites)
            vitesses = [e.vitesse_kmh for e in entites if hasattr(e, "vitesse_kmh")]
            avg = sum(vitesses) / nb if nb > 0 else 0.0

            # 1. Comptage des piétons actifs
            nb_pietons = 0
            for e in entites:
                t = getattr(e, "type_entite", None)
                if (TypeVehicule is not None and t == TypeVehicule.PIETON) or str(t) == "TypeVehicule.PIETON":
                    nb_pietons += 1

            nb_vehicules_purs = nb - nb_pietons
            self.lbl_kpi_pietons.setText(f"{nb_vehicules_purs} véh. | {nb_pietons} piét.")

            # 2. Détection robuste des freinages d'urgence / incidents (comptabilisés 1 seule fois par épisode)
            freinant_ids = {
                getattr(e, "id_entite", None)
                for e in entites
                if getattr(e, "freinage_mecanique", False) and getattr(e, "id_entite", None) is not None
            }
            nouveaux_freinages = freinant_ids - self._vehicules_en_freinage
            if nouveaux_freinages:
                self._total_incidents += len(nouveaux_freinages)
                for eid in nouveaux_freinages:
                    ent = next((e for e in entites if getattr(e, "id_entite", None) == eid), None)
                    px = getattr(ent, "pos_x", 0.0) if ent else 0.0
                    py = getattr(ent, "pos_y", 0.0) if ent else 0.0
                    if self.simulation_id is not None:
                        self.db.insert_evenement(
                            self.simulation_id,
                            "INCIDENT",
                            f"Freinage d'urgence véhicule {eid}",
                            px,
                            py,
                        )
            self._vehicules_en_freinage = freinant_ids

            # 3. Calcul du temps moyen de passage au carrefour (|x| < 25m et |y| < 25m)
            entites_ids_actuels = {getattr(e, "id_entite", None) for e in entites}
            for e in entites:
                eid = getattr(e, "id_entite", None)
                if not eid:
                    continue
                px = abs(getattr(e, "pos_x", 999.0))
                py = abs(getattr(e, "pos_y", 999.0))
                dans_carrefour = px < 25.0 and py < 25.0

                if dans_carrefour and eid not in self._vehicules_entree:
                    self._vehicules_entree[eid] = now
                elif not dans_carrefour and eid in self._vehicules_entree:
                    temps_franchissement = now - self._vehicules_entree.pop(eid)
                    if 0.5 < temps_franchissement < 60.0:
                        self._temps_passages.append(temps_franchissement)
                        if len(self._temps_passages) > 50:
                            self._temps_passages.pop(0)

            # Nettoyage des véhicules ayant quitté la scène sans franchir la zone extérieure
            ids_morts = [
                eid for eid, t_in in self._vehicules_entree.items()
                if eid not in entites_ids_actuels and (now - t_in > 10.0)
            ]
            for eid in ids_morts:
                self._vehicules_entree.pop(eid, None)

            # Restitution du KPI de temps de passage
            if self._temps_passages:
                temps_moyen = sum(self._temps_passages) / len(self._temps_passages)
                self.lbl_temps_passage.setText(f"{temps_moyen:.1f} s")
            elif avg > 1.0:
                # Estimation géométrique (zone de carrefour de 40 mètres / vitesse convertie en m/s)
                temps_estime = 40.0 / (avg / 3.6)
                self.lbl_temps_passage.setText(f"{temps_estime:.1f} s")
            else:
                self.lbl_temps_passage.setText("0.0 s")

            # 4. Actualisation des labels KPIs dans l'IHM
            self.lbl_veh_count.setText(str(nb))
            self.lbl_avg_speed.setText(f"{avg:.1f} km/h")
            self.lbl_incidents.setText(str(self._total_incidents))

            # Actualisation des KPIs d'aide à la décision et V2I
            t_vta = getattr(inter, 'temps_franchissement_moyen_vta', 0.0)
            gain = getattr(inter, 'gain_temps_estime_pct', 45.0)
            veh_franchis = getattr(inter, 'vehicules_franchis_total', 0)
            mu = getattr(inter, 'mu', 0.85)

            if hasattr(self, 'lbl_temps_vta'):
                if t_vta > 0.0:
                    self.lbl_temps_vta.setText(f"{t_vta:.1f}s")
                    self.lbl_temps_vta.setStyleSheet("color: #00E676; font-size: 20pt; font-weight: bold; border: none;")
                    self.lbl_kpi_vta_sub.setText(f"Priorité active (-{gain:.0f}%)")
                else:
                    self.lbl_temps_vta.setText("0.0s")
                    self.lbl_temps_vta.setStyleSheet("color: #FF9100; font-size: 20pt; font-weight: bold; border: none;")
                    self.lbl_kpi_vta_sub.setText(f"En attente VTA (-{gain:.0f}%)")

            if hasattr(self, 'lbl_vehicules_franchis'):
                self.lbl_vehicules_franchis.setText(str(veh_franchis))

            if hasattr(self, 'lbl_adherence_mu'):
                qualite = "Sec" if mu >= 0.70 else "Pluie" if mu >= 0.30 else "Verglas"
                self.lbl_adherence_mu.setText(f"µ = {mu:.2f}")
                self.lbl_kpi_meteo_sub.setText(f"Chaussée {qualite}")

            # 5. Échantillonnage de la courbe pyqtgraph (rolling window de 60 points)
            t_relatif = round(now - self.temps_debut_sim, 1)
            if now - self._dernier_point_graph >= 0.5:
                self._dernier_point_graph = now
                self.historique_temps.append(t_relatif)
                self.historique_vitesse.append(avg)
                self.historique_vehicules.append(nb)

                if len(self.historique_temps) > 60:
                    self.historique_temps = self.historique_temps[-60:]
                    self.historique_vitesse = self.historique_vitesse[-60:]
                    self.historique_vehicules = self.historique_vehicules[-60:]

                self.courbe_vitesse.setData(self.historique_temps, self.historique_vitesse)

                # Propagation automatique vers la fenêtre détaillée si créée
                if self.fenetre_graphiques is not None:
                    self.fenetre_graphiques.ajouter_point(t_relatif, avg, nb)

            # 6. Sauvegarde périodique en base SQLite (cadencée à 1 seconde)
            if now - self._dernier_insert_db >= 1.0:
                self._dernier_insert_db = now
                if self.simulation_id is None:
                    scenario_actuel = self.combo_scenario.currentText()
                    if scenario_actuel.startswith("--"):
                        scenario_actuel = "Standard"
                    self.simulation_id = self.db.creer_simulation(scenario_actuel)

                self.db.insert_metrique(
                    self.simulation_id,
                    nb_vehicules=nb,
                    vitesse_moy=avg,
                    nb_pietons=nb_pietons,
                    nb_incidents=self._total_incidents,
                )

                if inter is not None and hasattr(inter, "feu_ns") and hasattr(inter, "feu_eo"):
                    val_ns = getattr(inter.feu_ns, "value", 1)
                    val_eo = getattr(inter.feu_eo, "value", 3)
                    etat_courant = (val_ns, val_eo)
                    if etat_courant != self._dernier_etat_feux:
                        self._dernier_etat_feux = etat_courant
                        self.db.insert_etat_feux(self.simulation_id, val_ns, val_eo)
                        self.db.insert_evenement(
                            self.simulation_id,
                            "TRANSITION_FEUX",
                            f"Changement d'état feux: NS={val_ns}, EO={val_eo}",
                        )

                self.db.mettre_a_jour_duree(self.simulation_id, t_relatif)

        except Exception as e:
            logger.error(f"Erreur update_from_tick: {e}", exc_info=True)

    def exporter_csv_courant(self):
        """Ouvre un dialogue de sélection de fichier et exporte les métriques de la simulation courante."""
        try:
            target_id = self.simulation_id
            metriques = self.db.get_metriques_simulation(target_id)
            if not metriques:
                QMessageBox.warning(
                    self,
                    "Aucune Donnée",
                    "Aucune métrique n'est enregistrée pour le moment. Lancez la simulation avant d'exporter.",
                )
                return

            nom_fichier = f"simulation_{target_id or 'courante'}.csv"
            chemin, _ = QFileDialog.getSaveFileName(
                self,
                "Exporter les métriques en CSV",
                nom_fichier,
                "Fichiers CSV (*.csv)",
            )
            if chemin:
                succes = self.db.exporter_csv(target_id, chemin)
                if succes:
                    QMessageBox.information(
                        self,
                        "Export Réussi",
                        f"Les {len(metriques)} métriques ont été exportées avec succès dans :\n{chemin}",
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "Export Échoué",
                        "Une erreur s'est produite lors de la génération du fichier CSV.",
                    )
        except Exception as e:
            logger.error(f"Erreur export CSV: {e}", exc_info=True)

    def ouvrir_historique(self):
        """Ouvre la boîte de dialogue modale d'historique des simulations passées."""
        try:
            dialogue = DialogHistorique(self.db, self)
            dialogue.exec()
        except Exception as e:
            logger.error(f"Erreur ouverture historique: {e}", exc_info=True)

    def ouvrir_graphiques_detailles(self):
        """Affiche la fenêtre de graphiques détaillés temps réel synchronisée avec l'historique."""
        try:
            if self.fenetre_graphiques is None:
                self.fenetre_graphiques = FenetreGraphiques(self)
                # Pré-remplissage avec l'ensemble des points accumulés dans la session courante
                for t, v, n in zip(self.historique_temps, self.historique_vitesse, self.historique_vehicules):
                    self.fenetre_graphiques.ajouter_point(t, v, n)

            self.fenetre_graphiques.show()
            self.fenetre_graphiques.raise_()
            self.fenetre_graphiques.activateWindow()
        except Exception as e:
            logger.error(f"Erreur ouverture graphiques détaillés: {e}", exc_info=True)

    def _sur_toggle_v2i(self, checked: bool):
        """Notifie le moteur physique de l'état d'activation de la préemption V2I."""
        p = self.parent()
        while p is not None:
            if hasattr(p, "moteur"):
                setattr(p.moteur, "preemption_v2i_active", checked)
                break
            p = p.parent()

    def set_serveur_connecte(self, connecte: bool):
        """Met à jour l'indicateur visuel de connexion au serveur SCADA."""
        if hasattr(self, "lbl_status_serveur"):
            if connecte:
                self.lbl_status_serveur.setText("[ONLINE TCP/UDP] CONNECTE")
                self.lbl_status_serveur.setStyleSheet("color: #10B981; font-weight: bold; font-size: 10px;")
            else:
                self.lbl_status_serveur.setText("[AUTONOME LOCAL]")
                self.lbl_status_serveur.setStyleSheet("color: #F59E0B; font-weight: bold; font-size: 10px;")

    def ajouter_log_trame(self, direction: str, proto: str, seq: int, taille: int, type_trame: str):
        """Enregistre et affiche une trame dans le moniteur réseau Mini-Wireshark."""
        if proto.upper() == "TCP":
            self._compteur_tcp += 1
        elif proto.upper() == "UDP":
            self._compteur_udp += 1

        if hasattr(self, "lbl_compteur_paquets"):
            self.lbl_compteur_paquets.setText(f"TCP: {self._compteur_tcp} | UDP: {self._compteur_udp}")

        sens = "TX" if direction.upper() in ("TX", "OUT", "SEND") else "RX"
        ligne = f"[{sens}][{proto.upper()} #{seq:02d}] {taille} B (0x45534B32) -> {type_trame}"
        self._lignes_mini_wireshark.append(ligne)
        if len(self._lignes_mini_wireshark) > 8:
            self._lignes_mini_wireshark.pop(0)

        if hasattr(self, "list_trames_v2x"):
            self.list_trames_v2x.setPlainText("\n".join(self._lignes_mini_wireshark))
