"""Modélisation cinématique et dynamique des entités mobiles du carrefour.

Ce module implémente la hiérarchie des entités mobiles (véhicules motorisés,
poids lourds, convois exceptionnels, véhicules d'urgence VTA/VTI, cyclistes et piétons).
Les entités sont régies par les lois du modèle cinématique d'Euler et subissent
les forces aérodynamiques, la résistance au roulement ainsi que les commandes
d'accélération et de braquage.
L'encapsulation est assurée de manière stricte via des propriétés (@property).
"""

import logging
import math
import random
from enum import Enum

logger = logging.getLogger(__name__)


class TypeVehicule(Enum):
    """Énumération des différentes catégories d'usagers et de véhicules.

    Attributes:
        VOITURE: Véhicule de tourisme standard (masse ~1500 kg).
        POIDS_LOURD: Camion de transport de marchandises (masse ~25000 kg).
        CONVOI_EXCEPTIONNEL: Véhicule hors gabarit et de masse élevée (~60000 kg).
        VIG_VTA: Véhicule d'intervention d'urgence prioritaire (ambulance, pompiers, police).
        VIG_VTI: Véhicule technique d'intervention d'infrastructure.
        PIETON: Usager vulnérable à pied traversant aux passages protégés (~75 kg).
        CYCLISTE: Usager deux-roues non motorisé ou à assistance électrique (~90 kg).
    """
    VOITURE = 1
    POIDS_LOURD = 2
    CONVOI_EXCEPTIONNEL = 3
    VIG_VTA = 4
    VIG_VTI = 5
    PIETON = 6
    CYCLISTE = 7


