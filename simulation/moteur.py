"""
Moteur central de la simulation.
Exécuté dans un thread séparé (QThread) pour ne pas bloquer l'interface graphique.
Calcule la physique (positions, cinématique) en temps réel.
"""

import time
from PyQt6.QtCore import QThread, pyqtSignal
from simulation.vehicules import TypeVehicule


class MoteurSimulation(QThread):
    # Signal émis à chaque "tick" de simulation, transportant la liste des entités
    tick_simulation = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.entites = []
        self._en_cours = False
        
        # Le temps s'écoule plus vite dans la simu ? (1.0 = temps réel)
        self.multiplicateur_temps = 1.0

    def ajouter_entite(self, entite):
        """Ajoute un usager à la boucle physique."""
        self.entites.append(entite)

    def demarrer(self):
        self._en_cours = True
        self.start()

    def arreter(self):
        self._en_cours = False
        self.wait() # Attend la fin propre du thread

    def run(self):
        """Boucle principale de calcul physique (environ 60 FPS)."""
        temps_precedent = time.time()
        
        while self._en_cours:
            temps_actuel = time.time()
            # Delta-time (dt) : temps écoulé depuis la dernière frame, en secondes
            dt = (temps_actuel - temps_precedent) * self.multiplicateur_temps
            temps_precedent = temps_actuel
            
            # --- CALCUL PHYSIQUE ---
            for entite in self.entites:
                # Récupération de la position et de la vitesse native (m/s)
                x, y = entite.position
                vitesse_ms = entite.vitesse_kmh / 3.6 
                
                # MVP : Tout le monde avance sur l'axe X (de la gauche vers la droite)
                # La distance = vitesse * temps
                nouvelle_distance = vitesse_ms * dt
                nouveau_x = x + nouvelle_distance
                
                # Mise à jour des coordonnées
                entite.position = (nouveau_x, y)
                
            # Envoi des données calculées à l'Interface Graphique
            self.tick_simulation.emit(self.entites)
            
            # Pause de 16 millisecondes (~60 itérations par seconde)
            time.sleep(0.016)
