"""Point d'entrée secondaire du simulateur Esk-2718.

Ce module constitue un lanceur léger redirigeant l'exécution vers
`client_main.py` afin de respecter les critères de modularité et
d'éviter toute duplication de code au sein du dépôt.
"""

import os
import sys

repertoire_courant = os.path.abspath(os.path.dirname(__file__))
if repertoire_courant not in sys.path:
    sys.path.insert(0, repertoire_courant)

from client_main import main

if __name__ == "__main__":
    main()
