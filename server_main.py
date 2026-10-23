"""Point d'entrée principal du serveur de carrefour intelligent Esk-2718.

Ce script lance le nœud serveur (ServerNode) qui orchestre la régulation des feux,
le multiplexage des connexions TCP/UDP, et l'enregistrement des métriques en BDD.
Il prend en charge la surcharge des paramètres réseau en ligne de commande (CLI),
la capture des crashs fatals et un tableau de bord console structuré.
"""

import sys
import json
import os
import time
import logging
import threading

# Assurer la résolution des imports internes quel que soit le répertoire d'appel
repertoire_src = os.path.abspath(os.path.dirname(__file__))
if repertoire_src not in sys.path:
    sys.path.insert(0, repertoire_src)

# Configuration globale de la journalisation avec format horodaté
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("server_main")

# Gestion des imports tolérante à l'emplacement d'exécution (racine ou src/)
try:
    from network.server_node import ServerNode
except ImportError:
    from src.network.server_node import ServerNode


def global_exception_hook(exctype, value, tb):
    """Intercepteur global d'exceptions non gérées pour capturer les crashs fatals.

    Args:
        exctype (type): Type de l'exception levée.
        value (BaseException): Instance de l'exception levée.
        tb (TracebackType): Traceback associé à l'exception.
    """
    logger.critical(
        f"[Serveur] Crash fatal non intercepté : {value}",
        exc_info=(exctype, value, tb)
    )
    # Écriture de sécurité dans un fichier de log de crash
    try:
        with open("server_fatal_crash.log", "a", encoding="utf-8") as f_crash:
            f_crash.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {exctype.__name__}: {value}\n")
    except Exception:
        pass


# Enregistrement du hook global d'exception
sys.excepthook = global_exception_hook


def parse_arguments(argv: list) -> dict:
    """Analyse les arguments passés en ligne de commande via sys.argv sans argparse.

    Arguments reconnus :
        --ip <ip> ou --ip=<ip> : Adresse IP d'écoute.
        --tcp-port <port>, --tcp-port=<port>, --tcp_port : Port d'écoute TCP.
        --udp-port <port>, --udp-port=<port>, --udp_port : Port d'écoute UDP.
        -h ou --help : Affiche l'aide et quitte.

    Args:
        argv (list): Liste des arguments reçus (généralement sys.argv[1:]).

    Returns:
        dict: Dictionnaire contenant les paramètres extraits de la ligne de commande.
    """
    cli_params = {}
    idx = 0
    total = len(argv)

    try:
        while idx < total:
            arg = argv[idx]

            if arg in ("-h", "--help"):
                print("Usage: python server_main.py [--ip <IP>] [--tcp-port <PORT>] [--udp-port <PORT>]")
                print("  --ip        Adresse IP d'écoute (ex: 127.0.0.1 ou 0.0.0.0)")
                print("  --tcp-port  Port TCP pour les connexions fiables (ex: 5000)")
                print("  --udp-port  Port UDP pour les alertes d'urgence VTA (ex: 5001)")
                sys.exit(0)

            elif arg.startswith("--ip="):
                cli_params["server_ip"] = arg.split("=", 1)[1]
            elif arg == "--ip" and idx + 1 < total:
                idx += 1
                cli_params["server_ip"] = argv[idx]

            elif arg.startswith("--tcp-port=") or arg.startswith("--tcp_port="):
                try:
                    cli_params["server_tcp_port"] = int(arg.split("=", 1)[1])
                except ValueError:
                    logger.warning(f"[Serveur] Port TCP invalide spécifié dans {arg}")
            elif arg in ("--tcp-port", "--tcp_port") and idx + 1 < total:
                idx += 1
                try:
                    cli_params["server_tcp_port"] = int(argv[idx])
                except ValueError:
                    logger.warning(f"[Serveur] Port TCP invalide : {argv[idx]}")

            elif arg.startswith("--udp-port=") or arg.startswith("--udp_port="):
                try:
                    cli_params["server_udp_port"] = int(arg.split("=", 1)[1])
                except ValueError:
                    logger.warning(f"[Serveur] Port UDP invalide spécifié dans {arg}")
            elif arg in ("--udp-port", "--udp_port") and idx + 1 < total:
                idx += 1
                try:
                    cli_params["server_udp_port"] = int(argv[idx])
                except ValueError:
                    logger.warning(f"[Serveur] Port UDP invalide : {argv[idx]}")

            else:
                logger.debug(f"[Serveur] Argument non reconnu ou ignoré : {arg}")

            idx += 1

    except Exception as e:
        logger.error(f"[Serveur] Erreur lors de l'analyse des arguments CLI : {e}", exc_info=True)

    return cli_params


