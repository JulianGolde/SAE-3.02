# Projet Esk-2718 — SAÉ 3.02

## Simulation 2D de régulation intelligente de carrefours pour véhicules prioritaires

> *Esk* = lettre **E** dans l'alphabet Aurebesh (Star Wars) | *2718* = premiers chiffres de *e* ≈ 2,71828…

---

###  Identification

| Information | Détail |
|---|---|
| **Groupe** | Esk-2718 |
| **Auteur** | Golde Julian |
| **Formation** | BUT R&T — Semestre 3, IUT de Colmar |
| **Projet** | SAÉ 3.02 — Développer une application communicante |

---

###  Installation

#### Prérequis
- Python 3.14+ installé ([python.org](https://www.python.org/downloads/))
- Git installé ([git-scm.com](https://git-scm.com/))

#### Étapes

1. **Cloner le dépôt** :
```bash
git clone https://github.com/VOTRE_UTILISATEUR/esk-2718.git
cd esk-2718
```

2. **Créer et activer l'environnement virtuel** :
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

3. **Installer les dépendances** :
```bash
pip install -r requirements.txt
```

4. **Lancer l'application** :
```bash
python src/main.py
```

---

### 📁 Structure du projet

```
esk-2718/
├── README.md                  # Ce fichier
├── requirements.txt           # Dépendances Python (versions figées)
├── Cahier_des_Charges_Esk-2718.md
├── src/                       # Code source
│   ├── main.py                # Point d'entrée de l'application
│   ├── gui/                   # Interface graphique (PyQt6)
│   │   └── __init__.py
│   ├── network/               # Communications réseau (sockets TCP/UDP)
│   │   └── __init__.py
│   ├── simulation/            # Moteur de simulation (véhicules, feux, piétons)
│   │   └── __init__.py
│   └── database/              # Stockage et métriques (sqlite3)
│       └── __init__.py
├── data/                      # Scénarios et fichiers de données
├── docs/                      # Documentation technique et guide utilisateur
├── tests/                     # Tests unitaires et d'intégration
├── comptes_rendus/            # CR hebdomadaires
└── .gitignore
```

---

### 📖 Documentation

- [Cahier des Charges](Cahier_des_Charges_Esk-2718.md)
- Documentation technique : *à venir*
- Guide utilisateur : *à venir*

---

### ⚙️ Stack technique

| Composant | Technologie |
|---|---|
| Langage | Python 3.14.7 |
| Interface graphique | PyQt6 (QGraphicsScene / QGraphicsView) |
| Réseau | socket (TCP/UDP), select, json |
| Multi-threading | QThread + Signals/Slots, threading |
| Base de données | sqlite3 |
| Graphiques | pyqtgraph |

---

### 📝 Note sur l'utilisation de l'IA

L'assistance d'un modèle de langage (LLM) a été utilisée pour la mise en forme de la documentation et la structuration du projet. Tous les choix techniques et fonctionnels ont été validés sous la responsabilité de l'auteur.