class EntitePhysique:
    """Entité cinématique de base régie par les lois d'intégration d'Euler.

    Cette classe définit les grandeurs d'état scalaires et vectorielles
    nécessaires au calcul de la trajectoire (position euclidienne, vitesse scalaire,
    orientation angulaire / cap, voie de circulation cible) ainsi que les commandes
    de pilotage (accélération, consigne de changement de direction).

    Attributes:
        __id_entite (str): Identifiant unique de l'entité.
        __type_entite (TypeVehicule): Catégorie d'usager.
        __masse_kg (float): Masse inertielle en kilogrammes.
        __pos_x (float): Coordonnée cartésienne X sur le plan horizontal (en mètres).
        __pos_y (float): Coordonnée cartésienne Y sur le plan horizontal (en mètres).
        __vitesse (float): Vitesse scalaire instantanée le long du vecteur cap (en m/s).
        __cap (float): Angle d'orientation actuel par rapport à l'axe X (en radians).
        __cap_cible (float): Angle d'orientation visé après virage (en radians).
        __voie_cible_y (float): Coordonnée Y de consigne pour le suivi de voie (en mètres).
        __voie_cible_x (float): Coordonnée X de consigne pour le suivi de voie (en mètres).
        __est_axe_x (bool): Vrai si le déplacement principal s'effectue sur l'axe Est-Ouest.
        __commande_acceleration (float): Consigne d'accélération longitudinale (en m/s²).
        __commande_braquage (float): Vitesse angulaire de braquage (en rad/s).
        __freinage_mecanique (bool): Indicateur d'engagement des étriers de frein mécanique.
        __action_intersection (float | None): Cap consigne à adopter au carrefour, ou None.
        __etat_depassement (int): État de dépassement (0: nominal, 1: déboîtement, 2: rabattement).
        a_detruire (bool): Marqueur de destruction pour le ramasse-miettes spatial.
        __longueur_m (float): Encombrement longitudinal (en mètres).
        __largeur_m (float): Encombrement transversal (en mètres).
        __surface_frontale_m2 (float): Surface frontale exposée à la traînée d'air (en m²).
        __cx (float): Coefficient adimensionnel de traînée aérodynamique.
    """

    def __init__(self, id_entite: str, type_entite: TypeVehicule, masse_kg: float = 1000.0):
        """Initialise une nouvelle entité physique dans le plan de simulation.

        Args:
            id_entite (str): Identifiant textuel unique de l'entité.
            type_entite (TypeVehicule): Catégorie d'usager associée.
            masse_kg (float, optional): Masse de l'entité en kg. Par défaut 1000.0.
        """
        self.__id_entite = str(id_entite)
        self.__type_entite = type_entite

        # États dynamiques et géométrie euclidienne
        self.__masse_kg = float(masse_kg)
        self.__pos_x = 0.0
        self.__pos_y = 0.0
        self.__vitesse = 0.0
        self.__cap = 0.0
        self.__cap_cible = 0.0
        self.__voie_cible_y = 0.0
        self.__voie_cible_x = 0.0
        self.__est_axe_x = True

        # Consignes de contrôle et pilotage
        self.__commande_acceleration = 0.0
        self.__commande_braquage = 0.0
        self.__freinage_mecanique = False
        self.__action_intersection = None
        self.__etat_depassement = 0  # 0: suivi nominal, 1: déboîtement, 2: rabattement
        self.indicateur_virage = 0  # -1: gauche, +1: droite, 0: tout droit
        self.en_virage_bezier = False
        self.en_panne = False
        self.a_detruire = False

        # Paramètres géométriques et aérodynamiques
        self.__longueur_m = 4.0
        self.__largeur_m = 1.8
        self.__surface_frontale_m2 = 2.2
        self.__cx = 0.3

    # ==============================
    # Propriétés de base et d'état
    # ==============================

    @property
    def id_entite(self) -> str:
        """Obtient l'identifiant unique de l'entité.

        Returns:
            str: Identifiant textuel.
        """
        return self.__id_entite

    @property
    def type_entite(self) -> TypeVehicule:
        """Obtient la catégorie d'usager ou type de véhicule.

        Returns:
            TypeVehicule: Type de l'entité.
        """
        return self.__type_entite

    @property
    def masse_kg(self) -> float:
        """Obtient la masse de l'entité.

        Returns:
            float: Masse en kilogrammes (kg).
        """
        return self.__masse_kg

    @property
    def pos_x(self) -> float:
        """Obtient la position longitudinale X.

        Returns:
            float: Position X en mètres.
        """
        return self.__pos_x

    @pos_x.setter
    def pos_x(self, val: float):
        """Définit la position longitudinale X.

        Args:
            val (float): Nouvelle coordonnée X en mètres.
        """
        self.__pos_x = float(val)

    @property
    def pos_y(self) -> float:
        """Obtient la position transversale Y.

        Returns:
            float: Position Y en mètres.
        """
        return self.__pos_y

    @pos_y.setter
    def pos_y(self, val: float):
        """Définit la position transversale Y.

        Args:
            val (float): Nouvelle coordonnée Y en mètres.
        """
        self.__pos_y = float(val)

    @property
    def vitesse(self) -> float:
        """Obtient la vitesse scalaire instantanée le long du vecteur cap.

        Returns:
            float: Vitesse en mètres par seconde (m/s).
        """
        return self.__vitesse

    @vitesse.setter
    def vitesse(self, val: float):
        """Définit la vitesse scalaire instantanée.

        Args:
            val (float): Vitesse en mètres par seconde (m/s, >= 0).
        """
        self.__vitesse = max(0.0, float(val))

    @property
    def cap(self) -> float:
        """Obtient l'orientation angulaire courante de l'entité.

        Returns:
            float: Cap en radians dans le plan cartésien [-pi, pi].
        """
        return self.__cap

    @cap.setter
    def cap(self, val: float):
        """Définit l'orientation angulaire courante de l'entité.

        Args:
            val (float): Cap en radians.
        """
        ancien_cap = self.__cap
        self.__cap = float(val)
        if self.__cap_cible == ancien_cap:
            self.__cap_cible = float(val)

    @property
    def cap_cible(self) -> float:
        """Obtient l'orientation angulaire visée après négociation du virage.

        Returns:
            float: Cap cible en radians.
        """
        return self.__cap_cible

    @cap_cible.setter
    def cap_cible(self, val: float):
        """Définit l'orientation angulaire visée.

        Args:
            val (float): Nouveau cap cible en radians.
        """
        self.__cap_cible = float(val)

    @property
    def voie_cible_y(self) -> float:
        """Obtient la position transversale Y visée pour le maintien de voie.

        Returns:
            float: Coordonnée Y en mètres.
        """
        return self.__voie_cible_y

    @voie_cible_y.setter
    def voie_cible_y(self, val: float):
        """Définit la position transversale Y visée.

        Args:
            val (float): Nouvelle coordonnée Y en mètres.
        """
        self.__voie_cible_y = float(val)

    @property
    def voie_cible_x(self) -> float:
        """Obtient la position longitudinale X visée pour le maintien de voie.

        Returns:
            float: Coordonnée X en mètres.
        """
        return self.__voie_cible_x

    @voie_cible_x.setter
    def voie_cible_x(self, val: float):
        """Définit la position longitudinale X visée.

        Args:
            val (float): Nouvelle coordonnée X en mètres.
        """
        self.__voie_cible_x = float(val)

    @property
    def est_axe_x(self) -> bool:
        """Indique si l'entité se déplace principalement sur l'axe longitudinal Est-Ouest.

        Returns:
            bool: Vrai si axe X (Est-Ouest), Faux si axe Y (Nord-Sud).
        """
        return self.__est_axe_x

    @est_axe_x.setter
    def est_axe_x(self, val: bool):
        """Définit l'axe principal de déplacement de l'entité.

        Args:
            val (bool): Vrai pour axe X, Faux pour axe Y.
        """
        self.__est_axe_x = bool(val)

    @property
    def commande_acceleration(self) -> float:
        """Obtient la commande d'accélération longitudinale consigne.

        Returns:
            float: Accélération en m/s² (positive pour traction, négative pour freinage).
        """
        return self.__commande_acceleration

    @commande_acceleration.setter
    def commande_acceleration(self, val: float):
        """Définit la commande d'accélération longitudinale consigne.

        Args:
            val (float): Accélération en m/s².
        """
        self.__commande_acceleration = float(val)

    @property
    def commande_braquage(self) -> float:
        """Obtient la vitesse angulaire de braquage consigne.

        Returns:
            float: Braquage en radians par seconde (rad/s).
        """
        return self.__commande_braquage

    @commande_braquage.setter
    def commande_braquage(self, val: float):
        """Définit la vitesse angulaire de braquage consigne.

        Args:
            val (float): Braquage en rad/s.
        """
        self.__commande_braquage = float(val)

    @property
    def freinage_mecanique(self) -> bool:
        """Indique si les étriers de frein mécanique sont activés.

        Returns:
            bool: Vrai en cas de freinage mécanique actif, Faux pour décélération par frein moteur.
        """
        return self.__freinage_mecanique

    @freinage_mecanique.setter
    def freinage_mecanique(self, val: bool):
        """Définit l'état des étriers de frein mécanique.

        Args:
            val (bool): Vrai pour activer le frein mécanique.
        """
        self.__freinage_mecanique = bool(val)

    @property
    def action_intersection(self) -> float | None:
        """Obtient l'angle de virage planifié pour l'intersection, le cas échéant.

        Returns:
            float | None: Cap ciblé au franchissement du carrefour, ou None si tout droit.
        """
        return self.__action_intersection

    @action_intersection.setter
    def action_intersection(self, val: float | None):
        """Définit l'angle de virage planifié pour le franchissement du carrefour.

        Args:
            val (float | None): Cap en radians ou None.
        """
        self.__action_intersection = float(val) if val is not None else None
        if self.__action_intersection is not None:
            delta = (self.__action_intersection - self.cap + math.pi) % (2.0 * math.pi) - math.pi
            if delta < -0.1:
                self.indicateur_virage = -1
            elif delta > 0.1:
                self.indicateur_virage = 1
            else:
                self.indicateur_virage = 0

    @property
    def etat_depassement(self) -> int:
        """Obtient l'état courant de la manœuvre de dépassement.

        Returns:
            int: 0 = circulation nominale sur voie, 1 = déboîtement / voie opposée,
                2 = manœuvre de rabattement en cours.
        """
        return self.__etat_depassement

    @etat_depassement.setter
    def etat_depassement(self, val: int):
        """Définit l'état de la manœuvre de dépassement.

        Args:
            val (int): Nouvel état (0, 1 ou 2).
        """
        self.__etat_depassement = int(val)

    @property
    def longueur_m(self) -> float:
        """Obtient la longueur totale hors-tout de l'entité.

        Returns:
            float: Longueur en mètres.
        """
        return self.__longueur_m

    @longueur_m.setter
    def longueur_m(self, val: float):
        """Définit la longueur totale hors-tout de l'entité.

        Args:
            val (float): Longueur en mètres (> 0).
        """
        self.__longueur_m = max(0.1, float(val))

    @property
    def largeur_m(self) -> float:
        """Obtient la largeur totale hors-tout de l'entité.

        Returns:
            float: Largeur en mètres.
        """
        return self.__largeur_m

    @largeur_m.setter
    def largeur_m(self, val: float):
        """Définit la largeur totale hors-tout de l'entité.

        Args:
            val (float): Largeur en mètres (> 0).
        """
        self.__largeur_m = max(0.1, float(val))

    @property
    def cx(self) -> float:
        """Obtient le coefficient de pénétration dans l'air (traînée aérodynamique).

        Returns:
            float: Coefficient adimensionnel Cx.
        """
        return self.__cx

    @cx.setter
    def cx(self, val: float):
        """Définit le coefficient de pénétration dans l'air.

        Args:
            val (float): Coefficient Cx (> 0).
        """
        self.__cx = max(0.01, float(val))

    @property
    def surface_frontale_m2(self) -> float:
        """Obtient la surface frontale effective exposée à l'air.

        Returns:
            float: Surface frontale en mètres carrés (m²).
        """
        return self.__surface_frontale_m2

    @surface_frontale_m2.setter
    def surface_frontale_m2(self, val: float):
        """Définit la surface frontale effective exposée à l'air.

        Args:
            val (float): Surface en m² (> 0).
        """
        self.__surface_frontale_m2 = max(0.01, float(val))

    @property
    def vitesse_kmh(self) -> float:
        """Calcule la vitesse scalaire instantanée en kilomètres par heure.

        Returns:
            float: Vitesse en km/h (conversion : v_ms * 3.6).
        """
        return self.vitesse * 3.6


