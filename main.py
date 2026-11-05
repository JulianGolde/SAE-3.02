"""Point d'entrée principal racine du simulateur Esk-2718.

Ce script redirige l'exécution vers src/client_main.py avec propagation
des arguments en ligne de commande.
"""

import os
import sys

repertoire_src = os.path.abspath(os.path.join(os.path.dirname(__file__), "src"))
if repertoire_src not in sys.path:
    sys.path.insert(0, repertoire_src)

from client_main import main

if __name__ == "__main__":
    main()
