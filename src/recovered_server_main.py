import sys
import json
import os
from network.server_node import ServerNode

def main():
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.json")
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except Exception:
        config = {
            "server_ip": "127.0.0.1",
            "server_tcp_port": 5000,
            "server_udp_port": 5001
        }
        
    server = ServerNode(config)
    server.start()
    
    print("Server running. Press Enter to stop.")
    try:
        input()
    except KeyboardInterrupt:
        pass
        
    server.stop()
    server.join()
    print("Server stopped.")

if __name__ == "__main__":
    main()