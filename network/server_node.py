"""Module de communication réseau côté serveur pour la simulation de carrefour.

Ce module implémente le nœud serveur (ServerNode) qui multiplexe les connexions
TCP des clients pour la synchronisation d'état et la collecte de métriques, tout en
écoutant les alertes de véhicules prioritaires (VTA) via UDP.
"""

import socket
import select
import struct
import json
import threading
import queue
import logging
import time
import os
import sys

logger = logging.getLogger(__name__)

try:
    from database.db_manager import DBManager
    from simulation.intersection import IntersectionManager, CouleurFeu
except ImportError:
    from src.database.db_manager import DBManager
    from src.simulation.intersection import IntersectionManager, CouleurFeu

FRAME_TYPE_TO_CODE = {
    "connect": 1,
    "state": 2,
    "metrics": 3,
    "vta_alert": 4,
    "vta_end": 5,
    "ack": 6,
    "scenario": 7,
    "disconnect": 8,
}
CODE_TO_FRAME_TYPE = {v: k for k, v in FRAME_TYPE_TO_CODE.items()}


def code_pour_type_trame(frame_type: str) -> int:
    """Retourne le code numérique 1 octet associé à un type de trame."""
    return FRAME_TYPE_TO_CODE.get(str(frame_type).lower(), 0)


def type_trame_pour_code(code: int) -> str:
    """Retourne le libellé textuel associé à un code type de trame binaire."""
    return CODE_TO_FRAME_TYPE.get(code, "inconnu")


def packager_entete_binaire(frame_type_code: int, seq: int, payload_bytes: bytes) -> bytes:
    """Génère l'en-tête binaire standardisé Esk-2718 avec le module struct.

    Format '!4sBII' (13 octets) :
      - 4s : Magic 'ESK2' (4 octets)
      - B  : Code type trame (uint8, 1 octet)
      - I  : Numéro de séquence (uint32, 4 octets)
      - I  : Longueur du payload (uint32, 4 octets)

    Args:
        frame_type_code (int): Code numérique du type de message.
        seq (int): Numéro de séquence séquentiel.
        payload_bytes (bytes): Données utiles de la trame.

    Returns:
        bytes: En-tête binaire de 13 octets.
    """
    return struct.pack("!4sBII", b"ESK2", int(frame_type_code), int(seq), len(payload_bytes))


def depackager_entete_binaire(entete_bytes: bytes) -> tuple[bytes, int, int, int]:
    """Décapsule l'en-tête binaire standardisé Esk-2718 avec struct.unpack.

    Args:
        entete_bytes (bytes): Au moins 13 octets représentant l'en-tête binaire.

    Returns:
        tuple[bytes, int, int, int]: (magic, code_type, seq, payload_len).
    """
    if len(entete_bytes) < 13:
        raise ValueError(f"En-tête binaire incomplet ({len(entete_bytes)} octets au lieu de 13)")
    magic, code_type, seq, payload_len = struct.unpack("!4sBII", entete_bytes[:13])
    if magic != b"ESK2":
        raise ValueError(f"Magic invalide: {magic} (attendu b'ESK2')")
    return magic, code_type, seq, payload_len


dépackager_entete_binaire = depackager_entete_binaire


