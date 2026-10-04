import logging
logger = logging.getLogger(__name__)

"""
Module de gestion de l'environnement physique du carrefour.
Implémente l'encapsulation via @property et une modélisation
mathématique continue avec variations environnementales (bruit).
"""

import math
import random
from enum import Enum


class ConditionsMeteo(Enum):
    """Énumération des conditions météorologiques."""
    DEGAGE = 1
    PLUIE = 2
    GEL = 3


class Environnement:
    """Classe gérant l'environnement (météo, température, route)."""
    def __init__(self, temperature=20.0, usure_route=0.0, hauteur_eau_mm=0.0):
        """Initialise l'objet avec les paramètres requis.
        
        Args:
            *args: Arguments divers.
            **kwargs: Paramètres nommés.
        """
        # Utilisation d'un seul underscore pour les attributs protégés liés aux @property
        self._temperature = 20.0
        self._usure_route = 0.0
        self._hauteur_eau_mm = 0.0
        self._meteo = ConditionsMeteo.DEGAGE
        
        # Le passage par les propriétés déclenche les validations (setters)
        self.temperature = temperature
        self.usure_route = usure_route
        self.hauteur_eau_mm = hauteur_eau_mm

    # ==============================
    # Propriétés Pythoniques
    # ==============================
    @property
    def temperature(self):
        """Température ambiante.
        
        Returns:
            float: Température.
        """
        return self._temperature

    @temperature.setter
    def temperature(self, valeur):
        """Température ambiante.
        
        Returns:
            float: Température.
        """
        if valeur < -50.0 or valeur > 70.0:
            raise ValueError(f"Température irréaliste : {valeur}°C")
        self._temperature = valeur

    @property
    def usure_route(self):
        """Niveau d'usure de la route.
        
        Returns:
            float: Usure.
        """
        return self._usure_route

    @usure_route.setter
    def usure_route(self, valeur):
        """Niveau d'usure de la route.
        
        Returns:
            float: Usure.
        """
        if not (0.0 <= valeur <= 1.0):
            raise ValueError("L'usure doit être comprise entre 0.0 et 1.0.")
        self._usure_route = valeur

    @property
    def hauteur_eau_mm(self):
        """Hauteur d'eau sur la route.
        
        Returns:
            float: Hauteur en mm.
        """
        return self._hauteur_eau_mm

    @hauteur_eau_mm.setter
    def hauteur_eau_mm(self, valeur):
        """Hauteur d'eau sur la route.
        
        Returns:
            float: Hauteur en mm.
        """
        if valeur < 0.0:
            raise ValueError("La hauteur d'eau ne peut pas être négative.")
        self._hauteur_eau_mm = valeur

    @property
    def meteo(self):
        """Conditions météorologiques actuelles.
        
        Returns:
            ConditionsMeteo: Météo.
        """
        return self._meteo

    @meteo.setter
    def meteo(self, valeur):
        """Conditions météorologiques actuelles.
        
        Returns:
            ConditionsMeteo: Météo.
        """
        if not isinstance(valeur, ConditionsMeteo):
            raise TypeError("Le paramètre doit être une instance de ConditionsMeteo.")
        self._meteo = valeur

    # ==============================
    # Logique métier (Physique)
    # ==============================
    def calculer_coefficient_friction(self):
        """Calcule le coefficient de friction selon la météo et la route.
        
        Returns:
            float: Coefficient de friction.
        """
        """
        Calcule le coefficient de friction (µ) théorique de la route.
        Inclut des variations aléatoires par tranches généralistes.
        """
        # 1. Base théorique d'un asphalte avec variation (état de base de la route)
        friction_base = random.uniform(0.80, 0.90)

        # 2. Dégradation par l'usure de l'infrastructure
        friction_base = friction_base * (1.0 - (0.3 * self.usure_route))

        # 3. Impact continu de la température (Modèle gaussien)
        ecart_optimal = (self.temperature - 22.0) / 30.0
        facteur_temperature = math.exp(-(ecart_optimal ** 2))
        friction_temp = friction_base * facteur_temperature

        # 4. Modèle de friction selon la météo
        if self.meteo == ConditionsMeteo.PLUIE and self.hauteur_eau_mm > 0:
            # Aquaplaning : loi exponentielle + variation due aux flaques
            attenuation_eau = random.uniform(0.12, 0.18)
            facteur_eau = math.exp(-attenuation_eau * self.hauteur_eau_mm)
            friction_finale = friction_temp * facteur_eau
        elif self.meteo == ConditionsMeteo.GEL:
            # Sur glace, la friction varie fortement selon l'épaisseur et la densité (0.1 à 0.2)
            friction_finale = friction_temp * random.uniform(0.1, 0.2)
        else:
            # Route dégagée : micro-poussières et irrégularités
            friction_finale = friction_temp * random.uniform(0.95, 1.05)
        
        return max(0.05, min(1.0, friction_finale))
