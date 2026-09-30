"""
Scène graphique 2D pour la simulation du carrefour.
Gère le dessin des routes, passages piétons et entités (véhicules, animaux).
"""

from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtGui import QBrush, QPen, QColor
from PyQt6.QtCore import Qt, QRectF


class CarrefourScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Définition de la taille de la scène (repère centré sur 0,0)
        self.setSceneRect(-400, -400, 800, 800)
        
        # Fond vert (herbe)
        self.setBackgroundBrush(QBrush(QColor("#4CAF50")))
        
        self._draw_infrastructure()

    def _draw_infrastructure(self):
        """Dessine les routes et les marquages au sol."""
        road_width = 160
        asphalt_brush = QBrush(QColor("#333333"))
        no_pen = QPen(Qt.PenStyle.NoPen)
        
        # Route Verticale
        self.addRect(-road_width/2, -400, road_width, 800, no_pen, asphalt_brush)
        # Route Horizontale
        self.addRect(-400, -road_width/2, 800, road_width, no_pen, asphalt_brush)
        
        # Marquage au sol (Lignes discontinues centrales)
        line_pen = QPen(QColor("#FFFFFF"))
        line_pen.setWidth(4)
        line_pen.setStyle(Qt.PenStyle.DashLine)
        
        # Ligne centrale verticale
        self.addLine(0, -400, 0, -road_width/2, line_pen)
        self.addLine(0, road_width/2, 0, 400, line_pen)
        
        # Ligne centrale horizontale
        self.addLine(-400, 0, -road_width/2, 0, line_pen)
        self.addLine(road_width/2, 0, 400, 0, line_pen)
        
        # Passages piétons (simples rectangles blancs)
        pedestrian_pen = QPen(QColor("#FFFFFF"), 2)
        pedestrian_brush = QBrush(QColor("#FFFFFF"))
        
        # Exemple de passage piéton (Nord)
        for i in range(-70, 70, 20):
            self.addRect(i, -road_width/2 - 30, 10, 25, pedestrian_pen, pedestrian_brush)

    def mettre_a_jour_entites(self, liste_entites):
        """
        Efface les anciennes entités et redessine les nouvelles à leurs positions actuelles.
        """
        # 1. On supprime tous les objets graphiques "mobiles" (on garde l'infrastructure)
        for item in self.items():
            # Si c'est un QGraphicsRectItem et qu'il a une donnée "mobile"
            if item.data(0) == "mobile":
                self.removeItem(item)
                
        # 2. On dessine chaque entité à ses coordonnées exactes
        for entite in liste_entites:
            x, y = entite.position
            
            # Dimensions par défaut (Voiture)
            largeur = 40
            hauteur = 20
            couleur = QColor("#2196F3") # Bleu standard
            
            # Personnalisation visuelle rudimentaire selon le type
            from simulation.vehicules import TypeVehicule
            if entite.type_entite == TypeVehicule.POIDS_LOURD:
                largeur = 80
                hauteur = 25
                couleur = QColor("#607D8B") # Gris bleu
            elif entite.type_entite == TypeVehicule.VIG_VTA:
                couleur = QColor("#F44336") # Rouge pompiers
            elif entite.type_entite == TypeVehicule.PIETON:
                largeur = 10
                hauteur = 10
                couleur = QColor("#9C27B0") # Violet
            elif entite.type_entite == TypeVehicule.CYCLISTE:
                largeur = 15
                hauteur = 10
                couleur = QColor("#00BCD4") # Cyan
                
            rect = self.addRect(x, y - (hauteur/2), largeur, hauteur, QPen(Qt.PenStyle.NoPen), QBrush(couleur))
            # On marque l'objet comme mobile pour pouvoir l'effacer à la prochaine frame
            rect.setData(0, "mobile")

