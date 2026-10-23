"""Module de gestion de l'environnement physique et météorologique du carrefour.

Ce module modélise les conditions ambiantes impactant directement l'adhérence
des véhicules au sol : température, niveau d'usure de la chaussée, hauteur
d'eau superficielle et météo générale (dégagé, pluie, gel).
Il fournit le calcul physique dynamique du coefficient de friction (adhérence pneu-chaussée).
"""

import logging
import math
import random
from enum import Enum

logger = logging.getLogger(__name__)


class ConditionsMeteo(Enum):
    """Énumération des conditions météorologiques applicables au carrefour.

    Attributes:
        DEGAGE: Temps sec et clair, adhérence nominale.
        PLUIE: Précipitations liquides induisant un risque d'aquaplanage.
        GEL: Présence de verglas ou givre réduisant drastiquement l'adhérence.
    """
    DEGAGE = 1
    PLUIE = 2
    GEL = 3


class Environnement:
    """Gestionnaire de l'environnement physique et météorologique de la chaussée.

    Cette classe encapsule l'état de l'infrastructure routière et des conditions
    météorologiques associées. Elle applique des lois physiques pour évaluer
    en continu le coefficient de frottement effectif (µ) pneu-route, prenant en
    compte l'usure, la température et les phénomènes d'aquaplanage.

    Attributes:
        _temperature (float): Température ambiante en degrés Celsius (°C).
        _usure_route (float): Niveau d'usure de l'asphalte (normalisé entre 0.0 et 1.0).
        _hauteur_eau_mm (float): Épaisseur du film d'eau sur la chaussée en millimètres.
        _meteo (ConditionsMeteo): Condition météorologique courante.
    """

    def __init__(self, temperature: float = 20.0, usure_route: float = 0.0, hauteur_eau_mm: float = 0.0):
        """Initialise un nouvel environnement physique pour le carrefour.

        Args:
            temperature (float, optional): Température initiale en °C (entre -50.0 et 70.0).
                Par défaut 20.0.
            usure_route (float, optional): Taux initial d'usure de la chaussée (entre 0.0 et 1.0).
                Par défaut 0.0 (chaussée neuve).
            hauteur_eau_mm (float, optional): Hauteur d'eau initiale en mm (>= 0.0).
                Par défaut 0.0.

        Raises:
            ValueError: Si l'une des grandeurs physiques dépasse les bornes admissibles.
        """
        # Attributs protégés sous-jacents aux propriétés
        self._temperature = 20.0
        self._usure_route = 0.0
        self._hauteur_eau_mm = 0.0
        self._meteo = ConditionsMeteo.DEGAGE

        # Affectation via les setters pour valider immédiatement les contraintes
        self.temperature = temperature
        self.usure_route = usure_route
        self.hauteur_eau_mm = hauteur_eau_mm

    # ==============================
    # Propriétés et Validations
    # ==============================

    @property
    def temperature(self) -> float:
        """Obtient la température ambiante de l'environnement.

        Returns:
            float: Température en degrés Celsius (°C).
        """
        return self._temperature

    @temperature.setter
    def temperature(self, valeur: float):
        """Définit la température ambiante après vérification des limites physiques.

        Args:
            valeur (float): Température en degrés Celsius (°C), dans l'intervalle [-50.0, 70.0].

        Raises:
            ValueError: Si la température est en dehors de la plage [-50.0, 70.0].
        """
        if valeur < -50.0 or valeur > 70.0:
            raise ValueError(f"Température irréaliste : {valeur}°C. Bornes acceptées : [-50.0, 70.0].")
        self._temperature = float(valeur)

    @property
    def usure_route(self) -> float:
        """Obtient le niveau d'usure surfacique de la chaussée.

        Returns:
            float: Coefficient d'usure compris entre 0.0 (parfait état) et 1.0 (très dégradé).
        """
        return self._usure_route

    @usure_route.setter
    def usure_route(self, valeur: float):
        """Définit le niveau d'usure surfacique de la chaussée.

        Args:
            valeur (float): Taux d'usure normalisé, dans l'intervalle [0.0, 1.0].

        Raises:
            ValueError: Si le niveau d'usure est inférieur à 0.0 ou supérieur à 1.0.
        """
        if not (0.0 <= valeur <= 1.0):
            raise ValueError(f"L'usure doit être comprise entre 0.0 et 1.0 (valeur reçue : {valeur}).")
        self._usure_route = float(valeur)

    @property
    def hauteur_eau_mm(self) -> float:
        """Obtient la hauteur du film d'eau présent sur la route.

        Returns:
            float: Épaisseur du film d'eau en millimètres (mm).
        """
        return self._hauteur_eau_mm

    @hauteur_eau_mm.setter
    def hauteur_eau_mm(self, valeur: float):
        """Définit la hauteur du film d'eau présent sur la chaussée.

        Args:
            valeur (float): Hauteur d'eau en millimètres, doit être positive ou nulle.

        Raises:
            ValueError: Si la hauteur d'eau fournie est négative.
        """
        if valeur < 0.0:
            raise ValueError(f"La hauteur d'eau ne peut pas être négative (valeur reçue : {valeur} mm).")
        self._hauteur_eau_mm = float(valeur)

    @property
    def meteo(self) -> ConditionsMeteo:
        """Obtient la condition météorologique courante du carrefour.

        Returns:
            ConditionsMeteo: Constante de l'énumération représentant la météo.
        """
        return self._meteo

    @meteo.setter
    def meteo(self, valeur: ConditionsMeteo):
        """Définit la condition météorologique courante du carrefour.

        Args:
            valeur (ConditionsMeteo): Nouvelle condition météorologique.

        Raises:
            TypeError: Si la valeur passée n'est pas une instance de ConditionsMeteo.
        """
        if not isinstance(valeur, ConditionsMeteo):
            raise TypeError(
                f"Le paramètre météo doit être une instance de ConditionsMeteo (reçu : {type(valeur).__name__})."
            )
        self._meteo = valeur

    # ==============================
    # Calculs Physiques d'Adhérence
    # ==============================

    def calculer_coefficient_friction(self) -> float:
        """Calcule le coefficient de friction effectif (µ) de la chaussée.

        Ce modèle cinématique et tribologique évalue l'adhérence pneu-route en
        combinant quatre composantes physiques :
        1. **Adhérence nominale** : base théorique d'un asphalte sec standard avec micro-rugosités
           (µ initial compris aléatoirement entre 0.80 et 0.90).
        2. **Dégradation par usure mécanique** : atténuation linéaire liée à l'état du bitume
           selon la formule : `µ_usure = µ_base * (1.0 - 0.3 * usure_route)`.
        3. **Sensibilité thermique** : modèle gaussien centré sur la température optimale de 22°C
           avec écart-type thermique de 30°C : `facteur = exp(-((T - 22.0) / 30.0)^2)`.
        4. **Conditions de surface et aquaplanage** :
           - En temps de pluie (`ConditionsMeteo.PLUIE`), atténuation exponentielle en fonction
             de la hauteur d'eau superficielle simulant la perte de contact hydrodynamique
             (aquaplanage) : `facteur_eau = exp(-attenuation * hauteur_eau_mm)` avec
             `attenuation` tirée uniformément dans [0.12, 0.18].
           - En temps de gel (`ConditionsMeteo.GEL`), réduction drastique simulant le verglas
             par un facteur multiplicateur compris entre 0.10 et 0.20.
           - En conditions dégagées, légère dispersion aléatoire [0.95, 1.05] simulant poussières
             et granulométrie locale.

        Returns:
            float: Coefficient de frottement adimensionnel borné strictement dans [0.05, 1.0].
        """
        try:
            # Étape 1 : Base théorique d'un asphalte standard avec rugosité naturelle
            friction_base = random.uniform(0.80, 0.90)

            # Étape 2 : Prise en compte de la détérioration de l'infrastructure routière
            # Une usure maximale (1.0) dégrade l'adhérence de base de 30 %.
            friction_base = friction_base * (1.0 - (0.3 * self._usure_route))

            # Étape 3 : Modèle thermique continu (profil gaussien centré sur 22 °C)
            # L'adhérence des pneumatiques est optimale aux alentours de 20-22 °C et diminue lors de froids ou chaleurs extrêmes.
            ecart_optimal = (self._temperature - 22.0) / 30.0
            facteur_temperature = math.exp(-(ecart_optimal ** 2))
            friction_temp = friction_base * facteur_temperature

            # Étape 4 : Dégradation hydrodynamique (météo et aquaplanage)
            if self._meteo == ConditionsMeteo.PLUIE and self._hauteur_eau_mm > 0.0:
                # Modélisation de l'aquaplanage : la couche d'eau soulève le pneumatique,
                # diminuant exponentiellement la surface de contact direct avec le bitume.
                attenuation_eau = random.uniform(0.12, 0.18)
                facteur_eau = math.exp(-attenuation_eau * self._hauteur_eau_mm)
                friction_finale = friction_temp * facteur_eau
            elif self._meteo == ConditionsMeteo.GEL:
                # Présence d'un film de glace ou de verglas : rupture quasi-totale du frottement sec
                facteur_gel = random.uniform(0.10, 0.20)
                friction_finale = friction_temp * facteur_gel
            else:
                # Chaussée dégagée : variations mineures dues aux poussières et à la granulométrie
                facteur_sec = random.uniform(0.95, 1.05)
                friction_finale = friction_temp * facteur_sec

            # Étape 5 : Application des bornes physiques d'adhérence (minimum 0.05, maximum 1.0)
            return max(0.05, min(1.0, friction_finale))

        except Exception as e:
            logger.error(
                f"[Environnement] Erreur imprévue lors du calcul du coefficient de friction : {e}",
                exc_info=True
            )
            # Valeur de repli sécuritaire représentative d'une chaussée standard
            return 0.70
