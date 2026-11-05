# Format des Scénarios JSON

Les scénarios permettent de charger rapidement des situations spécifiques (ex: heures de pointe, bouchons, passage de véhicules d'urgence) sans avoir à placer manuellement chaque entité.

## Structure Globale

Un fichier scénario est un tableau JSON contenant des objets. Chaque objet représente une entité physique (véhicule, piéton, cycliste) à instancier dans la simulation.

### Exemple de Fichier

```json
[
  {
    "id": "v_1234",
    "type": "VOITURE",
    "pos_x": -30.0,
    "pos_y": -2.0,
    "cap": 0.0,
    "vitesse": 10.5
  },
  {
    "id": "vta_99",
    "type": "VIG_VTA",
    "pos_x": 40.0,
    "pos_y": 2.0,
    "cap": 3.14159,
    "vitesse": 15.0
  }
]
```

## Description des Champs

- **`id`** *(chaîne, optionnel)* : L'identifiant unique du véhicule. S'il n'est pas fourni, un UUID sera généré automatiquement.
- **`type`** *(chaîne, requis)* : Le type d'entité. Les valeurs possibles doivent correspondre à l'énumération `TypeVehicule` :
  - `VOITURE`
  - `POIDS_LOURD`
  - `CONVOI_EXCEPTIONNEL`
  - `VIG_VTA` (Véhicule d'Urgence)
  - `VIG_VTI`
  - `PIETON`
  - `CYCLISTE`
- **`pos_x`** *(flottant, requis)* : La coordonnée X de départ (en mètres). Le centre du carrefour est à `0.0`.
- **`pos_y`** *(flottant, requis)* : La coordonnée Y de départ (en mètres).
- **`cap`** *(flottant, requis)* : L'orientation de l'entité en radians.
  - `0.0` : Direction Est
  - `1.57` (π/2) : Direction Sud
  - `3.14` (π) : Direction Ouest
  - `-1.57` (-π/2) : Direction Nord
- **`vitesse`** *(flottant, optionnel, défaut: `0.0`)* : La vitesse initiale du véhicule en m/s.

## Ajout de Nouveaux Scénarios

Pour ajouter un nouveau scénario :
1. Créez un fichier `.json` dans `data/scenarios/`.
2. Ajoutez son nom et le chemin dans la méthode `charger_scenario` de `client_main.py` pour qu'il apparaisse dans l'interface utilisateur.
