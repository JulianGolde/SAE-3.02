import math
import random
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsDropShadowEffect
from PyQt6.QtGui import QBrush, QPen, QColor, QRadialGradient, QLinearGradient, QPainterPath
from PyQt6.QtCore import Qt, pyqtSignal
from simulation.intersection import CouleurFeu
from simulation.vehicules import TypeVehicule

class CarrefourScene(QGraphicsScene):
    PIXELS_PAR_METRE = 10.0
    signal_entite_selectionnee = pyqtSignal(str)
    signal_clic_vide = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(-500, -500, 1000, 1000)
        bg_grad = QRadialGradient(0, 0, 800)
        bg_grad.setColorAt(0.0, QColor("#4CAF50"))
        bg_grad.setColorAt(1.0, QColor("#2E7D32"))
        self.setBackgroundBrush(QBrush(bg_grad))
        self.meteo = "Dégagé"
        
        self.vues_entites = {} 
        self.objets_meteo = []
        self.arbres = []
        self.flaques = []
        self.compteur_arbres = 0.0
        
        self._draw_infrastructure()
        
    def set_meteo(self, etat):
        self.meteo = etat
        visibilite_flaques = (etat in ("Pluie", "Tempête"))
        for flaque in self.flaques:
            flaque.setVisible(visibilite_flaques)

    def _draw_infrastructure(self):
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
        
        # Routes
        self.addRect(-road_width/2, -500, road_width, 1000, no_pen, QBrush(road_grad_v))
        self.addRect(-500, -road_width/2, 1000, road_width, no_pen, QBrush(road_grad_h))
        self.addRect(-road_width/2, -road_width/2, road_width, road_width, no_pen, QBrush(QColor("#333333")))
        
        # Pistes cyclables
        bike_pen = QPen(Qt.PenStyle.NoPen)
        bike_brush = QBrush(QColor("#795548"))
        self.addRect(-road_width/2 - 20, -500, 20, 1000, bike_pen, bike_brush)
        self.addRect(road_width/2, -500, 20, 1000, bike_pen, bike_brush)
        self.addRect(-500, -road_width/2 - 20, 1000, 20, bike_pen, bike_brush)
        self.addRect(-500, road_width/2, 1000, 20, bike_pen, bike_brush)
        
        # Lignes médianes
        line_pen = QPen(QColor("#FFFFFF"), 2, Qt.PenStyle.DashLine)
        self.addLine(0, -500, 0, -road_width/2, line_pen)
        self.addLine(0, road_width/2, 0, 500, line_pen)
        self.addLine(-500, 0, -road_width/2, 0, line_pen)
        self.addLine(road_width/2, 0, 500, 0, line_pen)
        
        # Lignes de stop
        stop_pen = QPen(QColor("#FFFFFF"), 4)
        stop_d = 10.0 * self.PIXELS_PAR_METRE # 10m from center
        # Stop line is drawn halfway across the road (on the right side for driving direction)
        self.addLine(-road_width/2, -stop_d, 0, -stop_d, stop_pen) # Coming from North (going South)
        self.addLine(0, stop_d, road_width/2, stop_d, stop_pen) # Coming from South (going North)
        self.addLine(-stop_d, 0, -stop_d, road_width/2, stop_pen) # Coming from West (going East)
        self.addLine(stop_d, -road_width/2, stop_d, 0, stop_pen) # Coming from East (going West)
        
        # Passages piétons
        ped_pen = QPen(QColor("#FFFFFF"), 2)
        ped_brush = QBrush(QColor("#FFFFFF"))
        # Crossing is between 80px and 100px from center. We draw at 80px with width 20px.
        offset = 8.0 * self.PIXELS_PAR_METRE
        # Haut, Bas, Droite, Gauche
        for cx, cy, is_vertical in [(0, -offset - 20, True), (0, offset, True), (offset, 0, False), (-offset - 20, 0, False)]:
            for i in range(int(-road_width/2) + 5, int(road_width/2), 10):
                if is_vertical: self.addRect(i, cy, 6, 20, ped_pen, ped_brush)
                else: self.addRect(cx, i, 20, 6, ped_pen, ped_brush)

        # Flaques d'eau
        flaque_brush = QBrush(QColor(100, 150, 255, 100))
        for _ in range(15):
            fx, fy = random.randint(-400, 400), random.randint(-400, 400)
            flaque = self.addEllipse(fx, fy, random.randint(20, 50), random.randint(10, 30), no_pen, flaque_brush)
            flaque.setVisible(False)
            self.flaques.append(flaque)

        # Arbres
        tree_pen = QPen(QColor("#1B5E20"), 1)
        tree_brush = QBrush(QColor("#2E7D32"))
        positions_arbres = [(-150, -150), (150, -150), (-150, 150), (150, 150), (-250, 80), (80, -250), (200, 300), (-300, -200)]
        for tx, ty in positions_arbres:
            arbre = self.addEllipse(tx, ty, 30, 30, tree_pen, tree_brush)
            arbre.setTransformOriginPoint(tx+15, ty+15)
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(10); shadow.setOffset(5, 5); shadow.setColor(QColor(0, 0, 0, 150))
            arbre.setGraphicsEffect(shadow)
            self.arbres.append(arbre)
            
        # Feux
        self.feu_eo_1 = self.addEllipse(-130, 45, 20, 20, no_pen, QBrush(Qt.GlobalColor.black))
        self.feu_eo_2 = self.addEllipse(110, -65, 20, 20, no_pen, QBrush(Qt.GlobalColor.black))
        self.feu_ns_1 = self.addEllipse(-65, -130, 20, 20, no_pen, QBrush(Qt.GlobalColor.black))
        self.feu_ns_2 = self.addEllipse(45, 110, 20, 20, no_pen, QBrush(Qt.GlobalColor.black))

    def _obtenir_couleur_qt(self, enum_feu):
        if enum_feu == CouleurFeu.VERT: return QColor("#4CAF50")
        elif enum_feu == CouleurFeu.ORANGE: return QColor("#FF9800")
        return QColor("#F44336")

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
            for arbre in self.arbres: arbre.setRotation(angle_vent)

            for ligne in self.objets_meteo: self.removeItem(ligne)
            self.objets_meteo.clear()
            
            if self.meteo in ("Pluie", "Tempête"):
                pen_pluie = QPen(QColor(150, 200, 255, 180), 1 if self.meteo=="Pluie" else 2)
                for _ in range(50 if self.meteo=="Pluie" else 150):
                    rx, ry = random.randint(-450, 450), random.randint(-450, 450)
                    ligne = self.addLine(rx, ry, rx - 10, ry + 20, pen_pluie)
                    self.objets_meteo.append(ligne)

            ids_presents = set()
            for entite in liste_entites:
                ids_presents.add(entite.id_entite)
                px = entite.pos_x * self.PIXELS_PAR_METRE
                py = entite.pos_y * self.PIXELS_PAR_METRE
                
                if entite.id_entite not in self.vues_entites:
                    largeur_px = entite.longueur_m * self.PIXELS_PAR_METRE
                    hauteur_px = entite.largeur_m * self.PIXELS_PAR_METRE
                    
                    couleur = QColor("#2196F3")
                    if entite.type_entite == TypeVehicule.POIDS_LOURD: couleur = QColor("#607D8B")
                    elif entite.type_entite == TypeVehicule.CONVOI_EXCEPTIONNEL: couleur = QColor("#FF9800")
                    elif entite.type_entite == TypeVehicule.VIG_VTA: couleur = QColor("#F44336")
                    elif entite.type_entite == TypeVehicule.PIETON: couleur = QColor("#9C27B0")
                    elif entite.type_entite == TypeVehicule.CYCLISTE: couleur = QColor("#00BCD4")
                    
                    # Create an invisible container for the vehicle
                    group = self.addRect(-largeur_px/2, -hauteur_px/2, largeur_px, hauteur_px, QPen(Qt.PenStyle.NoPen), QBrush(Qt.GlobalColor.transparent))
                    
                    shadow = QGraphicsDropShadowEffect()
                    shadow.setBlurRadius(10); shadow.setOffset(3, 3); shadow.setColor(QColor(0, 0, 0, 150))
                    group.setGraphicsEffect(shadow)
                    
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
                        # Wheels
                        wheel_w = largeur_px * 0.2
                        wheel_h = hauteur_px * 0.25
                        for wx, wy in [(largeur_px*0.25, hauteur_px/2), (-largeur_px*0.25, hauteur_px/2), 
                                       (largeur_px*0.25, -hauteur_px/2), (-largeur_px*0.25, -hauteur_px/2)]:
                            w = self.addRect(wx - wheel_w/2, wy - wheel_h/2, wheel_w, wheel_h, QPen(Qt.PenStyle.NoPen), QBrush(QColor("#111")))
                            w.setParentItem(group)
                            
                        # Chassis
                        grad = QLinearGradient(-largeur_px/2, 0, largeur_px/2, 0)
                        grad.setColorAt(0.0, couleur.darker(150))
                        grad.setColorAt(0.5, couleur)
                        grad.setColorAt(1.0, couleur.darker(150))
                        chassis = self.addRect(-largeur_px/2, -hauteur_px/2.2, largeur_px, hauteur_px/1.1, QPen(QColor("#222"), 1), QBrush(grad))
                        chassis.setParentItem(group)
                        
                        # Windows
                        glass = QColor(135, 206, 235, 200)
                        windshield = self.addRect(largeur_px*0.1, -hauteur_px/2.5, largeur_px*0.2, hauteur_px/1.25, QPen(Qt.PenStyle.NoPen), QBrush(glass))
                        windshield.setParentItem(group)
                        rear_win = self.addRect(-largeur_px*0.35, -hauteur_px/2.5, largeur_px*0.15, hauteur_px/1.25, QPen(Qt.PenStyle.NoPen), QBrush(glass))
                        rear_win.setParentItem(group)
                        
                        # Lights
                        hl1 = self.addEllipse(largeur_px/2 - 4, -hauteur_px/2.5, 6, 6, QPen(Qt.PenStyle.NoPen), QBrush(QColor(255, 255, 200)))
                        hl2 = self.addEllipse(largeur_px/2 - 4, hauteur_px/2.5 - 6, 6, 6, QPen(Qt.PenStyle.NoPen), QBrush(QColor(255, 255, 200)))
                        hl1.setParentItem(group); hl2.setParentItem(group)
                        
                        # VTA Sirens
                        if entite.type_entite == TypeVehicule.VIG_VTA:
                            siren = self.addRect(-4, -hauteur_px/4, 8, hauteur_px/2, QPen(Qt.PenStyle.NoPen), QBrush(QColor(0, 50, 255, 220)))
                            siren.setParentItem(group)

                    hitbox = self.addRect(-largeur_px, -hauteur_px, largeur_px*2, hauteur_px*2, QPen(Qt.PenStyle.NoPen), QBrush(Qt.GlobalColor.transparent))
                    hitbox.setParentItem(group)
                    
                    group.setData(1, entite.id_entite)
                    group.setData(0, "mobile")
                    hitbox.setData(1, entite.id_entite)
                    hitbox.setData(0, "mobile")
                    
                    self.vues_entites[entite.id_entite] = group
                
                vue = self.vues_entites[entite.id_entite]
                vue.setPos(px, py)
                vue.setRotation(math.degrees(entite.cap))
                
            a_supprimer = []
            for e_id, vue in self.vues_entites.items():
                if e_id not in ids_presents:
                    self.removeItem(vue)
                    a_supprimer.append(e_id)
            for e_id in a_supprimer:
                del self.vues_entites[e_id]
                
        except Exception:
            pass
            
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
        except Exception:
            pass
