"""Scène graphique 2D haute performance et vue interactive pour la visualisation du carrefour.

Ce module implémente :
- `CarrefourView` : Sous-classe `QGraphicsView` avec zéro scrollbar, auto-adaptation (`fitInView`),
  zoom molette fluide (0.7x à 3.0x) et réinitialisation par double-clic ou touche R.
- `CarrefourScene` : Scène graphique vectorielle riche style « Smart City » / SCADA préfectoral
  (4 îlots architecturaux aux coins, trottoirs structurés, pistes cyclables, damier d'intersection,
  lampadaires avec halos lumineux météo, feux et antenne RSU cliquables, étiquette HUD flottante).
Conforme aux exigences de la SAÉ 3.02 (Esk-2718).
"""

import logging
import math
import random

import PyQt6.sip as sip
from PyQt6.QtCore import QPointF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from simulation.intersection import CouleurFeu, IntersectionManager
from simulation.vehicules import EntitePhysique, TypeVehicule

logger = logging.getLogger(__name__)


class CarrefourView(QGraphicsView):
    """Vue graphique 2D avec auto-adaptation (fitInView), zoom molette fluide et reset."""

    def __init__(self, scene: QGraphicsScene, parent=None):
        """Initialise la vue sans scrollbars avec zoom et navigation fluide.

        Args:
            scene (QGraphicsScene): Scène vectorielle à afficher.
            parent (QWidget | None): Widget parent Qt.
        """
        super().__init__(scene, parent)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setMouseTracking(True)
        self._zoom_factor = 1.0

    def fit_scene(self):
        """Ajuste parfaitement la scène dans la vue sans aucune barre de défilement."""
        if self.scene() is not None:
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self._zoom_factor = 1.0

    def reset_view(self):
        """Alias pour réinitialiser la vue à 100% de la scène."""
        self.fit_scene()

    def wheelEvent(self, event):
        """Zoom/dézoom fluide centré sur le curseur de souris, borné entre 0.7x et 3.0x."""
        delta = event.angleDelta().y()
        if delta == 0:
            return
        facteur = 1.15 if delta > 0 else (1.0 / 1.15)
        nouveau_zoom = self._zoom_factor * facteur
        if delta > 0:
            if self._zoom_factor >= 3.0:
                event.accept()
                return
            if nouveau_zoom > 3.0:
                facteur = 3.0 / self._zoom_factor
                self._zoom_factor = 3.0
            else:
                self._zoom_factor = nouveau_zoom
        else:
            if self._zoom_factor <= 0.7:
                event.accept()
                return
            if nouveau_zoom < 0.7:
                facteur = 0.7 / self._zoom_factor
                self._zoom_factor = 0.7
            else:
                self._zoom_factor = nouveau_zoom

        self.scale(facteur, facteur)
        event.accept()

    def keyPressEvent(self, event):
        """Raccourci clavier 'R' pour réinitialiser la vue (fitInView)."""
        if event.key() == Qt.Key.Key_R:
            self.fit_scene()
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Réinitialise la vue à 100% (fitInView) lors d'un double-clic."""
        self.fit_scene()
        event.accept()

    def resizeEvent(self, event):
        """Adapte automatiquement l'échelle lors du redimensionnement de la fenêtre."""
        super().resizeEvent(event)
        self.fit_scene()

    def showEvent(self, event):
        """Ajuste la vue dès son apparition à l'écran."""
        super().showEvent(event)
        QTimer.singleShot(0, self.fit_scene)


