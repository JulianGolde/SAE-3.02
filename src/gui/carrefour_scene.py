import logging
import math
import random
import PyQt6.sip as sip

from PyQt6.QtWidgets import QGraphicsScene, QGraphicsRectItem, QGraphicsEllipseItem
from PyQt6.QtGui import QBrush, QPen, QColor, QRadialGradient, QLinearGradient
from PyQt6.QtCore import Qt, pyqtSignal

from simulation.intersection import CouleurFeu
from simulation.vehicules import TypeVehicule

logger = logging.getLogger(__name__)

class CarrefourScene(QGraphicsScene):
    """Scène graphique gérant le rendu du carrefour et des véhicules optimisée."""
    
    PIXELS_PAR_METRE = 10.0
    
    signal_entite_selectionnee = pyqtSignal(str)
    signal_clic_vide = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setSceneRect(-500, -500, 1000, 1000)
        # Optimisation majeure : pas d'indexation BSP pour les éléments dynamiques fréquents
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        
        bg_grad = QRadialGradient(0, 0, 800)
        bg_grad.setColorAt(0.0, QColor("#3B4252")) # Realistic dark urban asphalt
        bg_grad.setColorAt(1.0, QColor("#2E3440"))
        self.setBackgroundBrush(QBrush(bg_grad))
        
        self.meteo = "Dégagé"
        
        self.vues_entites = {} 
        self.pool_vehicules = {} # Object pooling pour les véhicules
        self.objets_meteo = []
        self.arbres = []
        self.flaques = []
        self.traces_pneus = [] # Pour les skid marks
        self.verglas_overlay = None
        self.compteur_arbres = 0.0
        self.tick_lumiere = 0 # Pour les animations (gyrophares, clignotants)
        
        self.hologramme = None
        self.type_hologramme = None
        
        self._draw_infrastructure()
        
    def clear(self):
        """Surcharge de clear pour éviter les memory leaks et dangling references."""
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

    def set_meteo(self, etat):
        try:
            self.meteo = etat
            visibilite_flaques = (etat in ("Pluie", "Tempête"))
            for flaque in self.flaques:
                flaque.setVisible(visibilite_flaques)
            if self.verglas_overlay:
                self.verglas_overlay.setVisible(etat == "Gel")
        except Exception as e:
            logger.error(f"Erreur set_meteo: {e}", exc_info=True)

    def _draw_infrastructure(self):
        try:
            road_width = 8.0 * self.PIXELS_PAR_METRE 
            
            road_grad_v = QLinearGradient(-road_width/2, 0, road_width/2, 0)
            road_grad_v.setColorAt(0.0, QColor("#444444"))
            road_grad_v.setColorAt(0.05, QColor("#333333"))
            road_grad_v.setColorAt(0.95, QColor("#333333"))
            road_grad_v.setColorAt(1.0, QColor("#444444"))
            
            road_grad_h = QLinearGradient(0, -road_width/2, 0, road_width/2)
            road_grad_h.setColorAt(0.0, QColor("#444444"))
            road_grad_h.setColorAt(0.05, QColor("#333333"))
            road_grad_h.setColorAt(0.95, QColor("#333333"))
            road_grad_h.setColorAt(1.0, QColor("#444444"))
            
            no_pen = QPen(Qt.PenStyle.NoPen)
            
            self.addRect(-road_width/2, -500, road_width, 1000, no_pen, QBrush(road_grad_v))
            self.addRect(-500, -road_width/2, 1000, road_width, no_pen, QBrush(road_grad_h))
            self.addRect(-road_width/2, -road_width/2, road_width, road_width, no_pen, QBrush(QColor("#333333")))
            
            self.verglas_overlay = self.addRect(-road_width/2, -road_width/2, road_width, road_width, no_pen, QBrush(QColor(150, 200, 255, 120)))
            self.verglas_overlay.setVisible(self.meteo == "Gel")
            
            bike_pen = QPen(Qt.PenStyle.NoPen)
            bike_brush = QBrush(QColor("#B0BEC5")) # More concrete color for sidewalks instead of brown
            
            self.addRect(-road_width/2 - 20, -500, 20, 1000, bike_pen, bike_brush)
            self.addRect(road_width/2, -500, 20, 1000, bike_pen, bike_brush)
            self.addRect(-500, -road_width/2 - 20, 1000, 20, bike_pen, bike_brush)
            self.addRect(-500, road_width/2, 1000, 20, bike_pen, bike_brush)
            
            line_pen = QPen(QColor("#FFFFFF"), 2, Qt.PenStyle.DashLine)
            self.addLine(0, -500, 0, -road_width/2, line_pen)
            self.addLine(0, road_width/2, 0, 500, line_pen)
            self.addLine(-500, 0, -road_width/2, 0, line_pen)
            self.addLine(road_width/2, 0, 500, 0, line_pen)
            
            stop_pen = QPen(QColor("#FFFFFF"), 4)
            stop_d = 10.0 * self.PIXELS_PAR_METRE 
            
            self.addLine(-road_width/2, -stop_d, 0, -stop_d, stop_pen) 
            self.addLine(0, stop_d, road_width/2, stop_d, stop_pen) 
            self.addLine(-stop_d, 0, -stop_d, road_width/2, stop_pen) 
            self.addLine(stop_d, -road_width/2, stop_d, 0, stop_pen) 
            
            ped_pen = QPen(QColor("#FFFFFF"), 2)
            ped_brush = QBrush(QColor("#FFFFFF"))
            offset = 8.0 * self.PIXELS_PAR_METRE
            
            for cx, cy, is_vertical in [(0, -offset - 20, True), (0, offset, True), (offset, 0, False), (-offset - 20, 0, False)]:
                for i in range(int(-road_width/2) + 5, int(road_width/2), 10):
                    if is_vertical: self.addRect(i, cy, 6, 20, ped_pen, ped_brush)
                    else: self.addRect(cx, i, 20, 6, ped_pen, ped_brush)

            flaque_brush = QBrush(QColor(100, 150, 255, 100))
            for _ in range(15):
                fx, fy = random.randint(-400, 400), random.randint(-400, 400)
                flaque = self.addEllipse(fx, fy, random.randint(20, 50), random.randint(10, 30), no_pen, flaque_brush)
                flaque.setVisible(False)
                self.flaques.append(flaque)

            tree_pen = QPen(QColor("#1B5E20"), 1)
            tree_brush = QBrush(QColor("#2E7D32"))
            positions_arbres = [(-150, -150), (150, -150), (-150, 150), (150, 150), (-250, 80), (80, -250), (200, 300), (-300, -200)]
            
            for tx, ty in positions_arbres:
                # Replace heavy QGraphicsDropShadowEffect with simple ellipse shadow for performance
                shadow = self.addEllipse(tx+5, ty+5, 30, 30, no_pen, QBrush(QColor(0, 0, 0, 100)))
                arbre = self.addEllipse(tx, ty, 30, 30, tree_pen, tree_brush)
                arbre.setTransformOriginPoint(tx+15, ty+15)
                self.arbres.append(arbre)
                
            self.feu_eo_1 = self.addEllipse(-130, 45, 20, 20, no_pen, QBrush(Qt.GlobalColor.black))
            self.feu_eo_2 = self.addEllipse(110, -65, 20, 20, no_pen, QBrush(Qt.GlobalColor.black))
            self.feu_ns_1 = self.addEllipse(-65, -130, 20, 20, no_pen, QBrush(Qt.GlobalColor.black))
            self.feu_ns_2 = self.addEllipse(45, 110, 20, 20, no_pen, QBrush(Qt.GlobalColor.black))
        except Exception as e:
            logger.error(f"Erreur _draw_infrastructure: {e}", exc_info=True)

    def _obtenir_couleur_qt(self, enum_feu):
        try:
            if enum_feu == CouleurFeu.VERT: return QColor("#4CAF50")
            elif enum_feu == CouleurFeu.ORANGE: return QColor("#FF9800")
            return QColor("#F44336")
        except Exception:
            return QColor("#F44336")

    def _create_vehicle_view(self, entite):
        largeur_px = entite.longueur_m * self.PIXELS_PAR_METRE
        hauteur_px = entite.largeur_m * self.PIXELS_PAR_METRE
        
        couleur = QColor("#2196F3")
        if entite.type_entite == TypeVehicule.POIDS_LOURD: couleur = QColor("#607D8B")
        elif entite.type_entite == TypeVehicule.CONVOI_EXCEPTIONNEL: couleur = QColor("#FF9800")
        elif entite.type_entite == TypeVehicule.VIG_VTA: couleur = QColor("#F44336")
        elif entite.type_entite == TypeVehicule.PIETON: couleur = QColor("#9C27B0")
        elif entite.type_entite == TypeVehicule.CYCLISTE: couleur = QColor("#00BCD4")
        
        group = self.addRect(-largeur_px/2, -hauteur_px/2, largeur_px, hauteur_px, QPen(Qt.PenStyle.NoPen), QBrush(Qt.GlobalColor.transparent))
        
        # Fast shadow using simple rect instead of heavy QGraphicsDropShadowEffect
        shadow = self.addRect(-largeur_px/2 + 3, -hauteur_px/2 + 3, largeur_px, hauteur_px, QPen(Qt.PenStyle.NoPen), QBrush(QColor(0, 0, 0, 100)))
        shadow.setParentItem(group)
        
        if entite.type_entite == TypeVehicule.PIETON:
            body = self.addEllipse(-largeur_px/2, -hauteur_px/2, largeur_px, hauteur_px, QPen(Qt.PenStyle.NoPen), QBrush(couleur))
            body.setParentItem(group)
            head = self.addEllipse(-largeur_px/4, -hauteur_px/4, largeur_px/2, hauteur_px/2, QPen(Qt.PenStyle.NoPen), QBrush(QColor("#FFCC80")))
            head.setParentItem(group)
        elif entite.type_entite == TypeVehicule.CYCLISTE:
            frame = self.addRect(-largeur_px/2, -hauteur_px/6, largeur_px, hauteur_px/3, QPen(Qt.PenStyle.NoPen), QBrush(QColor("#B0BEC5")))
            frame.setParentItem(group)
            cyclist = self.addEllipse(-largeur_px/4, -hauteur_px/2, largeur_px/2, hauteur_px, QPen(Qt.PenStyle.NoPen), QBrush(couleur))
            cyclist.setParentItem(group)
        else:
            wheel_w = largeur_px * 0.2
            wheel_h = hauteur_px * 0.25
            for wx, wy in [(largeur_px*0.25, hauteur_px/2), (-largeur_px*0.25, hauteur_px/2), 
                           (largeur_px*0.25, -hauteur_px/2), (-largeur_px*0.25, -hauteur_px/2)]:
                w = self.addRect(wx - wheel_w/2, wy - wheel_h/2, wheel_w, wheel_h, QPen(Qt.PenStyle.NoPen), QBrush(QColor("#111")))
                w.setParentItem(group)
                
            grad = QLinearGradient(-largeur_px/2, 0, largeur_px/2, 0)
            grad.setColorAt(0.0, couleur.darker(150))
            grad.setColorAt(0.5, couleur)
            grad.setColorAt(1.0, couleur.darker(150))
            chassis = self.addRect(-largeur_px/2, -hauteur_px/2.2, largeur_px, hauteur_px/1.1, QPen(QColor("#222"), 1), QBrush(grad))
            chassis.setParentItem(group)
            
            glass = QColor(135, 206, 235, 200)
            windshield = self.addRect(largeur_px*0.1, -hauteur_px/2.5, largeur_px*0.2, hauteur_px/1.25, QPen(Qt.PenStyle.NoPen), QBrush(glass))
            windshield.setParentItem(group)
            rear_win = self.addRect(-largeur_px*0.35, -hauteur_px/2.5, largeur_px*0.15, hauteur_px/1.25, QPen(Qt.PenStyle.NoPen), QBrush(glass))
            rear_win.setParentItem(group)
            
            hl1 = self.addEllipse(largeur_px/2 - 4, -hauteur_px/2.5, 6, 6, QPen(Qt.PenStyle.NoPen), QBrush(QColor(255, 255, 200)))
            hl2 = self.addEllipse(largeur_px/2 - 4, hauteur_px/2.5 - 6, 6, 6, QPen(Qt.PenStyle.NoPen), QBrush(QColor(255, 255, 200)))
            hl1.setParentItem(group); hl2.setParentItem(group)
            
            # Clignotants
            clig_g = self.addEllipse(largeur_px/2 - 4, -hauteur_px/2.2, 4, 4, QPen(Qt.PenStyle.NoPen), QBrush(QColor(255, 165, 0)))
            clig_d = self.addEllipse(largeur_px/2 - 4, hauteur_px/2.2 - 4, 4, 4, QPen(Qt.PenStyle.NoPen), QBrush(QColor(255, 165, 0)))
            clig_g.setParentItem(group); clig_d.setParentItem(group)
            clig_g.setData(2, "clig_g"); clig_d.setData(2, "clig_d")
            clig_g.hide(); clig_d.hide()
            
            if entite.type_entite in (TypeVehicule.VIG_VTA, TypeVehicule.VIG_VTI):
                gyro_b = self.addRect(-4, -hauteur_px/4, 4, hauteur_px/2, QPen(Qt.PenStyle.NoPen), QBrush(QColor(0, 50, 255, 220)))
                gyro_r = self.addRect(0, -hauteur_px/4, 4, hauteur_px/2, QPen(Qt.PenStyle.NoPen), QBrush(QColor(255, 0, 0, 220)))
                gyro_b.setParentItem(group); gyro_r.setParentItem(group)
                gyro_b.setData(2, "gyro_b"); gyro_r.setData(2, "gyro_r")
                gyro_b.hide(); gyro_r.hide()

        hitbox = self.addRect(-largeur_px, -hauteur_px, largeur_px*2, hauteur_px*2, QPen(Qt.PenStyle.NoPen), QBrush(Qt.GlobalColor.transparent))
        hitbox.setParentItem(group)
        hitbox.setData(0, "mobile") 
        
        group.setData(0, "mobile")
        return group, hitbox

    def _get_vehicle_view(self, entite):
        t = entite.type_entite
        if t in self.pool_vehicules and self.pool_vehicules[t]:
            group = self.pool_vehicules[t].pop()
            group.setData(1, entite.id_entite)
            for child in group.childItems():
                if child.data(0) == "mobile":
                    child.setData(1, entite.id_entite)
            group.show()
            return group
            
        group, hitbox = self._create_vehicle_view(entite)
        group.setData(1, entite.id_entite)
        hitbox.setData(1, entite.id_entite)
        return group

    def mettre_a_jour_entites(self, liste_entites, intersection):
        try:
            c_eo = self._obtenir_couleur_qt(intersection.feu_eo)
            c_ns = self._obtenir_couleur_qt(intersection.feu_ns)
            
            self.feu_eo_1.setBrush(QBrush(c_eo)); self.feu_eo_2.setBrush(QBrush(c_eo))
            self.feu_ns_1.setBrush(QBrush(c_ns)); self.feu_ns_2.setBrush(QBrush(c_ns))

            self.compteur_arbres += 0.05
            angle_vent = math.sin(self.compteur_arbres) * 5.0
            if self.meteo == "Tempête": angle_vent *= 4.0
            elif self.meteo == "Pluie": angle_vent *= 2.0
            for arbre in self.arbres:
                arbre.setRotation(angle_vent)

            if self.meteo in ("Pluie", "Tempête"):
                nb_gouttes = 50 if self.meteo == "Pluie" else 150
                pen_pluie = QPen(QColor(150, 200, 255, 180), 1 if self.meteo=="Pluie" else 2)
                
                while len(self.objets_meteo) < nb_gouttes:
                    ligne = self.addLine(0, 0, 0, 0, pen_pluie)
                    self.objets_meteo.append(ligne)
                
                for i, ligne in enumerate(self.objets_meteo):
                    if i < nb_gouttes:
                        rx, ry = random.randint(-450, 450), random.randint(-450, 450)
                        ligne.setPen(pen_pluie)
                        ligne.setLine(rx, ry, rx - 10, ry + 20)
                        ligne.setVisible(True)
                    else:
                        ligne.setVisible(False)
            else:
                for ligne in self.objets_meteo:
                    ligne.setVisible(False)

            ids_presents = set()
            self.tick_lumiere += 1
            
            for entite in liste_entites:
                ids_presents.add(entite.id_entite)
                px = entite.pos_x * self.PIXELS_PAR_METRE
                py = entite.pos_y * self.PIXELS_PAR_METRE
                
                if entite.id_entite not in self.vues_entites:
                    # Stocker un tuple (vue, type_entite) pour éviter les problèmes d'enum
                    self.vues_entites[entite.id_entite] = (self._get_vehicle_view(entite), entite.type_entite)
                
                vue, _ = self.vues_entites[entite.id_entite]
                vue.setPos(px, py)
                vue.setRotation(math.degrees(entite.cap))
                
                acc = getattr(entite, 'commande_acceleration', 0.0)
                freinage = getattr(entite, 'freinage_mecanique', False)
                if freinage or acc < -4.0:
                    trace = self.addEllipse(px - 2, py - 2, 4, 4, QPen(Qt.PenStyle.NoPen), QBrush(QColor(0, 0, 0, 100)))
                    self.traces_pneus.append(trace)
                    if len(self.traces_pneus) > 300:
                        old_trace = self.traces_pneus.pop(0)
                        self.removeItem(old_trace)
                        if not sip.isdeleted(old_trace):
                            sip.delete(old_trace)
                
                for child in vue.childItems():
                    d2 = child.data(2)
                    if d2 in ("clig_g", "clig_d"):
                        clignote_g = getattr(entite, 'etat_depassement', 0) == 1
                        clignote_d = getattr(entite, 'etat_depassement', 0) == 2
                        ai = getattr(entite, 'action_intersection', None)
                        if ai is not None:
                            diff = (ai - getattr(entite, 'cap', 0) + math.pi) % (2 * math.pi) - math.pi
                            if diff < -0.1:
                                clignote_g = True
                            elif diff > 0.1:
                                clignote_d = True
                        if d2 == "clig_g":
                            child.setVisible(clignote_g and self.tick_lumiere % 10 < 5)
                        elif d2 == "clig_d":
                            child.setVisible(clignote_d and self.tick_lumiere % 10 < 5)
                    elif d2 == "gyro_b":
                        child.setVisible(self.tick_lumiere % 10 < 5)
                    elif d2 == "gyro_r":
                        child.setVisible(self.tick_lumiere % 10 >= 5)
                
            a_supprimer = []
            
            for e_id, (vue, t) in self.vues_entites.items():
                if e_id not in ids_presents:
                    a_supprimer.append(e_id)
            
            for e_id in a_supprimer:
                vue, t = self.vues_entites.pop(e_id)
                
                if t not in self.pool_vehicules:
                    self.pool_vehicules[t] = []
                    
                if len(self.pool_vehicules[t]) < 100:
                    vue.hide()
                    self.pool_vehicules[t].append(vue)
                else:
                    self.removeItem(vue)
                    if not sip.isdeleted(vue):
                        sip.delete(vue)
                
        except Exception as e:
            logger.error(f"Erreur mettre_a_jour_entites: {e}", exc_info=True)
            
    def mouseMoveEvent(self, event):
        try:
            super().mouseMoveEvent(event)
            
            main_window = self.parent()
            if not main_window or not hasattr(main_window, "type_a_placer"):
                return
                
            t = main_window.type_a_placer
            
            if t is None:
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
            
            voie = main_window.dashboard.combo_voie_spawn.currentText()
            pos_x, pos_y, cap = x, y, 0.0
            
            if voie == "Passage Piéton" or t == TypeVehicule.PIETON:
                if abs(x) > abs(y):
                    pos_x = 9.0 if x > 0 else -9.0
                    pos_y = max(-4.0, min(4.0, y))
                    cap = math.pi/2 if y < 0 else -math.pi/2
                else:
                    pos_x = max(-4.0, min(4.0, x))
                    pos_y = 9.0 if y > 0 else -9.0
                    cap = 0.0 if x < 0 else math.pi
            elif voie == "Nord -> Sud":
                pos_x = -2.0
                pos_y = y
                cap = math.pi/2
            elif voie == "Sud -> Nord":
                pos_x = 2.0
                pos_y = y
                cap = -math.pi/2
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
                    cap = math.pi/2 if pos_x < 0 else -math.pi/2
                    
            if self.hologramme is None or self.type_hologramme != t:
                if self.hologramme is not None:
                    self.removeItem(self.hologramme)
                    if not sip.isdeleted(self.hologramme):
                        sip.delete(self.hologramme)
                
                largeur_px = 4.0 * self.PIXELS_PAR_METRE
                hauteur_px = 2.0 * self.PIXELS_PAR_METRE
                if t == TypeVehicule.POIDS_LOURD: largeur_px = 10.0 * self.PIXELS_PAR_METRE
                elif t == TypeVehicule.PIETON: largeur_px, hauteur_px = 5.0, 5.0
                elif t == TypeVehicule.CYCLISTE: largeur_px, hauteur_px = 15.0, 5.0
                
                self.hologramme = QGraphicsRectItem(-largeur_px/2, -hauteur_px/2, largeur_px, hauteur_px)
                self.hologramme.setBrush(QBrush(QColor(255, 255, 255, 120)))
                self.hologramme.setPen(QPen(QColor(0, 255, 0), 2, Qt.PenStyle.DashLine))
                self.addItem(self.hologramme)
                self.type_hologramme = t
                
            self.hologramme.setPos(pos_x * self.PIXELS_PAR_METRE, pos_y * self.PIXELS_PAR_METRE)
            self.hologramme.setRotation(math.degrees(cap))
            
        except Exception as e:
            logger.error(f"Erreur mouseMoveEvent: {e}", exc_info=True)
            
    def mousePressEvent(self, event):
        try:
            item = self.itemAt(event.scenePos(), self.views()[0].transform())
            
            if item and item.data(0) == "mobile" and item.data(1):
                self.signal_entite_selectionnee.emit(item.data(1))
            else:
                scene_pos = event.scenePos()
                m_x = scene_pos.x() / self.PIXELS_PAR_METRE
                m_y = scene_pos.y() / self.PIXELS_PAR_METRE
                self.signal_clic_vide.emit(m_x, m_y)
            
            super().mousePressEvent(event)
        except Exception as e:
            logger.error(f"Erreur mousePressEvent: {e}", exc_info=True)
