"""Module de communication réseau côté client pour la simulation de carrefour.

Ce module implémente le nœud client (ClientNode) exécuté dans un thread Qt (QThread).
Il assure la connexion persistante TCP avec le serveur, l'envoi de métriques et le
relais rapide des alertes d'urgence VTA par datagrammes UDP, tout en garantissant
une stricte thread-safety via les signaux PyQt6.
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

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

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


class ClientNode(QThread):
    """Nœud client pour la communication réseau TCP et UDP avec le carrefour.

    Hérite de QThread pour exécuter la boucle de communication réseau de manière
    asynchrone sans bloquer l'interface graphique utilisateur. Les mises à jour
    reçues du réseau sont relayées au thread GUI exclusivement via des signaux Qt.

    Signals:
        etat_intersection_recu (int, int): Émis lors de la réception d'un état
            des feux (feu_ns, feu_eo). Valeurs : 1=VERT, 2=ORANGE, 3=ROUGE.
        connexion_statut (bool): Émis lors d'un changement de l'état de connexion TCP.
        alerte_ack_recue (dict): Émis lors de la réception d'un acquittement UDP.
        scenario_recu (str, dict): Émis lors de la notification d'un ordre de scénario.
        trame_reseau_log (str, str, int, int, str): Émis à chaque envoi/réception
            (direction: 'TX'/'RX', proto: 'TCP'/'UDP', seq, taille_octets, type_trame).
    """

    etat_intersection_recu = pyqtSignal(int, int)
    connexion_statut = pyqtSignal(bool)
    alerte_ack_recue = pyqtSignal(dict)
    scenario_recu = pyqtSignal(str, dict)
    trame_reseau_log = pyqtSignal(str, str, int, int, str)

    def __init__(self, config=None, moteur=None):
        """Initialise le nœud client et prépare les structures de communication.

        Args:
            config (dict, optional): Paramètres de configuration réseau (IP et ports).
            moteur (object, optional): Référence vers le moteur de simulation local.
        """
        super().__init__()
        self.config = config if config is not None else {}
        self.moteur = moteur

        # Paramètres d'adressage réseau
        self.server_ip = str(self.config.get("server_ip", "127.0.0.1"))
        self.server_tcp_port = int(self.config.get("server_tcp_port", 5000))
        self.server_udp_port = int(self.config.get("server_udp_port", 5001))
        self.client_udp_port = int(self.config.get("client_udp_port", 5002))

        # Identifiant unique de ce nœud client
        self.client_id = f"client_{os.getpid()}_{int(time.time())}"

        # Gestion des numéros de séquence (thread-safe)
        self._seq_counter = 0
        self._seq_lock = threading.Lock()

        # État interne et indicateurs
        self.running = False
        self.connected = False
        self.tcp_sock = None
        self.tcp_buffer = bytearray()

        # Gestion de la reconnexion avec backoff exponentiel
        self.reconnect_attempts = 0
        self.base_backoff = 1.0
        self.max_backoff = 16.0
        self.next_reconnect_time = 0.0

        # Limitation de fréquence pour les alertes d'urgence VTA
        self.vta_active = False
        self.last_vta_sent = 0.0

        # Intervalle pour l'envoi périodique des métriques du moteur (secondes)
        self.last_periodic_metrics = 0.0
        self.metrics_interval = 2.0

        # File d'attente thread-safe pour les messages sortants (FIFO)
        self.msg_queue = queue.Queue()

        # Connexion automatique du signal de feux au moteur s'il est fourni
        if self.moteur and hasattr(self.moteur, "intersection") and hasattr(self.moteur.intersection, "set_state"):
            try:
                self.etat_intersection_recu.connect(self.moteur.intersection.set_state)
                logger.info("[ClientNode] Signal etat_intersection_recu connecté automatiquement au moteur.")
            except Exception as e_sig:
                logger.warning(f"[ClientNode] Impossible de connecter automatiquement etat_intersection_recu : {e_sig}")

        # Initialisation de la socket UDP
        self._initialiser_socket_udp()

    @property
    def serveur_connecte(self) -> bool:
        """Indique si la connexion TCP au serveur SCADA est active."""
        return bool(self.connected)

    def _initialiser_socket_udp(self):
        """Crée et attache la socket UDP locale en mode non bloquant."""
        try:
            self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                self.udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except (AttributeError, OSError):
                pass

            try:
                self.udp_sock.bind(("0.0.0.0", self.client_udp_port))
                logger.info(f"[ClientNode] Socket UDP liée sur le port {self.client_udp_port}")
            except Exception as bind_err:
                logger.warning(
                    f"[ClientNode] Port UDP {self.client_udp_port} indisponible ({bind_err}). "
                    f"Attribution d'un port dynamique."
                )
                self.udp_sock.bind(("0.0.0.0", 0))

            self.udp_sock.setblocking(False)
        except Exception as e:
            logger.error(f"[ClientNode] Échec de la création de la socket UDP : {e}", exc_info=True)
            raise

    def _next_seq(self) -> int:
        """Génère un numéro de séquence strictement croissant.

        Returns:
            int: Prochain numéro de séquence.
        """
        with self._seq_lock:
            self._seq_counter += 1
            return self._seq_counter

    def _build_frame(self, frame_type: str, payload: dict) -> dict:
        """Construit une trame JSON structurée conforme au protocole Esk-2718.

        Args:
            frame_type (str): Type de la trame ('connect', 'metrics', 'vta_alert', etc.).
            payload (dict): Contenu utile de la trame.

        Returns:
            dict: Trame prête à être sérialisée.
        """
        return {
            "type": frame_type,
            "seq": self._next_seq(),
            "timestamp": time.time(),
            "payload": payload if isinstance(payload, dict) else {}
        }

    def _send_raw_tcp(self, raw_bytes: bytes, timeout: float = 0.5) -> bool:
        """Transmet des octets sur la socket TCP avec gestion des attentes select.

        Args:
            raw_bytes (bytes): Octets à émettre.
            timeout (float): Temps maximal accordé.

        Returns:
            bool: True si la totalité a été envoyée, False en cas de déconnexion.
        """
        if not self.connected or not self.tcp_sock:
            return False

        total_sent = 0
        taille = len(raw_bytes)
        deadline = time.time() + timeout

        while total_sent < taille:
            try:
                sent = self.tcp_sock.send(raw_bytes[total_sent:])
                if sent == 0:
                    return False
                total_sent += sent
            except (BlockingIOError, InterruptedError):
                temps_restant = max(0.01, deadline - time.time())
                _, writable, _ = select.select([], [self.tcp_sock], [], temps_restant)
                if not writable:
                    return False
            except Exception:
                return False

        return True

    def connect_server(self) -> bool:
        """Tente d'établir la connexion TCP avec le serveur de carrefour.

        Utilise une connexion non bloquante avec timeout court pour ne pas figer
        le thread ouvrier ni bloquer le traitement des alertes UDP.

        Returns:
            bool: True si la connexion a réussi, False sinon.
        """
        sock = None
        try:
            if self.tcp_sock:
                try:
                    self.tcp_sock.close()
                except Exception:
                    pass
                self.tcp_sock = None

            logger.info(f"[ClientNode] Tentative de connexion TCP vers {self.server_ip}:{self.server_tcp_port}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setblocking(False)

            err = sock.connect_ex((self.server_ip, self.server_tcp_port))
            # Sous Windows err=10035 (WSAEWOULDBLOCK), sous POSIX err=EINPROGRESS (115)
            if err != 0:
                _, writable, exceptional = select.select([], [sock], [sock], 0.3)
                if not writable or exceptional:
                    raise ConnectionRefusedError(f"Serveur injoignable sur {self.server_ip}:{self.server_tcp_port}")
                sock_err = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if sock_err != 0:
                    raise OSError(sock_err, f"Erreur de connexion socket : {sock_err}")

            self.tcp_sock = sock
            self.connected = True
            self.reconnect_attempts = 0
            self.tcp_buffer.clear()

            logger.info("[ClientNode] Connexion TCP établie avec succès vers le serveur.")
            self.connexion_statut.emit(True)

            # Envoi immédiat de la trame initiale d'identification
            connect_payload = {
                "client_id": self.client_id,
                "version": "1.0",
                "os": sys.platform
            }
            connect_frame = self._build_frame("connect", connect_payload)
            raw = (json.dumps(connect_frame) + "\n").encode("utf-8")
            self._send_raw_tcp(raw)
            self.trame_reseau_log.emit("TX", "TCP", connect_frame.get("seq", 1), len(raw), "connect")
            logger.info("[ClientNode][TCP-SEND] Trame d'identification 'connect' envoyée.")

            return True

        except Exception as e:
            self.connected = False
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
            self.tcp_sock = None

            # Calcul du délai exponentiel pour la prochaine tentative
            delay = min(self.max_backoff, self.base_backoff * (2 ** min(self.reconnect_attempts, 5)))
            self.next_reconnect_time = time.time() + delay
            self.reconnect_attempts += 1

            logger.warning(
                f"[ClientNode] Échec de connexion TCP ({e}). "
                f"Prochaine tentative dans {delay:.1f}s (essai n°{self.reconnect_attempts})."
            )
            self.connexion_statut.emit(False)
            return False

    def run(self):
        """Boucle de travail principale du thread client.

        Gère l'envoi des messages en file d'attente, l'écoute multiplexée
        sur les sockets UDP et TCP, l'envoi périodique des métriques, et la
        reconnexion automatique en cas de rupture réseau.
        """
        self.running = True
        logger.info("[ClientNode] Démarrage du thread réseau client.")

        # Première tentative de connexion
        self.connect_server()

        try:
            while self.running:
                try:
                    now = time.time()

                    # Gestion de la reconnexion automatique avec backoff
                    if not self.connected and now >= self.next_reconnect_time:
                        self.connect_server()

                    # Vidage de la file d'attente des messages sortants
                    self._traiter_file_sortante()

                    # Préparation des sockets à surveiller via select
                    sockets_to_watch = [self.udp_sock]
                    if self.connected and self.tcp_sock is not None:
                        sockets_to_watch.append(self.tcp_sock)

                    # Multiplexage non bloquant via select (50ms)
                    try:
                        readable, _, exceptional = select.select(sockets_to_watch, [], sockets_to_watch, 0.05)
                    except (OSError, ValueError, select.error) as select_err:
                        if not self.running:
                            break
                        logger.warning(f"[ClientNode] Erreur select client : {select_err}")
                        if self.tcp_sock and self.tcp_sock.fileno() == -1:
                            self._deconnecter_tcp("socket fermée invalide")
                        continue

                    if not self.running:
                        break

                    for err_sock in exceptional:
                        if err_sock is self.tcp_sock:
                            self._deconnecter_tcp("exception sur socket TCP")

                    for sock in readable:
                        if not self.running:
                            break
                        if sock is self.tcp_sock:
                            self._recevoir_donnees_tcp()
                        elif sock is self.udp_sock:
                            self._recevoir_donnees_udp()

                except Exception as e:
                    if self.running:
                        logger.error(f"[ClientNode] Erreur dans la boucle de communication : {e}", exc_info=True)
                        time.sleep(0.05)

        finally:
            # Nettoyage et fermeture des sockets dans le contexte du thread ouvrier
            self._fermer_sockets()
            logger.info("[ClientNode] Arrêt complet du nœud client effectué.")

    def _traiter_file_sortante(self):
        """Dépile et expédie les messages en attente dans self.msg_queue.

        Conserve les messages TCP dans la file si la connexion TCP est absente,
        évitant toute perte de données lors d'une déconnexion temporaire.
        """
        non_envoyes = []
        traites = 0

        while not self.msg_queue.empty() and traites < 50:
            traites += 1
            try:
                msg_proto, raw_data = self.msg_queue.get_nowait()
            except queue.Empty:
                break

            if msg_proto == "UDP":
                try:
                    self.udp_sock.sendto(raw_data, (self.server_ip, self.server_udp_port))
                    try:
                        tr = json.loads(raw_data.decode("utf-8", errors="ignore"))
                        t_type = tr.get("type", "vta_alert")
                        t_seq = tr.get("seq", 0)
                        self.trame_reseau_log.emit("TX", "UDP", int(t_seq), len(raw_data), str(t_type))
                    except Exception:
                        self.trame_reseau_log.emit("TX", "UDP", 0, len(raw_data), "UDP")
                except Exception as e_udp:
                    logger.error(f"[ClientNode] Erreur d'expédition UDP : {e_udp}", exc_info=True)

            elif msg_proto == "TCP":
                if self.connected and self.tcp_sock:
                    if not self._send_raw_tcp(raw_data):
                        non_envoyes.append((msg_proto, raw_data))
                        self._deconnecter_tcp("échec sendall TCP")
                        break
                    else:
                        try:
                            tr = json.loads(raw_data.decode("utf-8", errors="ignore").strip())
                            t_type = tr.get("type", "metrics")
                            t_seq = tr.get("seq", 0)
                            self.trame_reseau_log.emit("TX", "TCP", int(t_seq), len(raw_data), str(t_type))
                        except Exception:
                            self.trame_reseau_log.emit("TX", "TCP", 0, len(raw_data), "TCP")
                else:
                    # Serveur déconnecté : conserver le message TCP pour le rejouer
                    non_envoyes.append((msg_proto, raw_data))
                    break

        # Réenfiler les messages TCP non expédiés pour le prochain cycle (dans l'ordre FIFO)
        if non_envoyes:
            elements_restants = []
            while not self.msg_queue.empty():
                try:
                    elements_restants.append(self.msg_queue.get_nowait())
                except queue.Empty:
                    break

            # Limite globale pour éviter une consommation mémoire infinie (max 100 messages en file)
            fusion = (non_envoyes + elements_restants)[-100:]
            for elem in fusion:
                self.msg_queue.put(elem)

    def _recevoir_donnees_tcp(self):
        """Lit les données TCP entrantes, les fragmente en trames et les traite."""
        if not self.running or not self.connected or not self.tcp_sock:
            return
        try:
            data = self.tcp_sock.recv(4096)
            if not data:
                self._deconnecter_tcp("fermeture normale par le serveur")
                return

            self.tcp_buffer.extend(data)

            # Protection contre les buffers TCP anormaux
            if len(self.tcp_buffer) > 65536 and b"\n" not in self.tcp_buffer:
                logger.warning("[ClientNode] Buffer TCP trop volumineux sans saut de ligne. Réinitialisation.")
                self.tcp_buffer.clear()
                return

            while b"\n" in self.tcp_buffer:
                idx = self.tcp_buffer.find(b"\n")
                raw_line = bytes(self.tcp_buffer[:idx])
                del self.tcp_buffer[:idx + 1]

                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                try:
                    frame = json.loads(line)
                    self._handle_tcp_frame(frame)
                except Exception as json_err:
                    logger.warning(f"[ClientNode][TCP-PARSE] Trame TCP JSON invalide : {json_err}")

        except BlockingIOError:
            pass
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as conn_err:
            self._deconnecter_tcp(f"connexion coupée: {conn_err}")
        except OSError as e:
            if not self.running or e.errno in (10038, 9):
                return
            logger.error(f"[ClientNode] Erreur lors de la lecture TCP : {e}", exc_info=True)
            self._deconnecter_tcp(f"erreur lecture: {e}")
        except Exception as e:
            if not self.running:
                return
            logger.error(f"[ClientNode] Erreur lors de la lecture TCP : {e}", exc_info=True)
            self._deconnecter_tcp(f"erreur lecture: {e}")

    def _convertir_valeur_feu(self, val, defaut=3) -> int:
        """Convertit de façon sûre une valeur ou un nom d'état de feu en entier (1, 2 ou 3).

        Args:
            val (any): Valeur brute (int ou str).
            defaut (int): Valeur de repli (3 = ROUGE).

        Returns:
            int: Code couleur valide (1=VERT, 2=ORANGE, 3=ROUGE).
        """
        if isinstance(val, int) and val in (1, 2, 3):
            return val
        if isinstance(val, str):
            v = val.upper().strip()
            if v in ("VERT", "GREEN", "1"):
                return 1
            if v in ("ORANGE", "JAUNE", "YELLOW", "2"):
                return 2
            if v in ("ROUGE", "RED", "3"):
                return 3
        return defaut

    def _handle_tcp_frame(self, frame: dict):
        """Traite une trame structurée reçue via TCP.

        Args:
            frame (dict): Trame JSON reçue et décodée.
        """
        try:
            frame_type = frame.get("type")
            seq = frame.get("seq", 0)
            payload = frame.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}

            logger.debug(f"[ClientNode][TCP-RECV] Type: {frame_type} | Seq: {seq}")

            # Validation de l'empreinte binaire struct standard Esk-2718
            try:
                c_code = code_pour_type_trame(str(frame_type))
                entete_test = packager_entete_binaire(c_code, int(seq), json.dumps(payload).encode("utf-8"))
                _mag, _c, _s, _len = depackager_entete_binaire(entete_test)
            except Exception as e_st:
                logger.debug(f"[ClientNode] Validation struct TCP : {e_st}")

            self.trame_reseau_log.emit("RX", "TCP", int(seq), len(json.dumps(frame).encode("utf-8")), str(frame_type))

            if frame_type in ("state", "ack"):
                # Extraction sécurisée des couleurs de feux avec normalisation
                raw_ns = payload.get("feu_ns", frame.get("feu_ns", 3))
                raw_eo = payload.get("feu_eo", frame.get("feu_eo", 3))

                feu_ns = self._convertir_valeur_feu(raw_ns, defaut=3)
                feu_eo = self._convertir_valeur_feu(raw_eo, defaut=3)

                # Émission thread-safe vers l'interface graphique / moteur de simulation
                self.etat_intersection_recu.emit(int(feu_ns), int(feu_eo))

            elif frame_type == "scenario":
                scenario_name = payload.get("scenario_name", "inconnu")
                scenario_data = payload.get("data", {})
                logger.info(f"[ClientNode][SCENARIO] Ordre de scénario reçu : '{scenario_name}'")
                self.scenario_recu.emit(str(scenario_name), scenario_data)

            elif frame_type == "disconnect":
                reason = payload.get("reason", "arrêt serveur")
                logger.info(f"[ClientNode][DISCONNECT] Déconnexion ordonnée par le serveur : {reason}")
                self._deconnecter_tcp(f"ordre serveur: {reason}")

            else:
                logger.debug(f"[ClientNode][TCP-INFO] Trame reçue de type '{frame_type}'")

        except Exception as e:
            logger.error(f"[ClientNode] Erreur lors du décodage de la trame TCP : {e}", exc_info=True)

    def _recevoir_donnees_udp(self):
        """Lit et traite les paquets arrivant sur la socket UDP."""
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
                logger.warning(f"[ClientNode][UDP-PARSE] Paquet UDP non JSON de {addr} : {json_err}")
                return

            self._handle_udp_frame(frame, addr)

        except BlockingIOError:
            pass
        except OSError as e:
            if not self.running or e.errno in (10038, 9):
                return
            logger.error(f"[ClientNode] Erreur de réception UDP : {e}", exc_info=True)
        except Exception as e:
            if self.running:
                logger.error(f"[ClientNode] Erreur de réception UDP : {e}", exc_info=True)

    def _handle_udp_frame(self, frame: dict, addr: tuple):
        """Traite une trame structurée reçue par UDP (ex: acquittement ack).

        Args:
            frame (dict): Trame décodée.
            addr (tuple): Adresse de l'émetteur distant.
        """
        try:
            frame_type = frame.get("type")
            seq = frame.get("seq", 0)
            payload = frame.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}

            logger.debug(f"[ClientNode][UDP-RECV] Type: {frame_type} | Seq: {seq} de {addr}")

            # Validation de l'empreinte binaire struct standard Esk-2718
            try:
                c_code = code_pour_type_trame(str(frame_type))
                entete_test = packager_entete_binaire(c_code, int(seq), json.dumps(payload).encode("utf-8"))
                _mag, _c, _s, _len = depackager_entete_binaire(entete_test)
            except Exception as e_st:
                logger.debug(f"[ClientNode] Validation struct UDP : {e_st}")

            self.trame_reseau_log.emit("RX", "UDP", int(seq), len(json.dumps(frame).encode("utf-8")), str(frame_type))

            if frame_type == "ack":
                raw_ns = payload.get("feu_ns", frame.get("feu_ns", None))
                raw_eo = payload.get("feu_eo", frame.get("feu_eo", None))
                if raw_ns is not None and raw_eo is not None:
                    feu_ns = self._convertir_valeur_feu(raw_ns, defaut=3)
                    feu_eo = self._convertir_valeur_feu(raw_eo, defaut=3)
                    self.etat_intersection_recu.emit(int(feu_ns), int(feu_eo))
                self.alerte_ack_recue.emit(payload)

        except Exception as e:
            logger.error(f"[ClientNode] Erreur lors du traitement UDP : {e}", exc_info=True)

    def _deconnecter_tcp(self, reason: str = ""):
        """Clôture la socket TCP et arme la logique de reconnexion automatique.

        Args:
            reason (str, optional): Raison détaillée de la rupture.
        """
        self.connected = False
        if self.tcp_sock:
            try:
                self.tcp_sock.close()
            except Exception:
                pass
            self.tcp_sock = None

        if not self.running:
            return

        delay = min(self.max_backoff, self.base_backoff * (2 ** min(self.reconnect_attempts, 5)))
        self.next_reconnect_time = time.time() + delay
        self.reconnect_attempts += 1

        logger.warning(
            f"[ClientNode] Déconnexion TCP ({reason}). "
            f"Tentative de reconnexion dans {delay:.1f}s."
        )
        self.connexion_statut.emit(False)

    def send_vta_alert(self, axe_x=False, position=None, v_type="VIG_VTA", urgence=1):
        """Émet une trame UDP d'alerte pour accorder la priorité à un véhicule VTA.

        Gère les appels polymorphiques, que le premier argument soit un booléen
        d'axe ou une liste/tuple de coordonnées [x, y].

        Args:
            axe_x (bool | list | tuple): Axe d'approche (True si Est-Ouest) ou
                coordonnées [x, y] si appelé avec la position en premier argument.
            position (list | tuple | str, optional): Position [x, y] ou type de véhicule.
            v_type (str | int, optional): Type de véhicule d'urgence ('VIG_VTA') ou niveau d'urgence.
            urgence (int, optional): Niveau d'urgence (1, 2 ou 3).
        """
        try:
            # Prise en charge polymorphique robuste
            if isinstance(axe_x, (list, tuple)):
                coords = [float(p) for p in axe_x[:2]] if len(axe_x) >= 2 else [0.0, 0.0]
                resolved_pos = coords
                resolved_axe_x = abs(coords[0]) >= abs(coords[1])
                # Si le 2ème argument a été fourni, il est tombé dans position
                resolved_type = str(position) if position is not None else str(v_type)
                # Si le 3ème argument a été fourni, il est tombé dans v_type
                if isinstance(v_type, (int, float)):
                    resolved_urg = int(v_type)
                else:
                    resolved_urg = int(urgence)
            else:
                resolved_axe_x = bool(axe_x)
                if isinstance(position, (list, tuple)) and len(position) >= 2:
                    resolved_pos = [float(position[0]), float(position[1])]
                else:
                    resolved_pos = [0.0, 0.0]
                resolved_type = str(v_type)
                try:
                    resolved_urg = int(urgence)
                except (ValueError, TypeError):
                    resolved_urg = 1

            now = time.time()
            alert_tuple = (resolved_axe_x, resolved_pos[0], resolved_pos[1], resolved_type, resolved_urg)
            # Émission immédiate si changement d'alerte, sinon limitation à 200ms pour les redites de moteur.py
            if not self.vta_active or (getattr(self, "_last_vta_tuple", None) != alert_tuple) or (now - self.last_vta_sent > 0.2):
                self.vta_active = True
                self.last_vta_sent = now
                self._last_vta_tuple = alert_tuple

                payload = {
                    "axe_x": resolved_axe_x,
                    "position": resolved_pos,
                    "type": resolved_type,
                    "urgence": resolved_urg
                }
                frame = self._build_frame("vta_alert", payload)
                raw = json.dumps(frame).encode("utf-8")
                self.msg_queue.put(("UDP", raw))
                logger.info(
                    f"[ClientNode][VTA-SEND] Alerte envoyée sur axe_x={resolved_axe_x}, "
                    f"type={resolved_type}, urgence={resolved_urg}, pos={resolved_pos}"
                )

        except Exception as e:
            logger.error(f"[ClientNode] Erreur lors de l'envoi de l'alerte VTA : {e}", exc_info=True)

    def send_vta_end(self):
        """Transmet l'ordre de fin d'urgence VTA via UDP avec redondance."""
        try:
            if self.vta_active:
                self.vta_active = False
                self._last_vta_tuple = None
                payload = {}
                frame = self._build_frame("vta_end", payload)
                raw = json.dumps(frame).encode("utf-8")

                # Triple émission pour se prémunir contre les pertes de paquets UDP
                for _ in range(3):
                    self.msg_queue.put(("UDP", raw))

                logger.info("[ClientNode][VTA-END] Fin d'urgence transmise au serveur.")

        except Exception as e:
            logger.error(f"[ClientNode] Erreur lors de l'envoi de fin de VTA : {e}", exc_info=True)

    def send_metrics(self, count: int = 0, avg_speed: float = 0.0):
        """Enfile une trame de métriques de trafic pour transmission au serveur TCP.

        Conserve la trame dans self.msg_queue même si le client est momentanément
        déconnecté, garantissant l'expédition dès le rétablissement de la liaison.

        Args:
            count (int, optional): Nombre total de véhicules en circulation.
            avg_speed (float, optional): Vitesse moyenne mesurée en km/h.
        """
        try:
            payload = {
                "count": int(count),
                "avg_speed": round(float(avg_speed), 2)
            }
            frame = self._build_frame("metrics", payload)
            raw = (json.dumps(frame) + "\n").encode("utf-8")

            # Limitation de la taille de file d'attente à 100 éléments
            if self.msg_queue.qsize() < 100:
                self.msg_queue.put(("TCP", raw))
                logger.debug(f"[ClientNode][METRIQUES-SEND] Enfilé : {count} véhicules, {avg_speed:.1f} km/h")
            else:
                logger.warning("[ClientNode] File d'attente de métriques saturée (>100). Trame ignorée.")

        except Exception as e:
            logger.error(f"[ClientNode] Erreur lors de la préparation des métriques : {e}", exc_info=True)

    def send_scenario(self, scenario_name: str, data: dict = None):
        """Envoie une requête de synchronisation de scénario au serveur.

        Args:
            scenario_name (str): Nom du fichier ou du scénario.
            data (dict, optional): Données additionnelles du scénario.
        """
        try:
            payload = {
                "scenario_name": scenario_name,
                "data": data or {}
            }
            frame = self._build_frame("scenario", payload)
            raw = (json.dumps(frame) + "\n").encode("utf-8")
            self.msg_queue.put(("TCP", raw))
            logger.info(f"[ClientNode][SCENARIO-SEND] Scénario '{scenario_name}' enfilé pour le serveur.")

        except Exception as e:
            logger.error(f"[ClientNode] Erreur lors de l'envoi du scénario : {e}", exc_info=True)

    def _fermer_sockets(self):
        """Ferme proprement les sockets TCP et UDP du client."""
        if self.connected and self.tcp_sock:
            try:
                frame = self._build_frame("disconnect", {"reason": "client_shutdown"})
                raw = (json.dumps(frame) + "\n").encode("utf-8")
                self.tcp_sock.send(raw)
            except Exception:
                pass

        if self.tcp_sock:
            try:
                self.tcp_sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.tcp_sock.close()
            except Exception:
                pass
            self.tcp_sock = None

        if self.udp_sock:
            try:
                self.udp_sock.close()
            except Exception:
                pass
            self.udp_sock = None

    def stop(self):
        """Arrête proprement le thread client et attend sa terminaison."""
        logger.info("[ClientNode] Signal d'arrêt reçu. Fermeture des communications...")
        self.running = False
        self._fermer_sockets()
        if self.isRunning():
            self.wait(2000)
