"""Moteur physique et cinématique de simulation du carrefour intelligent.

Ce module constitue le cœur de calcul de la simulation dynamique Esk-2718.
Il implémente les lois de la cinématique et de la dynamique du véhicule,
l'évitement d'obstacles multi-points (boîtes englobantes 2D), la régulation
adaptative de vitesse (ACC), la gestion du couloir central pour les véhicules
d'urgence (VTA), les virages géométriques par arc sans dérapage en crabe,
ainsi que les barrières physiques anti-superposition (Yellow Box & anti-clipping).
"""

import copy
import logging
import math
import random
import time

from PyQt6.QtCore import QElapsedTimer, QMutex, QMutexLocker, QThread, pyqtSignal

from simulation.environnement import ConditionsMeteo, Environnement
from simulation.intersection import CouleurFeu, IntersectionManager
from simulation.vehicules import TypeVehicule, Vehicule

logger = logging.getLogger(__name__)


class EntiteSnapshot:
    """Instantané immuable d'une entité mobile transmis à l'IHM."""
    pass


class TrajectoireBezier:
    """Courbe de Bézier quadratique B(t) = (1-t)^2 P0 + 2(1-t)t P1 + t^2 P2."""

    def __init__(self, p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float]):
        self.p0 = (float(p0[0]), float(p0[1]))
        self.p1 = (float(p1[0]), float(p1[1]))
        self.p2 = (float(p2[0]), float(p2[1]))
        self.t = 0.0
        self.longueur_arc = self._calculer_longueur_arc()

    def _calculer_longueur_arc(self, n: int = 16) -> float:
        """Calcule la longueur d'arc par quadrature numérique de Simpson."""
        def norm_deriv(s: float) -> float:
            dx = 2.0 * (1.0 - s) * (self.p1[0] - self.p0[0]) + 2.0 * s * (self.p2[0] - self.p1[0])
            dy = 2.0 * (1.0 - s) * (self.p1[1] - self.p0[1]) + 2.0 * s * (self.p2[1] - self.p1[1])
            return math.hypot(dx, dy)

        h = 1.0 / n
        somme = norm_deriv(0.0) + norm_deriv(1.0)
        for i in range(1, n):
            s = i * h
            poids = 4.0 if i % 2 == 1 else 2.0
            somme += poids * norm_deriv(s)
        return max(0.1, (h / 3.0) * somme)

    def point(self, t: float) -> tuple[float, float]:
        """Évalue les coordonnées cartésiennes B(t)."""
        t = max(0.0, min(1.0, float(t)))
        u = 1.0 - t
        x = u * u * self.p0[0] + 2.0 * u * t * self.p1[0] + t * t * self.p2[0]
        y = u * u * self.p0[1] + 2.0 * u * t * self.p1[1] + t * t * self.p2[1]
        return x, y

    def tangente(self, t: float) -> tuple[float, float]:
        """Évalue le vecteur vitesse tangentiel B'(t)."""
        t = max(0.0, min(1.0, float(t)))
        dx = 2.0 * (1.0 - t) * (self.p1[0] - self.p0[0]) + 2.0 * t * (self.p2[0] - self.p1[0])
        dy = 2.0 * (1.0 - t) * (self.p1[1] - self.p0[1]) + 2.0 * t * (self.p2[1] - self.p1[1])
        return dx, dy

    def derivee(self, t: float) -> tuple[float, float]:
        """Évalue le vecteur vitesse tangentiel B'(t) (alias de tangente)."""
        return self.tangente(t)

    def cap(self, t: float) -> float:
        """Calcule l'angle tangentiel exact de la trajectoire en radians."""
        dx, dy = self.tangente(t)
        return math.atan2(dy, dx)

    def cap_tangentiel(self, t: float) -> float:
        """Calcule l'angle tangentiel exact en radians (alias de cap)."""
        return self.cap(t)


def calculer_points_bezier_virage(*args) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]] | None:
    """Calcule les points de contrôle P0, P1, P2 d'un virage par courbe de Bézier quadratique.

    Accepte soit un objet entité (1 argument), soit (pos_x, pos_y, cap, action_intersection) (4 arguments).

    P0 : Point d'entrée de l'intersection sur la voie d'origine
    P1 : Point d'inflexion (intersection géométrique de la voie d'entrée et de sortie)
    P2 : Point d'alignement sur la voie de sortie
    """
    if len(args) == 1:
        entite = args[0]
        ai = getattr(entite, 'action_intersection', None)
        cap = getattr(entite, 'cap', 0.0)
    elif len(args) == 4:
        pos_x, pos_y, cap, ai = args
    else:
        return None

    if ai is None:
        return None

    delta_psi = (ai - cap + math.pi) % (2.0 * math.pi) - math.pi
    est_virage_droite = (delta_psi > 0.1)

    cos_c = math.cos(cap)
    sin_c = math.sin(cap)
    r = 3.5 if est_virage_droite else 5.5

    if abs(cos_c) > abs(sin_c):
        if cos_c > 0:
            # Estbound (y = +2.0)
            if est_virage_droite:
                p1 = (-2.0, 2.0)
                p0 = (-2.0 - r, 2.0)
                p2 = (-2.0, 2.0 + r)
            else:
                p1 = (2.0, 2.0)
                p0 = (2.0 - r, 2.0)
                p2 = (2.0, 2.0 - r)
        else:
            # Westbound (y = -2.0)
            if est_virage_droite:
                p1 = (2.0, -2.0)
                p0 = (2.0 + r, -2.0)
                p2 = (2.0, -2.0 - r)
            else:
                p1 = (-2.0, -2.0)
                p0 = (-2.0 + r, -2.0)
                p2 = (-2.0, -2.0 + r)
    else:
        if sin_c > 0:
            # Southbound (x = -2.0)
            if est_virage_droite:
                p1 = (-2.0, -2.0)
                p0 = (-2.0, -2.0 - r)
                p2 = (-2.0 - r, -2.0)
            else:
                p1 = (-2.0, 2.0)
                p0 = (-2.0, 2.0 - r)
                p2 = (-2.0 + r, 2.0)
        else:
            # Northbound (x = +2.0)
            if est_virage_droite:
                p1 = (2.0, 2.0)
                p0 = (2.0, 2.0 + r)
                p2 = (2.0 + r, 2.0)
            else:
                p1 = (2.0, -2.0)
                p0 = (2.0, -2.0 + r)
                p2 = (2.0 - r, -2.0)

    return p0, p1, p2


