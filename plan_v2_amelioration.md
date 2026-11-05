# Plan d'Implémentation : Refonte Majeure de la Simulation (V2)

## Description de l'objectif
Transformer le MVP basique en un moteur de simulation professionnel et réaliste. Cela implique le passage d'une cinématique 1D (axe X) à une **cinématique 2D vectorielle** (Euclidienne) permettant les virages et la gestion des voies. L'interface graphique (IHM) sera profondément remaniée pour offrir une échelle spatio-temporelle réaliste, du relief (ombres, animations météo), et une interactivité totale (Drag & Drop, HUD des entités, contrôle manuel des feux, curseur de temps). Enfin, la logique métier intégrera le système tricolore, le Code de la route, et l'algorithme de fluidification pour les véhicules prioritaires (VPI/VPO).

---

## ⚠️ À Valider par l'Utilisateur (User Review Required)
- **Format des Scénarios** : Vous avez mentionné `XML` ou autre pour la base de données de scénarios. Êtes-vous ouvert à utiliser le format `JSON` ? Il est nativement beaucoup plus rapide et lisible en Python pour sérialiser des états de simulation, bien que le XML soit tout à fait faisable si imposé par un client.
- **Guidage Vectoriel** : Pour permettre aux véhicules de tourner, nous utiliserons un système de "Waypoints" (points de passage) couplé à un algorithme de *Steering Behaviors* (comportements de pilotage) pour des courbes fluides. Confirmez-vous cette approche ?

---

## Modifications Proposées

### 1. Moteur Physique & Vectoriel (`src/simulation/`)
- **[MODIFY] `vehicules.py`** : 
  - Remplacement des tuples `(x, y)` par des vecteurs 2D (librairie `numpy` ou implémentation Euclidienne maison).
  - Ajout des vecteurs de `Direction` (cap) et d'`Accélération`.
  - Implémentation du Freinage Moteur (décélération douce) vs Freinage Mécanique (urgence).
- **[MODIFY] `environnement.py`** :
  - Ajout de la composante Aérodynamique (Vecteur Vent, densité de l'air). La résistance de l'air $F_{aero} = \frac{1}{2} \rho v^2 S C_x$ impactera l'énergie cinétique.
- **[MODIFY] `moteur.py`** :
  - Intégration du paramètre "Échelle de temps" (Time Scale) modifiable dynamiquement (ex: x0.5, x1, x2).
  - Résolution du bug d'échelle temporelle : 1 mètre dans la simulation vaudra X pixels à l'écran (ex: 1m = 10px). Une voiture à 50 km/h (13.8 m/s) bougera de 138 pixels par seconde, garantissant un rendu fluide.

### 2. Rendu Graphique & Animations (`src/gui/carrefour_scene.py`)
- **[MODIFY] `carrefour_scene.py`** :
  - **Refonte de l'infrastructure** : Véritables voies délimitées (2 voies par axe avec sens de circulation), alignement correct des 4 passages piétons, et ajout des pistes cyclables en bordure.
  - **Relief & Héros** : Utilisation de `QGraphicsDropShadowEffect` sur les véhicules et les arbres pour simuler la 3D/l'éclairage.
  - **Animations Météo** : Si pluie, génération de `QGraphicsItem` temporaires (gouttes/flaques) mis à jour à chaque frame. Arbres animés par des rotations sinusoïdales (vent).
  - **Interaction** : Implémentation des événements de clic pour placer les véhicules sur une voie précise.

### 3. Logique Routière & Régulation (`src/simulation/`)
- **[NEW] `intersection.py`** :
  - Gestionnaire de Feux Tricolores (Rouge, Orange, Vert).
  - Algorithme de détection de présence (Zone d'approche) et de respect du Code de la Route (arrêt au feu).
  - **Algorithme VPI/VPO** : Si un VTA est détecté dans un rayon de X mètres, forçage d'une phase de dégagement (passage au vert pour le VTA, rouge pour les autres).

### 4. Panneau de Contrôle & HUD (`src/gui/dashboard.py`)
- **[MODIFY] `dashboard.py`** :
  - Ajout d'un curseur (Slider) de vitesse de simulation.
  - Boutons de forçage manuel des feux.
  - Menu déroulant `QComboBox` pour charger des scénarios prédéfinis.
- **[NEW] `hud_vehicule.py`** (ou Widget intégré) :
  - Affichage au survol/clic d'une entité de sa télémetrie en temps réel (Masse, Pneus, Énergie cinétique $E_c = \frac{1}{2}mv^2$, Freinage en cours).

---

## Plan de Vérification
### Vérification Automatisée
- Création de tests unitaires (via `pytest` ou `unittest`) pour vérifier les formules mathématiques : `test_energie_cinetique`, `test_freinage_moteur`, `test_vecteur_virage`.
### Vérification Manuelle
- Ajuster le slider de temps et vérifier que la physique (distances de freinage) reste constante mathématiquement.
- Placer un véhicule VTA via clic de souris et observer le changement des feux tricolores.
- Charger un scénario XML/JSON (ex: "Heure de pointe + Pluie") et vérifier l'apparition cohérente des entités sur leurs voies respectives.