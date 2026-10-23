"""Module de régulation et de gestion automatisée des feux tricolores du carrefour.

Ce module gère le phasage cyclique des feux de signalisation pour réguler
les flux de circulation orthogonaux (axe Nord-Sud et axe Est-Ouest).
Il supporte le mode automatique (cycle à 6 phases avec temps de dégagement et
sécurité tout-rouge), le forçage manuel par l'opérateur et la préemption prioritaire
d'urgence pour les véhicules d'intervention d'urgence (VTA).
"""

import logging
import math
from enum import Enum

logger = logging.getLogger(__name__)


class CouleurFeu(Enum):
    """Énumération des états de couleur des feux de signalisation tricolores.

    Attributes:
        VERT: Autorisation d'engagement sur le carrefour.
        ORANGE: Arrêt requis sauf impossibilité matérielle de s'arrêter en sécurité.
        ROUGE: Arrêt absolu obligatoire avant la ligne d'arrêt.
    """
    VERT = 1
    ORANGE = 2
    ROUGE = 3


class IntersectionManager:
    """Gestionnaire automatisé de carrefour à feux tricolores synchronisés.

    Cette classe pilote les cycles temporels des feux de circulation pour deux axes
    orthogonaux : l'axe Nord-Sud (NS) et l'axe Est-Ouest (EO). Elle assure l'exclusion
    mutuelle (aucun vert simultané sur les deux axes) et gère la préemption
    immédiate lors de l'approche d'un véhicule prioritaire VTA.

    Attributes:
        __feu_ns (CouleurFeu): État lumineux courant de l'axe Nord-Sud.
        __feu_eo (CouleurFeu): État lumineux courant de l'axe Est-Ouest.
        __timer (float): Accumulateur temporel en secondes dans la phase courante.
        __mode_manuel (bool): Indicateur d'écrasement manuel par l'opérateur.
        __urgence_active (bool): Indicateur de préemption d'urgence active pour véhicule prioritaire.
        __etat_cycle (int): Index de la phase courante (0 à 5) du cycle automatique.
        __durees (list[float]): Durées en secondes des 6 phases du cycle standard.
    """

    def __init__(self, duree_vert: float = 12.0, duree_orange: float = 3.0):
        """Initialise le gestionnaire de feux avec le cycle nominal de sécurité.

        Par défaut, la simulation commence en phase 0 : axe Nord-Sud au Vert,
        axe Est-Ouest au Rouge.
        """
        self.__feu_ns = CouleurFeu.VERT
        self.__feu_eo = CouleurFeu.ROUGE

        self.__timer = 0.0
        self.__mode_manuel = False
        self.__duree_mode_manuel = 0.0
        self.__urgence_active = False
        self.__etat_cycle = 0

        # Séquence temporelle des 6 phases (en secondes) :
        # Phase 0 (12.0s) : NS Vert / EO Rouge
        # Phase 1 (3.0s)  : NS Orange / EO Rouge
        # Phase 2 (1.5s)  : NS Rouge / EO Rouge (Sécurité intégrale tout-rouge)
        # Phase 3 (12.0s) : NS Rouge / EO Vert
        # Phase 4 (3.0s)  : NS Rouge / EO Orange
        # Phase 5 (1.5s)  : NS Rouge / EO Rouge (Sécurité intégrale tout-rouge)
        self.__durees = [float(duree_vert), float(duree_orange), 1.5, float(duree_vert), float(duree_orange), 1.5]

    @property
    def feu_ns(self) -> CouleurFeu:
        """Obtient l'état lumineux courant des feux de l'axe Nord-Sud.

        Returns:
            CouleurFeu: Couleur actuelle du feu sur l'axe Nord-Sud.
        """
        return self.__feu_ns

    @property
    def feu_eo(self) -> CouleurFeu:
        """Obtient l'état lumineux courant des feux de l'axe Est-Ouest.

        Returns:
            CouleurFeu: Couleur actuelle du feu sur l'axe Est-Ouest.
        """
        return self.__feu_eo

    @property
    def temps_restant_phase(self) -> float:
        """Calcule le temps restant en secondes dans la phase courante."""
        if self.__urgence_active:
            return 0.0
        if self.__mode_manuel:
            return max(0.0, 15.0 - self.__duree_mode_manuel)
        duree = self.__durees[self.__etat_cycle]
        return max(0.0, duree - self.__timer)

    @property
    def timer(self) -> float:
        """Temps écoulé dans la phase courante."""
        return self.__timer

    @timer.setter
    def timer(self, val: float):
        self.__timer = float(val)

    @property
    def etat_cycle(self) -> int:
        """Index de la phase courante (0 à 5)."""
        return self.__etat_cycle

    @etat_cycle.setter
    def etat_cycle(self, val: int):
        self.__etat_cycle = int(val)

    @property
    def urgence_active(self) -> bool:
        """Indicateur de préemption d'urgence active pour véhicule prioritaire."""
        return self.__urgence_active

    @urgence_active.setter
    def urgence_active(self, val: bool):
        self.__urgence_active = bool(val)

    @property
    def mode_manuel(self) -> bool:
        """Indicateur de mode manuel actif."""
        return self.__mode_manuel

    @mode_manuel.setter
    def mode_manuel(self, val: bool):
        self.__mode_manuel = bool(val)

    def optimiser_phase_adaptative(self, entites: list):
        """Régulation intelligente adaptative (Smart Traffic Control).

        Si aucun véhicule ne s'approche sur l'axe au VERT dans les 25 m mais
        qu'au moins 2 véhicules attendent au ROUGE sur l'axe perpendiculaire
        (et que le feu est vert depuis au moins 4.0 s), écourte la phase verte
        pour fluidifier le carrefour.

        Args:
            entites (list): Liste des entités physiques de la simulation.
        """
        try:
            if self.__urgence_active or self.__mode_manuel:
                return

            # Seulement sur les phases vertes : Phase 0 (NS Vert) ou Phase 3 (EO Vert)
            if self.__etat_cycle not in (0, 3):
                return

            # Condition de sécurité : vert depuis au moins 4.0 secondes
            if self.__timer < 4.0:
                return

            # Axe au VERT : False pour NS (phase 0), True pour EO (phase 3)
            axe_vert_x = (self.__etat_cycle == 3)

            # Vérifie si un véhicule s'approche sur l'axe vert à moins de 25 m
            vehicule_sur_vert = False
            for e in entites:
                t = getattr(e, 'type_entite', None)
                if str(t).endswith('PIETON') or (hasattr(t, 'name') and t.name == 'PIETON'):
                    continue

                est_x = getattr(e, 'est_axe_x', False)
                if est_x == axe_vert_x:
                    px = getattr(e, 'pos_x', 0.0)
                    py = getattr(e, 'pos_y', 0.0)
                    cap = getattr(e, 'cap', 0.0)
                    if axe_vert_x:
                        dist = abs(px)
                        approche = (px < 0 and math.cos(cap) > 0.1) or (px > 0 and math.cos(cap) < -0.1)
                    else:
                        dist = abs(py)
                        approche = (py < 0 and math.sin(cap) > 0.1) or (py > 0 and math.sin(cap) < -0.1)

                    if dist <= 25.0 and approche:
                        vehicule_sur_vert = True
                        break

            if vehicule_sur_vert:
                return

            # Vérifie si au moins 2 véhicules attendent au ROUGE sur l'axe sécant
            axe_rouge_x = not axe_vert_x
            nb_attente_rouge = 0
            for e in entites:
                t = getattr(e, 'type_entite', None)
                if str(t).endswith('PIETON') or (hasattr(t, 'name') and t.name == 'PIETON'):
                    continue

                est_x = getattr(e, 'est_axe_x', False)
                if est_x == axe_rouge_x:
                    px = getattr(e, 'pos_x', 0.0)
                    py = getattr(e, 'pos_y', 0.0)
                    cap = getattr(e, 'cap', 0.0)
                    if axe_rouge_x:
                        dist = abs(px)
                        approche = (px < 0 and math.cos(cap) > 0.1) or (px > 0 and math.cos(cap) < -0.1)
                    else:
                        dist = abs(py)
                        approche = (py < 0 and math.sin(cap) > 0.1) or (py > 0 and math.sin(cap) < -0.1)

                    if dist <= 25.0 and approche:
                        nb_attente_rouge += 1

            if nb_attente_rouge >= 2:
                # Écourte la phase verte pour passer à la phase de dégagement orange
                duree_phase = self.__durees[self.__etat_cycle]
                self.__timer = duree_phase
                logger.info(
                    f"[IntersectionManager] Phase verte {self.__etat_cycle} écourtée par l'algorithme "
                    f"adaptatif (0 véhicule sur axe vert, {nb_attente_rouge} en attente au rouge)."
                )

        except Exception as e:
            logger.error(f"[IntersectionManager] Erreur régulation adaptative : {e}", exc_info=True)

    def update(self, dt: float):
        """Fait progresser le cycle temporel des feux tricolores selon l'intervalle dt.

        Si le mode manuel ou le mode préemption d'urgence est actif, l'automate
        temporel est suspendu pour préserver la consigne prioritaire.

        Args:
            dt (float): Intervalle de temps écoulé en secondes depuis le dernier pas de calcul.
        """
        try:
            # Suspension de l'automate automatique en cas d'urgence prioritaire VTA
            if self.__urgence_active:
                return

            # Gestion du mode forçage manuel avec expiration automatique après 15 secondes (Bug 7)
            if self.__mode_manuel:
                self.__duree_mode_manuel += dt
                if self.__duree_mode_manuel >= 15.0:
                    self.reprendre_mode_automatique()
                return

            self.__timer += dt
            duree_phase = self.__durees[self.__etat_cycle]

            if self.__timer >= duree_phase:
                # Soustraction du temps de phase pour conserver le reliquat de précision temporelle
                self.__timer -= duree_phase
                self.__etat_cycle = (self.__etat_cycle + 1) % 6
                self._appliquer_etat()

        except Exception as e:
            logger.error(
                f"[IntersectionManager] Erreur lors de l'avancement temporel des feux : {e}",
                exc_info=True
            )

    def _appliquer_etat(self):
        """Applique les couleurs de feux correspondant à la phase courante de l'automate.

        Phases de l'automate :
            0: NS=VERT, EO=ROUGE (Écoulement nominal Nord-Sud)
            1: NS=ORANGE, EO=ROUGE (Dégagement Nord-Sud)
            2: NS=ROUGE, EO=ROUGE (Sécurité intégrale / tout-rouge avant bascule)
            3: NS=ROUGE, EO=VERT (Écoulement nominal Est-Ouest)
            4: NS=ROUGE, EO=ORANGE (Dégagement Est-Ouest)
            5: NS=ROUGE, EO=ROUGE (Sécurité intégrale / tout-rouge avant bascule)
        """
        try:
            if self.__etat_cycle == 0:
                self.__feu_ns, self.__feu_eo = CouleurFeu.VERT, CouleurFeu.ROUGE
            elif self.__etat_cycle == 1:
                self.__feu_ns, self.__feu_eo = CouleurFeu.ORANGE, CouleurFeu.ROUGE
            elif self.__etat_cycle == 2:
                self.__feu_ns, self.__feu_eo = CouleurFeu.ROUGE, CouleurFeu.ROUGE
            elif self.__etat_cycle == 3:
                self.__feu_ns, self.__feu_eo = CouleurFeu.ROUGE, CouleurFeu.VERT
            elif self.__etat_cycle == 4:
                self.__feu_ns, self.__feu_eo = CouleurFeu.ROUGE, CouleurFeu.ORANGE
            elif self.__etat_cycle == 5:
                self.__feu_ns, self.__feu_eo = CouleurFeu.ROUGE, CouleurFeu.ROUGE
        except Exception as e:
            logger.error(
                f"[IntersectionManager] Erreur lors de l'application de la phase {self.__etat_cycle} : {e}",
                exc_info=True
            )

    def forcer_vert_ns(self):
        """Force manuellement l'ouverture au vert de l'axe Nord-Sud (expire après 15 s).

        Bascule le système en mode manuel temporaire et impose le rouge sur l'axe Est-Ouest
        pour éviter tout risque de collision.
        """
        self.__mode_manuel = True
        self.__duree_mode_manuel = 0.0
        self.__feu_ns = CouleurFeu.VERT
        self.__feu_eo = CouleurFeu.ROUGE

    def forcer_vert_eo(self):
        """Force manuellement l'ouverture au vert de l'axe Est-Ouest (expire après 15 s).

        Bascule le système en mode manuel temporaire et impose le rouge sur l'axe Nord-Sud
        pour éliminer tout conflit de trajectoire.
        """
        self.__mode_manuel = True
        self.__duree_mode_manuel = 0.0
        self.__feu_ns = CouleurFeu.ROUGE
        self.__feu_eo = CouleurFeu.VERT

    def reprendre_mode_automatique(self):
        """Réactive le mode automatique de régulation cyclique des feux."""
        self.__mode_manuel = False
        self.__duree_mode_manuel = 0.0
        self.__timer = 0.0
        self._appliquer_etat()
        logger.info("[IntersectionManager] Reprise du cycle automatique des feux.")

    def forcer_passage_vta(self, axe_x: bool):
        """Déclenche la préemption prioritaire d'urgence pour un véhicule VTA en approche.

        Ouvre immédiatement au vert l'axe de circulation emprunté par le véhicule
        prioritaire et verrouille l'axe sécant au feu rouge pour dégager le carrefour.
        Préempte prioritairement le mode manuel si actif.

        Args:
            axe_x (bool): Vrai si le véhicule d'urgence circule sur l'axe Est-Ouest (X),
                Faux s'il circule sur l'axe Nord-Sud (Y).
        """
        try:
            self.__urgence_active = True
            self.__mode_manuel = False
            self.__duree_mode_manuel = 0.0
            if axe_x:
                self.__feu_eo = CouleurFeu.VERT
                self.__feu_ns = CouleurFeu.ROUGE
            else:
                self.__feu_ns = CouleurFeu.VERT
                self.__feu_eo = CouleurFeu.ROUGE
        except Exception as e:
            logger.error(
                f"[IntersectionManager] Erreur lors de la préemption d'urgence VTA : {e}",
                exc_info=True
            )

    def annuler_urgence(self):
        """Rétablit le fonctionnement normal de l'intersection après le passage de l'urgence.

        Désactive la préemption VTA et réapplique l'état de feux standard déterminé
        par la phase courante de l'automate.
        """
        try:
            if self.__urgence_active:
                self.__urgence_active = False
                self._appliquer_etat()
        except Exception as e:
            logger.error(
                f"[IntersectionManager] Erreur lors de l'annulation de l'urgence VTA : {e}",
                exc_info=True
            )

    def get_couleur_pour_voie(self, axe_x: bool) -> CouleurFeu:
        """Obtient l'état lumineux du feu régissant l'axe de circulation spécifié.

        Args:
            axe_x (bool): Vrai pour l'axe longitudinal Est-Ouest, Faux pour l'axe transversal Nord-Sud.

        Returns:
            CouleurFeu: Couleur active du feu régissant l'axe spécifié. En cas d'erreur,
                renvoie CouleurFeu.ROUGE par précaution de sécurité intrinsèque.
        """
        try:
            return self.__feu_eo if axe_x else self.__feu_ns
        except Exception as e:
            logger.error(
                f"[IntersectionManager] Erreur lors de la lecture du feu (axe_x={axe_x}) : {e}",
                exc_info=True
            )
            return CouleurFeu.ROUGE

    def set_state(self, feu_ns_val, feu_eo_val):
        """Définit explicitement l'état des feux (utilisé lors de réceptions réseau V2I).

        Args:
            feu_ns_val (CouleurFeu | int): Valeur ou énumération de feu pour l'axe Nord-Sud.
            feu_eo_val (CouleurFeu | int): Valeur ou énumération de feu pour l'axe Est-Ouest.
        """
        try:
            self.__feu_ns = CouleurFeu(feu_ns_val)
            self.__feu_eo = CouleurFeu(feu_eo_val)
        except Exception as e:
            logger.error(
                f"[IntersectionManager] Erreur lors de la mise à jour forcée d'état (ns={feu_ns_val}, eo={feu_eo_val}) : {e}",
                exc_info=True
            )