class CarrefourScene(QGraphicsScene):
    """Scène graphique vectorielle dédiée au rendu temps réel du carrefour urbain.

    Intègre un environnement architectural « Smart City » avec 4 îlots urbains thématiques,
    des éléments cliquables directement sur la carte (feux, antenne RSU) et une étiquette
    HUD flottante prévisualisant la trajectoire du véhicule sélectionné.

    Signals:
        signal_entite_selectionnee (str): Émis lorsqu'une entité mobile est cliquée.
        signal_clic_vide (float, float): Émis lors d'un clic sur la chaussée libre.
        signal_forcer_feux_ns (): Émis lors d'un clic direct sur un feu Nord-Sud.
        signal_forcer_feux_eo (): Émis lors d'un clic direct sur un feu Est-Ouest.
        signal_toggle_preemption_v2i (): Émis lors d'un clic direct sur l'antenne RSU.
    """

    PIXELS_PAR_METRE = 10.0

    signal_entite_selectionnee = pyqtSignal(str)
    signal_clic_vide = pyqtSignal(float, float)
    signal_forcer_feux_ns = pyqtSignal()
    signal_forcer_feux_eo = pyqtSignal()
    signal_toggle_preemption_v2i = pyqtSignal()

    def __init__(self, parent=None):
        """Initialise la scène graphique, son repère métrique et le décor Smart City."""
        super().__init__(parent)

        # Définition du cadre spatial (-500px à +500px, soit 100m x 100m)
        self.setSceneRect(-500, -500, 1000, 1000)
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)

        # Fond d'asphalte urbain réaliste
        bg_grad = QRadialGradient(0, 0, 800)
        bg_grad.setColorAt(0.0, QColor("#1E293B"))
        bg_grad.setColorAt(1.0, QColor("#0F172A"))
        self.setBackgroundBrush(QBrush(bg_grad))

        self.meteo = "Dégagé"
        self.preemption_v2i_active = True

        self.vues_entites = {}
        self.pool_vehicules = {}
        self.objets_meteo = []
        self.arbres = []
        self.flaques = []
        self.traces_pneus = []
        self.lampadaires_halos = []
        self.feux_ns_items = []
        self.feux_eo_items = []
        self.rsu_items = []
        self.passages_bateaux = []
        self.pictogrammes_velo = []

        self.verglas_overlay = None
        self.compteur_arbres = 0.0
        self.tick_lumiere = 0

        self.hologramme = None
        self.type_hologramme = None

        self._draw_infrastructure()

    def clear(self):
        """Réinitialise intégralement la scène et détruit proprement les objets C++."""
        try:
            for liste in self.pool_vehicules.values():
                for vue in liste:
                    if not sip.isdeleted(vue):
                        sip.delete(vue)
            self.pool_vehicules.clear()

            for vue, _ in self.vues_entites.values():
                if not sip.isdeleted(vue):
                    sip.delete(vue)
            self.vues_entites.clear()

            self.objets_meteo.clear()
            self.arbres.clear()
            self.flaques.clear()
            self.lampadaires_halos.clear()
            self.feux_ns_items.clear()
            self.feux_eo_items.clear()
            self.rsu_items.clear()
            self.passages_bateaux.clear()
            self.pictogrammes_velo.clear()

            for trace in self.traces_pneus:
                if not sip.isdeleted(trace):
                    sip.delete(trace)
            self.traces_pneus.clear()

            if self.verglas_overlay is not None and not sip.isdeleted(self.verglas_overlay):
                self.verglas_overlay.setVisible(False)

            if self.hologramme is not None and not sip.isdeleted(self.hologramme):
                sip.delete(self.hologramme)
            self.hologramme = None
            self.type_hologramme = None

            super().clear()
        except Exception as e:
            logger.error(f"[CarrefourScene] Erreur lors du nettoyage de la scène : {e}", exc_info=True)

    def set_meteo(self, etat: str):
        """Met à jour les effets visuels (flaques, verglas, lampadaires) selon la météo."""
        try:
            self.meteo = etat
            visibilite_pluie = (etat in ("Pluie", "Tempête"))
            for flaque in self.flaques:
                flaque.setVisible(visibilite_pluie)

            if self.verglas_overlay:
                self.verglas_overlay.setVisible(etat == "Gel")

            # Allumage des 8 halos lumineux dorés en cas de mauvais temps
            lumieres_actives = (etat in ("Pluie", "Tempête", "Gel"))
            for halo in self.lampadaires_halos:
                halo.setVisible(lumieres_actives)
        except Exception as e:
            logger.error(f"[CarrefourScene] Erreur set_meteo ({etat}) : {e}", exc_info=True)

    def set_preemption_v2i_active(self, active: bool):
        """Active/désactive le retour visuel radio sur la station RSU."""
        self.preemption_v2i_active = active
        couleur_onde = QColor(0, 229, 255, 160) if active else QColor(100, 116, 139, 60)
        for onde in self.rsu_ondes:
            onde.setPen(QPen(couleur_onde, 2))

    def _draw_infrastructure(self):
        """Dessine l'infrastructure routière et le décor architectural Smart City."""
        try:
            stylo_nul = QPen(Qt.PenStyle.NoPen)
            largeur_chaussee = 8.0 * self.PIXELS_PAR_METRE  # 80 px (8m)

            # =========================================================
            # 1. LES 4 ÎLOTS URBAINS THÉMATIQUES AUX 4 COINS DU CARREFOUR
            # =========================================================

            # --- COIN NORD-OUEST : PÔLE SECOURS / HÔPITAL & HÉLIPORT ---
            fond_hopital = self.addRect(-500, -500, 435, 435, stylo_nul, QBrush(QColor("#0F172A")))
            fond_hopital.setZValue(0)

            # Cour pavée hôpital
            cour_hop = self.addRect(-460, -460, 390, 390, stylo_nul, QBrush(QColor("#1E293B")))
            cour_hop.setZValue(1)

            # Bâtiment principal hospitalier avec toit structuré
            bat_hop = self.addRect(-430, -430, 280, 210, QPen(QColor("#334155"), 2), QBrush(QColor("#E2E8F0")))
            bat_hop.setZValue(2)
            toit_hop = self.addRect(-415, -415, 250, 180, QPen(QColor("#94A3B8"), 1), QBrush(QColor("#CBD5E1")))
            toit_hop.setZValue(3)

            # Héliport d'urgence sur le toit
            heli_zone = self.addRect(-330, -345, 90, 90, QPen(QColor("#F59E0B"), 3), QBrush(QColor("#475569")))
            heli_zone.setZValue(4)
            heli_cercle = self.addEllipse(-320, -335, 70, 70, QPen(QColor("#FFFFFF"), 3), QBrush(Qt.GlobalColor.transparent))
            heli_cercle.setZValue(5)

            font_heli = QFont("Consolas", 26, QFont.Weight.Bold)
            heli_txt = self.addSimpleText("H", font_heli)
            heli_txt.setBrush(QBrush(QColor("#FFFFFF")))
            heli_txt.setPos(-295, -325)
            heli_txt.setZValue(6)

            # Croix médicale d'urgence
            croix_bg = self.addRect(-400, -330, 40, 40, stylo_nul, QBrush(QColor("#FFFFFF")))
            croix_bg.setZValue(4)
            croix_v = self.addRect(-385, -325, 10, 30, stylo_nul, QBrush(QColor("#EF4444")))
            croix_v.setZValue(5)
            croix_h = self.addRect(-395, -315, 30, 10, stylo_nul, QBrush(QColor("#EF4444")))
            croix_h.setZValue(5)

            # Voie d'accès et marquage sol URGENCES
            font_urg = QFont("Segoe UI", 9, QFont.Weight.Bold)
            txt_urg = self.addSimpleText("ACCÈS URGENCES SAMU", font_urg)
            txt_urg.setBrush(QBrush(QColor("#EF4444")))
            txt_urg.setPos(-200, -95)
            txt_urg.setZValue(4)

            # --- COIN NORD-EST : PARC URBAIN & BASSIN D'EAU OCTOGONAL ---
            fond_parc = self.addRect(65, -500, 435, 435, stylo_nul, QBrush(QColor("#14532D")))
            fond_parc.setZValue(0)

            # Espace vert gazonné avec dégradé subtil
            pelouse = self.addRect(80, -480, 400, 400, stylo_nul, QBrush(QColor("#166534")))
            pelouse.setZValue(1)

            # Allée piétonne sinueuse pavée
            path_parc = QPainterPath()
            path_parc.moveTo(65, -200)
            path_parc.cubicTo(180, -210, 220, -320, 320, -320)
            path_parc.cubicTo(380, -320, 420, -250, 500, -250)
            allee = self.addPath(path_parc, QPen(QColor("#E2E8F0"), 18, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            allee.setZValue(2)

            # Bassin d'eau octogonal au cœur du parc
            octo_pts = []
            cx_bassin, cy_bassin, r_bassin = 260, -240, 45
            for i in range(8):
                angle = i * (math.pi / 4)
                octo_pts.append(QPointF(cx_bassin + r_bassin * math.cos(angle), cy_bassin + r_bassin * math.sin(angle)))
            bassin_rebord = self.addPolygon(QPolygonF(octo_pts), QPen(QColor("#94A3B8"), 3), QBrush(QColor("#0284C7")))
            bassin_rebord.setZValue(3)

            # Reflets de l'eau
            bassin_eau = self.addEllipse(cx_bassin - 25, cy_bassin - 25, 50, 50, stylo_nul, QBrush(QColor("#38BDF8")))
            bassin_eau.setZValue(4)
            bassin_jet = self.addEllipse(cx_bassin - 6, cy_bassin - 6, 12, 12, stylo_nul, QBrush(QColor("#FFFFFF")))
            bassin_jet.setZValue(5)

            # Bancs publics en bois le long de l'allée
            for bx, by in [(140, -185), (200, -180), (320, -345)]:
                banc = self.addRect(bx, by, 22, 7, QPen(QColor("#451A03"), 1), QBrush(QColor("#92400E")))
                banc.setZValue(4)

            # Bosquet d'arbres à feuillages nuancés
            arbres_parc = [
                (120, -420, 34, "#15803D"), (170, -440, 38, "#16A34A"),
                (140, -360, 30, "#22C55E"), (360, -400, 42, "#15803D"),
                (410, -360, 36, "#166534"), (350, -160, 32, "#16A34A")
            ]
            for ax, ay, d, coul in arbres_parc:
                self.addEllipse(ax + 4, ay + 4, d, d, stylo_nul, QBrush(QColor(0, 0, 0, 70))).setZValue(3)
                a_item = self.addEllipse(ax, ay, d, d, QPen(QColor("#14532D"), 1), QBrush(QColor(coul)))
                a_item.setZValue(4)
                self.arbres.append(a_item)

            # --- COIN SUD-OUEST : PÔLE TERTIAIRE & TRANSPORTS ---
            fond_tertiaire = self.addRect(-500, 65, 435, 435, stylo_nul, QBrush(QColor("#0F172A")))
            fond_tertiaire.setZValue(0)

            # Immeuble de bureaux vitré moderne avec reflets
            bat_bureau = self.addRect(-430, 160, 270, 240, QPen(QColor("#38BDF8"), 2), QBrush(QColor("#1E293B")))
            bat_bureau.setZValue(2)

            toit_verre = self.addRect(-415, 175, 240, 210, stylo_nul, QBrush(QColor("#0F172A")))
            toit_verre.setZValue(3)

            # Reflets diagonaux vitrés stylisés
            for offset in [-30, 20, 70, 120]:
                reflet = self.addLine(-400 + offset, 185, -330 + offset, 375, QPen(QColor(255, 255, 255, 30), 12))
                reflet.setZValue(4)

            # Unités techniques HVAC et panneaux solaires sur le toit
            for hx, hy in [(-400, 200), (-360, 200), (-400, 240)]:
                hvac = self.addRect(hx, hy, 28, 24, QPen(QColor("#64748B"), 1), QBrush(QColor("#475569")))
                hvac.setZValue(5)
                self.addEllipse(hx + 6, hy + 4, 16, 16, stylo_nul, QBrush(QColor("#334155"))).setZValue(6)

            # Panneaux photovoltaïques en rangées
            for px in range(-320, -200, 32):
                for py in range(210, 360, 24):
                    pv = self.addRect(px, py, 26, 18, QPen(QColor("#1E3A8A"), 1), QBrush(QColor("#172554")))
                    pv.setZValue(5)

            # Abribus le long de la route principale
            abribus_sol = self.addRect(-80, 120, 14, 60, stylo_nul, QBrush(QColor("#334155")))
            abribus_sol.setZValue(3)
            abribus_toit = self.addRect(-85, 115, 22, 70, QPen(QColor("#00E5FF"), 1), QBrush(QColor(0, 229, 255, 80)))
            abribus_toit.setZValue(6)

            font_bus = QFont("Segoe UI", 8, QFont.Weight.Bold)
            txt_bus = self.addSimpleText("BUS", font_bus)
            txt_bus.setBrush(QBrush(QColor("#FBBF24")))
            txt_bus.setPos(-58, 140)
            txt_bus.setZValue(4)

            # --- COIN SUD-EST : CENTRE DE SUPERVISION V2X & PARKING ---
            fond_v2x = self.addRect(65, 65, 435, 435, stylo_nul, QBrush(QColor("#0B132B")))
            fond_v2x.setZValue(0)

            # Bâtiment technique moderne avec paraboles
            bat_superv = self.addRect(210, 190, 210, 180, QPen(QColor("#00E5FF"), 2), QBrush(QColor("#1E293B")))
            bat_superv.setZValue(2)
            toit_superv = self.addRect(225, 205, 180, 150, stylo_nul, QBrush(QColor("#111827")))
            toit_superv.setZValue(3)

            # Paraboles de télécommunication sur le toit
            for dx, dy in [(260, 240), (340, 280)]:
                self.addEllipse(dx - 18, dy - 18, 36, 36, QPen(QColor("#94A3B8"), 1), QBrush(QColor("#F1F5F9"))).setZValue(5)
                self.addEllipse(dx - 6, dy - 6, 12, 12, stylo_nul, QBrush(QColor("#475569"))).setZValue(6)
                self.addLine(dx, dy, dx + 12, dy - 12, QPen(QColor("#00E5FF"), 2)).setZValue(7)

            # Parking marqué au sol avec places délimitées
            parking_zone = self.addRect(75, 180, 120, 200, stylo_nul, QBrush(QColor("#1F2937")))
            parking_zone.setZValue(2)
            for py in range(195, 370, 32):
                p_ligne = self.addLine(85, py, 145, py, QPen(QColor("#FFFFFF"), 2))
                p_ligne.setZValue(3)

            # Voitures garées dans le parking
            coul_garées = ["#38BDF8", "#EF4444", "#94A3B8", "#10B981"]
            for idx_p, cy_p in enumerate(range(200, 320, 32)):
                c_car = coul_garées[idx_p % len(coul_garées)]
                v_gare = self.addRect(95, cy_p + 3, 40, 20, QPen(QColor("#000000"), 1), QBrush(QColor(c_car)))
                v_gare.setZValue(4)

            # =========================================================
            # 2. CHAUSSÉE, DAMIER JAUNE, TROTTOIRS ET PISTES CYCLABLES
            # =========================================================
            # Dégradés d'asphalte
            degrade_v = QLinearGradient(-largeur_chaussee / 2, 0, largeur_chaussee / 2, 0)
            degrade_v.setColorAt(0.0, QColor("#1E222A"))
            degrade_v.setColorAt(0.5, QColor("#12161F"))
            degrade_v.setColorAt(1.0, QColor("#1E222A"))

            degrade_h = QLinearGradient(0, -largeur_chaussee / 2, 0, largeur_chaussee / 2)
            degrade_h.setColorAt(0.0, QColor("#1E222A"))
            degrade_h.setColorAt(0.5, QColor("#12161F"))
            degrade_h.setColorAt(1.0, QColor("#1E222A"))

            # Chaussées Nord-Sud et Est-Ouest
            self.addRect(-largeur_chaussee / 2, -500, largeur_chaussee, 1000, stylo_nul, QBrush(degrade_v)).setZValue(2)
            self.addRect(-500, -largeur_chaussee / 2, 1000, largeur_chaussee, stylo_nul, QBrush(degrade_h)).setZValue(2)
            self.addRect(-largeur_chaussee / 2, -largeur_chaussee / 2, largeur_chaussee, largeur_chaussee, stylo_nul, QBrush(QColor("#12161F"))).setZValue(2)

            # Damier jaune d'intersection (Yellow box junction) anti-blocage
            self.yellow_box_cadre = self.addRect(-40, -40, 80, 80, QPen(QColor(250, 204, 21, 140), 2), QBrush(Qt.GlobalColor.transparent))
            self.yellow_box_cadre.setZValue(3)
            stylo_damier = QPen(QColor(250, 204, 21, 90), 2)
            W = 40.0
            # Diagonales y - x = c
            for c in range(-60, 61, 15):
                x1 = max(-W, -W - c)
                x2 = min(W, W - c)
                if x1 < x2:
                    y1 = x1 + c
                    y2 = x2 + c
                    d1 = self.addLine(x1, y1, x2, y2, stylo_damier)
                    d1.setZValue(3)
            # Diagonales y + x = c
            for c in range(-60, 61, 15):
                x1 = max(-W, c - W)
                x2 = min(W, c + W)
                if x1 < x2:
                    y1 = c - x1
                    y2 = c - x2
                    d2 = self.addLine(x1, y1, x2, y2, stylo_damier)
                    d2.setZValue(3)

            # Pistes cyclables vertes le long des trottoirs
            brosse_velo = QBrush(QColor("#00897B"))
            self.addRect(-largeur_chaussee / 2 - 12, -500, 12, 1000, stylo_nul, brosse_velo).setZValue(3)
            self.addRect(largeur_chaussee / 2, -500, 12, 1000, stylo_nul, brosse_velo).setZValue(3)
            self.addRect(-500, -largeur_chaussee / 2 - 12, 1000, 12, stylo_nul, brosse_velo).setZValue(3)
            self.addRect(-500, largeur_chaussee / 2, 1000, 12, stylo_nul, brosse_velo).setZValue(3)

            # Pictogrammes vélo peints en blanc sur chaque piste cyclable
            def ajouter_pictogramme_velo(cx, cy, rotation_deg=0):
                p_blanc = QPen(QColor("#FFFFFF"), 1.5)
                b_vide = QBrush(Qt.GlobalColor.transparent)
                r1 = self.addEllipse(cx - 7, cy - 3, 6, 6, p_blanc, b_vide)
                r2 = self.addEllipse(cx + 1, cy - 3, 6, 6, p_blanc, b_vide)
                l1 = self.addLine(cx - 4, cy, cx - 1, cy - 6, p_blanc)
                l2 = self.addLine(cx - 1, cy - 6, cx + 4, cy, p_blanc)
                l3 = self.addLine(cx - 4, cy, cx + 4, cy, p_blanc)
                l4 = self.addLine(cx - 2, cy - 6, cx - 3, cy - 8, p_blanc)
                l5 = self.addLine(cx + 3, cy - 5, cx + 5, cy - 7, p_blanc)
                for item in [r1, r2, l1, l2, l3, l4, l5]:
                    item.setZValue(4)
                    item.setTransformOriginPoint(cx, cy)
                    item.setRotation(rotation_deg)
                    self.pictogrammes_velo.append(item)

            # Disposition des pictogrammes vélo aux approches du carrefour
            ajouter_pictogramme_velo(-220, 46, 0)
            ajouter_pictogramme_velo(220, 46, 0)
            ajouter_pictogramme_velo(-220, -46, 180)
            ajouter_pictogramme_velo(220, -46, 180)
            ajouter_pictogramme_velo(-46, -220, 90)
            ajouter_pictogramme_velo(-46, 220, 90)
            ajouter_pictogramme_velo(46, -220, 270)
            ajouter_pictogramme_velo(46, 220, 270)

            # Trottoirs gris clair en béton structuré avec bordures
            brosse_trottoir = QBrush(QColor("#CFD8DC"))
            self.addRect(-largeur_chaussee / 2 - 25, -500, 13, 1000, stylo_nul, brosse_trottoir).setZValue(3)
            self.addRect(largeur_chaussee / 2 + 12, -500, 13, 1000, stylo_nul, brosse_trottoir).setZValue(3)
            self.addRect(-500, -largeur_chaussee / 2 - 25, 1000, 13, stylo_nul, brosse_trottoir).setZValue(3)
            self.addRect(-500, largeur_chaussee / 2 + 12, 1000, 13, stylo_nul, brosse_trottoir).setZValue(3)

            # Passages bateaux (rampes d'accès abaissées aux passages piétons et accès cyclistes)
            brosse_bateau = QBrush(QColor("#90A4AE"))
            pen_bateau = QPen(QColor("#546E7A"), 1)
            # Raccordements Nord
            pb_n1 = self.addRect(-65, -105, 25, 25, pen_bateau, brosse_bateau)
            pb_n2 = self.addRect(40, -105, 25, 25, pen_bateau, brosse_bateau)
            # Raccordements Sud
            pb_s1 = self.addRect(-65, 80, 25, 25, pen_bateau, brosse_bateau)
            pb_s2 = self.addRect(40, 80, 25, 25, pen_bateau, brosse_bateau)
            # Raccordements Ouest
            pb_o1 = self.addRect(-105, -65, 25, 25, pen_bateau, brosse_bateau)
            pb_o2 = self.addRect(-105, 40, 25, 25, pen_bateau, brosse_bateau)
            # Raccordements Est
            pb_e1 = self.addRect(80, -65, 25, 25, pen_bateau, brosse_bateau)
            pb_e2 = self.addRect(80, 40, 25, 25, pen_bateau, brosse_bateau)
            for pb in [pb_n1, pb_n2, pb_s1, pb_s2, pb_o1, pb_o2, pb_e1, pb_e2]:
                pb.setZValue(3.5)
                self.passages_bateaux.append(pb)

            # Bordures de trottoir fines
            pen_bordure = QPen(QColor("#78909C"), 1)
            self.addLine(-largeur_chaussee / 2 - 25, -500, -largeur_chaussee / 2 - 25, 1000, pen_bordure).setZValue(4)
            self.addLine(largeur_chaussee / 2 + 25, -500, largeur_chaussee / 2 + 25, 1000, pen_bordure).setZValue(4)

            # Calque de verglas semi-transparent (activé si météo = Gel)
            self.verglas_overlay = self.addRect(
                -largeur_chaussee / 2, -largeur_chaussee / 2,
                largeur_chaussee, largeur_chaussee,
                stylo_nul, QBrush(QColor(186, 230, 253, 130))
            )
            self.verglas_overlay.setZValue(5)
            self.verglas_overlay.setVisible(self.meteo == "Gel")

            # Lignes axiales pointillées blanches
            stylo_pointille = QPen(QColor("#FFFFFF"), 2, Qt.PenStyle.DashLine)
            self.addLine(0, -500, 0, -largeur_chaussee / 2, stylo_pointille).setZValue(3)
            self.addLine(0, largeur_chaussee / 2, 0, 500, stylo_pointille).setZValue(3)
            self.addLine(-500, 0, -largeur_chaussee / 2, 0, stylo_pointille).setZValue(3)
            self.addLine(largeur_chaussee / 2, 0, 500, 0, stylo_pointille).setZValue(3)

            # Lignes d'arrêt avant carrefour (à 10 mètres du centre)
            stylo_arret = QPen(QColor("#FFFFFF"), 4)
            dist_arret = 10.0 * self.PIXELS_PAR_METRE
            self.addLine(-largeur_chaussee / 2, -dist_arret, 0, -dist_arret, stylo_arret).setZValue(4)
            self.addLine(0, dist_arret, largeur_chaussee / 2, dist_arret, stylo_arret).setZValue(4)
            self.addLine(-dist_arret, 0, -dist_arret, largeur_chaussee / 2, stylo_arret).setZValue(4)
            self.addLine(dist_arret, -largeur_chaussee / 2, dist_arret, 0, stylo_arret).setZValue(4)

            # Flèches directionnelles blanches peintes au sol sur chaque voie
            pen_fleche = QPen(QColor("#FFFFFF"), 2)
            # Voie Ouest vers Est
            self.addLine(-160, 20, -120, 20, pen_fleche).setZValue(4)
            self.addLine(-130, 15, -120, 20, pen_fleche).setZValue(4)
            self.addLine(-130, 25, -120, 20, pen_fleche).setZValue(4)
            # Voie Est vers Ouest
            self.addLine(160, -20, 120, -20, pen_fleche).setZValue(4)
            self.addLine(130, -15, 120, -20, pen_fleche).setZValue(4)
            self.addLine(130, -25, 120, -20, pen_fleche).setZValue(4)
            # Voie Nord vers Sud
            self.addLine(-20, -160, -20, -120, pen_fleche).setZValue(4)
            self.addLine(-25, -130, -20, -120, pen_fleche).setZValue(4)
            self.addLine(-15, -130, -20, -120, pen_fleche).setZValue(4)
            # Voie Sud vers Nord
            self.addLine(20, 160, 20, 120, pen_fleche).setZValue(4)
            self.addLine(15, 130, 20, 120, pen_fleche).setZValue(4)
            self.addLine(25, 130, 20, 120, pen_fleche).setZValue(4)

            # Passages piétons zébrés
            brosse_pieton = QBrush(QColor("#FFFFFF"))
            decal_pieton = 8.0 * self.PIXELS_PAR_METRE
            for cx, cy, est_vert in [
                (0, -decal_pieton - 20, True),
                (0, decal_pieton, True),
                (decal_pieton, 0, False),
                (-decal_pieton - 20, 0, False)
            ]:
                for i in range(int(-largeur_chaussee / 2) + 5, int(largeur_chaussee / 2), 10):
                    if est_vert:
                        self.addRect(i, cy, 6, 20, stylo_nul, brosse_pieton).setZValue(4)
                    else:
                        self.addRect(cx, i, 20, 6, stylo_nul, brosse_pieton).setZValue(4)

            # Flaques d'eau de pluie
            brosse_flaque = QBrush(QColor(56, 189, 248, 90))
            for _ in range(12):
                fx, fy = random.randint(-350, 350), random.randint(-350, 350)
                fl = self.addEllipse(fx, fy, random.randint(25, 55), random.randint(12, 28), stylo_nul, brosse_flaque)
                fl.setZValue(3)
                fl.setVisible(False)
                self.flaques.append(fl)

            # =========================================================
            # 3. ÉCLAIRAGE URBAIN : 8 LAMPADAIRES AVEC HALOS LUMINEUX DORÉS
            # =========================================================
            pos_lampes = [
                (-55, -110), (55, -110),
                (-55, 110), (55, 110),
                (-110, -55), (-110, 55),
                (110, -55), (110, 55),
            ]
            for lx, ly in pos_lampes:
                # Poteau et tête de lampadaire
                poteau = self.addEllipse(lx - 3, ly - 3, 6, 6, QPen(QColor("#334155"), 1), QBrush(QColor("#94A3B8")))
                poteau.setZValue(12)

                # Halo lumineux doré radial (allumé par temps de pluie, tempête, gel)
                halo_grad = QRadialGradient(lx, ly, 50)
                halo_grad.setColorAt(0.0, QColor(254, 240, 138, 120))
                halo_grad.setColorAt(0.6, QColor(250, 204, 21, 50))
                halo_grad.setColorAt(1.0, QColor(250, 204, 21, 0))
                halo = self.addEllipse(lx - 50, ly - 50, 100, 100, stylo_nul, QBrush(halo_grad))
                halo.setZValue(11)
                halo.setVisible(False)
                self.lampadaires_halos.append(halo)

            # =========================================================
            # 4. FEUX TRICOLORES CLIQUABLES DIRECTEMENT SUR LA CARTE 2D
            # =========================================================
            # Boîtiers feux avec curseur main
            def creer_boitier_feu(bx, by, w, h):
                box = self.addRect(bx, by, w, h, QPen(QColor("#00E5FF"), 1), QBrush(QColor("#0F172A")))
                box.setZValue(15)
                box.setCursor(Qt.CursorShape.PointingHandCursor)
                return box

            self.box_eo_1 = creer_boitier_feu(-135, 40, 28, 28)
            self.feu_eo_1 = self.addEllipse(-131, 44, 20, 20, stylo_nul, QBrush(Qt.GlobalColor.black))
            self.feu_eo_1.setZValue(16)
            self.feu_eo_1.setCursor(Qt.CursorShape.PointingHandCursor)

            self.box_eo_2 = creer_boitier_feu(105, -70, 28, 28)
            self.feu_eo_2 = self.addEllipse(109, -66, 20, 20, stylo_nul, QBrush(Qt.GlobalColor.black))
            self.feu_eo_2.setZValue(16)
            self.feu_eo_2.setCursor(Qt.CursorShape.PointingHandCursor)

            self.box_ns_1 = creer_boitier_feu(-70, -135, 28, 28)
            self.feu_ns_1 = self.addEllipse(-66, -131, 20, 20, stylo_nul, QBrush(Qt.GlobalColor.black))
            self.feu_ns_1.setZValue(16)
            self.feu_ns_1.setCursor(Qt.CursorShape.PointingHandCursor)

            self.box_ns_2 = creer_boitier_feu(40, 105, 28, 28)
            self.feu_ns_2 = self.addEllipse(44, 109, 20, 20, stylo_nul, QBrush(Qt.GlobalColor.black))
            self.feu_ns_2.setZValue(16)
            self.feu_ns_2.setCursor(Qt.CursorShape.PointingHandCursor)

            self.feux_eo_items = [self.box_eo_1, self.feu_eo_1, self.box_eo_2, self.feu_eo_2]
            self.feux_ns_items = [self.box_ns_1, self.feu_ns_1, self.box_ns_2, self.feu_ns_2]

            # Badges numériques de décompte sur les 4 feux tricolores (08s / VTA)
            self.badges_feux = []
            positions_badges = [(-138, 72), (102, -96), (-73, -162), (37, 138)]
            font_badge = QFont("Consolas", 8, QFont.Weight.Bold)
            for bx, by in positions_badges:
                b_bg = self.addRect(bx, by, 34, 18, QPen(QColor("#00E5FF"), 1), QBrush(QColor(15, 23, 42, 230)))
                b_bg.setZValue(18)
                b_txt = self.addSimpleText("08s", font_badge)
                b_txt.setBrush(QBrush(QColor("#00E5FF")))
                b_txt.setPos(bx + 4, by + 1)
                b_txt.setZValue(19)
                self.badges_feux.append((b_bg, b_txt))

            # =========================================================
            # 5. ANTENNE RSU CENTRALE CLIQUABLE AVEC RETOUR ONDES RADIO
            # =========================================================
            self.rsu_x = 80.0
            self.rsu_y = -80.0

            # Ondes radio concentriques animées
            self.rsu_ondes = []
            for _ in range(4):
                onde = self.addEllipse(0, 0, 0, 0, QPen(QColor(0, 229, 255, 150), 2), QBrush(Qt.GlobalColor.transparent))
                onde.setZValue(8)
                self.rsu_ondes.append(onde)

            # Pylône et antenne RSU avec curseur main
            self.rsu_socle = self.addRect(self.rsu_x - 12, self.rsu_y - 12, 24, 24, QPen(QColor("#00E5FF"), 2), QBrush(QColor("#1E293B")))
            self.rsu_socle.setZValue(9)
            self.rsu_socle.setCursor(Qt.CursorShape.PointingHandCursor)

            self.rsu_mat = self.addLine(self.rsu_x, self.rsu_y, self.rsu_x, self.rsu_y - 22, QPen(QColor("#00E5FF"), 3))
            self.rsu_mat.setZValue(10)
            self.rsu_mat.setCursor(Qt.CursorShape.PointingHandCursor)

            self.rsu_ant1 = self.addLine(self.rsu_x - 8, self.rsu_y - 14, self.rsu_x + 8, self.rsu_y - 14, QPen(QColor("#00E5FF"), 2))
            self.rsu_ant1.setZValue(10)
            self.rsu_ant1.setCursor(Qt.CursorShape.PointingHandCursor)

            self.rsu_ant2 = self.addLine(self.rsu_x - 13, self.rsu_y - 19, self.rsu_x + 13, self.rsu_y - 19, QPen(QColor("#00E5FF"), 2))
            self.rsu_ant2.setZValue(10)
            self.rsu_ant2.setCursor(Qt.CursorShape.PointingHandCursor)

            self.rsu_balise = self.addEllipse(self.rsu_x - 5, self.rsu_y - 27, 10, 10, stylo_nul, QBrush(QColor("#00E5FF")))
            self.rsu_balise.setZValue(11)
            self.rsu_balise.setCursor(Qt.CursorShape.PointingHandCursor)

            font_rsu = QFont("Consolas", 8, QFont.Weight.Bold)
            self.rsu_label = self.addSimpleText("RSU-01 [V2X/V2I]", font_rsu)
            self.rsu_label.setBrush(QBrush(QColor("#00E5FF")))
            self.rsu_label.setPos(self.rsu_x - 42, self.rsu_y + 14)
            self.rsu_label.setZValue(11)
            self.rsu_label.setCursor(Qt.CursorShape.PointingHandCursor)

            self.rsu_items = [
                self.rsu_socle, self.rsu_mat, self.rsu_ant1, self.rsu_ant2,
                self.rsu_balise, self.rsu_label
            ]

            # Faisceau de transmission V2X (VTA -> RSU) et badge flottant
            pen_v2x = QPen(QColor("#EF4444"), 2, Qt.PenStyle.DashLine)
            self.v2x_beam = self.addLine(0, 0, 0, 0, pen_v2x)
            self.v2x_beam.setZValue(15)
            self.v2x_beam.setVisible(False)

            self.v2x_label_bg = self.addRect(0, 0, 140, 20, QPen(QColor("#EF4444"), 1), QBrush(QColor(15, 23, 42, 230)))
            self.v2x_label_bg.setZValue(16)
            self.v2x_label_bg.setVisible(False)

            font_v2x = QFont("Consolas", 8, QFont.Weight.Bold)
            self.v2x_label = self.addSimpleText("UDP V2I [PRÉEMPTION]", font_v2x)
            self.v2x_label.setBrush(QBrush(QColor("#EF4444")))
            self.v2x_label.setZValue(17)
            self.v2x_label.setVisible(False)

            # Cône LiDAR / Radar et ligne de verrouillage cible obstacle
            self.lidar_cone = self.addPolygon(QPolygonF(), QPen(QColor(0, 230, 118, 150), 1), QBrush(QColor(0, 230, 118, 35)))
            self.lidar_cone.setZValue(12)
            self.lidar_cone.setVisible(False)

            self.lidar_cible_ligne = self.addLine(0, 0, 0, 0, QPen(QColor(239, 68, 68, 200), 2, Qt.PenStyle.DashDotLine))
            self.lidar_cible_ligne.setZValue(13)
            self.lidar_cible_ligne.setVisible(False)

            self.lidar_cible_point = self.addEllipse(0, 0, 8, 8, QPen(QColor("#EF4444"), 2), QBrush(QColor(239, 68, 68, 140)))
            self.lidar_cible_point.setZValue(14)
            self.lidar_cible_point.setVisible(False)

            self.lidar_cible_texte = self.addSimpleText("", QFont("Consolas", 8, QFont.Weight.Bold))
            self.lidar_cible_texte.setBrush(QBrush(QColor("#EF4444")))
            self.lidar_cible_texte.setZValue(14)
            self.lidar_cible_texte.setVisible(False)

            # Bandeau supérieur SCADA HUD Overlay
            self.scada_bandeau_bg = self.addRect(-480, -490, 960, 26, QPen(QColor("#334155"), 1), QBrush(QColor(15, 23, 42, 235)))
            self.scada_bandeau_bg.setZValue(25)

            font_scada = QFont("Consolas", 8, QFont.Weight.Bold)
            self.scada_bandeau_txt = self.addSimpleText("SCADA SUPERVISION V2X/V2I | MODE FEUX: ADAPTATIF | INITIALISATION...", font_scada)
            self.scada_bandeau_txt.setBrush(QBrush(QColor("#00E5FF")))
            self.scada_bandeau_txt.setPos(-470, -485)
            self.scada_bandeau_txt.setZValue(26)

            # =========================================================
            # 6. ÉTIQUETTE FLOTTANTE (CALLOUT HUD) & SURBRILLANCE TRAJECTOIRE
            # =========================================================
            self.callout_bg = self.addRect(0, 0, 160, 24, QPen(QColor("#00E5FF"), 1), QBrush(QColor(24, 26, 32, 220)))
            self.callout_bg.setZValue(30)
            self.callout_bg.setVisible(False)

            font_callout = QFont("Consolas", 8, QFont.Weight.Bold)
            self.callout_txt = self.addSimpleText("", font_callout)
            self.callout_txt.setBrush(QBrush(QColor("#00E5FF")))
            self.callout_txt.setZValue(31)
            self.callout_txt.setVisible(False)

            self.trajectoire_prevue_path = self.addPath(QPainterPath(), QPen(QColor("#00E5FF"), 2, Qt.PenStyle.DashLine))
            self.trajectoire_prevue_path.setZValue(22)
            self.trajectoire_prevue_path.setVisible(False)

        except Exception as e:
            logger.error(f"[CarrefourScene] Erreur lors du dessin de l'infrastructure : {e}", exc_info=True)

    def _obtenir_couleur_qt(self, enum_feu: CouleurFeu) -> QColor:
        """Convertit CouleurFeu en objet QColor."""
        try:
            if enum_feu == CouleurFeu.VERT:
                return QColor("#10B981")
            elif enum_feu == CouleurFeu.ORANGE:
                return QColor("#F59E0B")
            return QColor("#EF4444")
        except Exception:
            return QColor("#EF4444")

    def _create_vehicle_view(self, entite: EntitePhysique) -> tuple[QGraphicsRectItem, QGraphicsRectItem]:
        """Instancie la représentation vectorielle composite d'une entité mobile."""
        largeur_px = entite.longueur_m * self.PIXELS_PAR_METRE
        hauteur_px = entite.largeur_m * self.PIXELS_PAR_METRE

        couleur = QColor("#0284C7")
        if entite.type_entite == TypeVehicule.POIDS_LOURD:
            couleur = QColor("#64748B")
        elif entite.type_entite == TypeVehicule.CONVOI_EXCEPTIONNEL:
            couleur = QColor("#F59E0B")
        elif entite.type_entite == TypeVehicule.VIG_VTA:
            couleur = QColor("#EF4444")
        elif entite.type_entite == TypeVehicule.PIETON:
            couleur = QColor("#A855F7")
        elif entite.type_entite == TypeVehicule.CYCLISTE:
            couleur = QColor("#06B6D4")

        group = self.addRect(
            -largeur_px / 2, -hauteur_px / 2, largeur_px, hauteur_px,
            QPen(Qt.PenStyle.NoPen), QBrush(Qt.GlobalColor.transparent)
        )

        shadow = self.addRect(
            -largeur_px / 2 + 3, -hauteur_px / 2 + 3, largeur_px, hauteur_px,
            QPen(Qt.PenStyle.NoPen), QBrush(QColor(0, 0, 0, 80))
        )
        shadow.setParentItem(group)

        if entite.type_entite == TypeVehicule.PIETON:
            body = self.addEllipse(-largeur_px / 2, -hauteur_px / 2, largeur_px, hauteur_px, QPen(Qt.PenStyle.NoPen), QBrush(couleur))
            body.setParentItem(group)
            head = self.addEllipse(-largeur_px / 4, -hauteur_px / 4, largeur_px / 2, hauteur_px / 2, QPen(Qt.PenStyle.NoPen), QBrush(QColor("#FDE68A")))
            head.setParentItem(group)
        elif entite.type_entite == TypeVehicule.CYCLISTE:
            frame = self.addRect(-largeur_px / 2, -hauteur_px / 6, largeur_px, hauteur_px / 3, QPen(Qt.PenStyle.NoPen), QBrush(QColor("#94A3B8")))
            frame.setParentItem(group)
            cyclist = self.addEllipse(-largeur_px / 4, -hauteur_px / 2, largeur_px / 2, hauteur_px, QPen(Qt.PenStyle.NoPen), QBrush(couleur))
            cyclist.setParentItem(group)
        else:
            chassis = self.addRect(-largeur_px / 2, -hauteur_px / 2, largeur_px, hauteur_px, QPen(Qt.PenStyle.NoPen), QBrush(couleur))
            chassis.setParentItem(group)

            toit = self.addRect(-largeur_px / 4, -hauteur_px / 3, largeur_px / 2, hauteur_px * 2 / 3, QPen(Qt.PenStyle.NoPen), QBrush(couleur.darker(120)))
            toit.setParentItem(group)

            vitre = self.addRect(-largeur_px / 6, -hauteur_px / 4, largeur_px / 3, hauteur_px / 2, QPen(Qt.PenStyle.NoPen), QBrush(QColor("#38BDF8")))
            vitre.setParentItem(group)

        # Hitbox transparente pour la sélection par clic
        hitbox = self.addRect(
            -largeur_px / 2 - 5, -hauteur_px / 2 - 5, largeur_px + 10, hauteur_px + 10,
            QPen(Qt.PenStyle.NoPen), QBrush(Qt.GlobalColor.transparent)
        )
        hitbox.setParentItem(group)
        hitbox.setData(0, "mobile")
        hitbox.setCursor(Qt.CursorShape.PointingHandCursor)

        group.setZValue(20)
        return group, hitbox

    def _obtenir_vue_vehicule(self, entite: EntitePhysique) -> tuple[QGraphicsRectItem, QGraphicsRectItem]:
        """Récupère une vue depuis le pool ou en instancie une nouvelle."""
        pool = self.pool_vehicules.setdefault(entite.type_entite, [])
        if pool:
            vue = pool.pop()
            vue.setVisible(True)
            hitbox = vue.childItems()[-1] if vue.childItems() else vue
            return vue, hitbox
        return self._create_vehicle_view(entite)

    def mettre_a_jour_entites(self, entites: list, inter: IntersectionManager, id_selectionne: str | None = None):
        """Met à jour l'ensemble des éléments dynamiques et le HUD sur la scène."""
        try:
            self.tick_lumiere = (self.tick_lumiere + 1) % 60

            # 1. Mise à jour des feux tricolores
            if inter is not None and hasattr(inter, "feu_ns") and hasattr(inter, "feu_eo"):
                coul_ns = self._obtenir_couleur_qt(inter.feu_ns)
                coul_eo = self._obtenir_couleur_qt(inter.feu_eo)
                self.feu_ns_1.setBrush(QBrush(coul_ns))
                self.feu_ns_2.setBrush(QBrush(coul_ns))
                self.feu_eo_1.setBrush(QBrush(coul_eo))
                self.feu_eo_2.setBrush(QBrush(coul_eo))

                # Décompte temps restant sur badges
                t_rest = getattr(inter, 'temps_restant_phase', 8.0)
                txt_badge = "VTA" if getattr(inter, 'urgence_active', False) else f"{int(max(0, t_rest)):02d}s"
                coul_badge = QColor("#EF4444") if getattr(inter, 'urgence_active', False) else QColor("#00E5FF")

                for b_bg, b_txt in self.badges_feux:
                    b_txt.setText(txt_badge)
                    b_txt.setBrush(QBrush(coul_badge))
                    b_bg.setPen(QPen(coul_badge, 1))

            # 2. Animation des ondes radio RSU
            active_v2i = getattr(self, "preemption_v2i_active", True)
            couleur_ondes = QColor(0, 229, 255, 140) if active_v2i else QColor(100, 116, 139, 40)
            for idx, onde in enumerate(self.rsu_ondes):
                r_onde = ((self.tick_lumiere * 1.5 + idx * 25) % 100)
                onde.setRect(self.rsu_x - r_onde, self.rsu_y - r_onde, r_onde * 2, r_onde * 2)
                alpha = max(0, int(150 * (1.0 - r_onde / 100.0))) if active_v2i else 30
                c_onde = QColor(couleur_ondes)
                c_onde.setAlpha(alpha)
                onde.setPen(QPen(c_onde, 2))

            # 3. Synchronisation des véhicules mobiles
            entites_ids = set()
            vta_proche = None
            veh_sel = None

            for ent in entites:
                eid = ent.id_entite
                entites_ids.add(eid)
                px = ent.pos_x * self.PIXELS_PAR_METRE
                py = ent.pos_y * self.PIXELS_PAR_METRE
                cap_deg = math.degrees(ent.cap)

                if eid not in self.vues_entites:
                    vue, hitbox = self._obtenir_vue_vehicule(ent)
                    hitbox.setData(1, eid)
                    self.vues_entites[eid] = (vue, ent.type_entite)
                else:
                    vue, _ = self.vues_entites[eid]

                vue.setPos(px, py)
                vue.setRotation(cap_deg)

                if eid == id_selectionne:
                    veh_sel = ent

                # Détection VTA pour faisceau V2X (portée < 85m)
                t_val = getattr(ent, "type_entite", None)
                if (TypeVehicule is not None and t_val == TypeVehicule.VIG_VTA) or str(t_val) == "TypeVehicule.VIG_VTA":
                    dist_centre = math.hypot(ent.pos_x, ent.pos_y)
                    if dist_centre < 85.0:
                        vta_proche = ent

            # Nettoyage des entités disparues vers le pool
            disparus = [eid for eid in self.vues_entites if eid not in entites_ids]
            for eid in disparus:
                vue, t_type = self.vues_entites.pop(eid)
                vue.setVisible(False)
                self.pool_vehicules.setdefault(t_type, []).append(vue)

            # 4. Faisceau V2X VTA -> RSU
            if vta_proche is not None:
                vta_px = vta_proche.pos_x * self.PIXELS_PAR_METRE
                vta_py = vta_proche.pos_y * self.PIXELS_PAR_METRE
                self.v2x_beam.setLine(vta_px, vta_py, self.rsu_x, self.rsu_y)
                self.v2x_beam.setVisible(True)

                mid_x = (vta_px + self.rsu_x) / 2
                mid_y = (vta_py + self.rsu_y) / 2
                self.v2x_label_bg.setPos(mid_x - 70, mid_y - 10)
                self.v2x_label_bg.setVisible(True)
                self.v2x_label.setPos(mid_x - 65, mid_y - 6)
                self.v2x_label.setVisible(True)
            else:
                self.v2x_beam.setVisible(False)
                self.v2x_label_bg.setVisible(False)
                self.v2x_label.setVisible(False)

            # 5. Cône LiDAR et HUD flottant sur véhicule sélectionné
            if veh_sel is not None:
                px = veh_sel.pos_x * self.PIXELS_PAR_METRE
                py = veh_sel.pos_y * self.PIXELS_PAR_METRE
                cap = veh_sel.cap

                # Cône LiDAR
                portee_lidar = 60.0  # px
                ouverture = math.radians(25)
                p0 = QPointF(px, py)
                p1 = QPointF(px + portee_lidar * math.cos(cap - ouverture), py + portee_lidar * math.sin(cap - ouverture))
                p2 = QPointF(px + portee_lidar * math.cos(cap + ouverture), py + portee_lidar * math.sin(cap + ouverture))
                self.lidar_cone.setPolygon(QPolygonF([p0, p1, p2]))
                self.lidar_cone.setVisible(True)

                # Étiquette HUD flottante [ #ID | 48 km/h | Dist: 18m ]
                v_kmh = float(getattr(veh_sel, "vitesse_kmh", 0.0))
                dist_obs = getattr(veh_sel, "distance_obstacle", None)
                if dist_obs is not None and dist_obs < 100.0:
                    str_dist = f"Dist: {dist_obs:.0f}m"
                else:
                    str_dist = "Libre"

                txt_badge = f"[#{veh_sel.id_entite} | {v_kmh:.0f} km/h | {str_dist}]"
                self.callout_txt.setText(txt_badge)
                rect_t = self.callout_txt.boundingRect()
                box_w = rect_t.width() + 12
                box_h = rect_t.height() + 6
                self.callout_bg.setRect(px - box_w / 2, py - 35, box_w, box_h)
                self.callout_txt.setPos(px - box_w / 2 + 6, py - 32)
                self.callout_bg.setVisible(True)
                self.callout_txt.setVisible(True)

                # Cible obstacle verrouillée LiDAR / Radar
                if dist_obs is not None and dist_obs < 60.0:
                    cible_px = px + dist_obs * self.PIXELS_PAR_METRE * math.cos(cap)
                    cible_py = py + dist_obs * self.PIXELS_PAR_METRE * math.sin(cap)
                    self.lidar_cible_ligne.setLine(px, py, cible_px, cible_py)
                    self.lidar_cible_ligne.setVisible(True)
                    self.lidar_cible_point.setRect(cible_px - 4, cible_py - 4, 8, 8)
                    self.lidar_cible_point.setVisible(True)
                    self.lidar_cible_texte.setPos(cible_px + 6, cible_py - 6)
                    self.lidar_cible_texte.setText(f"{dist_obs:.1f}m")
                    self.lidar_cible_texte.setVisible(True)
                else:
                    self.lidar_cible_ligne.setVisible(False)
                    self.lidar_cible_point.setVisible(False)
                    self.lidar_cible_texte.setVisible(False)

                # Surbrillance de la trajectoire prévue (flèche droite ou courbe de Bézier avec pointe)
                path_traj = QPainterPath()
                path_traj.moveTo(px, py)
                act_virage = getattr(veh_sel, "action_intersection", None)
                if act_virage is not None:
                    # Courbe Bézier quadratique vers le virage
                    cx_turn = px + math.cos(cap) * 120
                    cy_turn = py + math.sin(cap) * 120
                    ex_turn = cx_turn + math.cos(act_virage) * 120
                    ey_turn = cy_turn + math.sin(act_virage) * 120
                    path_traj.quadTo(QPointF(cx_turn, cy_turn), QPointF(ex_turn, ey_turn))
                    # Pointe de flèche directionnelle en bout de courbe
                    arrow_len = 12.0
                    arrow_angle = math.radians(25)
                    path_traj.lineTo(ex_turn - arrow_len * math.cos(act_virage - arrow_angle),
                                     ey_turn - arrow_len * math.sin(act_virage - arrow_angle))
                    path_traj.moveTo(ex_turn, ey_turn)
                    path_traj.lineTo(ex_turn - arrow_len * math.cos(act_virage + arrow_angle),
                                     ey_turn - arrow_len * math.sin(act_virage + arrow_angle))
                else:
                    # Flèche droite avec pointe directionnelle
                    end_x = px + math.cos(cap) * 180
                    end_y = py + math.sin(cap) * 180
                    path_traj.lineTo(end_x, end_y)
                    arrow_len = 14.0
                    arrow_angle = math.radians(25)
                    path_traj.lineTo(end_x - arrow_len * math.cos(cap - arrow_angle),
                                     end_y - arrow_len * math.sin(cap - arrow_angle))
                    path_traj.moveTo(end_x, end_y)
                    path_traj.lineTo(end_x - arrow_len * math.cos(cap + arrow_angle),
                                     end_y - arrow_len * math.sin(cap + arrow_angle))

                self.trajectoire_prevue_path.setPath(path_traj)
                self.trajectoire_prevue_path.setVisible(True)
            else:
                self.lidar_cone.setVisible(False)
                self.lidar_cible_ligne.setVisible(False)
                self.lidar_cible_point.setVisible(False)
                self.lidar_cible_texte.setVisible(False)
                self.callout_bg.setVisible(False)
                self.callout_txt.setVisible(False)
                self.trajectoire_prevue_path.setVisible(False)

            # 6. Actualisation du bandeau SCADA HUD
            str_mode = "ADAPTATIF"
            if inter is not None and getattr(inter, 'urgence_active', False):
                str_mode = "URGENCE V2I PRIORITAIRE"
            str_meteo = self.meteo.upper()
            tot_inc = 0
            p = self.parent()
            if p is not None and hasattr(p, 'dashboard') and hasattr(p.dashboard, '_total_incidents'):
                tot_inc = p.dashboard._total_incidents
            str_secu = f"{tot_inc} INCIDENT" + ("S" if tot_inc > 1 else "")

            self.scada_bandeau_txt.setText(
                f"SCADA SUPERVISION  |  MODE FEUX: {str_mode}  |  MÉTÉO: {str_meteo}  |  SÉCURITÉ: {str_secu}  |  V2X BÉZIER"
            )

        except Exception as e:
            logger.error(f"[CarrefourScene] Erreur mettre_a_jour_entites: {e}", exc_info=True)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        """Gère le survol de la souris pour actualiser le gabarit de prévisualisation."""
        try:
            super().mouseMoveEvent(event)
            fenetre = self.parent()
            if not fenetre or not hasattr(fenetre, "type_a_placer"):
                return

            type_selectionne = fenetre.type_a_placer
            if type_selectionne is None:
                if self.hologramme is not None:
                    self.removeItem(self.hologramme)
                    if not sip.isdeleted(self.hologramme):
                        sip.delete(self.hologramme)
                    self.hologramme = None
                    self.type_hologramme = None
                return

            scene_pos = event.scenePos()
            x = scene_pos.x() / self.PIXELS_PAR_METRE
            y = scene_pos.y() / self.PIXELS_PAR_METRE

            voie = fenetre.dashboard.combo_voie_spawn.currentText()
            pos_x, pos_y, cap = x, y, 0.0

            if voie == "Passage Piéton" or type_selectionne == TypeVehicule.PIETON:
                if abs(x) > abs(y):
                    pos_x = 9.0 if x > 0 else -9.0
                    pos_y = max(-4.0, min(4.0, y))
                    cap = math.pi / 2 if y < 0 else -math.pi / 2
                else:
                    pos_x = max(-4.0, min(4.0, x))
                    pos_y = 9.0 if y > 0 else -9.0
                    cap = 0.0 if x < 0 else math.pi
            elif voie == "Nord -> Sud":
                pos_x = -2.0
                pos_y = y
                cap = math.pi / 2
            elif voie == "Sud -> Nord":
                pos_x = 2.0
                pos_y = y
                cap = -math.pi / 2
            elif voie == "Est -> Ouest":
                pos_y = -2.0
                pos_x = x
                cap = math.pi
            elif voie == "Ouest -> Est":
                pos_y = 2.0
                pos_x = x
                cap = 0.0
            else:
                if abs(y) < abs(x):
                    pos_x = x
                    pos_y = 2.0 if y > 0 else -2.0
                    cap = 0.0 if pos_y > 0 else math.pi
                else:
                    pos_y = y
                    pos_x = 2.0 if x > 0 else -2.0
                    cap = math.pi / 2 if pos_x < 0 else -math.pi / 2

            if self.hologramme is None or self.type_hologramme != type_selectionne:
                if self.hologramme is not None:
                    self.removeItem(self.hologramme)
                    if not sip.isdeleted(self.hologramme):
                        sip.delete(self.hologramme)

                largeur_px = 4.0 * self.PIXELS_PAR_METRE
                hauteur_px = 2.0 * self.PIXELS_PAR_METRE
                if type_selectionne == TypeVehicule.POIDS_LOURD:
                    largeur_px = 10.0 * self.PIXELS_PAR_METRE
                elif type_selectionne == TypeVehicule.PIETON:
                    largeur_px, hauteur_px = 5.0, 5.0
                elif type_selectionne == TypeVehicule.CYCLISTE:
                    largeur_px, hauteur_px = 15.0, 5.0

                self.hologramme = QGraphicsRectItem(-largeur_px / 2, -hauteur_px / 2, largeur_px, hauteur_px)
                self.hologramme.setBrush(QBrush(QColor(255, 255, 255, 120)))
                self.hologramme.setPen(QPen(QColor(0, 229, 255), 2, Qt.PenStyle.DashLine))
                self.addItem(self.hologramme)
                self.type_hologramme = type_selectionne

            self.hologramme.setPos(pos_x * self.PIXELS_PAR_METRE, pos_y * self.PIXELS_PAR_METRE)
            self.hologramme.setRotation(math.degrees(cap))

        except Exception as e:
            logger.error(f"[CarrefourScene] Erreur mouseMoveEvent: {e}", exc_info=True)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        """Gère les clics sur feux tricolores, antenne RSU, usagers ou chaussée libre."""
        try:
            pos = event.scenePos()
            items_cliques = self.items(pos)

            # 1. Vérification clic sur feux tricolores
            for it in items_cliques:
                if hasattr(self, "feux_ns_items") and it in self.feux_ns_items:
                    self.signal_forcer_feux_ns.emit()
                    event.accept()
                    return
                if hasattr(self, "feux_eo_items") and it in self.feux_eo_items:
                    self.signal_forcer_feux_eo.emit()
                    event.accept()
                    return
                if hasattr(self, "rsu_items") and it in self.rsu_items:
                    self.signal_toggle_preemption_v2i.emit()
                    event.accept()
                    return

            # 2. Vérification clic sur véhicule mobile
            mobile_item = next((it for it in items_cliques if it.data(0) == "mobile" and it.data(1)), None)
            if mobile_item:
                self.signal_entite_selectionnee.emit(mobile_item.data(1))
                event.accept()
                return

            # 3. Clic sur chaussée libre (spawn ou désélection)
            m_x = pos.x() / self.PIXELS_PAR_METRE
            m_y = pos.y() / self.PIXELS_PAR_METRE
            self.signal_clic_vide.emit(m_x, m_y)
            super().mousePressEvent(event)

        except Exception as e:
            logger.error(f"[CarrefourScene] Erreur mousePressEvent: {e}", exc_info=True)
