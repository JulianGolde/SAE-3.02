import socket
import json
import threading
import select
import time

class ClientNode(threading.Thread):
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

    def connect(self):
        try:
            if self.tcp_sock:
                self.tcp_sock.close()
            self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_sock.connect((self.server_ip, self.server_tcp_port))
            self.connected = True
            print("[ClientNode] Connected to Server via TCP.")
        except Exception as e:
            self.connected = False
            print(f"[ClientNode] Error connecting TCP: {e}")

    def run(self):
        self.running = True
        self.connect()
        last_reconnect = time.time()
        while self.running:
            try:
                now = time.time()
                if not self.connected and (now - last_reconnect > 1.0):
                    last_reconnect = now
                    self.connect()

                sockets = [self.udp_sock]
                if self.connected and self.tcp_sock:
                    sockets.append(self.tcp_sock)

                readable, _, _ = select.select(sockets, [], [], 0.1)
                for sock in readable:
                    if sock is self.tcp_sock:
                        try:
                            data = sock.recv(1024)
                            if not data:
                                print("[ClientNode] Disconnected from server.")
                                self.connected = False
                                break
                            self.tcp_buffer += data.decode('utf-8')
                            while '\n' in self.tcp_buffer:
                                msg, self.tcp_buffer = self.tcp_buffer.split('\n', 1)
                                if msg.strip():
                                    try:
                                        payload = json.loads(msg)
                                        self._handle_msg(payload)
                                    except Exception:
                                        pass
                        except Exception:
                            self.connected = False
                            break
                    elif sock is self.udp_sock:
                        data, addr = sock.recvfrom(1024)
                        try:
                            payload = json.loads(data.decode('utf-8'))
                            self._handle_msg(payload)
                        except Exception:
                            pass
            except Exception as e:
                self.connected = False
                if self.tcp_sock:
                    try:
                        self.tcp_sock.close()
                    except Exception:
                        pass
                    self.tcp_sock = None
                time.sleep(0.1)

    def _handle_msg(self, payload):
        if payload.get("type") in ("state", "ack"):
            feu_ns = payload.get("feu_ns", 3)
            feu_eo = payload.get("feu_eo", 3)
            self.moteur.intersection.set_state(feu_ns, feu_eo)

    def send_vta_alert(self, axe_x):
        now = time.time()
        # Resend UDP packet every 200ms to combat packet drop
        if not self.vta_active or (now - self.last_vta_sent > 0.2):
            self.vta_active = True
            self.last_vta_sent = now
            msg = json.dumps({"type": "vta_alert", "axe_x": axe_x})
            try:
                self.udp_sock.sendto(msg.encode('utf-8'), (self.server_ip, self.server_udp_port))
            except Exception:
                pass

    def send_vta_end(self):
        if self.vta_active:
            self.vta_active = False
            msg = json.dumps({"type": "vta_end"})
            try:
                for _ in range(3): # Redundancy for UDP drop
                    self.udp_sock.sendto(msg.encode('utf-8'), (self.server_ip, self.server_udp_port))
            except Exception:
                pass

    def send_metrics(self, count, avg_speed):
        if not self.connected:
            return
        msg = json.dumps({"type": "metrics", "count": count, "avg_speed": avg_speed}) + "\n"
        try:
            self.tcp_sock.send(msg.encode('utf-8'))
        except Exception:
            self.connected = False

    def stop(self):
        self.running = False
        try:
            if self.tcp_sock:
                self.tcp_sock.close()
            self.udp_sock.close()
        except Exception:
            pass
