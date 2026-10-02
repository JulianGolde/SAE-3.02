import socket
import json
import threading
import select
import time
from database.db_manager import DBManager
from simulation.intersection import IntersectionManager

class ServerNode(threading.Thread):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.db = DBManager()
        self.intersection = IntersectionManager()
        
        self.tcp_ip = config.get("server_ip", "0.0.0.0")
        if self.tcp_ip == "127.0.0.1": self.tcp_ip = "0.0.0.0"
        self.tcp_port = config.get("server_tcp_port", 5000)
        self.udp_port = config.get("server_udp_port", 5001)
        
        self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_sock.bind((self.tcp_ip, self.tcp_port))
        self.tcp_sock.listen(5)
        
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_sock.bind((self.tcp_ip, self.udp_port))
        
        self.clients = []
        self.client_buffers = {}
        self.running = False
        self.last_state = None

    def run(self):
        self.running = True
        last_update = time.time()
        print(f"[ServerNode] Listening TCP on {self.tcp_ip}:{self.tcp_port}, UDP on {self.udp_port}")
        
        while self.running:
            now = time.time()
            dt = now - last_update
            last_update = now
            self.intersection.update(dt)
            
            # Broadcast state if changed
            current_state = (self.intersection.feu_ns.value, self.intersection.feu_eo.value)
            if current_state != self.last_state:
                self.last_state = current_state
                self.broadcast_state()

            sockets = [self.tcp_sock, self.udp_sock] + self.clients
            try:
                readable, _, _ = select.select(sockets, [], [], 0.05)
            except Exception:
                # Handle socket closing mid-select by filtering dead sockets
                dead_clients = []
                for c in self.clients:
                    try:
                        if c.fileno() == -1:
                            dead_clients.append(c)
                    except Exception:
                        dead_clients.append(c)
                for c in dead_clients:
                    self._remove_client(c)
                continue
                
            for sock in readable:
                if sock is self.tcp_sock:
                    client, addr = self.tcp_sock.accept()
                    self.clients.append(client)
                    self.client_buffers[client] = ""
                    print(f"[ServerNode] New TCP client: {addr}")
                    self._send_state(client)
                elif sock is self.udp_sock:
                    try:
                        data, addr = self.udp_sock.recvfrom(1024)
                        payload = json.loads(data.decode('utf-8'))
                        self._handle_udp(payload, addr)
                    except Exception:
                        pass
                else:
                    try:
                        data = sock.recv(1024)
                        if not data:
                            self._remove_client(sock)
                            continue
                            
                        self.client_buffers[sock] += data.decode('utf-8')
                        while '\n' in self.client_buffers[sock]:
                            msg, self.client_buffers[sock] = self.client_buffers[sock].split('\n', 1)
                            if not msg.strip(): continue
                            try:
                                payload = json.loads(msg)
                                self._handle_tcp(payload)
                            except Exception:
                                pass
                    except Exception:
                        self._remove_client(sock)

    def _remove_client(self, client):
        if client in self.clients:
            self.clients.remove(client)
        if client in self.client_buffers:
            del self.client_buffers[client]
        try:
            client.close()
        except Exception:
            pass

    def _handle_udp(self, payload, addr):
        ptype = payload.get("type")
        if ptype == "vta_alert":
            axe_x = payload.get("axe_x", False)
            self.intersection.forcer_passage_vta(axe_x)
            ack_msg = json.dumps({
                "type": "ack", 
                "feu_ns": self.intersection.feu_ns.value,
                "feu_eo": self.intersection.feu_eo.value
            })
            self.udp_sock.sendto(ack_msg.encode('utf-8'), addr)
            
        elif ptype == "vta_end":
            self.intersection.annuler_urgence()

    def _handle_tcp(self, payload):
        if payload.get("type") == "metrics":
            count = payload.get("count", 0)
            avg = payload.get("avg_speed", 0.0)
            self.db.insert_metric(count, avg)
            
    def _send_state(self, client):
        msg = json.dumps({
            "type": "state",
            "feu_ns": self.intersection.feu_ns.value,
            "feu_eo": self.intersection.feu_eo.value
        }) + "\n"
        try:
            client.send(msg.encode('utf-8'))
        except Exception:
            self._remove_client(client)
            
    def broadcast_state(self):
        msg = json.dumps({
            "type": "state",
            "feu_ns": self.intersection.feu_ns.value,
            "feu_eo": self.intersection.feu_eo.value
        }) + "\n"
        bmsg = msg.encode('utf-8')
        for c in list(self.clients):
            try:
                c.send(bmsg)
            except Exception:
                self._remove_client(c)

    def stop(self):
        self.running = False
        try:
            self.tcp_sock.close()
            self.udp_sock.close()
        except Exception:
            pass