def load_configuration(cli_args: dict) -> dict:
    """Charge la configuration depuis config.json et applique les surcharges CLI.

    Args:
        cli_args (dict): Dictionnaire des paramètres fournis via la CLI.

    Returns:
        dict: Configuration complète résolue pour le serveur.
    """
    chemins_possibles = [
        os.path.join(os.path.dirname(__file__), "..", "config.json"),
        os.path.join(os.getcwd(), "config.json"),
        "config.json"
    ]

    config = {
        "server_ip": "127.0.0.1",
        "server_tcp_port": 5000,
        "server_udp_port": 5001,
        "client_udp_port": 5002
    }

    fichier_trouve = None
    for p in chemins_possibles:
        if os.path.exists(p):
            fichier_trouve = p
            break

    try:
        if fichier_trouve:
            with open(fichier_trouve, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                config.update(loaded)
                logger.info(f"[Serveur] Configuration chargée depuis {os.path.abspath(fichier_trouve)}")
        else:
            logger.warning("[Serveur] config.json introuvable. Valeurs par défaut utilisées.")
    except Exception as e:
        logger.error(
            f"[Serveur] Erreur lors de la lecture de config.json : {e}. Valeurs par défaut conservées.",
            exc_info=True
        )

    # Application des surcharges CLI (prioritaires sur le fichier)
    for k, v in cli_args.items():
        config[k] = v
        logger.info(f"[Serveur] Surcharge CLI appliquée : {k} = {v}")

    return config


def afficher_tableau_bord(server: ServerNode):
    """Affiche un tableau de bord console structuré sur l'état du carrefour.

    Args:
        server (ServerNode): Instance active du serveur de simulation.
    """
    try:
        statut = server.get_status()
        clients = statut.get("clients", [])
        nb_clients = statut.get("clients_count", 0)
        feu_ns = statut.get("feu_ns", "INCONNU")
        feu_eo = statut.get("feu_eo", "INCONNU")
        metrics_cnt = statut.get("metrics_count", 0)
        alerts_cnt = statut.get("alerts_count", 0)
        last_alert = statut.get("last_alert")

        lignes_clients = []
        if nb_clients == 0:
            lignes_clients.append("      (Aucun client connecté)")
        else:
            for c in clients:
                lignes_clients.append(
                    f"      - ID: {c.get('id')} | IP: {c.get('addr')} | Connecté depuis {c.get('connected_duration')}s"
                )

        dernier_vta_str = "Aucune"
        if last_alert:
            pos = last_alert.get("position", [0.0, 0.0])
            dernier_vta_str = (
                f"{last_alert.get('type')} sur axe_x={last_alert.get('axe_x')} "
                f"(pos: [{pos[0]:.1f}, {pos[1]:.1f}], urgence: {last_alert.get('urgence')})"
            )

        bordure = "=" * 68
        print(f"\n{bordure}")
        print("  [ESK-2718] SUPERVISION DU CARREFOUR INTELLIGENT (V2X / V2I)")
        print("-" * 68)
        print(f"  Écoute Réseau       : TCP {server.tcp_ip}:{server.tcp_port} | UDP :{server.udp_port}")
        print(f"  État des Feux       : Nord-Sud = [{feu_ns}] | Est-Ouest = [{feu_eo}]")
        print(f"  Clients Connectés   : {nb_clients}")
        for lc in lignes_clients:
            print(lc)
        print(f"  Métriques BDD       : {metrics_cnt} trames enregistrées")
        print(f"  Alertes VTA Reçues  : {alerts_cnt} | Dernière alerte: {dernier_vta_str}")
        print(f"{bordure}\n")

    except Exception as e:
        logger.error(f"[Serveur] Erreur lors de l'affichage du tableau de bord : {e}", exc_info=True)


def supervision_loop(server: ServerNode, stop_event: threading.Event):
    """Boucle d'affichage périodique de supervision en arrière-plan.

    Args:
        server (ServerNode): Instance du serveur.
        stop_event (threading.Event): Signal d'arrêt de la supervision.
    """
    logger.debug("[Serveur] Démarrage du moniteur de supervision console.")
    while not stop_event.is_set():
        try:
            time.sleep(5.0)
            if stop_event.is_set() or not server.running:
                break
            afficher_tableau_bord(server)
        except Exception as e:
            logger.error(f"[Serveur] Erreur dans la boucle de supervision : {e}", exc_info=True)


def main():
    """Fonction principale orchestrant le démarrage et le cycle de vie du serveur."""
    logger.info("=== Démarrage de l'Application Serveur Esk-2718 ===")

    # 1. Analyse des arguments de la ligne de commande (sans argparse)
    cli_params = parse_arguments(sys.argv[1:])

    # 2. Chargement de la configuration avec fallback sur config.json
    config = load_configuration(cli_params)

    # 3. Initialisation du nœud serveur
    try:
        server = ServerNode(config)
        server.start()
        logger.info("[Serveur] Nœud réseau démarré et en écoute.")
    except Exception as start_err:
        logger.error(f"[Serveur] Échec critique lors du lancement du serveur : {start_err}", exc_info=True)
        return 1

    # 4. Affichage initial du tableau de bord
    afficher_tableau_bord(server)

    # 5. Démarrage du thread de supervision périodique
    stop_supervision = threading.Event()
    moniteur = threading.Thread(
        target=supervision_loop,
        args=(server, stop_supervision),
        name="Thread-Supervision",
        daemon=True
    )
    moniteur.start()

    # 6. Attente d'arrêt (Ctrl+C ou Entrée)
    print("\n[Serveur] Le carrefour est actif. Appuyez sur [Entrée] ou [Ctrl+C] pour arrêter.")
    try:
        if sys.stdin and not sys.stdin.closed:
            try:
                line = sys.stdin.readline()
                if line == "":
                    # Fin de flux (ex: redirection depuis /dev/null ou démon d'arrière-plan)
                    logger.info("[Serveur] Mode arrière-plan : attente de signal d'interruption.")
                    while server.running and server.is_alive():
                        time.sleep(1.0)
                else:
                    logger.info("[Serveur] Signal d'arrêt reçu via l'entrée standard.")
            except (EOFError, KeyboardInterrupt):
                print("\n[Serveur] Interruption reçue.")
        else:
            while server.running and server.is_alive():
                time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[Serveur] Signal KeyboardInterrupt intercepté.")
    except Exception as e:
        logger.error(f"[Serveur] Erreur lors de l'attente principale : {e}", exc_info=True)

    # 7. Procédure de clôture propre
    print("[Serveur] Clôture des services réseau en cours...")
    stop_supervision.set()

    try:
        server.stop()
        server.join(timeout=3.0)
        logger.info("[Serveur] Serveur arrêté avec succès. Ressources libérées.")
        print("[Serveur] Arrêt propre terminé.")
    except Exception as stop_err:
        logger.error(f"[Serveur] Erreur lors de l'arrêt du serveur : {stop_err}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    try:
        code_retour = main()
        sys.exit(code_retour)
    except Exception as fatal_e:
        logger.critical(f"[Serveur] Crash fatal au niveau principal : {fatal_e}", exc_info=True)
        sys.exit(1)
