import logging
logger = logging.getLogger(__name__)

import math
import random
import time
from PyQt6.QtCore import QThread, pyqtSignal, QElapsedTimer, QMutex, QMutexLocker
from simulation.vehicules import TypeVehicule, Vehicule
from simulation.intersection import IntersectionManager, CouleurFeu

class MoteurSimulation(QThread):
    """
    Moteur principal de la simulation (tourne dans un QThread séparé).
    Gère la physique, les collisions et les déplacements de toutes les entités.
    """
    tick_simulation = pyqtSignal(list, object)

    def __init__(self):
        super().__init__()
        self.entites = []
        # Utilisation d'un QMutex pour éviter les data races (accès concurrents entre l'UI et le thread de simulation)
        self.mutex = QMutex()
        self.intersection = IntersectionManager()
        self.__en_cours = False
        self.multiplicateur_temps = 1.0
        self.densite_air_rho = 1.225 
        self.network_client = None
        self.last_metrics_time = 0

    def ajouter_entite(self, entite):
        """
        Ajoute une nouvelle entité dans la simulation de manière thread-safe.
        """
        # Verrouillage du mutex pour éviter que le thread de simulation lise la liste en même temps
        with QMutexLocker(self.mutex):
            try:
                # Initialisation des cibles pour le vecteur de direction et de voie
                entite.voie_cible_y = entite.pos_y
                entite.voie_cible_x = entite.pos_x
                entite.cap_cible = entite.cap
                entite.est_axe_x = abs(math.cos(entite.cap)) > 0.5
                
                # S'il s'agit d'un véhicule, on lui attribue potentiellement une direction aléatoire (tourner)
                if entite.type_entite != TypeVehicule.PIETON and getattr(entite, 'action_intersection', None) is None:
                    if random.random() < 0.2:
                        direction = random.choice([-math.pi/2, math.pi/2])
                        entite.action_intersection = entite.cap + direction

                # Ajout à la liste des entités
                self.entites.append(entite)
            except Exception as e:
                logger.error(f"[MoteurSimulation] Erreur lors de l'ajout de l'entité: {e}", exc_info=True)

    def vider_entites(self):
        """
        Vide toutes les entités de la simulation (utilisé lors du chargement d'un scénario).
        """
        with QMutexLocker(self.mutex):
            try:
                self.entites.clear()
            except Exception as e:
                logger.error(f"[MoteurSimulation] Erreur lors du vidage des entités: {e}", exc_info=True)

    def demarrer(self):
        """
        Démarre le thread de simulation.
        """
        self.__en_cours = True
        self.start()

    def arreter(self):
        """
        Arrête la boucle de simulation et attend la fin du thread.
        """
        self.__en_cours = False
        self.wait()

    def run(self):
        """
        Boucle principale du thread de simulation.
        Gère les mises à jour physiques à chaque intervalle de temps (dt).
        """
        timer = QElapsedTimer()
        timer.start()
        
        while self.__en_cours:
            try:
                # Calcul du temps écoulé depuis la dernière itération (dt) avec un multiplicateur
                dt = (timer.restart() / 1000.0) * self.multiplicateur_temps
                # Limite supérieure pour dt afin d'éviter les instabilités physiques
                if dt > 0.1: dt = 0.1 

                # Mise à jour de l'intersection si nous ne sommes pas en réseau
                if self.network_client is None:
                    self.intersection.update(dt)

                # Création d'une copie locale de la liste des entités pour éviter les accès concurrents
                # et filtrage des entités hors limites (garbage collection spatiale)
                with QMutexLocker(self.mutex):
                    self.entites = [e for e in self.entites if not getattr(e, 'a_detruire', False) and -55.0 < e.pos_x < 55.0 and -55.0 < e.pos_y < 55.0]
                    copie_entites = list(self.entites)

                # --- SPAWN AUTOMATIQUE ---
                try:
                    now = time.time()
                    if not hasattr(self, 'temps_dernier_spawn'):
                        self.temps_dernier_spawn = now
                        self.cpt_id = 9000
                    elif now - self.temps_dernier_spawn > 2.0:
                        self.temps_dernier_spawn = now
                        self.cpt_id += 1
                        # Choose a random type
                        t = random.choice([TypeVehicule.VOITURE, TypeVehicule.VOITURE, TypeVehicule.POIDS_LOURD, TypeVehicule.CYCLISTE])
                        
                        masse = 1500.0
                        if t == TypeVehicule.VOITURE: masse = max(800.0, random.gauss(1500.0, 200.0))
                        elif t == TypeVehicule.POIDS_LOURD: masse = max(10000.0, random.gauss(25000.0, 3000.0))
                        elif t == TypeVehicule.CYCLISTE: masse = max(40.0, random.gauss(90.0, 15.0))
                        
                        v = Vehicule(str(self.cpt_id), t, masse)
                        axe = random.choice(['x', 'y'])
                        sens = random.choice([1, -1])
                        
                        if axe == 'x':
                            v.pos_x = -48.0 * sens
                            v.pos_y = 2.0 * sens
                            v.cap = 0.0 if sens == 1 else math.pi
                        else:
                            v.pos_y = -48.0 * sens
                            v.pos_x = -2.0 * sens
                            v.cap = math.pi/2 if sens == 1 else -math.pi/2
                        
                        v.vitesse = 10.0
                        
                        # Vérification d'absence de chevauchement avant de spawner
                        chevauchement = False
                        for ent in copie_entites:
                            if math.hypot(ent.pos_x - v.pos_x, ent.pos_y - v.pos_y) < 15.0:
                                chevauchement = True
                                break
                        
                        if not chevauchement:
                            self.ajouter_entite(v)
                except Exception as e:
                    logger.error(f"[MoteurSimulation] Erreur dans le spawn automatique: {e}", exc_info=True)

                # 1. URGENCE VTA (Détection globale d'un véhicule d'urgence)
                vta_proche = False
                est_axe_x = False
                for entite in copie_entites:
                    if getattr(entite, 'type_entite', None) == TypeVehicule.VIG_VTA:
                        if math.hypot(entite.pos_x, entite.pos_y) < 70.0:
                            vta_proche = True
                            est_axe_x = entite.est_axe_x
                            break
                            
                # Envoi ou annulation de l'alerte VTA selon l'état du réseau
                if vta_proche:
                    if self.network_client:
                        self.network_client.send_vta_alert(est_axe_x)
                    else:
                        self.intersection.forcer_passage_vta(est_axe_x)
                else:
                    if self.network_client:
                        self.network_client.send_vta_end()
                    else:
                        self.intersection.annuler_urgence()

                # 2. COMPORTEMENT DE CHAQUE ENTITÉ
                for i, entite in enumerate(copie_entites):
                    # Gestion spécifique des piétons : déplacement simple et fixe sur les passages
                    if entite.type_entite == TypeVehicule.PIETON:
                        entite.commande_acceleration = 0.0
                        entite.vitesse = 1.5
                        if abs(math.cos(entite.cap)) > 0.5:
                            entite.pos_y = 9.0 if entite.pos_y > 0 else -9.0
                            if math.cos(entite.cap) > 0 and entite.pos_x > 10.0:
                                entite.a_detruire = True
                            elif math.cos(entite.cap) < 0 and entite.pos_x < -10.0:
                                entite.a_detruire = True
                        else:
                            entite.pos_x = 9.0 if entite.pos_x > 0 else -9.0
                            if math.sin(entite.cap) > 0 and entite.pos_y > 10.0:
                                entite.a_detruire = True
                            elif math.sin(entite.cap) < 0 and entite.pos_y < -10.0:
                                entite.a_detruire = True
                        continue

                    # Pour les autres véhicules, on initialise les variables d'analyse
                    est_axe_x = entite.est_axe_x
                    distance_arret = 999.0
                    obstacle_nature = "Aucun"
                    vitesse_obstacle = 0.0
                    
                    # --- CHANGEMENT DE DIRECTION A L'INTERSECTION ---
                    # Si un virage est prévu et qu'on s'approche du centre de l'intersection
                    if getattr(entite, 'action_intersection', None) is not None:
                        dist_centre = math.hypot(entite.pos_x, entite.pos_y)
                        if dist_centre < 10.0:
                            # On applique le changement de cap cible
                            entite.cap_cible = entite.action_intersection
                            entite.est_axe_x = abs(math.cos(entite.cap_cible)) > 0.5
                            # Ajustement de la cible transversale pour la nouvelle voie
                            if entite.est_axe_x:
                                entite.voie_cible_y = 2.0 if math.cos(entite.cap_cible) > 0 else -2.0
                            else:
                                entite.voie_cible_x = 2.0 if math.sin(entite.cap_cible) > 0 else -2.0
                            entite.action_intersection = None

                    # --- FEUX TRICOLORES ---
                    # Lecture de la couleur du feu pour l'axe de l'entité
                    couleur_feu = self.intersection.get_couleur_pour_voie(est_axe_x)
                    # Calcul de la distance à la ligne d'arrêt
                    if est_axe_x:
                        dist_ligne = -entite.pos_x - 10.0 - entite.longueur_m/2.0 if math.cos(entite.cap_cible) > 0 else entite.pos_x - 10.0 - entite.longueur_m/2.0
                    else:
                        dist_ligne = -entite.pos_y - 10.0 - entite.longueur_m/2.0 if math.sin(entite.cap_cible) > 0 else entite.pos_y - 10.0 - entite.longueur_m/2.0
                    
                    # Si le véhicule est concerné par le feu et n'est pas prioritaire (VTA)
                    if 0 < dist_ligne < 80.0 and entite.type_entite != TypeVehicule.VIG_VTA:
                        if couleur_feu == CouleurFeu.ROUGE:
                            distance_arret = dist_ligne
                            obstacle_nature = "FeuRouge"
                        elif couleur_feu == CouleurFeu.ORANGE:
                            # Si le véhicule est trop près (moins de 2s d'arrêt) il passe, sinon il s'arrête
                            if dist_ligne > (entite.vitesse * 2.0): 
                                distance_arret = dist_ligne
                                obstacle_nature = "FeuOrange"

                    # --- DÉTECTION VEHICULES (RAYCAST ET DISTANCE) ---
                    vehicule_devant = None
                    for j, autre in enumerate(copie_entites):
                        if i != j:
                            dx = autre.pos_x - entite.pos_x
                            dy = autre.pos_y - entite.pos_y
                            
                            # Vérification : sont-ils sur la même voie ou dans la trajectoire ?
                            meme_voie = False
                            if getattr(autre, 'type_entite', None) == TypeVehicule.PIETON:
                                dot_side_pieton = -dx * math.sin(entite.cap_cible) + dy * math.cos(entite.cap_cible)
                                if abs(dot_side_pieton) < 2.5:
                                    meme_voie = True
                            else:
                                if est_axe_x and getattr(autre, 'est_axe_x', False):
                                    if abs(entite.pos_y - autre.pos_y) < 1.4 or \
                                       abs(entite.voie_cible_y - autre.pos_y) < 1.4 or \
                                       abs(entite.pos_y - getattr(autre, 'voie_cible_y', autre.pos_y)) < 1.4 or \
                                       abs(entite.voie_cible_y - getattr(autre, 'voie_cible_y', autre.pos_y)) < 1.4:
                                        meme_voie = True
                                elif not est_axe_x and not getattr(autre, 'est_axe_x', True):
                                    if abs(entite.pos_x - autre.pos_x) < 1.4 or \
                                       abs(entite.voie_cible_x - autre.pos_x) < 1.4 or \
                                       abs(entite.pos_x - getattr(autre, 'voie_cible_x', autre.pos_x)) < 1.4 or \
                                       abs(entite.voie_cible_x - getattr(autre, 'voie_cible_x', autre.pos_x)) < 1.4:
                                        meme_voie = True
                                
                            # Vérification : sont-ils tous deux dans l'intersection ?
                            en_intersection = False
                            if math.hypot(entite.pos_x, entite.pos_y) < 20.0 and math.hypot(autre.pos_x, autre.pos_y) < 20.0:
                                # Vérification de l'angle devant le véhicule
                                dot_front = dx * math.cos(entite.cap) + dy * math.sin(entite.cap)
                                dot_side = -dx * math.sin(entite.cap) + dy * math.cos(entite.cap)
                                if 0 < dot_front < 15.0 and abs(dot_side) < 3.0:
                                    en_intersection = True

                            # Prévenir les collisions en croisement :
                            # Si on est dans l'intersection et pas sur la même voie
                            if en_intersection and not meme_voie:
                                entite_tourne = abs(entite.cap_cible - entite.cap) > 0.1
                                autre_tourne = abs(autre.cap_cible - autre.cap) > 0.1
                                
                                # Ajout de la vérification Euclidienne pour éviter le chevauchement (Collision Croisement)
                                dist_croisement = math.hypot(dx, dy)
                                if dist_croisement < 15.0:
                                    # Le véhicule qui tourne cède le passage à celui qui va tout droit
                                    if entite_tourne and not autre_tourne:
                                        if dist_croisement < distance_arret:
                                            distance_arret = dist_croisement
                                            obstacle_nature = "Pieton (Croisement)" if getattr(autre, 'type_entite', None) == TypeVehicule.PIETON else "Vehicule (Croisement)"
                                            vitesse_obstacle = autre.vitesse
                                            vehicule_devant = autre
                                    elif not entite_tourne and autre_tourne:
                                        # On est le véhicule qui va tout droit, on l'ignore (en intersection) pour qu'il s'arrête
                                        en_intersection = False
                                    # Si les deux tournent (même situation), priorité à l'ID pour briser la symétrie
                                    elif entite_tourne == autre_tourne and str(entite.id_entite) < str(autre.id_entite):
                                        en_intersection = False
                                    elif entite_tourne == autre_tourne and str(entite.id_entite) > str(autre.id_entite):
                                        if dist_croisement < distance_arret:
                                            distance_arret = dist_croisement
                                            obstacle_nature = "Pieton (Croisement)" if getattr(autre, 'type_entite', None) == TypeVehicule.PIETON else "Vehicule (Croisement)"
                                            proj_vitesse = autre.vitesse * (math.cos(autre.cap) * math.cos(entite.cap) + math.sin(autre.cap) * math.sin(entite.cap))
                                            vitesse_obstacle = proj_vitesse
                                            vehicule_devant = autre

                            # Détection classique (Devant soi)
                            if meme_voie or en_intersection:
                                # Produit scalaire pour savoir si l'autre véhicule est strictement devant
                                cap_eval = entite.cap if en_intersection and not meme_voie else entite.cap_cible
                                dot = dx * math.cos(cap_eval) + dy * math.sin(cap_eval)
                                
                                if 0 < dot < distance_arret:
                                    dist_nette = dot - (entite.longueur_m/2 + autre.longueur_m/2) - 1.0
                                    # Si ce véhicule est le plus proche et devant nous
                                    if dist_nette < distance_arret:
                                        distance_arret = dist_nette
                                        obstacle_nature = "Pieton" if getattr(autre, 'type_entite', None) == TypeVehicule.PIETON else "Vehicule"
                                        proj_vitesse = autre.vitesse * (math.cos(autre.cap) * math.cos(cap_eval) + math.sin(autre.cap) * math.sin(cap_eval))
                                        vitesse_obstacle = proj_vitesse
                                        vehicule_devant = autre

                    # --- LOGIQUE DE DÉPASSEMENT (Camions, VTA, etc.) ---
                    # Si un véhicule nous ralentit considérablement
                    est_bloque = (obstacle_nature == "Vehicule" and distance_arret < 25.0)
                    vta_veut_depasser = (entite.type_entite == TypeVehicule.VIG_VTA and obstacle_nature == "Vehicule" and vehicule_devant and vehicule_devant.vitesse < 21.0 and distance_arret < 80.0)
                    
                    if (est_bloque or vta_veut_depasser) and getattr(entite, 'etat_depassement', 0) == 0:
                        if entite.type_entite in (TypeVehicule.VIG_VTA, TypeVehicule.POIDS_LOURD, TypeVehicule.VOITURE):
                            # Vérification qu'on n'est pas en pleine intersection
                            if math.hypot(entite.pos_x, entite.pos_y) > 30.0:
                                voie_opposee_libre = True
                                # On inspecte la voie opposée pour s'assurer qu'il n'y a pas de collision imminente
                                for k, op in enumerate(copie_entites):
                                    if i != k and getattr(op, 'type_entite', None) != TypeVehicule.PIETON:
                                        is_on_opposite = False
                                        if est_axe_x and getattr(op, 'est_axe_x', False) and abs(op.pos_y - (-entite.voie_cible_y)) < 1.2:
                                            is_on_opposite = True
                                        elif not est_axe_x and not getattr(op, 'est_axe_x', True) and abs(op.pos_x - (-entite.voie_cible_x)) < 1.2:
                                            is_on_opposite = True
                                        
                                        if is_on_opposite:
                                            dx_op = op.pos_x - entite.pos_x
                                            dy_op = op.pos_y - entite.pos_y
                                            dot_op = dx_op * math.cos(entite.cap_cible) + dy_op * math.sin(entite.cap_cible)
                                            # On vérifie seulement les véhicules devant nous ou juste à côté
                                            if -10.0 < dot_op < 100.0:
                                                if entite.type_entite == TypeVehicule.VIG_VTA and getattr(op, 'vitesse', 0.0) < 2.0:
                                                    continue
                                                voie_opposee_libre = False
                                                break
                                                
                                # Si la voie opposée est libre, on initie un dépassement
                                if voie_opposee_libre:
                                    entite.etat_depassement = 1
                                    if est_axe_x: entite.voie_cible_y = -entite.voie_cible_y
                                    else: entite.voie_cible_x = -entite.voie_cible_x

                    # Phase de rabattement (retour sur la voie initiale)
                    if getattr(entite, 'etat_depassement', 0) == 1:
                        peut_se_rabattre = True
                        for k, autre in enumerate(copie_entites):
                            if i != k and getattr(autre, 'type_entite', None) != TypeVehicule.PIETON:
                                voie_origine_y = -entite.voie_cible_y if est_axe_x else entite.pos_y
                                voie_origine_x = -entite.voie_cible_x if not est_axe_x else entite.pos_x
                                
                                sur_voie_origine = False
                                if est_axe_x and getattr(autre, 'est_axe_x', False) and abs(autre.pos_y - voie_origine_y) < 2.0:
                                    sur_voie_origine = True
                                elif not est_axe_x and not getattr(autre, 'est_axe_x', True) and abs(autre.pos_x - voie_origine_x) < 2.0:
                                    sur_voie_origine = True
                                    
                                if sur_voie_origine:
                                    dx_autre = autre.pos_x - entite.pos_x
                                    dy_autre = autre.pos_y - entite.pos_y
                                    dot_autre = dx_autre * math.cos(entite.cap_cible) + dy_autre * math.sin(entite.cap_cible)
                                    
                                    # Marges de sécurité avant de se rabattre
                                    marge_arriere = autre.longueur_m / 2.0 + entite.longueur_m / 2.0 + 5.0
                                    marge_avant = autre.longueur_m / 2.0 + entite.longueur_m / 2.0 + 12.0
                                    if -marge_arriere < dot_autre < marge_avant:
                                        peut_se_rabattre = False
                                        break
                                        
                        # Si on peut se rabattre, on change de phase
                        if peut_se_rabattre:
                            entite.etat_depassement = 2

                    if getattr(entite, 'etat_depassement', 0) == 2:
                        if est_axe_x: 
                            entite.voie_cible_y = 2.0 if math.cos(entite.cap_cible) > 0 else -2.0
                            if abs(entite.pos_y - entite.voie_cible_y) < 0.2:
                                entite.etat_depassement = 0
                        else: 
                            entite.voie_cible_x = 2.0 if math.sin(entite.cap_cible) > 0 else -2.0
                            if abs(entite.pos_x - entite.voie_cible_x) < 0.2:
                                entite.etat_depassement = 0
                                
                    # --- DEGAGEMENT VTA ---
                    forcer_arret = False
                    if entite.type_entite not in (TypeVehicule.VIG_VTA, TypeVehicule.PIETON) and vta_proche:
                        for v in copie_entites:
                            if getattr(v, 'type_entite', None) == TypeVehicule.VIG_VTA:
                                if est_axe_x == v.est_axe_x:
                                    # Vérifier si on est sur la même voie (ou si le VTA a l'intention d'y venir pour dépasser)
                                    sur_notre_voie = False
                                    if est_axe_x:
                                        if abs(entite.pos_y - v.pos_y) < 2.0 or abs(entite.pos_y - getattr(v, 'voie_cible_y', v.pos_y)) < 2.0:
                                            sur_notre_voie = True
                                    else:
                                        if abs(entite.pos_x - v.pos_x) < 2.0 or abs(entite.pos_x - getattr(v, 'voie_cible_x', v.pos_x)) < 2.0:
                                            sur_notre_voie = True
                                            
                                    if sur_notre_voie:
                                        dx_v = entite.pos_x - v.pos_x
                                        dy_v = entite.pos_y - v.pos_y
                                        dot_vta = dx_v * math.cos(v.cap) + dy_v * math.sin(v.cap)
                                        dist_vta = math.hypot(dx_v, dy_v)
                                        # Si on est devant le VTA (dot_vta > 0) à moins de 80m
                                        if 0 < dot_vta < 80.0 and dist_vta < 80.0:
                                            forcer_arret = True
                                            # On se déporte sur le bord (trottoir)
                                            if est_axe_x:
                                                entite.voie_cible_y = 3.5 if entite.pos_y > 0 else -3.5
                                            else:
                                                entite.voie_cible_x = 3.5 if entite.pos_x > 0 else -3.5
                                            break

                    # Retour sur la voie normale après le passage du VTA
                    if not forcer_arret and getattr(entite, 'etat_depassement', 0) == 0:
                        if est_axe_x:
                            if abs(entite.voie_cible_y) > 3.0:
                                entite.voie_cible_y = 2.0 if entite.voie_cible_y > 0 else -2.0
                        else:
                            if abs(entite.voie_cible_x) > 3.0:
                                entite.voie_cible_x = 2.0 if entite.voie_cible_x > 0 else -2.0

                    # --- PID ACCÉLÉRATION & FREINAGE PROGRESSIF ---
                    # Vitesse cible selon le type de véhicule
                    cible = 13.8 
                    if entite.type_entite == TypeVehicule.CYCLISTE: cible = 5.5
                    elif entite.type_entite == TypeVehicule.POIDS_LOURD: cible = 11.0
                    elif entite.type_entite == TypeVehicule.VIG_VTA: cible = 50.0

                    if forcer_arret:
                        # Freinage d'urgence pour laisser passer
                        entite.commande_acceleration = -5.0
                        entite.freinage_mecanique = True
                        if entite.vitesse < 0.5:
                            entite.vitesse = 0.0
                    elif distance_arret < 60.0:
                        marge = 2.0 + entite.vitesse * 1.0 if obstacle_nature in ("Vehicule", "Vehicule (Croisement)", "Pieton", "Pieton (Croisement)") else 0.5
                        dist_utile = max(0.0, distance_arret - marge)
                        
                        # Vitesse de sécurité calculée par rapport à l'obstacle
                        v_securite = max(0.0, vitesse_obstacle) + math.sqrt(2 * 2.0 * dist_utile)
                        if obstacle_nature in ("Pieton", "Pieton (Croisement)"):
                            v_securite = math.sqrt(2 * 2.0 * dist_utile)
                        vitesse_cible = min(cible, v_securite)

                        erreur_v = vitesse_cible - entite.vitesse

                        # Application de l'accélération ou du freinage selon l'erreur de vitesse
                        if erreur_v > 0.1:
                            entite.commande_acceleration = min(2.5, erreur_v * 1.0)
                            entite.freinage_mecanique = False
                        elif erreur_v < -0.1:
                            acc_requise = erreur_v * 2.0
                            if acc_requise > -1.5:
                                entite.commande_acceleration = acc_requise
                                entite.freinage_mecanique = False
                            else:
                                entite.commande_acceleration = max(acc_requise, -8.0)
                                entite.freinage_mecanique = True
                        else:
                            entite.commande_acceleration = 0.0
                            entite.freinage_mecanique = False
                            
                        # Arrêt complet si on est très proche d'un obstacle fixe
                        if distance_arret <= 1.0 or (distance_arret <= 3.5 and obstacle_nature in ("Pieton", "Pieton (Croisement)")):
                            entite.commande_acceleration = -10.0
                            entite.freinage_mecanique = True
                            entite.vitesse = 0.0
                    else:
                        entite.freinage_mecanique = False
                        if entite.vitesse < cible:
                            entite.commande_acceleration = 2.5
                        else:
                            entite.commande_acceleration = 0.0

                    # --- TRAJECTOIRES VECTORIELLES & BRAQUAGE ---
                    # Lissage progressif du cap (pour éviter les mouvements brusques)
                    erreur_cap = entite.cap_cible - entite.cap
                    while erreur_cap > math.pi: erreur_cap -= 2*math.pi
                    while erreur_cap < -math.pi: erreur_cap += 2*math.pi
                    entite.cap += erreur_cap * min(1.0, 3.0 * dt)

                    # Ajustement graduel de la position transversale
                    if est_axe_x:
                        erreur_y = entite.voie_cible_y - entite.pos_y
                        entite.pos_y += erreur_y * min(1.0, 1.5 * dt)
                    else:
                        erreur_x = entite.voie_cible_x - entite.pos_x
                        entite.pos_x += erreur_x * min(1.0, 1.5 * dt)

                # --- INTÉGRATION D'EULER FINALE ---
                for entite in copie_entites:
                    if getattr(entite, 'type_entite', None) != TypeVehicule.PIETON:
                        # Calcul des forces en jeu (Moteur, Aérodynamique, Frottements mécaniques)
                        force_moteur = entite.commande_acceleration * getattr(entite, 'masse_kg', 1000)
                        force_aero = entite.get_force_aerodynamique(self.densite_air_rho) if hasattr(entite, 'get_force_aerodynamique') else 0.0
                        
                        crr = 0.015 
                        friction_mecanique = crr * getattr(entite, 'masse_kg', 1000) * 9.81 if entite.vitesse > 0.1 else 0.0
                        
                        # Loi de Newton: F = m*a
                        acceleration_nette = (force_moteur - force_aero - friction_mecanique) / getattr(entite, 'masse_kg', 1000)
                        
                        # Mise à jour de la vitesse
                        entite.vitesse += acceleration_nette * dt
                        if entite.vitesse < 0.0: entite.vitesse = 0.0 
                    
                    # Application du vecteur vitesse à la position géométrique
                    entite.pos_x += entite.vitesse * math.cos(entite.cap) * dt
                    entite.pos_y += entite.vitesse * math.sin(entite.cap) * dt
                    
                # Calcul et envoi des statistiques réseau de manière périodique
                now = time.time()
                if self.network_client and now - self.last_metrics_time > 1.0:
                    self.last_metrics_time = now
                    nb = len(copie_entites)
                    s = sum(e.vitesse_kmh for e in copie_entites if hasattr(e, 'vitesse_kmh'))
                    avg = s / nb if nb > 0 else 0.0
                    self.network_client.send_metrics(nb, avg)
                    
            except Exception as e:
                # Capture d'une erreur imprévue durant le calcul physique
                logger.error(f"[MoteurSimulation] Erreur physique dans la boucle principale: {e}", exc_info=True)
                
            # Émission des données mises à jour vers l'interface graphique UI
            try:
                class EntiteSnapshot:
                    pass
                
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
                    safe_entites.append(snap)
                    
                import copy
                safe_inter = copy.deepcopy(self.intersection)
                self.tick_simulation.emit(safe_entites, safe_inter)
            except Exception as emit_err:
                logger.error(f"[MoteurSimulation] Erreur lors de l'émission du signal de tick: {emit_err}", exc_info=True)

            try:
                # Pause courte pour limiter l'usage CPU et respecter ~60 FPS
                self.msleep(16)
            except Exception as e:
                logger.error(f"[MoteurSimulation] Erreur lors de l'attente msleep: {e}", exc_info=True)
