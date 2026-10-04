import logging
logger = logging.getLogger(__name__)

import sys
import json
import os
from network.server_node import ServerNode

def main():
    """Fonction d'entrée principale du programme."""
    """
    Fonction principale du serveur.
    Elle charge la configuration depuis un fichier JSON,
    initialise le ServerNode et gère l'arrêt propre via une interruption.
    """
    # Chemin vers le fichier de configuration (remonte d'un dossier depuis 'src')
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.json")
    try:
        # Tentative de lecture et de chargement du fichier JSON
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as parse_error:
        # En cas d'erreur (fichier inexistant ou JSON invalide), on utilise une configuration par défaut
        print(f"[Serveur] Fichier de configuration non trouvé ou invalide : {parse_error}. Utilisation des valeurs par défaut.")
        config = {
            "server_ip": "127.0.0.1",
            "server_tcp_port": 5000,
            "server_udp_port": 5001
        }
        
    try:
        # Initialisation du nœud serveur avec la configuration récupérée
        server = ServerNode(config)
        # Démarrage du serveur (threads d'écoute TCP/UDP)
        server.start()
    except Exception as e:
        # Capture de toute erreur critique lors du démarrage (ex: port déjà utilisé)
        logger.error(f"[Serveur] Erreur fatale lors du démarrage du serveur: {e}", exc_info=True)
        return
        
    print("[Serveur] Le serveur est en cours d'exécution. Appuyez sur Entrée pour l'arrêter.")
    try:
        # On attend une action de l'utilisateur pour maintenir le script principal actif
        input()
    except KeyboardInterrupt:
        # Si l'utilisateur effectue un Ctrl+C, on l'intercepte proprement
        print("\n[Serveur] Interruption clavier détectée.")
    except Exception as e:
        # Autres erreurs inattendues lors de l'attente
        logger.error(f"[Serveur] Erreur inattendue : {e}", exc_info=True)
        
    try:
        # Arrêt des services du serveur (fermeture des sockets, etc.)
        server.stop()
        # On attend la fin effective des threads internes du serveur
        server.join()
        print("[Serveur] Serveur arrêté avec succès.")
    except Exception as stop_error:
        # Si l'arrêt échoue pour une raison quelconque
        logger.error(f"[Serveur] Erreur lors de l'arrêt du serveur : {stop_error}", exc_info=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as fatal:
        logger.error(f"[Serveur] Crash critique de l'application serveur : {fatal}", exc_info=True)

