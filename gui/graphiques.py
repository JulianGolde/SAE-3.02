"""Module de visualisation graphique temps réel pour Esk-2718.

Fournit des widgets pyqtgraph interactifs pour afficher l'évolution temporelle
de la vitesse moyenne et du nombre de véhicules circulant sur le carrefour.
Conforme aux exigences de la SAÉ 3.02 : librairies autorisées (PyQt6, pyqtgraph),
labels en français, rolling window de 120 points et thème Cyber-SCADA sombre.
"""

import logging
from datetime import datetime

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# Configuration globale de pyqtgraph pour un rendu Cyber-SCADA sombre, fluide et contrasté
pg.setConfigOption("background", "#181A20")
pg.setConfigOption("foreground", "#CBD5E1")
pg.setConfigOption("antialias", True)


class GraphiqueTempsReel(QWidget):
    """Widget composite contenant deux graphiques pyqtgraph temps réel synchronisés.

    Affiche la vitesse moyenne (km/h) et le nombre de véhicules au cours du temps,
    avec une fenêtre glissante (rolling window) bornée à 120 points au maximum.
    """

    def __init__(self, parent: QWidget | None = None, max_points: int = 120):
        """Initialise le widget composite avec ses deux graphiques pyqtgraph.

        Args:
            parent (QWidget | None): Widget parent Qt.
            max_points (int): Nombre maximal d'échantillons conservés dans la fenêtre glissante.
        """
        super().__init__(parent)
        self.max_points = max(1, int(max_points))

        # Séries temporelles
        self.temps_data: list[float] = []
        self.vitesse_data: list[float] = []
        self.vehicules_data: list[int] = []
        self.temps_origine: float | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        # 1. Graphique de la Vitesse Moyenne
        self.plot_vitesse = pg.PlotWidget(
            title="<span style='color: #00E5FF; font-weight: bold; font-size: 11pt;'>📈 Vitesse Moyenne des Véhicules</span>"
        )
        self.plot_vitesse.setBackground("#181A20")
        self.plot_vitesse.showGrid(x=True, y=True, alpha=0.25)
        self.plot_vitesse.setLabel("bottom", "Temps (s)", color="#94A3B8")
        self.plot_vitesse.setLabel("left", "Vitesse (km/h)", color="#94A3B8")
        self.plot_vitesse.setMouseEnabled(x=True, y=True)

        pen_vitesse = pg.mkPen(color="#00E5FF", width=2.5)
        self.courbe_vitesse = self.plot_vitesse.plot(
            pen=pen_vitesse, name="Vitesse Moyenne"
        )

        # 2. Graphique du Nombre de Véhicules
        self.plot_vehicules = pg.PlotWidget(
            title="<span style='color: #FF9100; font-weight: bold; font-size: 11pt;'>🚗 Nombre de Véhicules Actifs</span>"
        )
        self.plot_vehicules.setBackground("#181A20")
        self.plot_vehicules.showGrid(x=True, y=True, alpha=0.25)
        self.plot_vehicules.setLabel("bottom", "Temps (s)", color="#94A3B8")
        self.plot_vehicules.setLabel("left", "Nombre de véhicules", color="#94A3B8")
        self.plot_vehicules.setMouseEnabled(x=True, y=True)

        pen_vehicules = pg.mkPen(color="#FF9100", width=2.5)
        self.courbe_vehicules = self.plot_vehicules.plot(
            pen=pen_vehicules, name="Véhicules"
        )

        layout.addWidget(self.plot_vitesse)
        layout.addWidget(self.plot_vehicules)

    def _convertir_timestamp(self, ts) -> float:
        """Convertit un timestamp hétérogène (float, int, datetime, ISO str) en valeur numérique float.

        Args:
            ts: Horodatage sous forme numérique, datetime ou chaîne ISO.

        Returns:
            float: Horodatage converti en secondes.
        """
        if isinstance(ts, (int, float)):
            return float(ts)
        if isinstance(ts, datetime):
            return ts.timestamp()
        if isinstance(ts, str):
            try:
                # Format standard SQLite 'YYYY-MM-DD HH:MM:SS' ou ISO
                dt = datetime.fromisoformat(ts.replace(" ", "T"))
                return dt.timestamp()
            except Exception:
                try:
                    return float(ts)
                except Exception:
                    return 0.0
        return 0.0

    def ajouter_point(self, timestamp, vitesse_moy: float, nb_vehicules: int):
        """Ajoute un point de mesure et actualise l'affichage des deux courbes pyqtgraph.

        Args:
            timestamp (float | int | str | datetime): Horodatage en secondes ou date.
            vitesse_moy (float): Vitesse moyenne constatée sur le carrefour (km/h).
            nb_vehicules (int): Nombre de véhicules mesurés.
        """
        try:
            val_t = self._convertir_timestamp(timestamp)
            if self.temps_origine is None:
                self.temps_origine = val_t

            if val_t > 1000000000:
                # Timestamp absolu POSIX : conversion en temps relatif par rapport au début
                t_relatif = round(val_t - self.temps_origine, 1)
            else:
                t_relatif = round(val_t, 1)

            self.temps_data.append(t_relatif)
            self.vitesse_data.append(max(0.0, float(vitesse_moy)))
            self.vehicules_data.append(max(0, int(nb_vehicules)))

            # Application de la fenêtre glissante (rolling window) de 120 points maximum
            if len(self.temps_data) > self.max_points:
                self.temps_data = self.temps_data[-self.max_points:]
                self.vitesse_data = self.vitesse_data[-self.max_points:]
                self.vehicules_data = self.vehicules_data[-self.max_points:]

            # Rendu direct par listes Python vers pyqtgraph (sans dépendance externe NumPy)
            self.courbe_vitesse.setData(self.temps_data, self.vitesse_data)
            self.courbe_vehicules.setData(self.temps_data, self.vehicules_data)
        except Exception as e:
            logger.error(f"[GraphiqueTempsReel] Erreur lors de l'ajout du point: {e}", exc_info=True)

    def charger_metriques(self, metriques: list):
        """Charge une série historique de métriques enregistrées pour restitution visuelle complète.

        Args:
            metriques (list): Liste de dictionnaires ou LigneResultat provenant de la base SQLite.
        """
        self.reinitialiser()
        for idx, m in enumerate(metriques):
            ts = m.get("timestamp", idx) if isinstance(m, dict) else (m[2] if len(m) > 2 else idx)
            v = m.get("vitesse_moyenne", 0.0) if isinstance(m, dict) else (m[4] if len(m) > 4 else 0.0)
            n = m.get("nb_vehicules", 0) if isinstance(m, dict) else (m[3] if len(m) > 3 else 0)
            self.ajouter_point(ts, v, n)

    def reinitialiser(self):
        """Efface l'historique des courbes et réinitialise l'axe temporel."""
        self.temps_data.clear()
        self.vitesse_data.clear()
        self.vehicules_data.clear()
        self.temps_origine = None

        self.courbe_vitesse.setData([], [])
        self.courbe_vehicules.setData([], [])