class MoteurSimulation(QThread):
    """Moteur physique de simulation multi-entités exécuté dans un QThread autonome.

    Cette classe coordonne la dynamique globale de la circulation urbaine. Elle
    maintient l'état de l'intersection et l'ensemble des entités mobiles (véhicules,
    transports de marchandises, convois, véhicules d'urgence, cyclistes et piétons).
    L'accès à la liste partagée des entités est protégé par un verrou d'exclusion
    mutuelle (QMutex) pour empêcher les accès concurrents avec l'interface graphique.

    Signals:
        tick_simulation (list, object): Signal émis à chaque pas de calcul contenant
            une liste d'instantanés d'entités (EntiteSnapshot) et une copie de
            l'état de l'intersection (IntersectionManager).
    """

    tick_simulation = pyqtSignal(list, object)

    def __init__(self):
        """Initialise le moteur physique de simulation et ses structures de contrôle."""
        super().__init__()
        self.entites = []
        self.mutex = QMutex()
        self.intersection = IntersectionManager()
        self.environnement = Environnement()
        self.__en_cours = False
        self.multiplicateur_temps = 1.0
        self.densite_air_rho = 1.225
        self.network_client = None
        self.last_metrics_time = 0.0

        # KPI Métier : Préemption V2I & Mesure des temps de franchissement
        self.preemption_v2i_active = True
        self.temps_ecoule = 0.0
        self.temps_vta_traverses = []
        self.temps_vehicules_traverses = []
        self.vehicules_franchis_total = 0
        self._vehicules_entree_carrefour = {}
        self.temps_dernier_spawn = 0.0
        self.cpt_id = 9000

    @property
    def temps_franchissement_moyen_vta(self) -> float:
        """Temps moyen de franchissement mesuré pour les véhicules prioritaires VTA (s)."""
        if self.temps_vta_traverses:
            return sum(self.temps_vta_traverses) / len(self.temps_vta_traverses)
        return 0.0

    @property
    def temps_franchissement_moyen_global(self) -> float:
        """Temps moyen de franchissement mesuré pour l'ensemble des véhicules (s)."""
        if self.temps_vehicules_traverses:
            return sum(self.temps_vehicules_traverses) / len(self.temps_vehicules_traverses)
        return 0.0

    @property
    def gain_temps_estime_pct(self) -> float:
        """Gain de temps estimé en pourcentage grâce à la préemption prioritaire V2I."""
        t_vta = self.temps_franchissement_moyen_vta
        t_ref = self.temps_franchissement_moyen_global if self.temps_franchissement_moyen_global > 0 else 8.5
        if t_vta > 0 and t_ref > t_vta:
            return min(100.0, ((t_ref - t_vta) / t_ref) * 100.0)
        return 45.0 if self.preemption_v2i_active else 0.0

    def ajouter_entite(self, entite):
        """Ajoute une nouvelle entité dans la simulation de manière sécurisée (thread-safe)."""
        with QMutexLocker(self.mutex):
            try:
                entite.voie_cible_y = entite.pos_y
                entite.voie_cible_x = entite.pos_x
                entite.cap_cible = entite.cap
                entite.est_axe_x = abs(math.cos(entite.cap)) > 0.5
                entite.etat_depassement = 0

                # Cantonnage strict des cyclistes sur piste cyclable latérale (+/- 3.6 m)
                if getattr(entite, 'type_entite', None) == TypeVehicule.CYCLISTE:
                    entite.action_intersection = None
                    entite.en_virage_bezier = False
                    entite.trajectoire_bezier = None
                    if entite.est_axe_x:
                        sign = 1.0 if math.cos(entite.cap) > 0 else -1.0
                        entite.pos_y = 3.6 * sign
                        entite.voie_cible_y = entite.pos_y
                    else:
                        sign = 1.0 if math.sin(entite.cap) > 0 else -1.0
                        entite.pos_x = -3.6 * sign
                        entite.voie_cible_x = entite.pos_x

                # Véhicule d'urgence VTA : toujours tout droit
                if getattr(entite, 'type_entite', None) == TypeVehicule.VIG_VTA:
                    entite.action_intersection = None
                    entite.en_virage_bezier = False
                    entite.trajectoire_bezier = None

                self.entites.append(entite)
            except Exception as e:
                logger.error(f"[MoteurSimulation] Erreur lors de l'insertion de l'entité : {e}", exc_info=True)

    def vider_entites(self):
        """Supprime l'intégralité des entités de la simulation de manière thread-safe."""
        with QMutexLocker(self.mutex):
            try:
                self.entites.clear()
            except Exception as e:
                logger.error(f"[MoteurSimulation] Erreur lors de la suppression des entités : {e}", exc_info=True)

    def demarrer(self):
        """Active le drapeau d'exécution et lance le fil d'exécution (QThread)."""
        self.__en_cours = True
        self.start()

    def arreter(self):
        """Notifie l'arrêt de la boucle de calcul et bloque jusqu'à la terminaison complète."""
        self.__en_cours = False
        self.wait()

    @staticmethod
    def calculer_points_physiques(entite):
        """Calcule les coordonnées mondiales de 3 points physiques le long de l'axe de l'entité.

        Règle 4 : Modélisation volumétrique 2D pour éviter le clipping des remorques longues.
        1. Pare-chocs avant
        2. Centre géométrique
        3. Pare-chocs arrière
        """
        demi_l = entite.longueur_m / 2.0
        cos_c = math.cos(entite.cap)
        sin_c = math.sin(entite.cap)
        p_avant = (entite.pos_x + demi_l * cos_c, entite.pos_y + demi_l * sin_c)
        p_centre = (entite.pos_x, entite.pos_y)
        p_arriere = (entite.pos_x - demi_l * cos_c, entite.pos_y - demi_l * sin_c)
        return p_avant, p_centre, p_arriere

    @staticmethod
    def projeter_point_repere_local(px, py, front_x, front_y, theta):
        """Projette un point monde (px, py) dans le repère local défini par l'origine (front_x, front_y) et le cap theta.

        Returns:
            tuple[float, float]: (dist_longitudinale, dist_laterale)
        """
        dx = px - front_x
        dy = py - front_y
        dist_long = dx * math.cos(theta) + dy * math.sin(theta)
        dist_lat = -dx * math.sin(theta) + dy * math.cos(theta)
        return dist_long, dist_lat

    def detecter_obstacles_multipoints(self, entite, autres_entites):
        """Détecte les obstacles frontaux par projection multi-points (Règle 4).

        Args:
            entite (Vehicule): Véhicule observateur.
            autres_entites (list[Vehicule]): Ensemble des autres entités présentes sur la carte.

        Returns:
            tuple: (distance_arret, obstacle_nature, vitesse_obstacle, vehicule_devant)
        """
        distance_arret = 999.0
        obstacle_nature = "Aucun"
        vitesse_obstacle = 0.0
        vehicule_devant = None

        demi_l = entite.longueur_m / 2.0
        front_x = entite.pos_x + demi_l * math.cos(entite.cap)
        front_y = entite.pos_y + demi_l * math.sin(entite.cap)

        # Si le véhicule est en train de virer, nous projetons également selon son cap_cible futur
        caps_eval = [entite.cap]
        if getattr(entite, 'cap_cible', None) is not None and abs(entite.cap_cible - entite.cap) > 0.05:
            caps_eval.append(entite.cap_cible)

        for autre in autres_entites:
            if getattr(autre, 'id_entite', None) == entite.id_entite:
                continue

            # Cas particulier des piétons sur le passage clouté
            if getattr(autre, 'type_entite', None) == TypeVehicule.PIETON:
                for theta in caps_eval:
                    d_long, d_lat = self.projeter_point_repere_local(autre.pos_x, autre.pos_y, front_x, front_y, theta)
                    if 0.0 < d_long < 40.0 and abs(d_lat) < 4.5:
                        dist_nette = max(0.0, d_long - 2.0)
                        if dist_nette < distance_arret:
                            distance_arret = dist_nette
                            obstacle_nature = "Pieton"
                            vitesse_obstacle = 0.0
                            vehicule_devant = autre
                continue

            # Véhicules roulants : test sur les 3 points physiques
            points_autre = self.calculer_points_physiques(autre)
            if entite.type_entite == TypeVehicule.VIG_VTA:
                largeur_couloir = 1.0  # Max 1.0 m pour le VTA dans le couloir central
            elif autre.type_entite == TypeVehicule.CYCLISTE and entite.type_entite != TypeVehicule.CYCLISTE:
                largeur_couloir = 1.1  # Piste cyclable latérale séparée de 1.6m : aucun ralentissement des voitures/camions
            else:
                largeur_couloir = (entite.largeur_m / 2.0) + (autre.largeur_m / 2.0) + 0.6

            # Si l'autre véhicule est un VTA en plein dépassement dans le couloir central,
            # les véhicules normaux sur leur voie ne doivent pas freiner inutilement derrière lui
            if autre.type_entite == TypeVehicule.VIG_VTA and getattr(autre, 'etat_depassement', 0) == 1:
                continue

            for px, py in points_autre:
                for theta in caps_eval:
                    d_long, d_lat = self.projeter_point_repere_local(px, py, front_x, front_y, theta)
                    if 0.0 < d_long < 60.0 and abs(d_lat) < largeur_couloir:
                        dist_nette = max(0.0, d_long - 1.5)
                        if dist_nette < distance_arret:
                            distance_arret = dist_nette
                            obstacle_nature = "Vehicule"
                            proj_vit = autre.vitesse * (
                                math.cos(autre.cap) * math.cos(theta) + math.sin(autre.cap) * math.sin(theta)
                            )
                            vitesse_obstacle = max(0.0, proj_vit)
                            vehicule_devant = autre

        return distance_arret, obstacle_nature, vitesse_obstacle, vehicule_devant

    def verifier_yellow_box(self, entite, autres_entites):
        """Règle 5 : Vérifie si la voie de sortie du carrefour est encombrée avant de s'y engager.

        Returns:
            bool: True si la voie de sortie est encombrée par un véhicule à l'arrêt dans le même sens.
        """
        cap_cible = getattr(entite, 'action_intersection', None)
        if cap_cible is None:
            cap_cible = getattr(entite, 'cap_cible', entite.cap)

        est_sortie_x = abs(math.cos(cap_cible)) > 0.5

        for autre in autres_entites:
            if getattr(autre, 'id_entite', None) == entite.id_entite:
                continue
            if getattr(autre, 'type_entite', None) in (TypeVehicule.PIETON, TypeVehicule.CYCLISTE):
                continue

            # Véhicule allant dans le même sens (math.cos(entite.cap_cible - autre.cap) > 0.8)
            if math.cos(cap_cible - autre.cap) <= 0.8:
                continue

            # Complètement à l'arrêt (< 0.3 m/s)
            if getattr(autre, 'vitesse', 0.0) >= 0.3:
                continue

            # Juste à la sortie immédiate du carrefour (10.0 < dist_sortie < 16.0 m)
            if est_sortie_x:
                sens_x = 1 if math.cos(cap_cible) > 0 else -1
                voie_y = 2.0 if sens_x > 0 else -2.0
                dist_sortie = autre.pos_x * sens_x
                dans_sortie = (10.0 < dist_sortie < 16.0) and abs(autre.pos_y - voie_y) < 1.5
            else:
                sens_y = 1 if math.sin(cap_cible) > 0 else -1
                voie_x = -2.0 if sens_y > 0 else 2.0
                dist_sortie = autre.pos_y * sens_y
                dans_sortie = (10.0 < dist_sortie < 16.0) and abs(autre.pos_x - voie_x) < 1.5

            if dans_sortie:
                return True

        return False

    def etape_simulation(self, dt):
        """Exécute une itération unique d'intégration physique et comportementale.

        Cette méthode est isolée pour permettre des tests unitaires et déterministes.
        """
        self.temps_ecoule += dt

        # 1. Gestion des feux tricolores (mode autonome ou client non connecté)
        if self.network_client is None or not getattr(self.network_client, 'connected', False):
            self.intersection.update(dt)

        # 2. Filtrage spatial et extraction d'une copie locale immuable sous mutex
        with QMutexLocker(self.mutex):
            self.entites = [
                e for e in self.entites
                if not getattr(e, 'a_detruire', False) and -55.0 < e.pos_x < 55.0 and -55.0 < e.pos_y < 55.0
            ]
            copie_entites = list(self.entites)

        # Régulation Intelligente Adaptative (Smart Traffic Control)
        if self.network_client is None or not getattr(self.network_client, 'connected', False):
            self.intersection.optimiser_phase_adaptative(copie_entites)

        # Mesure des temps de franchissement réels du carrefour
        maintenant_mesure = self.temps_ecoule
        ids_actifs = set()
        for e in copie_entites:
            eid = getattr(e, 'id_entite', None)
            if not eid:
                continue
            ids_actifs.add(eid)
            dist_centre = math.hypot(e.pos_x, e.pos_y)
            # Produit scalaire radial r . u : négatif si le véhicule s'approche du centre, positif s'il s'en éloigne
            cos_cap = math.cos(getattr(e, 'cap', 0.0))
            sin_cap = math.sin(getattr(e, 'cap', 0.0))
            sens_radial = e.pos_x * cos_cap + e.pos_y * sin_cap

            # Entrée dans la zone carrefour (en approche vers le centre à moins de 25m)
            if dist_centre <= 25.0 and sens_radial < -0.5:
                if eid not in self._vehicules_entree_carrefour:
                    self._vehicules_entree_carrefour[eid] = maintenant_mesure
            # Sortie effective du carrefour (s'éloigne du centre et a dépassé 16m)
            elif dist_centre >= 16.0 and sens_radial > 0.5 and eid in self._vehicules_entree_carrefour:
                duree = maintenant_mesure - self._vehicules_entree_carrefour.pop(eid)
                if 0.2 < duree < 120.0:
                    self.vehicules_franchis_total += 1
                    if getattr(e, 'type_entite', None) == TypeVehicule.VIG_VTA:
                        self.temps_vta_traverses.append(duree)
                        if len(self.temps_vta_traverses) > 50:
                            self.temps_vta_traverses.pop(0)
                    else:
                        self.temps_vehicules_traverses.append(duree)
                        if len(self.temps_vehicules_traverses) > 100:
                            self.temps_vehicules_traverses.pop(0)

        # Nettoyage des véhicules disparus de la simulation
        ids_orphelins = [i for i in self._vehicules_entree_carrefour if i not in ids_actifs]
        for i in ids_orphelins:
            self._vehicules_entree_carrefour.pop(i, None)

        # 3. Génération automatique cadencée des véhicules
        try:
            maintenant = self.temps_ecoule
            if not hasattr(self, 'cpt_id'):
                self.cpt_id = 9000
            ref_temps = getattr(self, 'temps_dernier_spawn', 0.0)
            if ref_temps > 1e8:
                declencher_spawn = (time.time() - ref_temps > 2.5)
                if declencher_spawn:
                    self.temps_dernier_spawn = time.time()
            else:
                declencher_spawn = (maintenant - ref_temps >= 2.5) or (ref_temps == 0.0 and len(copie_entites) == 0)
                if declencher_spawn:
                    self.temps_dernier_spawn = maintenant

            if declencher_spawn:
                if len(copie_entites) >= 12:
                    pass
                else:
                    self.cpt_id += 1

                    type_aleatoire = random.choices(
                        [TypeVehicule.VOITURE, TypeVehicule.POIDS_LOURD, TypeVehicule.CYCLISTE],
                        weights=[0.70, 0.15, 0.15],
                        k=1
                    )[0]

                    masse = 1500.0
                    if type_aleatoire == TypeVehicule.VOITURE:
                        masse = max(800.0, random.gauss(1500.0, 200.0))
                    elif type_aleatoire == TypeVehicule.POIDS_LOURD:
                        masse = max(10000.0, random.gauss(25000.0, 3000.0))
                    elif type_aleatoire == TypeVehicule.CYCLISTE:
                        masse = max(40.0, random.gauss(90.0, 15.0))

                    nouveau_vehicule = Vehicule(str(self.cpt_id), type_aleatoire, masse)
                    axe = random.choice(['x', 'y'])
                    sens = random.choice([1, -1])

                    if type_aleatoire == TypeVehicule.CYCLISTE:
                        if axe == 'x':
                            nouveau_vehicule.pos_x = -48.0 * sens
                            nouveau_vehicule.pos_y = 3.6 * sens
                            nouveau_vehicule.cap = 0.0 if sens == 1 else math.pi
                        else:
                            nouveau_vehicule.pos_y = -48.0 * sens
                            nouveau_vehicule.pos_x = -3.6 * sens
                            nouveau_vehicule.cap = math.pi / 2 if sens == 1 else -math.pi / 2
                        nouveau_vehicule.vitesse = 5.5
                        nouveau_vehicule.action_intersection = None
                        nouveau_vehicule.en_virage_bezier = False
                    else:
                        if axe == 'x':
                            nouveau_vehicule.pos_x = -48.0 * sens
                            nouveau_vehicule.pos_y = 2.0 * sens
                            nouveau_vehicule.cap = 0.0 if sens == 1 else math.pi
                        else:
                            nouveau_vehicule.pos_y = -48.0 * sens
                            nouveau_vehicule.pos_x = -2.0 * sens
                            nouveau_vehicule.cap = math.pi / 2 if sens == 1 else -math.pi / 2
                        nouveau_vehicule.vitesse = 10.0

                    chevauchement = False
                    for entite_existante in copie_entites:
                        if math.hypot(
                            entite_existante.pos_x - nouveau_vehicule.pos_x,
                            entite_existante.pos_y - nouveau_vehicule.pos_y,
                        ) < 15.0:
                            chevauchement = True
                            break

                    if not chevauchement:
                        if type_aleatoire != TypeVehicule.CYCLISTE and random.random() < 0.20:
                            direction_virage = random.choice([-math.pi / 2, math.pi / 2])
                            nouveau_vehicule.action_intersection = nouveau_vehicule.cap + direction_virage
                        self.ajouter_entite(nouveau_vehicule)
        except Exception as e_spawn:
            logger.error(f"[MoteurSimulation] Erreur génération automatique : {e_spawn}", exc_info=True)

        # 4. Détection globale des véhicules prioritaires d'urgence (VTA)
        vta_instances = [e for e in copie_entites if getattr(e, 'type_entite', None) == TypeVehicule.VIG_VTA]
        vta_proche = False
        axe_urgence_x = False
        vta_entite = None

        for vta in vta_instances:
            dist_centre = math.hypot(vta.pos_x, vta.pos_y)
            dist_apres_centre = (
                (vta.pos_x if math.cos(vta.cap) > 0 else -vta.pos_x)
                if vta.est_axe_x
                else (vta.pos_y if math.sin(vta.cap) > 0 else -vta.pos_y)
            )
            # Approche à moins de 85 m et pas encore éloigné de plus de 18 m après le centre
            if dist_centre < 85.0 and dist_apres_centre <= 18.0:
                vta_proche = True
                axe_urgence_x = vta.est_axe_x
                vta_entite = vta
                break

        if vta_proche and self.preemption_v2i_active:
            self.intersection.forcer_passage_vta(axe_urgence_x)
            if self.network_client:
                try:
                    pos_vta = [round(vta_entite.pos_x, 1), round(vta_entite.pos_y, 1)] if vta_entite else [0.0, 0.0]
                    self.network_client.send_vta_alert(axe_urgence_x, pos_vta, "VIG_VTA", 1)
                except Exception as e_net:
                    logger.error(f"[MoteurSimulation] Erreur envoi alerte VTA : {e_net}")
        else:
            self.intersection.annuler_urgence()
            if self.network_client:
                try:
                    self.network_client.send_vta_end()
                except Exception as e_net:
                    logger.error(f"[MoteurSimulation] Erreur fin alerte VTA : {e_net}")

        # 5. Comportement individuel par entité
        for entite in copie_entites:
            # Traitement spécifique des piétons
            if entite.type_entite == TypeVehicule.PIETON:
                entite.commande_acceleration = 0.0
                traversant_axe_y = abs(math.cos(entite.cap)) > 0.5
                feu_voiture = (
                    self.intersection.get_couleur_pour_voie(False)
                    if traversant_axe_y
                    else self.intersection.get_couleur_pour_voie(True)
                )

                if traversant_axe_y:
                    entite.pos_y = 9.0 if entite.pos_y > 0 else -9.0
                    est_sur_trottoir = abs(entite.pos_x) > 4.0
                    approche_chaussee = (
                        (entite.pos_x < -4.0 and math.cos(entite.cap) > 0)
                        or (entite.pos_x > 4.0 and math.cos(entite.cap) < 0)
                    )
                    if feu_voiture == CouleurFeu.VERT and est_sur_trottoir and approche_chaussee:
                        entite.vitesse = 0.0
                    else:
                        entite.vitesse = 1.5

                    if (math.cos(entite.cap) > 0 and entite.pos_x > 10.0) or (
                        math.cos(entite.cap) < 0 and entite.pos_x < -10.0
                    ):
                        entite.a_detruire = True
                else:
                    entite.pos_x = 9.0 if entite.pos_x > 0 else -9.0
                    est_sur_trottoir = abs(entite.pos_y) > 4.0
                    approche_chaussee = (
                        (entite.pos_y < -4.0 and math.sin(entite.cap) > 0)
                        or (entite.pos_y > 4.0 and math.sin(entite.cap) < 0)
                    )
                    if feu_voiture == CouleurFeu.VERT and est_sur_trottoir and approche_chaussee:
                        entite.vitesse = 0.0
                    else:
                        entite.vitesse = 1.5

                    if (math.sin(entite.cap) > 0 and entite.pos_y > 10.0) or (
                        math.sin(entite.cap) < 0 and entite.pos_y < -10.0
                    ):
                        entite.a_detruire = True
                continue

            # Véhicules roulants
            est_axe_x = entite.est_axe_x
            distance_arret = 999.0
            obstacle_nature = "Aucun"
            vitesse_obstacle = 0.0

            # -------------------------------------------------------------
            # RÈGLE 1 : Interdiction formelle de dépasser pour véhicules non prioritaires
            # -------------------------------------------------------------
            if entite.type_entite != TypeVehicule.VIG_VTA:
                entite.etat_depassement = 0

            # -------------------------------------------------------------
            # RÈGLE 2 : Couloir central d'urgence VTA et dégagement latéral extérieur
            # -------------------------------------------------------------
            vta_sur_meme_axe = False
            for vta in vta_instances:
                if vta.id_entite != entite.id_entite and vta.est_axe_x == est_axe_x:
                    dist_vta = math.hypot(vta.pos_x - entite.pos_x, vta.pos_y - entite.pos_y)
                    if dist_vta < 75.0:
                        vta_sur_meme_axe = True
                        break

            # Distance à la ligne d'arrêt
            if est_axe_x:
                dist_ligne = (
                    -entite.pos_x - 10.0 - entite.longueur_m / 2.0
                    if math.cos(entite.cap_cible) > 0
                    else entite.pos_x - 10.0 - entite.longueur_m / 2.0
                )
            else:
                dist_ligne = (
                    -entite.pos_y - 10.0 - entite.longueur_m / 2.0
                    if math.sin(entite.cap_cible) > 0
                    else entite.pos_y - 10.0 - entite.longueur_m / 2.0
                )

            dist_centre = math.hypot(entite.pos_x, entite.pos_y)
            est_engage_intersection = (
                dist_centre < 9.5
                or getattr(entite, 'trajectoire_bezier', None) is not None
                or getattr(entite, 'en_virage_bezier', False)
            )
            dans_carrefour_proche = dist_centre < 11.0

            # -------------------------------------------------------------
            # RÈGLE 1 & 2 : Attribution des voies cibles (cyclistes sur piste latérale +/- 3.6m)
            # -------------------------------------------------------------
            if entite.type_entite == TypeVehicule.CYCLISTE:
                entite.action_intersection = None
                entite.en_virage_bezier = False
                entite.trajectoire_bezier = None
                if est_axe_x:
                    entite.voie_cible_y = 3.6 if math.cos(entite.cap_cible) > 0 else -3.6
                else:
                    entite.voie_cible_x = -3.6 if math.sin(entite.cap_cible) > 0 else 3.6

            elif entite.type_entite == TypeVehicule.VIG_VTA:
                entite.action_intersection = None
                entite.en_virage_bezier = False
                entite.trajectoire_bezier = None

            else:
                # Véhicule ordinaire : évacuation immédiate du carrefour si VTA approche
                if vta_proche and dans_carrefour_proche:
                    entite.action_intersection = None
                    entite.trajectoire_bezier = None
                    entite.en_virage_bezier = False
                    entite.forcer_arret = False
                    if est_axe_x:
                        entite.voie_cible_y = 3.3 if math.cos(entite.cap_cible) > 0 else -3.3
                    else:
                        entite.voie_cible_x = -3.3 if math.sin(entite.cap_cible) > 0 else 3.3
                elif vta_sur_meme_axe or vta_proche or getattr(entite, 'forcer_arret', False):
                    if est_axe_x:
                        entite.voie_cible_y = 3.3 if math.cos(entite.cap_cible) > 0 else -3.3
                    else:
                        entite.voie_cible_x = -3.3 if math.sin(entite.cap_cible) > 0 else 3.3
                else:
                    if est_axe_x:
                        entite.voie_cible_y = 2.0 if math.cos(entite.cap_cible) > 0 else -2.0
                    else:
                        entite.voie_cible_x = -2.0 if math.sin(entite.cap_cible) > 0 else 2.0

            # -------------------------------------------------------------
            # RÈGLE 3 : Trajectoires de virage par courbe de Bézier quadratique
            # -------------------------------------------------------------
            if getattr(entite, 'action_intersection', None) is not None and entite.type_entite not in (TypeVehicule.CYCLISTE, TypeVehicule.VIG_VTA):
                delta_psi = (entite.action_intersection - entite.cap + math.pi) % (2.0 * math.pi) - math.pi
                if not getattr(entite, 'en_virage_bezier', False):
                    if dist_centre < 38.0:
                        if delta_psi < -0.1:
                            entite.indicateur_virage = -1
                        elif delta_psi > 0.1:
                            entite.indicateur_virage = 1
                        else:
                            entite.indicateur_virage = 0
                    else:
                        entite.indicateur_virage = 0

                est_virage_gauche = (delta_psi < -0.1)

                # La vérification de priorité en face doit se faire AVANT de franchir la ligne d'arrêt (0.0 < dist_ligne < 3.0 m)
                priorite_bloquee = False
                if est_virage_gauche and 0.0 < dist_ligne < 3.0:
                    for opp in copie_entites:
                        if opp.id_entite == entite.id_entite or opp.type_entite in (TypeVehicule.PIETON, TypeVehicule.CYCLISTE):
                            continue
                        if getattr(opp, 'est_axe_x', False) == est_axe_x:
                            sens_oppose = (
                                math.cos(opp.cap) * math.cos(entite.cap)
                                + math.sin(opp.cap) * math.sin(entite.cap)
                            ) < -0.7
                            if sens_oppose and getattr(opp, 'action_intersection', None) is None:
                                dx_opp = opp.pos_x - entite.pos_x
                                dy_opp = opp.pos_y - entite.pos_y
                                proj_long_opp = dx_opp * math.cos(entite.cap) + dy_opp * math.sin(entite.cap)
                                if 0.0 < proj_long_opp < 45.0 and (opp.vitesse > 0.5 or math.hypot(opp.pos_x, opp.pos_y) < 10.5):
                                    priorite_bloquee = True
                                    break

                if priorite_bloquee:
                    distance_arret = min(distance_arret, dist_ligne)
                    obstacle_nature = "Vehicule (Priorité Face)"
                else:
                    # Enclenchement de la trajectoire de Bézier
                    if getattr(entite, 'trajectoire_bezier', None) is None:
                        pts = calculer_points_bezier_virage(entite)
                        if pts is not None:
                            p0, p1, p2 = pts
                            dx = entite.pos_x - p0[0]
                            dy = entite.pos_y - p0[1]
                            dist_vers_p0 = -(dx * math.cos(entite.cap) + dy * math.sin(entite.cap))
                            if ((-1.5 <= dist_vers_p0 <= 0.8) or (math.hypot(dx, dy) < 2.5 and dist_vers_p0 > -2.0) or (dist_ligne <= 0.0 and dist_centre < 9.5)) and dist_vers_p0 > -6.0:
                                entite.trajectoire_bezier = TrajectoireBezier((entite.pos_x, entite.pos_y), p1, p2)
                                entite.en_virage_bezier = True
                                entite.cap_cible = entite.action_intersection
            elif not getattr(entite, 'en_virage_bezier', False):
                entite.indicateur_virage = 0

            # -------------------------------------------------------------
            # SIGNALISATION LUMINEUSE & RÈGLE 5 (YELLOW BOX)
            # Immunité du VTA aux feux et à la Yellow Box uniquement si V2I active
            # -------------------------------------------------------------
            if (entite.type_entite != TypeVehicule.VIG_VTA or not self.preemption_v2i_active) and not est_engage_intersection:
                couleur_feu = self.intersection.get_couleur_pour_voie(est_axe_x)

                # Règle 5 : Yellow Box (uniquement quand juste devant la ligne d'arrêt : 0.5 < dist_ligne < 3.5 m)
                if 0.5 < dist_ligne < 3.5:
                    if self.verifier_yellow_box(entite, copie_entites):
                        distance_arret = min(distance_arret, dist_ligne)
                        obstacle_nature = "YellowBoxCarrefourEncombre"

                # Arrêt aux feux Rouge et Orange
                if 0.0 < dist_ligne < 80.0:
                    if couleur_feu == CouleurFeu.ROUGE:
                        distance_arret = min(distance_arret, dist_ligne)
                        obstacle_nature = "FeuRouge"
                    elif couleur_feu == CouleurFeu.ORANGE:
                        if dist_ligne > (entite.vitesse * 2.0):
                            distance_arret = min(distance_arret, dist_ligne)
                            obstacle_nature = "FeuOrange"

            # -------------------------------------------------------------
            # RÈGLE 4 : Détection multi-points des obstacles
            # -------------------------------------------------------------
            dist_obs, nat_obs, vit_obs, veh_devant = self.detecter_obstacles_multipoints(entite, copie_entites)
            if dist_obs < distance_arret:
                distance_arret = dist_obs
                obstacle_nature = nat_obs
                vitesse_obstacle = vit_obs

            # Dégagement prioritaire absolu au milieu du carrefour :
            if est_engage_intersection:
                # Une fois engagé dans l'intersection ou sur sa courbe de Bézier,
                # le véhicule ne s'arrête plus (sauf si un piéton est juste sous ses roues à < 2.5 m)
                if obstacle_nature == "Pieton" and distance_arret < 2.5:
                    pass
                else:
                    distance_arret = 999.0
                    obstacle_nature = "Aucun"

            # -------------------------------------------------------------
            # GESTION DU DÉPASSEMENT VTA (COULOIR CENTRAL)
            # -------------------------------------------------------------
            if entite.type_entite == TypeVehicule.VIG_VTA:
                if est_axe_x:
                    voie_normale = 2.0 if math.cos(entite.cap_cible) > 0 else -2.0
                    voie_centrale = 0.3 if math.cos(entite.cap_cible) > 0 else -0.3
                    long_apres_centre = entite.pos_x if math.cos(entite.cap_cible) > 0 else -entite.pos_x
                else:
                    voie_normale = -2.0 if math.sin(entite.cap_cible) > 0 else 2.0
                    voie_centrale = -0.3 if math.sin(entite.cap_cible) > 0 else 0.3
                    long_apres_centre = entite.pos_y if math.sin(entite.cap_cible) > 0 else -entite.pos_y

                etat_actuel = getattr(entite, 'etat_depassement', 0)

                if etat_actuel == 0:
                    vehicule_devant_proche = False
                    for autre in copie_entites:
                        if autre.id_entite == entite.id_entite or autre.type_entite == TypeVehicule.PIETON:
                            continue
                        if getattr(autre, 'est_axe_x', False) == est_axe_x:
                            meme_sens = (
                                math.cos(autre.cap) * math.cos(entite.cap)
                                + math.sin(autre.cap) * math.sin(entite.cap)
                            ) > 0.5
                            if meme_sens:
                                d_l, d_lat = self.projeter_point_repere_local(
                                    autre.pos_x, autre.pos_y, entite.pos_x, entite.pos_y, entite.cap_cible
                                )
                                if 0.0 < d_l < 65.0 and abs(d_lat) < 2.5:
                                    vehicule_devant_proche = True
                                    break
                    if vehicule_devant_proche:
                        entite.etat_depassement = 1
                        if est_axe_x:
                            entite.voie_cible_y = voie_centrale
                        else:
                            entite.voie_cible_x = voie_centrale
                    else:
                        if est_axe_x:
                            entite.voie_cible_y = voie_normale
                        else:
                            entite.voie_cible_x = voie_normale

                elif etat_actuel == 1:
                    # VERROUILLAGE HYSTÉRÉSIS STRICT TANT QUE LE CARREFOUR N'EST PAS FRANCHI
                    if est_axe_x:
                        entite.voie_cible_y = voie_centrale
                    else:
                        entite.voie_cible_x = voie_centrale

                    franchi_carrefour = (long_apres_centre > 18.0)

                    # Vérifie si un véhicule est sur sa voie d'origine dans [-12.0m, +30.0m]
                    vehicule_sur_voie_origine = False
                    for autre in copie_entites:
                        if autre.id_entite == entite.id_entite or autre.type_entite == TypeVehicule.PIETON:
                            continue
                        if getattr(autre, 'est_axe_x', False) != est_axe_x:
                            continue
                        meme_sens = (
                            math.cos(autre.cap) * math.cos(entite.cap)
                            + math.sin(autre.cap) * math.sin(entite.cap)
                        ) > 0.5
                        if not meme_sens:
                            continue
                        pos_autre_lat = autre.pos_y if est_axe_x else autre.pos_x
                        if abs(pos_autre_lat - voie_normale) < 2.0:
                            d_l, _ = self.projeter_point_repere_local(
                                autre.pos_x, autre.pos_y, entite.pos_x, entite.pos_y, entite.cap_cible
                            )
                            if -12.0 <= d_l <= 30.0:
                                vehicule_sur_voie_origine = True
                                break

                    # Rabattement autorisé UNIQUEMENT si le carrefour est franchi ET voie d'origine libre
                    if franchi_carrefour and not vehicule_sur_voie_origine:
                        entite.etat_depassement = 2
                        if est_axe_x:
                            entite.voie_cible_y = voie_normale
                        else:
                            entite.voie_cible_x = voie_normale

                elif etat_actuel == 2:
                    if est_axe_x:
                        entite.voie_cible_y = voie_normale
                        delta_pos = abs(entite.pos_y - voie_normale)
                    else:
                        entite.voie_cible_x = voie_normale
                        delta_pos = abs(entite.pos_x - voie_normale)

                    if delta_pos < 0.08:
                        if est_axe_x:
                            entite.pos_y = voie_normale
                        else:
                            entite.pos_x = voie_normale
                        entite.etat_depassement = 0

            # -------------------------------------------------------------
            # RÉGULATEUR ADAPTATIF DE VITESSE (ACC) & FREINAGE
            # -------------------------------------------------------------
            vitesse_consigne = 13.8
            if entite.type_entite == TypeVehicule.CYCLISTE:
                vitesse_consigne = 5.5
            elif entite.type_entite == TypeVehicule.POIDS_LOURD:
                vitesse_consigne = 11.0
            elif entite.type_entite == TypeVehicule.VIG_VTA:
                vitesse_consigne = 20.0

            # Évacuation carrefour devant VTA
            if vta_proche and entite.type_entite != TypeVehicule.VIG_VTA and dans_carrefour_proche:
                vitesse_consigne = 14.0

            pos_lat_actuelle = entite.pos_y if est_axe_x else entite.pos_x

            if distance_arret < 60.0:
                marge_securite = (
                    2.0 + entite.vitesse * 1.0
                    if obstacle_nature in ("Vehicule", "Vehicule (Croisement)", "Vehicule (Priorité Face)")
                    else 0.5
                )
                dist_utile = max(0.0, distance_arret - marge_securite)
                v_securite = max(0.0, vitesse_obstacle) + math.sqrt(2.0 * 2.0 * dist_utile)
                if obstacle_nature in ("Pieton", "YellowBoxCarrefourEncombre"):
                    v_securite = math.sqrt(2.0 * 2.0 * dist_utile)

                vitesse_cible = min(vitesse_consigne, v_securite)
            else:
                vitesse_cible = vitesse_consigne

            # Priorité absolue de dégagement du carrefour (virage Bézier ou carrefour)
            if est_engage_intersection and (obstacle_nature != "Pieton" or distance_arret >= 2.5):
                vitesse_cible = max(vitesse_cible, 6.0)

            # Évacuation immédiate carrefour si VTA approche
            if vta_proche and entite.type_entite != TypeVehicule.VIG_VTA and dans_carrefour_proche:
                vitesse_cible = max(vitesse_cible, 14.0)

            # Dégagement latéral vers bas-côté pour véhicules non prioritaires
            if entite.type_entite != TypeVehicule.VIG_VTA and (vta_sur_meme_axe or vta_proche or getattr(entite, 'forcer_arret', False)):
                if not dans_carrefour_proche:
                    if abs(pos_lat_actuelle) < 3.0 and obstacle_nature != "Pieton":
                        # En cours de rangement latéral : maintenir au moins 5.0 m/s
                        vitesse_cible = max(vitesse_cible, 5.0)
                    elif abs(pos_lat_actuelle) >= 3.0 and dist_ligne > 2.0:
                        # Rangé sur le bas-côté : arrêt
                        vitesse_cible = 0.0

            # VTA en mission : maintien de la vitesse longitudinale à au moins 18.0 m/s
            if entite.type_entite == TypeVehicule.VIG_VTA and (getattr(entite, 'etat_depassement', 0) == 1 or vta_proche):
                if obstacle_nature != "Pieton" or distance_arret >= 2.5:
                    vitesse_cible = max(18.0, vitesse_consigne)

            erreur_vitesse = vitesse_cible - entite.vitesse

            if erreur_vitesse > 0.10:
                entite.commande_acceleration = min(2.5, erreur_vitesse * 1.0)
                entite.freinage_mecanique = False
            elif erreur_vitesse < -0.10:
                acc_requise = erreur_vitesse * 2.0
                if acc_requise > -1.5:
                    entite.commande_acceleration = acc_requise
                    entite.freinage_mecanique = False
                else:
                    mu = self.environnement.calculer_coefficient_friction()
                    facteur_abs = 1.0 if getattr(entite, 'possede_abs', True) else 0.75
                    decel_max = -9.81 * mu * facteur_abs * (1.0 - 0.25 * getattr(entite, 'usure_pneus', 0.0))
                    entite.commande_acceleration = max(acc_requise, decel_max)
                    entite.freinage_mecanique = True
            else:
                entite.commande_acceleration = 0.0
                entite.freinage_mecanique = False

            if distance_arret <= 1.0 or (distance_arret <= 3.5 and obstacle_nature == "Pieton"):
                degagement_urgence = (
                    (est_engage_intersection and obstacle_nature != "Pieton")
                    or (vta_proche and entite.type_entite != TypeVehicule.VIG_VTA and dans_carrefour_proche)
                    or (entite.type_entite == TypeVehicule.VIG_VTA and (getattr(entite, 'etat_depassement', 0) == 1 or vta_proche) and obstacle_nature != "Pieton")
                    or (entite.type_entite != TypeVehicule.VIG_VTA and (vta_sur_meme_axe or vta_proche) and abs(pos_lat_actuelle) < 3.0 and obstacle_nature != "Pieton")
                )
                if not degagement_urgence:
                    entite.commande_acceleration = -10.0
                    entite.freinage_mecanique = True
                    entite.vitesse = 0.0

            # Prise en compte prioritaire de la panne / arrêt simulé
            if getattr(entite, 'en_panne', False):
                entite.vitesse = 0.0
                entite.commande_acceleration = 0.0
                entite.freinage_mecanique = True
                distance_arret = 0.0
                obstacle_nature = "Panne Véhicule"

            # Enregistrement des données télémétriques sur l'entité
            entite.distance_arret = distance_arret
            entite.obstacle_nature = obstacle_nature

            # -------------------------------------------------------------
            # ASSERVISSEMENT DE TRAJECTOIRE ET BRAQUAGE (RÈGLE 3)
            # -------------------------------------------------------------
            if getattr(entite, 'trajectoire_bezier', None) is not None:
                # La trajectoire et le cap sont directement régis par la courbe de Bézier quadratique
                pass
            else:
                if entite.type_entite == TypeVehicule.VIG_VTA:
                    entite.est_axe_x = abs(math.cos(entite.cap_cible)) > 0.5
                    entite.cap = entite.cap_cible
                    erreur_cap = 0.0
                else:
                    erreur_cap = entite.cap_cible - entite.cap
                    while erreur_cap > math.pi:
                        erreur_cap -= 2 * math.pi
                    while erreur_cap < -math.pi:
                        erreur_cap += 2 * math.pi

                if abs(erreur_cap) > 0.15:
                    # Phase de rotation géométrique active : aucun déport latéral arbitraire
                    vitesse_rotation = 3.5
                    facteur_v = min(1.0, entite.vitesse / 2.0) if entite.vitesse > 0.1 else 0.2
                    entite.cap += math.copysign(min(abs(erreur_cap), vitesse_rotation * dt * facteur_v), erreur_cap)
                else:
                    # Aligné sur l'axe : mise à jour de l'axe et ajustement latéral
                    entite.est_axe_x = abs(math.cos(entite.cap_cible)) > 0.5
                    entite.cap = entite.cap_cible

                    if entite.est_axe_x:
                        erreur_lat = entite.voie_cible_y - entite.pos_y
                    else:
                        erreur_lat = entite.voie_cible_x - entite.pos_x

                    if entite.type_entite == TypeVehicule.VIG_VTA:
                        # Vitesse transversale constante et fluide de 3.0 m/s sans dépassement
                        v_lat = 3.0
                        if abs(erreur_lat) < 0.08:
                            if entite.est_axe_x:
                                entite.pos_y = entite.voie_cible_y
                            else:
                                entite.pos_x = entite.voie_cible_x
                        else:
                            step_lat = math.copysign(min(abs(erreur_lat), v_lat * dt), erreur_lat)
                            if entite.est_axe_x:
                                entite.pos_y += step_lat
                            else:
                                entite.pos_x += step_lat
                    else:
                        est_manoeuvre_urgente = (
                            (vta_sur_meme_axe or vta_proche or getattr(entite, 'forcer_arret', False))
                        )
                        if est_manoeuvre_urgente:
                            v_lat = max(2.5, abs(erreur_lat) * 3.0)
                            step_lat = math.copysign(min(abs(erreur_lat), v_lat * dt), erreur_lat)
                            if entite.est_axe_x:
                                entite.pos_y += step_lat
                            else:
                                entite.pos_x += step_lat
                        else:
                            if entite.vitesse > 0.1:
                                facteur_v = min(1.0, entite.vitesse / 3.0)
                                step_lat = erreur_lat * min(1.0, 2.0 * dt * facteur_v)
                                if entite.est_axe_x:
                                    entite.pos_y += step_lat
                                else:
                                    entite.pos_x += step_lat

        # -------------------------------------------------------------
        # 6. INTÉGRATION CINÉMATIQUE D'EULER & BARRIÈRE ANTI-CLIPPING (RÈGLE 5)
        # -------------------------------------------------------------
        for entite in copie_entites:
            if getattr(entite, 'type_entite', None) != TypeVehicule.PIETON:
                if getattr(entite, 'en_panne', False):
                    entite.vitesse = 0.0
                    entite.commande_acceleration = 0.0
                else:
                    masse = getattr(entite, 'masse_kg', 1000.0)
                    force_moteur = entite.commande_acceleration * masse
                    force_aero = (
                        entite.get_force_aerodynamique(self.densite_air_rho)
                        if hasattr(entite, 'get_force_aerodynamique')
                        else 0.0
                    )
                    crr = 0.015
                    friction_mecanique = crr * masse * 9.81 if entite.vitesse > 0.10 else 0.0
                    acceleration_nette = (force_moteur - force_aero - friction_mecanique) / masse

                    entite.vitesse += acceleration_nette * dt
                    if entite.vitesse < 0.0:
                        entite.vitesse = 0.0

            # Sauvegarde de la position pré-intégration
            pos_x_prev = entite.pos_x
            pos_y_prev = entite.pos_y

            # Intégration de la position (courbe de Bézier quadratique ou ligne droite)
            if getattr(entite, 'trajectoire_bezier', None) is not None:
                bez = entite.trajectoire_bezier
                dt_prog = dt * (entite.vitesse / max(0.1, bez.longueur_arc))
                bez.t += dt_prog
                if bez.t < 1.0:
                    entite.pos_x, entite.pos_y = bez.point(bez.t)
                    entite.cap = bez.cap(bez.t)
                else:
                    entite.pos_x, entite.pos_y = bez.p2
                    entite.cap = entite.cap_cible
                    entite.est_axe_x = abs(math.cos(entite.cap_cible)) > 0.5
                    if entite.est_axe_x:
                        entite.voie_cible_y = 2.0 if math.cos(entite.cap_cible) > 0 else -2.0
                    else:
                        entite.voie_cible_x = -2.0 if math.sin(entite.cap_cible) > 0 else 2.0
                    entite.trajectoire_bezier = None
                    entite.en_virage_bezier = False
                    entite.action_intersection = None
                    entite.indicateur_virage = 0
            else:
                entite.pos_x += entite.vitesse * math.cos(entite.cap) * dt
                entite.pos_y += entite.vitesse * math.sin(entite.cap) * dt

            # Règle 5 : Barrière physique anti-clipping dur (< 1.2 m)
            # Désactive totalement l'anti-clipping pour VIG_VTA dans son couloir d'urgence
            if getattr(entite, 'type_entite', None) == TypeVehicule.VIG_VTA and (getattr(entite, 'etat_depassement', 0) in (1, 2) or vta_proche):
                continue

            if getattr(entite, 'type_entite', None) != TypeVehicule.PIETON and entite.vitesse > 0.0:
                demi_l = entite.longueur_m / 2.0
                front_x = entite.pos_x + demi_l * math.cos(entite.cap)
                front_y = entite.pos_y + demi_l * math.sin(entite.cap)

                for autre in copie_entites:
                    if autre.id_entite == entite.id_entite:
                        continue
                    if autre.type_entite == TypeVehicule.PIETON:
                        pts = [(autre.pos_x, autre.pos_y)]
                    else:
                        pts = self.calculer_points_physiques(autre)

                    clipping_detecte = False
                    for px, py in pts:
                        dx = px - front_x
                        dy = py - front_y
                        proj_front = dx * math.cos(entite.cap) + dy * math.sin(entite.cap)
                        proj_lat = -dx * math.sin(entite.cap) + dy * math.cos(entite.cap)
                        if entite.type_entite == TypeVehicule.VIG_VTA:
                            largeur_totale = 1.0  # Max 1.0 m pour le VTA dans le couloir central
                        elif autre.type_entite == TypeVehicule.CYCLISTE and entite.type_entite != TypeVehicule.CYCLISTE:
                            largeur_totale = 1.1  # Piste cyclable séparée de 1.6m : aucun blocage par les cyclistes
                        else:
                            largeur_totale = (entite.largeur_m / 2.0) + (getattr(autre, 'largeur_m', 1.8) / 2.0) + 0.2

                        # Obstacle situé immédiatement devant le pare-chocs (< 1.2 m) ou en pénétration frontale
                        if -entite.longueur_m < proj_front < 1.2 and abs(proj_lat) < largeur_totale:
                            if proj_front <= 0.0 or math.hypot(dx, dy) < 1.2:
                                clipping_detecte = True
                                break

                    if clipping_detecte:
                        # Annulation UNIQUEMENT du déplacement longitudinal (fin du rollback latéral)
                        entite.vitesse = 0.0
                        if entite.est_axe_x:
                            entite.pos_x = pos_x_prev
                        else:
                            entite.pos_y = pos_y_prev
                        break

        # 7. Transmission des métriques réseau (1 Hz)
        maintenant = time.time()
        if self.network_client and maintenant - self.last_metrics_time > 1.0:
            self.last_metrics_time = maintenant
            nb_vehicules = len(copie_entites)
            somme_vitesses = sum(e.vitesse_kmh for e in copie_entites if hasattr(e, 'vitesse_kmh'))
            vitesse_moyenne = somme_vitesses / nb_vehicules if nb_vehicules > 0 else 0.0
            self.network_client.send_metrics(nb_vehicules, vitesse_moyenne)

        # 8. Émission de l'instantané d'affichage vers l'IHM
        try:
            safe_entites = []
            for e in copie_entites:
                snap = EntiteSnapshot()
                snap.id_entite = getattr(e, 'id_entite', None)
                snap.type_entite = getattr(e, 'type_entite', None)
                snap.pos_x = getattr(e, 'pos_x', 0.0)
                snap.pos_y = getattr(e, 'pos_y', 0.0)
                snap.cap = getattr(e, 'cap', 0.0)
                snap.longueur_m = getattr(e, 'longueur_m', 4.0)
                snap.largeur_m = getattr(e, 'largeur_m', 1.8)
                snap.vitesse = getattr(e, 'vitesse', 0.0)
                snap.vitesse_kmh = getattr(e, 'vitesse_kmh', 0.0)
                snap.masse_kg = getattr(e, 'masse_kg', 1000.0)
                snap.freinage_mecanique = getattr(e, 'freinage_mecanique', False)
                snap.commande_acceleration = getattr(e, 'commande_acceleration', 0.0)
                snap.possede_abs = getattr(e, 'possede_abs', False)
                snap.age_pneus = getattr(e, 'age_pneus', 0.0)
                snap.usure_pneus = getattr(e, 'usure_pneus', 0.0)
                snap.action_intersection = getattr(e, 'action_intersection', None)
                snap.cap_cible = getattr(e, 'cap_cible', snap.cap)
                snap.indicateur_virage = getattr(e, 'indicateur_virage', 0)
                snap.en_virage_bezier = getattr(e, 'en_virage_bezier', False)
                snap.en_panne = getattr(e, 'en_panne', False)
                snap.etat_depassement = getattr(e, 'etat_depassement', 0)
                snap.obstacle_nature = getattr(e, 'obstacle_nature', 'Aucun')
                snap.distance_obstacle = getattr(e, 'distance_arret', 999.0)
                safe_entites.append(snap)

            safe_inter = copy.deepcopy(self.intersection)
            safe_inter.preemption_v2i_active = self.preemption_v2i_active
            safe_inter.temps_franchissement_moyen_vta = self.temps_franchissement_moyen_vta
            safe_inter.gain_temps_estime_pct = self.gain_temps_estime_pct
            safe_inter.vehicules_franchis_total = self.vehicules_franchis_total
            safe_inter.mu = self.environnement.calculer_coefficient_friction()
            self.tick_simulation.emit(safe_entites, safe_inter)
        except Exception as e_emit:
            logger.error(f"[MoteurSimulation] Erreur émission snapshot : {e_emit}", exc_info=True)

    def run(self):
        """Boucle principale d'intégration physique cadencée à ~60 Hz."""
        timer = QElapsedTimer()
        timer.start()

        while self.__en_cours:
            try:
                dt = (timer.restart() / 1000.0) * self.multiplicateur_temps
                if dt > 0.10:
                    dt = 0.10

                self.etape_simulation(dt)

            except Exception as e_boucle:
                logger.error(f"[MoteurSimulation] Erreur dans la boucle physique : {e_boucle}", exc_info=True)

            try:
                self.msleep(16)
            except Exception as e_sleep:
                logger.error(f"[MoteurSimulation] Erreur msleep : {e_sleep}", exc_info=True)