class Vehicule(EntitePhysique):
    """Spécialisation d'EntitePhysique dotée d'équipements mécaniques et de sécurité.

    Cette classe paramètre les caractéristiques dimensionnelles, aérodynamiques
    et mécaniques spécifiques à chaque profil d'usager (voiture particulière,
    poids lourd, convoi exceptionnel, véhicule prioritaire VTA, piéton, cycliste).
    Elle modélise également l'équipement ABS, l'âge et l'usure des pneumatiques.

    Attributes:
        __possede_abs (bool): Présence du système d'antiblocage des roues.
        __age_pneus (float): Âge moyen des pneumatiques en années.
        __usure_pneus (float): Taux d'usure des bandes de roulement (de 0.0 neuf à 1.0 lisse).
    """

    def __init__(self, id_vehicule: str, v_type: TypeVehicule, masse_kg: float | None = None):
        """Initialise un nouveau véhicule avec ses caractéristiques d'équipement.

        Selon la catégorie choisie, les grandeurs physiques (masse, dimensions,
        surface frontale, coefficient de traînée Cx) sont tirées selon des lois
        normales ou uniformes représentatives de la réalité urbaine.

        Args:
            id_vehicule (str): Identifiant textuel unique du véhicule.
            v_type (TypeVehicule): Catégorie d'usager associée.
            masse_kg (float | None, optional): Masse forcée en kg, ou None pour
                utiliser la distribution statistique par défaut.
        """
        masse_initiale = 1500.0
        try:
            if v_type == TypeVehicule.VOITURE:
                masse_initiale = max(800.0, random.gauss(1500.0, 200.0))
                longueur, largeur, cx, surface = 4.5, 1.8, 0.3, 2.2
            elif v_type == TypeVehicule.POIDS_LOURD:
                masse_initiale = max(10000.0, random.gauss(25000.0, 3000.0))
                longueur, largeur, cx, surface = 12.0, 2.5, 0.8, 8.0
            elif v_type == TypeVehicule.CONVOI_EXCEPTIONNEL:
                masse_initiale = max(35000.0, random.gauss(60000.0, 5000.0))
                longueur, largeur, cx, surface = 20.0, 3.0, 0.9, 10.0
            elif v_type in (TypeVehicule.VIG_VTA, TypeVehicule.VIG_VTI):
                masse_initiale = max(2500.0, random.gauss(3500.0, 300.0))
                longueur, largeur, cx, surface = 5.0, 2.0, 0.4, 3.5
            elif v_type == TypeVehicule.PIETON:
                masse_initiale = max(40.0, random.gauss(75.0, 15.0))
                longueur, largeur, cx, surface = 0.5, 0.5, 1.0, 0.8
            elif v_type == TypeVehicule.CYCLISTE:
                masse_initiale = max(40.0, random.gauss(90.0, 15.0))
                longueur, largeur, cx, surface = 1.8, 0.6, 0.9, 1.0
            else:
                longueur, largeur, cx, surface = 4.0, 1.8, 0.3, 2.2
        except Exception as e:
            logger.error(
                f"[Vehicule] Erreur lors de la génération des paramètres physiques pour {id_vehicule} : {e}",
                exc_info=True
            )
            longueur, largeur, cx, surface = 4.0, 1.8, 0.3, 2.2

        if masse_kg is None:
            masse_kg = masse_initiale

        super().__init__(id_vehicule, v_type, masse_kg)
        self.longueur_m = longueur
        self.largeur_m = largeur
        self.cx = cx
        self.surface_frontale_m2 = surface

        # Dotation en équipements de sécurité et état d'usure des pneumatiques
        if v_type == TypeVehicule.PIETON:
            self.__possede_abs = False
            self.__age_pneus = 0.0
            self.__usure_pneus = 0.0
        elif v_type == TypeVehicule.CYCLISTE:
            self.__possede_abs = False
            self.__age_pneus = random.uniform(0.0, 5.0)
            self.__usure_pneus = random.uniform(0.0, 1.0)
        else:
            # 85 % du parc automobile équipé d'ABS
            self.__possede_abs = (random.random() > 0.15)
            self.__age_pneus = random.uniform(0.0, 30.0)
            self.__usure_pneus = random.uniform(0.0, 1.0)

    @property
    def possede_abs(self) -> bool:
        """Indique si le véhicule est équipé du système d'antiblocage ABS.

        Returns:
            bool: Vrai si l'ABS est présent et opérationnel.
        """
        return self.__possede_abs

    @property
    def age_pneus(self) -> float:
        """Obtient l'ancienneté estimée des pneumatiques.

        Returns:
            float: Âge moyen des pneus en années.
        """
        return self.__age_pneus

    @property
    def usure_pneus(self) -> float:
        """Obtient le taux d'usure de la bande de roulement des pneumatiques.

        Returns:
            float: Coefficient d'usure normalisé entre 0.0 (neuf) et 1.0 (complètement usé).
        """
        return self.__usure_pneus

    def get_force_aerodynamique(self, densite_air_rho: float = 1.225) -> float:
        """Calcule la force de traînée aérodynamique opposée au mouvement du véhicule.

        L'équation physique s'exprime selon la formule de traînée quadratique :
            F_aero = 0.5 * rho * S * Cx * v^2

        où :
            rho : masse volumique de l'air en kg/m³ (typiquement 1.225 à 20°C au niveau de la mer).
            S   : surface frontale en m².
            Cx  : coefficient adimensionnel de traînée.
            v   : vitesse instantanée en m/s.

        Args:
            densite_air_rho (float, optional): Masse volumique de l'air en kg/m³. Par défaut 1.225.

        Returns:
            float: Intensité scalaire de la force de traînée en Newtons (N).
        """
        try:
            return 0.5 * densite_air_rho * self.surface_frontale_m2 * self.cx * (self.vitesse ** 2)
        except Exception as e:
            logger.error(
                f"[Vehicule] Erreur lors du calcul de la force aérodynamique pour {self.id_entite} : {e}",
                exc_info=True
            )
            return 0.0