class ServerNode(threading.Thread):
    """Nœud serveur réseau gérant les communications TCP et UDP du carrefour.

    Cette classe hérite de threading.Thread et assure le multiplexage non bloquant
    via select.select() pour gérer simultanément plusieurs clients de simulation,
    la diffusion de l'état des feux tricolores, l'enregistrement des métriques en
    base de données SQLite et la prise en compte en temps réel des alertes VTA.

    Attributes:
        config (dict): Paramètres de configuration réseau et serveur.
        db (DBManager): Gestionnaire de la base de données locale SQLite.
        intersection (IntersectionManager): Gestionnaire de la logique des feux.
        tcp_ip (str): Adresse IP d'écoute pour les sockets.
        tcp_port (int): Port d'écoute pour les connexions TCP fiables.
        udp_port (int): Port d'écoute pour les paquets UDP temps réel.
        clients (list[socket.socket]): Liste des sockets clients TCP actifs.
        client_buffers (dict[socket.socket, bytearray]): Buffers d'octets de réception par socket client.
        client_metadata (dict[socket.socket, dict]): Métadonnées associées à chaque client.
        running (bool): Indicateur d'exécution du thread d'écoute réseau.
    """

    def __init__(self, config=None, db=None, intersection=None):
        """Initialise le nœud serveur et configure les sockets réseau.

        Args:
            config (dict, optional): Dictionnaire contenant les adresses et ports.
                Par défaut None (utilise les valeurs par défaut).
            db (DBManager, optional): Instance existante de DBManager.
            intersection (IntersectionManager, optional): Instance de IntersectionManager.
        """
        super().__init__(name="Thread-ServerNode")
        self.config = config if config is not None else {}
        self.db = db if db is not None else DBManager()
        self.intersection = intersection if intersection is not None else IntersectionManager()

        # Session de simulation pour la persistance SQLite
        self.simulation_id = None
        self.start_time = time.time()
        try:
            self.simulation_id = self.db.creer_simulation("Serveur_V2X_Supervision")
            logger.info(f"[ServerNode] Session de simulation BDD initialisée : ID={self.simulation_id}")
        except Exception as e_sim:
            logger.warning(f"[ServerNode] Impossible d'initialiser une session en BDD : {e_sim}")

        # Configuration stricte des adresses et ports sans écrasement implicite
        self.tcp_ip = str(self.config.get("server_ip", "127.0.0.1"))
        self.tcp_port = int(self.config.get("server_tcp_port", 5000))
        self.udp_port = int(self.config.get("server_udp_port", 5001))

        # Initialisation du compteur de séquence thread-safe
        self._seq_counter = 0
        self._seq_lock = threading.Lock()

        # Verrous pour synchronisation interne
        self._clients_lock = threading.Lock()
        self._stats_lock = threading.Lock()

        # Structures de suivi des clients connectés (buffers en bytearray pour l'intégrité UTF-8)
        self.clients = []
        self.client_buffers = {}
        self.client_metadata = {}

        # Statistiques et états pour la supervision
        self.running = False
        self.last_state = None
        self.metrics_count = 0
        self.alerts_count = 0
        self.last_alert_info = None

        # Sockets principales
        self.tcp_sock = None
        self.udp_sock = None

        # Création et configuration des sockets
        self._initialiser_sockets()

    def _initialiser_sockets(self):
        """Crée, lie et configure les sockets TCP et UDP en mode non-bloquant.

        Raises:
            OSError: En cas d'impossibilité de lier les sockets aux ports spécifiés.
        """
        try:
            # Socket TCP pour les flux fiables (connexion, état, métriques)
            self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp_sock.bind((self.tcp_ip, self.tcp_port))
            self.tcp_sock.listen(10)
            self.tcp_sock.setblocking(False)

            # Socket UDP pour les flux à faible latence (alertes VTA)
            self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                self.udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except (AttributeError, OSError):
                pass
            self.udp_sock.bind((self.tcp_ip, self.udp_port))
            self.udp_sock.setblocking(False)

            logger.info(
                f"[ServerNode] Sockets initialisées : TCP {self.tcp_ip}:{self.tcp_port}, "
                f"UDP {self.tcp_ip}:{self.udp_port}"
            )
        except Exception as e:
            logger.error(f"[ServerNode] Échec critique lors de l'initialisation des sockets : {e}", exc_info=True)
            raise

    def _next_seq(self) -> int:
        """Génère un numéro de séquence strictement croissant et thread-safe.

        Returns:
            int: Prochain numéro de séquence de trame.
        """
        with self._seq_lock:
            self._seq_counter += 1
            return self._seq_counter

    def _build_frame(self, frame_type: str, payload: dict) -> dict:
        """Construit une trame structurée conforme au protocole Esk-2718.

        Format généré :
            {"type": "...", "seq": int, "timestamp": float, "payload": {...}}

        Args:
            frame_type (str): Type de la trame ('state', 'ack', etc.).
            payload (dict): Données métier associées au message.

        Returns:
            dict: Trame complète prête pour la sérialisation JSON.
        """
        return {
            "type": frame_type,
            "seq": self._next_seq(),
            "timestamp": time.time(),
            "payload": payload if isinstance(payload, dict) else {}
        }

    def _send_raw_tcp(self, sock: socket.socket, raw_bytes: bytes, timeout: float = 1.0) -> bool:
        """Envoie des octets sur une socket TCP de manière non bloquante mais fiable.

        Args:
            sock (socket.socket): Socket destinataire.
            raw_bytes (bytes): Données binaires à expédier.
            timeout (float): Délai maximal d'attente de disponibilité en écriture.

        Returns:
            bool: True si la totalité des données a été envoyée, False sinon.
        """
        total_sent = 0
        taille = len(raw_bytes)
        deadline = time.time() + timeout

        while total_sent < taille:
            try:
                sent = sock.send(raw_bytes[total_sent:])
                if sent == 0:
                    return False
                total_sent += sent
            except (BlockingIOError, InterruptedError):
                temps_restant = max(0.01, deadline - time.time())
                _, writable, _ = select.select([], [sock], [], temps_restant)
                if not writable:
                    return False
            except Exception:
                return False

        return True

    def run(self):
        """Boucle principale du serveur multiplexant les entrées/sorties réseau.

        Exécute la mise à jour continue du cycle de feux du carrefour, le
        multiplexage I/O via select.select(), la gestion des connexions/déconnexions
        et le traitement de l'ensemble des trames entrantes.
        """
        self.running = True
        last_update = time.time()
        logger.info("[ServerNode] Démarrage de la boucle de multiplexage (select) sur le serveur.")

        try:
            while self.running:
                try:
                    # 1. Mise à jour de la logique temporelle du carrefour
                    now = time.time()
                    dt = now - last_update
                    last_update = now

                    try:
                        self.intersection.update(dt)
                    except Exception as e_inter:
                        logger.error(
                            f"[ServerNode] Erreur lors de l'actualisation de l'intersection : {e_inter}",
                            exc_info=True
                        )

                    # 2. Diffusion automatique de l'état des feux en cas de transition
                    current_state = (self.intersection.feu_ns.value, self.intersection.feu_eo.value)
                    if current_state != self.last_state:
                        self.last_state = current_state
                        self.broadcast_state()

                    # 3. Préparation de la liste des sockets pour le multiplexage
                    with self._clients_lock:
                        sockets_to_watch = [self.tcp_sock, self.udp_sock] + list(self.clients)

                    # 4. Surveillance non bloquante via select (timeout court de 50ms)
                    try:
                        readable, _, exceptional = select.select(sockets_to_watch, [], sockets_to_watch, 0.05)
                    except (OSError, ValueError, select.error) as select_err:
                        if not self.running:
                            break
                        logger.warning(
                            f"[ServerNode] Exception select interceptée : {select_err}. Nettoyage des sockets."
                        )
                        self._filter_dead_sockets()
                        continue

                    if not self.running:
                        break

                    # Traitement des sockets en état exceptionnel
                    for err_sock in exceptional:
                        if err_sock not in (self.tcp_sock, self.udp_sock):
                            logger.warning("[ServerNode] État exceptionnel détecté sur une socket client.")
                            self._remove_client(err_sock, reason="état exceptionnel")

                    # 5. Traitement des flux de données prêts à la lecture
                    for sock in readable:
                        if not self.running:
                            break
                        if sock is self.tcp_sock:
                            self._accept_tcp_client()
                        elif sock is self.udp_sock:
                            self._handle_udp_data()
                        else:
                            self._handle_client_data(sock)

                except Exception as loop_err:
                    if self.running:
                        logger.error(
                            f"[ServerNode] Erreur inattendue dans la boucle principale : {loop_err}",
                            exc_info=True
                        )
                        time.sleep(0.01)

        finally:
            # Clôture propre des sockets dans le contexte du thread serveur
            self._fermer_toutes_les_sockets()
            logger.info("[ServerNode] Fin de la boucle d'exécution du serveur.")

    def _filter_dead_sockets(self):
        """Identifie et supprime les sockets fermées ou devenues invalides."""
        with self._clients_lock:
            clients_snapshot = list(self.clients)

        for client in clients_snapshot:
            try:
                fileno = client.fileno()
                if fileno == -1:
                    self._remove_client(client, reason="descripteur invalide (-1)")
            except Exception:
                self._remove_client(client, reason="échec d'interrogation du descripteur")

    def _accept_tcp_client(self):
        """Accepte une nouvelle connexion entrante d'un client TCP."""
        if not self.running:
            return
        try:
            client_sock, client_addr = self.tcp_sock.accept()
            client_sock.setblocking(False)

            with self._clients_lock:
                # Limitation préventive pour respecter les descripteurs sous Windows (FD_SETSIZE 64)
                if len(self.clients) >= 50:
                    logger.warning(f"[ServerNode] Limite de clients atteinte (50). Connexion refusée pour {client_addr}")
                    client_sock.close()
                    return

                self.clients.append(client_sock)
                self.client_buffers[client_sock] = bytearray()
                self.client_metadata[client_sock] = {
                    "addr": client_addr,
                    "connected_at": time.time(),
                    "client_id": "en_attente",
                    "last_seen": time.time()
                }

            logger.info(
                f"[ServerNode][TCP-ACCEPT] Nouveau client connecté depuis {client_addr}. "
                f"Total clients actifs: {len(self.clients)}"
            )

            # Envoi immédiat de l'état actuel des feux au nouveau client
            self._send_state(client_sock)

        except BlockingIOError:
            pass
        except Exception as e:
            if self.running:
                logger.error(f"[ServerNode] Erreur lors de l'acceptation d'un client TCP : {e}", exc_info=True)

    def _handle_udp_data(self):
        """Lit et traite un paquet de données reçu sur la socket UDP."""
        if not self.running:
            return
        try:
            data, addr = self.udp_sock.recvfrom(4096)
            if not data:
                return

            text = data.decode("utf-8", errors="replace").strip()
            if not text:
                return

            try:
                frame = json.loads(text)
            except Exception as json_err:
                logger.warning(f"[ServerNode][UDP-PARSE] Données UDP non JSON reçues de {addr} : {json_err}")
                return

            self._handle_udp_frame(frame, addr)

        except BlockingIOError:
            pass
        except Exception as e:
            if self.running:
                logger.error(f"[ServerNode] Erreur lors de la lecture UDP : {e}", exc_info=True)

    def _handle_udp_frame(self, frame: dict, addr: tuple):
        """Traite une trame structurée reçue par UDP (alertes VTA et acquittements).

        Args:
            frame (dict): Trame désérialisée conforme au protocole.
            addr (tuple): Adresse (ip, port) de l'émetteur du paquet.
        """
        try:
            frame_type = frame.get("type")
            seq = frame.get("seq", 0)
            payload = frame.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}

            logger.info(f"[ServerNode][UDP-RECV] De {addr} | Type: {frame_type} | Seq: {seq}")

            # Inspection et validation de l'empreinte binaire standardisée Esk-2718
            c_code = code_pour_type_trame(str(frame_type))
            if c_code > 0:
                entete_test = packager_entete_binaire(c_code, int(seq), json.dumps(payload).encode("utf-8"))
                _mag, _c, _s, _len = depackager_entete_binaire(entete_test)

            if frame_type == "vta_alert":
                position = payload.get("position", frame.get("position", [0.0, 0.0]))
                if not isinstance(position, (list, tuple)) or len(position) < 2:
                    position = [0.0, 0.0]
                else:
                    position = [float(position[0]), float(position[1])]

                # Détermination intelligente et robuste de l'axe :
                # 1. Utiliser le booléen explicite 'axe_x' s'il est présent dans payload ou frame
                # 2. Sinon, inférer à partir des coordonnées géométriques (|x| >= |y| => Est-Ouest)
                if "axe_x" in payload:
                    axe_x = bool(payload["axe_x"])
                elif "axe_x" in frame:
                    axe_x = bool(frame["axe_x"])
                else:
                    axe_x = abs(position[0]) >= abs(position[1])

                v_type = str(payload.get("type", frame.get("type", "VIG_VTA")))
                try:
                    urgence = int(payload.get("urgence", frame.get("urgence", 1)))
                except (ValueError, TypeError):
                    urgence = 1

                with self._stats_lock:
                    self.alerts_count += 1
                    self.last_alert_info = {
                        "axe_x": axe_x,
                        "position": position,
                        "type": v_type,
                        "urgence": urgence,
                        "timestamp": time.time(),
                        "addr": addr
                    }

                logger.info(
                    f"[ServerNode][VTA-ALERTE] Véhicule prioritaire détecté : {v_type} "
                    f"sur axe_x={axe_x}, position={position}, urgence={urgence}"
                )

                # Forçage immédiat du feu vert pour l'axe d'approche
                self.intersection.forcer_passage_vta(bool(axe_x))

                # Enregistrement de l'alerte prioritaire en BDD
                try:
                    self.db.insert_evenement(
                        self.simulation_id,
                        "ALERTE_VTA",
                        f"VTA {v_type} urgence={urgence} axe_x={axe_x}",
                        position[0],
                        position[1]
                    )
                except Exception as e_db:
                    logger.debug(f"[ServerNode] Erreur enregistrement BDD alerte VTA : {e_db}")

                # Diffusion immédiate de l'état modifié aux clients TCP
                self.broadcast_state()

                # Envoi d'un acquittement rapide (ack) en UDP à l'émetteur
                ack_payload = {
                    "status": "ack",
                    "feu_ns": self.intersection.feu_ns.value,
                    "feu_eo": self.intersection.feu_eo.value,
                    "ref_seq": seq
                }
                ack_frame = self._build_frame("ack", ack_payload)
                raw_ack = json.dumps(ack_frame).encode("utf-8")
                try:
                    self.udp_sock.sendto(raw_ack, addr)
                    logger.debug(f"[ServerNode][UDP-SEND] Acquittement ack envoyé à {addr}")
                except Exception as send_err:
                    logger.error(f"[ServerNode] Erreur d'envoi UDP ack vers {addr} : {send_err}", exc_info=True)

            elif frame_type == "vta_end":
                logger.info(f"[ServerNode][VTA-FIN] Fin de l'alerte prioritaire notifiée par {addr}")
                self.intersection.annuler_urgence()

                # Enregistrement de fin d'alerte en BDD
                try:
                    self.db.insert_evenement(
                        self.simulation_id,
                        "FIN_VTA",
                        "Fin de priorité d'urgence VTA"
                    )
                except Exception as e_db:
                    logger.debug(f"[ServerNode] Erreur enregistrement BDD fin VTA : {e_db}")

                self.broadcast_state()

                # Acquittement de fin d'urgence
                ack_payload = {
                    "status": "ack_end",
                    "feu_ns": self.intersection.feu_ns.value,
                    "feu_eo": self.intersection.feu_eo.value,
                    "ref_seq": seq
                }
                ack_frame = self._build_frame("ack", ack_payload)
                raw_ack = json.dumps(ack_frame).encode("utf-8")
                try:
                    self.udp_sock.sendto(raw_ack, addr)
                except Exception:
                    pass

            elif frame_type == "ack":
                logger.debug(f"[ServerNode][UDP-RECV] Acquittement reçu de {addr}")

            else:
                logger.warning(f"[ServerNode][UDP-WARN] Type de trame UDP inconnu : {frame_type}")

        except Exception as e:
            logger.error(f"[ServerNode] Erreur lors du traitement d'une trame UDP : {e}", exc_info=True)

    def _handle_client_data(self, client_sock: socket.socket):
        """Lit et extrait les trames complètes délimitées par saut de ligne sur TCP.

        Préserve l'intégrité des caractères UTF-8 multi-octets en conservant
        les fragments dans un buffer binaire (bytearray) avant décodage par ligne.

        Args:
            client_sock (socket.socket): Socket du client concerné.
        """
        if not self.running:
            return
        try:
            data = client_sock.recv(4096)
            if not data:
                # Fermeture ordonnée par le client distant (EOF)
                self._remove_client(client_sock, reason="déconnexion normale du client")
                return

            # Ajout au buffer persistant binaire du client
            with self._clients_lock:
                if client_sock not in self.client_buffers:
                    return
                buf = self.client_buffers[client_sock]
                buf.extend(data)

                # Protection anti-saturation mémoire (max 64 Ko par client)
                if len(buf) > 65536 and b"\n" not in buf:
                    logger.warning("[ServerNode] Buffer client trop volumineux sans délimiteur. Fermeture.")
                    self._remove_client(client_sock, reason="dépassement buffer")
                    return

            # Extraction des trames complètes délimitées par b'\n'
            while True:
                with self._clients_lock:
                    buf = self.client_buffers.get(client_sock)
                    if buf is None or b"\n" not in buf:
                        break
                    idx = buf.find(b"\n")
                    raw_line = bytes(buf[:idx])
                    del buf[:idx + 1]

                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                try:
                    frame = json.loads(line)
                    self._handle_tcp_frame(frame, client_sock)
                except Exception as json_err:
                    logger.warning(f"[ServerNode][TCP-PARSE] Trame JSON invalide reçue d'un client : {json_err}")

        except BlockingIOError:
            pass
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            self._remove_client(client_sock, reason="connexion interrompue brutalement")
        except OSError as e:
            if not self.running or e.errno in (10038, 9):
                return
            logger.error(f"[ServerNode] Erreur lors de la lecture d'une socket TCP : {e}", exc_info=True)
            self._remove_client(client_sock, reason=f"erreur de lecture: {e}")
        except Exception as e:
            if not self.running:
                return
            logger.error(f"[ServerNode] Erreur lors de la lecture d'une socket TCP : {e}", exc_info=True)
            self._remove_client(client_sock, reason=f"erreur de lecture: {e}")

    def _handle_tcp_frame(self, frame: dict, client_sock: socket.socket):
        """Traite une trame TCP complète reçue d'un client de simulation.

        Args:
            frame (dict): Trame structurée reçue.
            client_sock (socket.socket): Socket source ayant émis la trame.
        """
        try:
            frame_type = frame.get("type")
            seq = frame.get("seq", 0)
            payload = frame.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}

            # Mise à jour de la dernière activité client
            with self._clients_lock:
                meta = self.client_metadata.get(client_sock)
                if meta:
                    meta["last_seen"] = time.time()
                addr = meta.get("addr") if meta else "client"

            logger.info(f"[ServerNode][TCP-RECV] De {addr} | Type: {frame_type} | Seq: {seq}")

            # Inspection et validation de l'empreinte binaire standardisée Esk-2718
            c_code = code_pour_type_trame(str(frame_type))
            if c_code > 0:
                entete_test = packager_entete_binaire(c_code, int(seq), json.dumps(payload).encode("utf-8"))
                _mag, _c, _s, _len = depackager_entete_binaire(entete_test)

            if frame_type == "connect":
                # Message initial envoyé par le client lors de sa connexion
                client_id = payload.get("client_id", "client_anonyme")
                with self._clients_lock:
                    if client_sock in self.client_metadata:
                        self.client_metadata[client_sock]["client_id"] = client_id
                logger.info(f"[ServerNode][CLIENT-IDENT] Client identifié : '{client_id}' depuis {addr}")

                # Enregistrement de la connexion en BDD
                try:
                    self.db.insert_evenement(
                        self.simulation_id,
                        "CLIENT_CONNECT",
                        f"Client connecté : '{client_id}' depuis {addr}"
                    )
                except Exception as e_db:
                    logger.debug(f"[ServerNode] Erreur enregistrement BDD connexion : {e_db}")

                # Réponse immédiate avec l'état actuel de l'intersection
                self._send_state(client_sock)

            elif frame_type == "metrics":
                # Réception des métriques de trafic (nombre de véhicules, vitesse moyenne)
                count = int(payload.get("count", frame.get("count", 0)))
                avg_speed = float(payload.get("avg_speed", frame.get("avg_speed", 0.0)))

                with self._stats_lock:
                    self.metrics_count += 1

                logger.info(
                    f"[ServerNode][METRIQUES] Enregistrement : {count} véhicules, "
                    f"vitesse moy: {avg_speed:.2f} km/h"
                )

                # Insertion sécurisée dans la base de données SQLite locale
                try:
                    self.db.insert_metrique(self.simulation_id, count, avg_speed)
                except Exception as db_err:
                    logger.error(f"[ServerNode] Erreur lors de l'insertion en BDD : {db_err}", exc_info=True)

            elif frame_type == "scenario":
                # Notification de chargement ou sélection de scénario
                scenario_name = payload.get("scenario_name", "inconnu")
                logger.info(f"[ServerNode][SCENARIO] Chargement du scénario demandé : '{scenario_name}'")

                # Enregistrement de l'événement scénario en BDD
                try:
                    self.db.insert_evenement(
                        self.simulation_id,
                        "SCENARIO",
                        f"Chargement scénario : '{scenario_name}'"
                    )
                except Exception as e_db:
                    logger.debug(f"[ServerNode] Erreur enregistrement BDD scénario : {e_db}")

                # Synchronisation vers les autres clients connectés
                self.broadcast_frame("scenario", payload, exclude_sock=client_sock)

            elif frame_type == "disconnect":
                # Déconnexion propre et explicite notifiée par le client
                reason = payload.get("reason", "déconnexion explicite")
                logger.info(f"[ServerNode][CLIENT-DECONNEXION] Le client a demandé sa fermeture : {reason}")

                # Enregistrement de la déconnexion en BDD
                try:
                    self.db.insert_evenement(
                        self.simulation_id,
                        "CLIENT_DECONNECT",
                        f"Déconnexion client : '{addr}' ({reason})"
                    )
                except Exception as e_db:
                    logger.debug(f"[ServerNode] Erreur enregistrement BDD déconnexion : {e_db}")

                self._remove_client(client_sock, reason=reason)

            else:
                logger.warning(f"[ServerNode][TCP-WARN] Type de trame TCP inconnu : '{frame_type}'")

        except Exception as e:
            logger.error(f"[ServerNode] Erreur lors du traitement d'une trame TCP : {e}", exc_info=True)

    def _remove_client(self, client_sock: socket.socket, reason: str = ""):
        """Supprime de façon thread-safe un client déconnecté et libère ses ressources.

        Args:
            client_sock (socket.socket): Socket client à fermer et retirer.
            reason (str, optional): Motif explicite de la déconnexion.
        """
        with self._clients_lock:
            meta = self.client_metadata.pop(client_sock, None)
            addr = meta.get("addr") if meta else "inconnu"
            if client_sock in self.clients:
                self.clients.remove(client_sock)
            if client_sock in self.client_buffers:
                del self.client_buffers[client_sock]

        try:
            client_sock.close()
        except Exception:
            pass

        logger.info(
            f"[ServerNode][CLIENT-RETIRE] Client {addr} déconnecté ({reason}). "
            f"Clients restants: {len(self.clients)}"
        )

    def _send_state(self, client_sock: socket.socket):
        """Transmet l'état instantané des feux à un client TCP particulier.

        Args:
            client_sock (socket.socket): Socket client destinataire.
        """
        try:
            payload = {
                "feu_ns": self.intersection.feu_ns.value,
                "feu_eo": self.intersection.feu_eo.value,
                "feu_ns_nom": self.intersection.feu_ns.name,
                "feu_eo_nom": self.intersection.feu_eo.name
            }
            frame = self._build_frame("state", payload)
            raw = (json.dumps(frame) + "\n").encode("utf-8")
            if not self._send_raw_tcp(client_sock, raw):
                self._remove_client(client_sock, reason="échec d'envoi de l'état")
            else:
                logger.debug("[ServerNode][TCP-SEND] État initial envoyé au client")
        except Exception as e:
            logger.error(f"[ServerNode] Échec d'envoi de l'état au client : {e}", exc_info=True)
            self._remove_client(client_sock, reason="échec envoi état")

    def broadcast_state(self):
        """Diffuse l'état actuel des feux à TOUS les clients connectés via TCP."""
        payload = {
            "feu_ns": self.intersection.feu_ns.value,
            "feu_eo": self.intersection.feu_eo.value,
            "feu_ns_nom": self.intersection.feu_ns.name,
            "feu_eo_nom": self.intersection.feu_eo.name
        }
        self.broadcast_frame("state", payload)

        # Enregistrement de l'état des feux en base de données SQLite
        try:
            self.db.insert_etat_feux(
                self.simulation_id,
                self.intersection.feu_ns.value,
                self.intersection.feu_eo.value
            )
        except Exception as e_db:
            logger.debug(f"[ServerNode] Erreur enregistrement BDD état feux : {e_db}")

    def broadcast_frame(self, frame_type: str, payload: dict, exclude_sock: socket.socket = None):
        """Diffuse une trame quelconque à tous les clients connectés via TCP.

        Args:
            frame_type (str): Type de la trame.
            payload (dict): Contenu utile.
            exclude_sock (socket.socket, optional): Socket à exclure de la diffusion.
        """
        frame = self._build_frame(frame_type, payload)
        raw = (json.dumps(frame) + "\n").encode("utf-8")

        with self._clients_lock:
            clients_copy = list(self.clients)

        for client in clients_copy:
            if client is exclude_sock:
                continue
            if not self._send_raw_tcp(client, raw):
                logger.warning("[ServerNode] Échec d'envoi broadcast vers un client. Déconnexion.")
                self._remove_client(client, reason="erreur broadcast")

    def get_status(self) -> dict:
        """Retourne un instantané complet de l'état du serveur pour la console.

        Returns:
            dict: Synthèse contenant le nombre de clients, l'état des feux,
                les compteurs de métriques et d'alertes.
        """
        with self._clients_lock:
            clients_info = []
            for c, meta in self.client_metadata.items():
                clients_info.append({
                    "addr": f"{meta.get('addr')}",
                    "id": meta.get("client_id", "inconnu"),
                    "connected_duration": int(time.time() - meta.get("connected_at", time.time()))
                })

        with self._stats_lock:
            metrics_cnt = self.metrics_count
            alerts_cnt = self.alerts_count
            last_alert = dict(self.last_alert_info) if self.last_alert_info else None

        return {
            "running": self.running,
            "clients_count": len(clients_info),
            "clients": clients_info,
            "feu_ns": self.intersection.feu_ns.name,
            "feu_eo": self.intersection.feu_eo.name,
            "metrics_count": metrics_cnt,
            "alerts_count": alerts_cnt,
            "last_alert": last_alert
        }

    def _fermer_toutes_les_sockets(self):
        """Clôture l'intégralité des sockets réseau du serveur de manière ordonnée."""
        with self._clients_lock:
            clients_to_close = list(self.clients)
            self.clients.clear()
            self.client_buffers.clear()
            self.client_metadata.clear()

        # Envoi d'une notification de déconnexion avant clôture
        disconnect_frame = self._build_frame("disconnect", {"reason": "server_shutdown"})
        raw_disc = (json.dumps(disconnect_frame) + "\n").encode("utf-8")

        for client in clients_to_close:
            try:
                client.send(raw_disc)
            except Exception:
                pass
            try:
                client.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                client.close()
            except Exception:
                pass

        if self.tcp_sock:
            try:
                self.tcp_sock.close()
            except Exception as e:
                logger.error(f"[ServerNode] Erreur lors de la fermeture de la socket TCP : {e}", exc_info=True)
            self.tcp_sock = None

        if self.udp_sock:
            try:
                self.udp_sock.close()
            except Exception as e:
                logger.error(f"[ServerNode] Erreur lors de la fermeture de la socket UDP : {e}", exc_info=True)
            self.udp_sock = None

    def stop(self):
        """Signale l'arrêt du serveur et ferme les sockets d'écoute."""
        logger.info("[ServerNode] Signal d'arrêt reçu. Arrêt du serveur...")
        self.running = False

        # Mise à jour de la durée totale de session en BDD
        if self.simulation_id is not None:
            try:
                duree = time.time() - self.start_time
                self.db.mettre_a_jour_duree(self.simulation_id, duree)
            except Exception as e_dur:
                logger.debug(f"[ServerNode] Erreur mise à jour durée BDD : {e_dur}")

        try:
            if self.tcp_sock:
                self.tcp_sock.close()
        except Exception:
            pass
        try:
            if self.udp_sock:
                self.udp_sock.close()
        except Exception:
            pass
        if not self.is_alive():
            self._fermer_toutes_les_sockets()
