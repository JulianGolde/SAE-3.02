import os
import re

TARGET_FILES = [
    "client_main.py",
    "gui/carrefour_scene.py",
    "gui/dashboard.py",
    "simulation/vehicules.py",
    "simulation/intersection.py",
    "simulation/environnement.py",
    "network/client_node.py",
    "network/server_node.py",
    "server_main.py",
    "database/db_manager.py"
]

DOC_MAP = {
    "MainWindow": '"""Fenêtre principale de l\'application cliente gérant l\'interface utilisateur et la simulation."""',
    "__init__": '"""Initialise l\'objet avec les paramètres requis.\n\nArgs:\n    *args: Arguments divers.\n    **kwargs: Paramètres nommés.\n"""',
    "set_type_a_placer": '"""Définit le type de véhicule à placer sur la scène.\n\nArgs:\n    t (TypeVehicule): Type de véhicule à placer.\n"""',
    "keyPressEvent": '"""Gère les événements de pression de touche au clavier.\n\nArgs:\n    event (QKeyEvent): L\'événement clavier.\n"""',
    "closeEvent": '"""Gère la fermeture de l\'application de manière propre.\n\nArgs:\n    event (QCloseEvent): L\'événement de fermeture.\n"""',
    "rafraichir_interface": '"""Met à jour l\'interface graphique à chaque cycle du moteur.\n\nArgs:\n    entites (list): Liste des entités actives.\n    inter (Intersection): État actuel de l\'intersection.\n"""',
    "change_vitesse": '"""Modifie la vitesse d\'exécution de la simulation.\n\nArgs:\n    val (int): Nouvelle valeur de multiplicateur.\n"""',
    "change_meteo": '"""Change les conditions météorologiques actuelles.\n\nArgs:\n    etat (str): Nouvel état météo.\n"""',
    "toggle_simulation": '"""Bascule l\'état de la simulation (pause/lecture)."""',
    "selectionner_entite": '"""Sélectionne une entité spécifique dans la simulation.\n\nArgs:\n    entite_id (str): Identifiant de l\'entité.\n"""',
    "spawn_clic": '"""Gère le clic sur la scène pour placer une entité.\n\nArgs:\n    x (float): Coordonnée X.\n    y (float): Coordonnée Y.\n"""',
    "prevoir_virage": '"""Programme un virage pour l\'entité sélectionnée.\n\nArgs:\n    angle (float): Angle du virage en radians.\n"""',
    "charger_scenario": '"""Charge un scénario de simulation depuis un fichier."""',
    "CarrefourScene": '"""Scène graphique gérant le rendu du carrefour et des véhicules."""',
    "set_meteo": '"""Applique un effet météorologique à la scène.\n\nArgs:\n    etat (str): L\'état de la météo (ex: Pluie, Tempête).\n"""',
    "_draw_infrastructure": '"""Dessine l\'infrastructure routière sur la scène."""',
    "_obtenir_couleur_qt": '"""Récupère la couleur Qt associée à un type de véhicule.\n\nArgs:\n    type_v (TypeVehicule): Le type de véhicule.\n\nReturns:\n    QColor: La couleur correspondante.\n"""',
    "mettre_a_jour_entites": '"""Actualise les positions de toutes les entités visuelles.\n\nArgs:\n    entites (list): Entités physiques.\n    inter (IntersectionManager): Gestionnaire de feux.\n"""',
    "mouseMoveEvent": '"""Gère le survol de la souris sur la scène.\n\nArgs:\n    event (QGraphicsSceneMouseEvent): L\'événement souris.\n"""',
    "mousePressEvent": '"""Gère le clic de la souris sur la scène.\n\nArgs:\n    event (QGraphicsSceneMouseEvent): L\'événement souris.\n"""',
    "DashboardPanel": '"""Panneau latéral contenant les contrôles de la simulation."""',
    "TypeVehicule": '"""Énumération des différents types de véhicules."""',
    "EntitePhysique": '"""Représente une entité physique de base (position, vitesse)."""',
    "Vehicule": '"""Représente un véhicule physique avec une dynamique propre."""',
    "id_entite": '"""Identifiant unique de l\'entité.\n\nReturns:\n    str: L\'identifiant.\n"""',
    "type_entite": '"""Type du véhicule.\n\nReturns:\n    TypeVehicule: Le type.\n"""',
    "masse_kg": '"""Masse du véhicule en kg.\n\nReturns:\n    float: La masse.\n"""',
    "pos_x": '"""Position X du véhicule.\n\nReturns:\n    float: La position.\n"""',
    "pos_y": '"""Position Y du véhicule.\n\nReturns:\n    float: La position.\n"""',
    "vitesse": '"""Vitesse actuelle en m/s.\n\nReturns:\n    float: La vitesse.\n"""',
    "cap": '"""Cap (orientation) actuel en radians.\n\nReturns:\n    float: Le cap.\n"""',
    "cap_cible": '"""Cap ciblé pour le véhicule.\n\nReturns:\n    float: Le cap cible.\n"""',
    "voie_cible_y": '"""Cible Y de la voie.\n\nReturns:\n    float: La coordonnée.\n"""',
    "voie_cible_x": '"""Cible X de la voie.\n\nReturns:\n    float: La coordonnée.\n"""',
    "est_axe_x": '"""Vérifie si le véhicule se déplace sur l\'axe X.\n\nReturns:\n    bool: Vrai si axe X.\n"""',
    "commande_acceleration": '"""Commande d\'accélération appliquée.\n\nReturns:\n    float: L\'accélération.\n"""',
    "commande_braquage": '"""Commande de braquage appliquée.\n\nReturns:\n    float: L\'angle de braquage.\n"""',
    "freinage_mecanique": '"""Indique si le freinage mécanique est actif.\n\nReturns:\n    bool: L\'état du frein.\n"""',
    "action_intersection": '"""Action prévue à l\'intersection (virage).\n\nReturns:\n    float: L\'angle d\'action.\n"""',
    "etat_depassement": '"""État d\'un dépassement éventuel.\n\nReturns:\n    int: L\'état du dépassement.\n"""',
    "longueur_m": '"""Longueur du véhicule en mètres.\n\nReturns:\n    float: La longueur.\n"""',
    "largeur_m": '"""Largeur du véhicule en mètres.\n\nReturns:\n    float: La largeur.\n"""',
    "cx": '"""Coefficient de traînée aérodynamique.\n\nReturns:\n    float: Le Cx.\n"""',
    "surface_frontale_m2": '"""Surface frontale du véhicule.\n\nReturns:\n    float: La surface.\n"""',
    "vitesse_kmh": '"""Vitesse du véhicule en km/h.\n\nReturns:\n    float: La vitesse en km/h.\n"""',
    "possede_abs": '"""Indique si le véhicule a l\'ABS.\n\nReturns:\n    bool: Vrai si ABS présent.\n"""',
    "age_pneus": '"""Âge des pneus en années.\n\nReturns:\n    float: L\'âge.\n"""',
    "usure_pneus": '"""Usure des pneus (0 à 1).\n\nReturns:\n    float: Le niveau d\'usure.\n"""',
    "get_force_aerodynamique": '"""Calcule la force aérodynamique s\'appliquant au véhicule.\n\nArgs:\n    rho (float): Densité de l\'air.\n\nReturns:\n    float: La force en Newtons.\n"""',
    "CouleurFeu": '"""Énumération des couleurs de feux de signalisation."""',
    "IntersectionManager": '"""Gestionnaire de l\'intersection et des feux tricolores."""',
    "feu_ns": '"""Obtient la couleur du feu Nord-Sud.\n\nReturns:\n    CouleurFeu: La couleur.\n"""',
    "feu_eo": '"""Obtient la couleur du feu Est-Ouest.\n\nReturns:\n    CouleurFeu: La couleur.\n"""',
    "update": '"""Met à jour l\'état des feux selon le temps écoulé.\n\nArgs:\n    dt (float): Différentiel de temps.\n"""',
    "_appliquer_etat": '"""Applique l\'état interne courant aux feux."""',
    "forcer_vert_ns": '"""Force les feux Nord-Sud au vert."""',
    "forcer_vert_eo": '"""Force les feux Est-Ouest au vert."""',
    "forcer_passage_vta": '"""Adapte les feux pour le passage d\'un véhicule d\'urgence.\n\nArgs:\n    voie (str): Voie du véhicule.\n"""',
    "annuler_urgence": '"""Rétablit le fonctionnement normal des feux."""',
    "get_couleur_pour_voie": '"""Obtient la couleur du feu pour une voie donnée.\n\nArgs:\n    axe_x (bool): Vrai si voie Est-Ouest.\n\nReturns:\n    CouleurFeu: La couleur.\n"""',
    "set_state": '"""Définit manuellement les couleurs des feux.\n\nArgs:\n    ns (CouleurFeu): Feu Nord-Sud.\n    eo (CouleurFeu): Feu Est-Ouest.\n"""',
    "ConditionsMeteo": '"""Énumération des conditions météorologiques."""',
    "Environnement": '"""Classe gérant l\'environnement (météo, température, route)."""',
    "temperature": '"""Température ambiante.\n\nReturns:\n    float: Température.\n"""',
    "usure_route": '"""Niveau d\'usure de la route.\n\nReturns:\n    float: Usure.\n"""',
    "hauteur_eau_mm": '"""Hauteur d\'eau sur la route.\n\nReturns:\n    float: Hauteur en mm.\n"""',
    "meteo": '"""Conditions météorologiques actuelles.\n\nReturns:\n    ConditionsMeteo: Météo.\n"""',
    "calculer_coefficient_friction": '"""Calcule le coefficient de friction selon la météo et la route.\n\nReturns:\n    float: Coefficient de friction.\n"""',
    "ClientNode": '"""Nœud client pour la communication réseau."""',
    "connect": '"""Établit la connexion avec le serveur.\n\nReturns:\n    bool: Vrai si succès.\n"""',
    "run": '"""Boucle principale du client réseau."""',
    "_handle_msg": '"""Traite un message reçu du serveur.\n\nArgs:\n    msg (dict): Le message.\n"""',
    "send_vta_alert": '"""Envoie une alerte de véhicule d\'urgence.\n\nArgs:\n    voie (str): La voie.\n"""',
    "send_vta_end": '"""Signale la fin de l\'alerte d\'urgence."""',
    "send_metrics": '"""Envoie les métriques au serveur.\n\nArgs:\n    count (int): Nombre de véhicules.\n    speed (float): Vitesse moyenne.\n"""',
    "stop": '"""Arrête le client réseau."""',
    "ServerNode": '"""Nœud serveur gérant les connexions TCP et UDP."""',
    "_remove_client": '"""Retire un client déconnecté.\n\nArgs:\n    addr: Adresse du client.\n"""',
    "_handle_udp": '"""Gère les messages entrants en UDP."""',
    "_handle_tcp": '"""Gère les connexions TCP entrantes."""',
    "_send_state": '"""Envoie l\'état de la simulation à un client.\n\nArgs:\n    addr: Adresse du client.\n    state: L\'état à envoyer.\n"""',
    "broadcast_state": '"""Diffuse l\'état à tous les clients.\n\nArgs:\n    state: L\'état de la simulation.\n"""',
    "main": '"""Fonction d\'entrée principale du programme."""',
    "DBManager": '"""Gestionnaire de la base de données de métriques."""',
    "_init_db": '"""Initialise les tables de la base de données."""',
    "insert_metric": '"""Insère une métrique dans la base.\n\nArgs:\n    count (int): Nombre de véhicules.\n    speed (float): Vitesse moyenne.\n"""'
}

