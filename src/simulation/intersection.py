import logging
logger = logging.getLogger(__name__)

from enum import Enum

class CouleurFeu(Enum):
    """Énumération des couleurs de feux de signalisation."""
    VERT = 1
    ORANGE = 2
    ROUGE = 3

class IntersectionManager:
    """Gestionnaire de l'intersection et des feux tricolores."""
    """Gestionnaire Automatisé des Feux Tricolores."""
    def __init__(self):
        """Initialise l'objet avec les paramètres requis.
        
        Args:
            *args: Arguments divers.
            **kwargs: Paramètres nommés.
        """
        self.__feu_ns = CouleurFeu.VERT
        self.__feu_eo = CouleurFeu.ROUGE
        
        self.__timer = 0.0
        self.__mode_manuel = False
        self.__urgence_active = False
        self.__etat_cycle = 0 
        self.__durees = [12.0, 3.0, 1.5, 12.0, 3.0, 1.5]

    @property
    def feu_ns(self): return self.__feu_ns

    @property
    def feu_eo(self): return self.__feu_eo

    def update(self, dt):
        """Obtient la couleur du feu Nord-Sud.
        
        Returns:
            CouleurFeu: La couleur.
        """
        try:
            if self.__mode_manuel or self.__urgence_active: 
                return
                
            self.__timer += dt
            if self.__timer >= self.__durees[self.__etat_cycle]:
                self.__timer -= self.__durees[self.__etat_cycle]
                self.__etat_cycle = (self.__etat_cycle + 1) % 6
                self._appliquer_etat()
        except Exception:
            pass
            
    def _appliquer_etat(self):
        """Applique l'état interne courant aux feux."""
        try:
            if self.__etat_cycle == 0: self.__feu_ns, self.__feu_eo = CouleurFeu.VERT, CouleurFeu.ROUGE
            elif self.__etat_cycle == 1: self.__feu_ns, self.__feu_eo = CouleurFeu.ORANGE, CouleurFeu.ROUGE
            elif self.__etat_cycle == 2: self.__feu_ns, self.__feu_eo = CouleurFeu.ROUGE, CouleurFeu.ROUGE
            elif self.__etat_cycle == 3: self.__feu_ns, self.__feu_eo = CouleurFeu.ROUGE, CouleurFeu.VERT
            elif self.__etat_cycle == 4: self.__feu_ns, self.__feu_eo = CouleurFeu.ROUGE, CouleurFeu.ORANGE
            elif self.__etat_cycle == 5: self.__feu_ns, self.__feu_eo = CouleurFeu.ROUGE, CouleurFeu.ROUGE
        except Exception:
            pass

    def forcer_vert_ns(self):
        """Force les feux Nord-Sud au vert."""
        self.__mode_manuel = True
        self.__feu_ns = CouleurFeu.VERT
        self.__feu_eo = CouleurFeu.ROUGE
        
    def forcer_vert_eo(self):
        """Force les feux Est-Ouest au vert."""
        self.__mode_manuel = True
        self.__feu_ns = CouleurFeu.ROUGE
        self.__feu_eo = CouleurFeu.VERT

    def forcer_passage_vta(self, axe_x: bool):
        """Adapte les feux pour le passage d'un véhicule d'urgence.
        
        Args:
            voie (str): Voie du véhicule.
        """
        try:
            self.__urgence_active = True
            if axe_x:
                self.__feu_eo = CouleurFeu.VERT
                self.__feu_ns = CouleurFeu.ROUGE
            else:
                self.__feu_ns = CouleurFeu.VERT
                self.__feu_eo = CouleurFeu.ROUGE
        except Exception:
            pass

    def annuler_urgence(self):
        """Rétablit le fonctionnement normal des feux."""
        try:
            if self.__urgence_active:
                self.__urgence_active = False
                self._appliquer_etat()
        except Exception:
            pass

    def get_couleur_pour_voie(self, axe_x: bool) -> CouleurFeu:
        """Obtient la couleur du feu pour une voie donnée.
        
        Args:
            axe_x (bool): Vrai si voie Est-Ouest.
        
        Returns:
            CouleurFeu: La couleur.
        """
        try:
            return self.__feu_eo if axe_x else self.__feu_ns
        except Exception:
            return CouleurFeu.ROUGE

    def set_state(self, feu_ns_val, feu_eo_val):
        """Définit manuellement les couleurs des feux.
        
        Args:
            ns (CouleurFeu): Feu Nord-Sud.
            eo (CouleurFeu): Feu Est-Ouest.
        """
        self.__feu_ns = CouleurFeu(feu_ns_val)
        self.__feu_eo = CouleurFeu(feu_eo_val)
