import math
import random
import time
from PyQt6.QtCore import QThread, pyqtSignal, QElapsedTimer
from simulation.vehicules import TypeVehicule
from simulation.intersection import IntersectionManager, CouleurFeu

class MoteurSimulation(QThread):
    tick_simulation = pyqtSignal(list, object)

    def __init__(self):
        super().__init__()
        self.entites = []
        self.intersection = IntersectionManager()
        self.__en_cours = False
        self.multiplicateur_temps = 1.0
        self.densite_air_rho = 1.225 
        self.network_client = None
        self.last_metrics_time = 0

    def ajouter_entite(self, entite):
        try:
            entite.voie_cible_y = entite.pos_y
            entite.voie_cible_x = entite.pos_x
            entite.cap_cible = entite.cap
            entite.est_axe_x = abs(math.cos(entite.cap)) > 0.5
            
            if entite.type_entite != TypeVehicule.PIETON and getattr(entite, 'action_intersection', None) is None:
                if random.random() < 0.2:
                    direction = random.choice([-math.pi/2, math.pi/2])
                    entite.action_intersection = entite.cap + direction

            self.entites.append(entite)
        except Exception:
            pass

    def demarrer(self):
        self.__en_cours = True
        self.start()

    def arreter(self):
        self.__en_cours = False
        self.wait()

    def run(self):
        timer = QElapsedTimer()
        timer.start()
        
        while self.__en_cours:
            try:
                dt = (timer.restart() / 1000.0) * self.multiplicateur_temps
                if dt > 0.1: dt = 0.1 

                if self.network_client is None:
                    self.intersection.update(dt)
                self.entites = [e for e in self.entites if -150.0 < e.pos_x < 150.0 and -150.0 < e.pos_y < 150.0]

                # 1. URGENCE VTA (Global)
                vta_proche = False
                est_axe_x = False
                for entite in self.entites:
                    if entite.type_entite == TypeVehicule.VIG_VTA:
                        if math.hypot(entite.pos_x, entite.pos_y) < 70.0:
                            vta_proche = True
                            est_axe_x = entite.est_axe_x
                            break
                            
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
                for i, entite in enumerate(self.entites):
                    if entite.type_entite == TypeVehicule.PIETON:
                        # Les piétons se déplacent à vitesse fixe sur les clous
                        entite.commande_acceleration = 0.0
                        entite.vitesse = 1.5
                        if abs(math.cos(entite.cap)) > 0.5:
                            entite.pos_y = 9.0 if entite.pos_y > 0 else -9.0
                            if entite.pos_x > 4.5:
                                entite.cap = math.pi
                                entite.pos_x = 4.5
                            elif entite.pos_x < -4.5:
                                entite.cap = 0.0
                                entite.pos_x = -4.5
                        else:
                            entite.pos_x = 9.0 if entite.pos_x > 0 else -9.0
                            if entite.pos_y > 4.5:
                                entite.cap = -math.pi/2
                                entite.pos_y = 4.5
                            elif entite.pos_y < -4.5:
                                entite.cap = math.pi/2
                                entite.pos_y = -4.5
                        continue

                    est_axe_x = entite.est_axe_x
                    distance_arret = 999.0
                    obstacle_nature = "Aucun"
                    vitesse_obstacle = 0.0
                    
                    # --- CHANGEMENT DE DIRECTION A L'INTERSECTION ---
                    if entite.action_intersection is not None:
                        dist_centre = math.hypot(entite.pos_x, entite.pos_y)
                        if dist_centre < 10.0:
                            # On effectue le virage
                            entite.cap_cible = entite.action_intersection
                            entite.est_axe_x = abs(math.cos(entite.cap_cible)) > 0.5
                            if entite.est_axe_x:
                                entite.voie_cible_y = 2.0 if math.cos(entite.cap_cible) > 0 else -2.0
                            else:
                                entite.voie_cible_x = 2.0 if math.sin(entite.cap_cible) > 0 else -2.0
                            entite.action_intersection = None

                    # --- FEUX TRICOLORES ---
                    couleur_feu = self.intersection.get_couleur_pour_voie(est_axe_x)
                    if est_axe_x:
                        dist_ligne = -entite.pos_x - 10.0 - entite.longueur_m/2.0 if math.cos(entite.cap_cible) > 0 else entite.pos_x - 10.0 - entite.longueur_m/2.0
                    else:
                        dist_ligne = -entite.pos_y - 10.0 - entite.longueur_m/2.0 if math.sin(entite.cap_cible) > 0 else entite.pos_y - 10.0 - entite.longueur_m/2.0
                    
                    if 0 < dist_ligne < 80.0 and entite.type_entite != TypeVehicule.VIG_VTA:
                        if couleur_feu == CouleurFeu.ROUGE:
                            distance_arret = dist_ligne
                            obstacle_nature = "FeuRouge"
                        elif couleur_feu == CouleurFeu.ORANGE:
                            # Zone V0: si trop près et rapide, on passe (distance_arret reste 999)
                            if dist_ligne > (entite.vitesse * 2.0): # 2 secondes pour s'arrêter
                                distance_arret = dist_ligne
                                obstacle_nature = "FeuOrange"

                    # --- DÉTECTION VEHICULES (RAYCAST) ---
                    vehicule_devant = None
                    for j, autre in enumerate(self.entites):
                        if i != j and autre.type_entite != TypeVehicule.PIETON:
                            dx = autre.pos_x - entite.pos_x
                            dy = autre.pos_y - entite.pos_y
                            
                            # Sont-ils sur la même voie ?
                            meme_voie = False
                            if est_axe_x and autre.est_axe_x and abs(entite.pos_y - autre.pos_y) < 2.0:
                                meme_voie = True
                            elif not est_axe_x and not autre.est_axe_x and abs(entite.pos_x - autre.pos_x) < 2.0:
                                meme_voie = True
                                
                            # Check dans l'intersection (bounding box / cone de détection)
                            en_intersection = False
                            if math.hypot(entite.pos_x, entite.pos_y) < 20.0 and math.hypot(autre.pos_x, autre.pos_y) < 20.0:
                                dot_front = dx * math.cos(entite.cap) + dy * math.sin(entite.cap)
                                dot_side = -dx * math.sin(entite.cap) + dy * math.cos(entite.cap)
                                if 0 < dot_front < 15.0 and abs(dot_side) < 3.0:
                                    en_intersection = True

                            # Prévenir les deadlocks en intersection:
                            if en_intersection and not meme_voie:
                                entite_tourne = abs(entite.cap_cible - entite.cap) > 0.1
                                autre_tourne = abs(autre.cap_cible - autre.cap) > 0.1
                                
                                # Le véhicule qui tourne cède le passage à celui qui va tout droit
                                if not entite_tourne and autre_tourne:
                                    en_intersection = False
                                # Si même situation, priorité à l'ID pour briser la symétrie
                                elif entite_tourne == autre_tourne and str(entite.id_entite) < str(autre.id_entite):
                                    en_intersection = False

                            if meme_voie or en_intersection:
                                # Produit scalaire pour savoir s'il est devant
                                # On utilise cap_cible pour la même voie, et cap pour l'intersection
                                cap_eval = entite.cap if en_intersection and not meme_voie else entite.cap_cible
                                dot = dx * math.cos(cap_eval) + dy * math.sin(cap_eval)
                                
                                if 0 < dot < distance_arret:
                                    dist_nette = dot - (entite.longueur_m/2 + autre.longueur_m/2) - 1.0
                                    if dist_nette < distance_arret:
                                        distance_arret = dist_nette
                                        obstacle_nature = "Vehicule"
                                        vitesse_obstacle = autre.vitesse
                                        vehicule_devant = autre

                    # --- LOGIQUE DE DÉPASSEMENT (Camions, VTA, etc.) ---
                    if obstacle_nature == "Vehicule" and distance_arret < 25.0 and entite.etat_depassement == 0:
                        peut_depasser = False
                        if entite.type_entite in (TypeVehicule.VIG_VTA, TypeVehicule.POIDS_LOURD, TypeVehicule.VOITURE):
                            # Vérifier si on approche de l'intersection (pas de dépassement)
                            if math.hypot(entite.pos_x, entite.pos_y) > 30.0:
                                # Vérifier la voie opposée
                                voie_opposee_libre = True
                                for k, op in enumerate(self.entites):
                                    if i != k:
                                        if est_axe_x and abs(op.pos_y - (-entite.voie_cible_y)) < 2.0:
                                            dx = op.pos_x - entite.pos_x
                                            if abs(dx) < 60.0: voie_opposee_libre = False
                                        elif not est_axe_x and abs(op.pos_x - (-entite.voie_cible_x)) < 2.0:
                                            dy = op.pos_y - entite.pos_y
                                            if abs(dy) < 60.0: voie_opposee_libre = False
                                if voie_opposee_libre:
                                    entite.etat_depassement = 1
                                    if est_axe_x: entite.voie_cible_y = -entite.voie_cible_y
                                    else: entite.voie_cible_x = -entite.voie_cible_x

                    # Rabattement
                    if entite.etat_depassement == 1:
                        peut_se_rabattre = True
                        for k, autre in enumerate(self.entites):
                            if i != k and autre.type_entite != TypeVehicule.PIETON:
                                voie_origine_y = -entite.voie_cible_y if est_axe_x else entite.pos_y
                                voie_origine_x = -entite.voie_cible_x if not est_axe_x else entite.pos_x
                                
                                sur_voie_origine = False
                                if est_axe_x and autre.est_axe_x and abs(autre.pos_y - voie_origine_y) < 2.0:
                                    sur_voie_origine = True
                                elif not est_axe_x and not autre.est_axe_x and abs(autre.pos_x - voie_origine_x) < 2.0:
                                    sur_voie_origine = True
                                    
                                if sur_voie_origine:
                                    dx = autre.pos_x - entite.pos_x
                                    dy = autre.pos_y - entite.pos_y
                                    dot = dx * math.cos(entite.cap_cible) + dy * math.sin(entite.cap_cible)
                                    
                                    marge_arriere = autre.longueur_m / 2.0 + entite.longueur_m / 2.0 + 2.0
                                    marge_avant = autre.longueur_m / 2.0 + entite.longueur_m / 2.0 + 10.0
                                    if -marge_arriere < dot < marge_avant:
                                        peut_se_rabattre = False
                                        break
                                        
                        if peut_se_rabattre:
                            entite.etat_depassement = 2

                    if entite.etat_depassement == 2:
                        if est_axe_x: entite.voie_cible_y = 2.0 if math.cos(entite.cap_cible) > 0 else -2.0
                        else: entite.voie_cible_x = 2.0 if math.sin(entite.cap_cible) > 0 else -2.0
                        entite.etat_depassement = 0

                    # --- PID ACCÉLÉRATION & FREINAGE PROGRESSIF ---
                    cible = 13.8 
                    if entite.type_entite == TypeVehicule.CYCLISTE: cible = 5.5
                    elif entite.type_entite == TypeVehicule.POIDS_LOURD: cible = 11.0
                    elif entite.type_entite == TypeVehicule.VIG_VTA: cible = 22.0

                    if distance_arret < 60.0:
                        marge = 2.0 + entite.vitesse * 1.0 if obstacle_nature == "Vehicule" else 0.5
                        dist_utile = max(0.0, distance_arret - marge)
                        
                        v_securite = vitesse_obstacle + math.sqrt(2 * 2.0 * dist_utile)
                        vitesse_cible = min(cible, v_securite)

                        erreur_v = vitesse_cible - entite.vitesse

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
                            
                        if distance_arret <= 0.5 and vitesse_obstacle < 0.1:
                            entite.commande_acceleration = -5.0
                            entite.freinage_mecanique = True
                            entite.vitesse = 0.0
                    else:
                        entite.freinage_mecanique = False
                        if entite.vitesse < cible:
                            entite.commande_acceleration = 2.5
                        else:
                            entite.commande_acceleration = 0.0

                    # --- TRAJECTOIRES VECTORIELLES & BRAQUAGE ---
                    # Lisser le cap vers cap_cible
                    erreur_cap = entite.cap_cible - entite.cap
                    while erreur_cap > math.pi: erreur_cap -= 2*math.pi
                    while erreur_cap < -math.pi: erreur_cap += 2*math.pi
                    entite.cap += erreur_cap * min(1.0, 3.0 * dt)

                    # Ajuster la position transversale avec un braquage simulé
                    if est_axe_x:
                        erreur_y = entite.voie_cible_y - entite.pos_y
                        entite.pos_y += erreur_y * min(1.0, 1.5 * dt)
                    else:
                        erreur_x = entite.voie_cible_x - entite.pos_x
                        entite.pos_x += erreur_x * min(1.0, 1.5 * dt)

                # --- INTEGRATION D'EULER FINALE ---
                for entite in self.entites:
                    if entite.type_entite != TypeVehicule.PIETON:
                        force_moteur = entite.commande_acceleration * entite.masse_kg
                        force_aero = entite.get_force_aerodynamique(self.densite_air_rho) if hasattr(entite, 'get_force_aerodynamique') else 0.0
                        
                        crr = 0.015 
                        friction_mecanique = crr * entite.masse_kg * 9.81 if entite.vitesse > 0.1 else 0.0
                        
                        acceleration_nette = (force_moteur - force_aero - friction_mecanique) / entite.masse_kg
                        
                        entite.vitesse += acceleration_nette * dt
                        if entite.vitesse < 0.0: entite.vitesse = 0.0 
                    
                    entite.pos_x += entite.vitesse * math.cos(entite.cap) * dt
                    entite.pos_y += entite.vitesse * math.sin(entite.cap) * dt
                    
                now = time.time()
                if self.network_client and now - self.last_metrics_time > 1.0:
                    self.last_metrics_time = now
                    nb = len(self.entites)
                    s = sum(e.vitesse_kmh for e in self.entites)
                    avg = s / nb if nb > 0 else 0.0
                    self.network_client.send_metrics(nb, avg)
                    
            except Exception as e:
                print(f"[MoteurSimulation] Erreur physique: {e}")
                
            self.tick_simulation.emit(self.entites, self.intersection)
            self.msleep(16)