def fix_file(filepath):
    path = os.path.join(r"c:\Users\lazer\Nextcloud\cours réseau\Semestre 3\SAE\SAE 3.02- Développer une application communicante\src", filepath)
    if not os.path.exists(path):
        return
        
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Regex to match the bad class docstring exactly (accounting for varying whitespace)
    bad_class_doc = r'(\s*)"""\s*Classe responsable de l\'implémentation de la logique métier\.\s*"""'
    content = re.sub(bad_class_doc, "", content)
    
    # Regex to match the bad func docstring exactly
    bad_func_doc = r'(\s*)"""\s*Exécute l\'action demandée\.\s*Args:\s*\*args: Arguments positionnels\.\s*\*\*kwargs: Arguments nommés\.\s*Returns:\s*Résultat de l\'exécution ou None\.\s*"""'
    content = re.sub(bad_func_doc, "", content)
    
    # Now that bad docstrings are removed, let's parse with ast and inject new ones!
    # Wait, ast unparsing drops comments. Let's do it with regex.
    # We find `class X(...)` or `def X(...)` and insert the docstring on the next line.
    
    lines = content.split('\n')
    new_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        new_lines.append(line)
        
        # Match class or def
        m_class = re.match(r'^(\s*)class\s+([a-zA-Z0-9_]+)', line)
        m_def = re.match(r'^(\s*)def\s+([a-zA-Z0-9_]+)', line)
        
        if m_class or m_def:
            name = m_class.group(2) if m_class else m_def.group(2)
            indent = m_class.group(1) if m_class else m_def.group(1)
            
            # Need to skip until the definition ends (e.g., closing parenthesis and colon)
            # This is simple: just wait for a line ending with `:`
            while not lines[i].rstrip().endswith(':'):
                i += 1
                new_lines.append(lines[i])
                line = lines[i]
                
            # Now insert docstring
            if name in DOC_MAP:
                doc = DOC_MAP[name]
                doc_lines = doc.split("\n")
                for d in doc_lines:
                    new_lines.append(f"{indent}    {d}")
                    
        i += 1
        
    # Extra fix for client_main.py: full screen and logging.basicConfig
    if filepath == "client_main.py":
        out_content = "\n".join(new_lines)
        
        # Fix fullscreen
        out_content = out_content.replace("w.setWindowState(Qt.WindowState.WindowFullScreen)\n    # Affiche formellement la fenêtre graphique à l'écran\n    w.showFullScreen()\n    w.setWindowState(Qt.WindowState.WindowFullScreen)", 
        "w.showFullScreen()\n    w.setWindowState(Qt.WindowState.WindowFullScreen)")
        
        # Fix basic config
        if "logging.basicConfig" not in out_content:
            out_content = out_content.replace(
                "if __name__ == \"__main__\":\n",
                "if __name__ == \"__main__\":\n    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')\n"
            )
        new_lines = out_content.split("\n")
        
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines))

for f in TARGET_FILES:
    fix_file(f)
print("Done")
