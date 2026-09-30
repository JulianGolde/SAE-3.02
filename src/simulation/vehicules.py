"""
Modèles physiques des entités circulant sur le carrefour.
Gère les VIG, la cinématique et encapsule la logique via @property.
"""

import math
import random
from enum import Enum


class TypeVehicule(Enum):
    VOITURE = 1
    POIDS_LOURD = 2
    CONVOI_EXCEPTIONNEL = 3
    VIG_VTA = 4   # Sapeurs-pompiers, SAMU, Police (Gyrophare, 2 tons)
    VIG_VTI = 5   # Ambulance privée, EDF, Saleuses (Facilité de passage)
    PIETON = 6    # Traversée sur passages protégés
    CYCLISTE = 7  # Vélos, trottinettes (mobilité douce)


class EntitePhysique:
    """Classe de base stricte. Encapsulation via @property."""
    
    def __init__(self, id_entite, type_entite, masse_kg):
        if not id_entite:
            raise ValueError("L'ID de l'entité ne peut être vide.")
        if not isinstance(type_entite, TypeVehicule):
            raise TypeError("Le type d'entité est invalide.")
            
        self._id_entite = id_entite
        self._type_entite = type_entite
        self._vitesse_ms = 0.0
        self._position_xy = (0.0, 0.0)
        
        # Déclenche le validateur du setter
        self.masse_kg = masse_kg

    # ==============================
    # Propriétés (Getters/Setters)
    # ==============================
    @property
    def id_entite(self):
        return self._id_entite

    @property
    def type_entite(self):
        return self._type_entite

    @property
    def masse_kg(self):
        return self._masse_kg

    @masse_kg.setter
    def masse_kg(self, valeur):
        if valeur <= 0:
            raise ValueError(f"Masse invalide ({valeur} kg). Elle doit être strictement positive.")
        self._masse_kg = valeur

    @property
    def vitesse_kmh(self):
        return self._vitesse_ms * 3.6

    @vitesse_kmh.setter
    def vitesse_kmh(self, valeur):
        # Restriction retirée : permet les vitesses négatives (marche arrière)
        self._vitesse_ms = valeur / 3.6

    @property
    def position(self):
        return self._position_xy

    @position.setter
    def position(self, coords):
        if not isinstance(coords, tuple) or len(coords) != 2:
            raise ValueError("La position doit être un tuple (x, y).")
        self._position_xy = coords


class Vehicule(EntitePhysique):
    """
    Représentation d'un véhicule avec son équipement (technologie des pneus, ABS).
    """
    def __init__(self, id_vehicule, v_type):
        # Tirage réaliste de la masse
        if v_type == TypeVehicule.VOITURE:
            masse_initiale = random.gauss(1500.0, 200.0)
        elif v_type == TypeVehicule.POIDS_LOURD:
            masse_initiale = random.gauss(25000.0, 3000.0)
        elif v_type == TypeVehicule.CONVOI_EXCEPTIONNEL:
            masse_initiale = random.gauss(60000.0, 5000.0)
        elif v_type in (TypeVehicule.VIG_VTA, TypeVehicule.VIG_VTI):
            masse_initiale = random.gauss(3500.0, 300.0)
        elif v_type == TypeVehicule.PIETON:
            masse_initiale = random.gauss(75.0, 15.0) 
        elif v_type == TypeVehicule.CYCLISTE:
            masse_initiale = random.gauss(90.0, 15.0) 
        else:
            raise ValueError("Type d'entité inconnu lors de la définition de la masse.")
            
        super().__init__(id_vehicule, v_type, masse_initiale)
        
        # Un piéton n'a pas de pneus, un vélo n'a pas d'ABS.
        if v_type == TypeVehicule.PIETON:
            self._possede_abs = False
            self._age_technologique_pneus_annees = 0.0
            self._usure_pneus = 0.0
        elif v_type == TypeVehicule.CYCLISTE:
            self._possede_abs = False
            self._age_technologique_pneus_annees = random.uniform(0.0, 5.0)
            self._usure_pneus = random.uniform(0.0, 1.0)
        else:
            self._possede_abs = (random.random() > 0.15)
            self._age_technologique_pneus_annees = random.uniform(0.0, 30.0) 
            self._usure_pneus = random.uniform(0.0, 1.0)

    @property
    def possede_abs(self): 
        return self._possede_abs

    # --- Mécanique de freinage ---
    def calculer_distance_freinage(self, coeff_friction_route):
        """
        Calcule la distance d'arrêt (mètres) basée sur l'énergie cinétique.
        """
        # Si on est déjà à l'arrêt, ou en marche arrière très lente
        if abs(self._vitesse_ms) <= 0.01:
            return 0.0
            
        g = 9.81 
        
        # Le piéton s'arrête quasiment instantanément (il dissipe son énergie par ses jambes)
        if self.type_entite == TypeVehicule.PIETON:
            return (self._vitesse_ms ** 2) / (2.0 * g * coeff_friction_route)
        
        # L'inertie pénalise le freinage des poids très lourds
        facteur_inertie = 1.0 if self.masse_kg < 3500 else 0.85
        
        facteur_abs = 1.0 if self._possede_abs else 0.7
        
        # Dégradation de l'adhérence par la vétusté et l'usure de la gomme
        facteur_age_pneu = max(0.5, 1.0 - (self._age_technologique_pneus_annees * 0.015))
        facteur_usure_pneu = max(0.4, 1.0 - (self._usure_pneus * 0.6))
        
        mu_effectif = coeff_friction_route * facteur_inertie * facteur_abs * facteur_age_pneu * facteur_usure_pneu
        mu_effectif = max(0.01, mu_effectif)
        
        distance = (self._vitesse_ms ** 2) / (2.0 * g * mu_effectif)
        return distance
