import logging
logger = logging.getLogger(__name__)

import socket
import json
import select
import time
import queue

from PyQt6.QtCore import QThread, pyqtSignal

class ClientNode(QThread):
    """Nœud client pour la communication réseau."""
    
    # Signal pour mettre à jour l'état de l'intersection de manière thread-safe
    etat_intersection_recu = pyqtSignal(int, int)

    def __init__(self, config, moteur):
        super().__init__()
        self.config = config
        self.moteur = moteur
        self.running = False
        self.connected = False
        
        self.server_ip = config.get("server_ip", "127.0.0.1")
        self.server_tcp_port = config.get("server_tcp_port", 5000)
        self.server_udp_port = config.get("server_udp_port", 5001)
        self.client_udp_port = config.get("client_udp_port", 5002)
        
        self.tcp_sock = None
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.udp_sock.bind(("0.0.0.0", self.client_udp_port))
        except Exception:
            self.udp_sock.bind(("0.0.0.0", 0)) # fallback
        
        self.vta_active = False
        self.last_vta_sent = 0
        self.tcp_buffer = ""
        
        # File d'attente pour les messages sortants (thread-safe)
        self.msg_queue = queue.Queue()

    def connect_server(self):
        try:
            if self.tcp_sock:
                self.tcp_sock.close()
            self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_sock.connect((self.server_ip, self.server_tcp_port))
            self.connected = True
            logger.info("[ClientNode] Connected to Server via TCP.")
        except Exception as e:
            self.connected = False
            logger.error(f"[ClientNode] Error connecting TCP: {e}")

    def run(self):
        self.running = True
        self.connect_server()
        last_reconnect = time.time()
        
        while self.running:
            try:
                now = time.time()
                if not self.connected and (now - last_reconnect > 2.0):
                    last_reconnect = now
                    self.connect_server()

                # Traitement de la file d'attente des messages sortants
                while not self.msg_queue.empty():
                    msg_type, msg_data = self.msg_queue.get()
                    if msg_type == "UDP":
                        try:
                            self.udp_sock.sendto(msg_data, (self.server_ip, self.server_udp_port))
                        except Exception as e:
                            logger.error(f"UDP send error: {e}")
                    elif msg_type == "TCP" and self.connected and self.tcp_sock:
                        try:
                            self.tcp_sock.sendall(msg_data)
                        except Exception as e:
                            logger.error(f"TCP send error: {e}")
                            self.connected = False

                sockets = [self.udp_sock]
                if self.connected and self.tcp_sock:
                    sockets.append(self.tcp_sock)

                readable, _, _ = select.select(sockets, [], [], 0.05)
                for sock in readable:
                    if sock is self.tcp_sock:
                        try:
                            data = sock.recv(2048)
                            if not data:
                                logger.info("[ClientNode] Disconnected from server.")
                                self.connected = False
                                break
                            self.tcp_buffer += data.decode('utf-8')
                            while '\n' in self.tcp_buffer:
                                msg, self.tcp_buffer = self.tcp_buffer.split('\n', 1)
                                if msg.strip():
                                    try:
                                        payload = json.loads(msg)
                                        self._handle_msg(payload)
                                    except Exception as e:
                                        logger.warning(f"JSON decode error: {e}")
                        except Exception as e:
                            logger.error(f"TCP recv error: {e}")
                            self.connected = False
                            break
                    elif sock is self.udp_sock:
                        data, addr = sock.recvfrom(2048)
                        try:
                            payload = json.loads(data.decode('utf-8'))
                            self._handle_msg(payload)
                        except Exception as e:
                            logger.warning(f"UDP JSON decode error: {e}")
            except Exception as e:
                logger.error(f"Client run error: {e}", exc_info=True)
                self.connected = False
                if self.tcp_sock:
                    try:
                        self.tcp_sock.close()
                    except Exception:
                        pass
                    self.tcp_sock = None
                time.sleep(0.5)

    def _handle_msg(self, payload):
        if payload.get("type") in ("state", "ack"):
            feu_ns = payload.get("feu_ns", 3)
            feu_eo = payload.get("feu_eo", 3)
            # Utilisation du signal QThread
            self.etat_intersection_recu.emit(feu_ns, feu_eo)

    def send_vta_alert(self, axe_x):
        now = time.time()
        if not self.vta_active or (now - self.last_vta_sent > 0.2):
            self.vta_active = True
            self.last_vta_sent = now
            msg = json.dumps({"type": "vta_alert", "axe_x": axe_x})
            self.msg_queue.put(("UDP", msg.encode('utf-8')))

    def send_vta_end(self):
        if self.vta_active:
            self.vta_active = False
            msg = json.dumps({"type": "vta_end"})
            # Redundancy for UDP drop
            for _ in range(3):
                self.msg_queue.put(("UDP", msg.encode('utf-8')))

    def send_metrics(self, count, avg_speed):
        if not self.connected:
            return
        msg = json.dumps({"type": "metrics", "count": count, "avg_speed": avg_speed}) + "\n"
        self.msg_queue.put(("TCP", msg.encode('utf-8')))

    def stop(self):
        self.running = False
        try:
            if self.tcp_sock:
                self.tcp_sock.close()
            self.udp_sock.close()
        except Exception:
            pass
