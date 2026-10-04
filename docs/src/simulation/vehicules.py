"""
Modèles physiques vectoriels (Intégration d'Euler).
Implémente le Modèle Cinématique et l'Aérodynamisme.
Encapsulation stricte via @property (attributs pseudo-privés).
"""
import math
import random
from enum import Enum


class TypeVehicule(Enum):
    VOITURE = 1
    POIDS_LOURD = 2
    CONVOI_EXCEPTIONNEL = 3
    VIG_VTA = 4
    VIG_VTI = 5
    PIETON = 6
    CYCLISTE = 7


class EntitePhysique:
    """Entité soumise aux lois de la dynamique d'Euler."""
    
    def __init__(self, id_entite, type_entite, masse_kg):
        self.__id_entite = id_entite
        self.__type_entite = type_entite
        
        # États Dynamiques (Euclidiens)
        self.__masse_kg = masse_kg
        self.__pos_x = 0.0      
        self.__pos_y = 0.0      
        self.__vitesse = 0.0    
        self.__cap = 0.0        
        self.__cap_cible = 0.0
        self.__voie_cible_y = 0.0
        self.__voie_cible_x = 0.0
        self.__est_axe_x = True
        
        # Inputs de pilotage
        self.__commande_acceleration = 0.0 
        self.__commande_braquage = 0.0     
        self.__freinage_mecanique = False
        self.__action_intersection = None
        self.__etat_depassement = 0 # 0: normal, 1: deboitement, 2: rabattement
        
        # Caractéristiques Géométriques et Aérodynamiques
        self.__longueur_m = 4.0     
        self.__largeur_m = 1.8
        self.__surface_frontale_m2 = 2.2 
        self.__cx = 0.3 

    # ==============================
    # Propriétés (Getters/Setters)
    # ==============================
    @property
    def id_entite(self): return self.__id_entite
    @property
    def type_entite(self): return self.__type_entite
    @property
    def masse_kg(self): return self.__masse_kg

    @property
    def pos_x(self): return self.__pos_x
    @pos_x.setter
    def pos_x(self, val): self.__pos_x = val

    @property
    def pos_y(self): return self.__pos_y
    @pos_y.setter
    def pos_y(self, val): self.__pos_y = val

    @property
    def vitesse(self): return self.__vitesse
    @vitesse.setter
    def vitesse(self, val): self.__vitesse = val
    
    @property
    def cap(self): return self.__cap
    @cap.setter
    def cap(self, val): self.__cap = val

    @property
    def cap_cible(self): return self.__cap_cible
    @cap_cible.setter
    def cap_cible(self, val): self.__cap_cible = val

    @property
    def voie_cible_y(self): return self.__voie_cible_y
    @voie_cible_y.setter
    def voie_cible_y(self, val): self.__voie_cible_y = val

    @property
    def voie_cible_x(self): return self.__voie_cible_x
    @voie_cible_x.setter
    def voie_cible_x(self, val): self.__voie_cible_x = val
    
    @property
    def est_axe_x(self): return self.__est_axe_x
    @est_axe_x.setter
    def est_axe_x(self, val): self.__est_axe_x = val

    @property
    def commande_acceleration(self): return self.__commande_acceleration
    @commande_acceleration.setter
    def commande_acceleration(self, val): self.__commande_acceleration = val

    @property
    def commande_braquage(self): return self.__commande_braquage
    @commande_braquage.setter
    def commande_braquage(self, val): self.__commande_braquage = val

    @property
    def freinage_mecanique(self): return self.__freinage_mecanique
    @freinage_mecanique.setter
    def freinage_mecanique(self, val): self.__freinage_mecanique = val
    
    @property
    def action_intersection(self): return self.__action_intersection
    @action_intersection.setter
    def action_intersection(self, val): self.__action_intersection = val
    
    @property
    def etat_depassement(self): return self.__etat_depassement
    @etat_depassement.setter
    def etat_depassement(self, val): self.__etat_depassement = val

    @property
    def longueur_m(self): return self.__longueur_m
    @longueur_m.setter
    def longueur_m(self, val): self.__longueur_m = val

    @property
    def largeur_m(self): return self.__largeur_m
    @largeur_m.setter
    def largeur_m(self, val): self.__largeur_m = val

    @property
    def cx(self): return self.__cx
    @cx.setter
    def cx(self, val): self.__cx = val

    @property
    def surface_frontale_m2(self): return self.__surface_frontale_m2
    @surface_frontale_m2.setter
    def surface_frontale_m2(self, val): self.__surface_frontale_m2 = val

    @property
    def vitesse_kmh(self): return self.vitesse * 3.6


class Vehicule(EntitePhysique):
    """Véhicule avec équipement (pneus, ABS, aérodynamisme)."""
    
    def __init__(self, id_vehicule, v_type):
        masse_initiale = 1500.0
        try:
            if v_type == TypeVehicule.VOITURE:
                masse_initiale = random.gauss(1500.0, 200.0)
                longueur, largeur, cx, surface = 4.5, 1.8, 0.3, 2.2
            elif v_type == TypeVehicule.POIDS_LOURD:
                masse_initiale = random.gauss(25000.0, 3000.0)
                longueur, largeur, cx, surface = 12.0, 2.5, 0.8, 8.0
            elif v_type == TypeVehicule.CONVOI_EXCEPTIONNEL:
                masse_initiale = random.gauss(60000.0, 5000.0)
                longueur, largeur, cx, surface = 20.0, 3.0, 0.9, 10.0
            elif v_type in (TypeVehicule.VIG_VTA, TypeVehicule.VIG_VTI):
                masse_initiale = random.gauss(3500.0, 300.0)
                longueur, largeur, cx, surface = 5.0, 2.0, 0.4, 3.5
            elif v_type == TypeVehicule.PIETON:
                masse_initiale = random.gauss(75.0, 15.0) 
                longueur, largeur, cx, surface = 0.5, 0.5, 1.0, 0.8
            elif v_type == TypeVehicule.CYCLISTE:
                masse_initiale = random.gauss(90.0, 15.0) 
                longueur, largeur, cx, surface = 1.8, 0.6, 0.9, 1.0
            else:
                longueur, largeur, cx, surface = 4.0, 1.8, 0.3, 2.2
        except Exception:
            longueur, largeur, cx, surface = 4.0, 1.8, 0.3, 2.2
            
        super().__init__(id_vehicule, v_type, masse_initiale)
        self.longueur_m = longueur
        self.largeur_m = largeur
        self.cx = cx
        self.surface_frontale_m2 = surface

        # Équipement spécifique
        if v_type == TypeVehicule.PIETON:
            self.__possede_abs = False
            self.__age_pneus = 0.0
            self.__usure_pneus = 0.0
        elif v_type == TypeVehicule.CYCLISTE:
            self.__possede_abs = False
            self.__age_pneus = random.uniform(0.0, 5.0)
            self.__usure_pneus = random.uniform(0.0, 1.0)
        else:
            self.__possede_abs = (random.random() > 0.15)
            self.__age_pneus = random.uniform(0.0, 30.0) 
            self.__usure_pneus = random.uniform(0.0, 1.0)

    @property
    def possede_abs(self): return self.__possede_abs
    
    @property
    def age_pneus(self): return self.__age_pneus
    
    @property
    def usure_pneus(self): return self.__usure_pneus

    def get_force_aerodynamique(self, densite_air_rho=1.225):
        """F_aero = 0.5 * rho * S * Cx * v^2"""
        try:
            return 0.5 * densite_air_rho * self.surface_frontale_m2 * self.cx * (self.vitesse ** 2)
        except Exception:
            return 0.0