class FenetreGraphiques(QDialog):
    """Boîte de dialogue affichant les graphiques temps réel complets et détaillés."""

    def __init__(self, parent: QWidget | None = None):
        """Initialise la boîte de dialogue avec le widget graphique dédié."""
        super().__init__(parent)
        self.setWindowTitle("📊 Analyse Graphique Temps Réel — Esk-2718")
        self.setMinimumSize(780, 520)
        self.setStyleSheet("""
            QDialog {
                background-color: #181A20;
                color: #FFFFFF;
            }
            QPushButton {
                background-color: #222630;
                color: #FFFFFF;
                border: 1px solid #333947;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2D3342;
                border-color: #00E5FF;
            }
        """)

        layout = QVBoxLayout(self)
        self.graphique = GraphiqueTempsReel(self, max_points=120)
        layout.addWidget(self.graphique)

        btn_layout = QHBoxLayout()
        btn_reinit = QPushButton("🔄 Réinitialiser Courbes")
        btn_reinit.clicked.connect(self.graphique.reinitialiser)

        btn_fermer = QPushButton("Fermer")
        btn_fermer.clicked.connect(self.accept)

        btn_layout.addWidget(btn_reinit)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_fermer)
        layout.addLayout(btn_layout)

    def ajouter_point(self, timestamp, vitesse_moy: float, nb_vehicules: int):
        """Délègue l'ajout de point au widget graphique interne."""
        self.graphique.ajouter_point(timestamp, vitesse_moy, nb_vehicules)

    def charger_metriques(self, metriques: list):
        """Charge une série complète de métriques dans le widget interne."""
        self.graphique.charger_metriques(metriques)
