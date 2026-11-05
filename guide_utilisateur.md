# Manuel d'Utilisation & Guide de l'Opérateur
## Poste de Contrôle et Simulation de Régulation Intelligente — Projet Esk-2718
### SAÉ 3.02 — BUT Réseaux & Télécommunications

---

| Référence Documentaire | Version | Date d'Édition | Auteur / Groupe |
|:---|:---:|:---:|:---:|
| **GUIDE-UTIL-ESK2718** | **2.0 — Finale** | Octobre 2026 | Julian Golde / Équipe Esk-2718 |

---

## 1. Introduction et Prise en Main du Poste de Contrôle

L'application **Esk-2718** met à la disposition des opérateurs de circulation urbaine un poste de commandement interactif en temps réel. Elle permet de visualiser, d'expérimenter et d'évaluer l'impact des régulations de carrefours à feux intelligents et des protocoles de communication V2X/V2I lors du passage de véhicules prioritaires.

### 1.1 Lancement de l'Application
Le poste de contrôle opérateur s'exécute sur le nœud client (ou sur un poste unique en boucle locale) :

```bash
# Activation de l'environnement virtuel
source venv/bin/activate   # (ou venv\Scripts\activate sous Windows)

# Lancement en mode standard (Plein écran immersif)
python3 src/client_main.py --ip 192.168.1.10

# Lancement en mode fenêtré maximisé (recommandé si petit écran de VM)
python3 src/client_main.py --ip 192.168.1.10 --windowed
```

---

## 2. Présentation de l'Interface Graphique (IHM)

L'écran principal de l'application est scindé en deux espaces de travail complémentaires : la **Scène Graphique 2D** à gauche et le **Panneau Latéral de Contrôle (Dashboard)** à droite.

```
+-------------------------------------------------------------+-------------------------------+
|                      SCÈNE 2D (80% Largeur)                 |   PANNEAU DE CONTRÔLE (20%)   |
|                                                             |                               |
|                     Voie Nord-Sud                           | [▶️ Démarrer / ⏸️ Pause]      |
|                           │                                 | Vitesse : [====●====] x1.0    |
|                           │                                 | Météo   : [ Dégagé      ▼ ]   |
|                           ▼                                 +-------------------------------+
|      ─────────────────────┬─────────────────────            |   CONTRÔLE DES FEUX           |
|                           │  Feu N-S                        | [Feu N-S: VERT] [Feu E-O: ROU] |
|                           │  (Vert/Rouge)                   +-------------------------------+
|      Voie Ouest-Est       │         Voie Ouest-Est          |   SPAWN D'USAGERS (1 à 5)     |
|      ═════════════════════╪═════════════════════            | [🚗 Voiture]    [🚛 Poids L.]  |
|                           │                                 | [🚨 VTA Secours][🚶 Piéton]   |
|                           │  Feu E-O                        | [🚴 Cycliste]   [Échap: Annul]|
|      ─────────────────────┴─────────────────────            +-------------------------------+
|                           ▲                                 |   HUD D'INSPECTION (Télém.)   |
|                           │                                 | ID : 9042 | Type : VOITURE    |
|                           │                                 | Vitesse   : 48.5 km/h         |
|                     Voie Sud-Nord                           | Freinage  : NON | ABS: OUI    |
|                                                             +-------------------------------+
|                                                             |   HISTORIQUE & EXPORT BDD     |
| [Hologramme fantôme sous le curseur de souris]              | [📜 Historique des simulations|
+-------------------------------------------------------------+-------------------------------+
```

### 2.1 La Scène Graphique 2D (`CarrefourScene`)
- **Infrastructure réaliste** : Représentation vectorielle aux normes urbaines d'un carrefour à 4 branches avec chaussée bitumée, marquages au sol blancs continus et discontinus, passages piétons protégés et bordures de trottoir.
- **Feux tricolores dynamiques** : Rendu visuel fidèle des optiques lumineuses avec halo lumineux rayonnant (Vert, Orange de transition, Rouge de sécurité).
- **Intempéries et effets météorologiques dynamiques** :
  - *Dégagé* : Asphalte sombre propre et visibilité maximale.
  - *Pluie* : Apparition de flaques d'eau sur la chaussée et réflexion spéculaire.
  - *Tempête* : Rafales venteuses influençant la masse volumique de l'air $\rho$.
  - *Gel / Verglas* : Nappe de givre bleutée recouvrant l'intersection avec dérapage et allongement notable des distances de freinage.
- **Hologramme de prévisualisation (Ghost Cursor)** : Lorsqu'un usager est sélectionné pour être placé, un rectangle fantôme semi-transparent vert en pointillés suit le curseur de la souris sur la voie d'approche, visualisant son gabarit et son orientation exacte avant tout clic.

---

## 3. Commandes et Pilotage de la Simulation

### 3.1 Gestion Temporelle
- **Bouton `▶️ Démarrer / ⏸️ Mettre en Pause`** : Démarre ou suspend instantanément le moteur physique ainsi que l'ensemble des entités mobiles.
- **Curseur de vitesse de simulation (`Slider Vitesse`)** : Permet de moduler la vitesse d'écoulement du temps physique entre **x0.1** (ralenti d'observation cinématique fine) et **x5.0** (accélération temporelle pour tests de charge de trafic).

### 3.2 Contrôle Météorologique
Le menu déroulant *Météo* modifie instantanément les paramètres du moteur physique et de la scène graphique :
- **Dégagé** : Adhérence nominale ($K_{\text{adh}} = 1.0$), densité de l'air $\rho = 1.225\,\text{kg/m}^3$.
- **Pluie** : Adhérence réduite ($K_{\text{adh}} = 0.70$), distance d'arrêt allongée de 40%.
- **Tempête** : Forte résistance au vent ($\rho = 2.5\,\text{kg/m}^3$), adhérence dégradée ($K_{\text{adh}} = 0.45$).
- **Gel** : Adhérence critique ($K_{\text{adh}} = 0.20$), risque de perte de contrôle en cas de freinage brusque sans ABS.

### 3.3 Contrôle Forcé des Feux Tricolores
Deux boutons de forçage manuel permettent à l'opérateur de prendre la main sur les automates de feux :
- **Bouton `Feux Nord-Sud`** : Force le passage au vert sur l'axe Nord-Sud (basculant l'axe perpendiculaire au rouge).
- **Bouton `Feux Est-Ouest`** : Force le passage au vert sur l'axe Est-Ouest.

### 3.4 Injection de Scénarios Prédéfinis
Le menu déroulant de scénarios permet d'initialiser des configurations d'essai normalisées :
1. **Scénario `Heure de Pointe`** : Génère un trafic dense sur les quatre voies avec flux piétons continus, testant les capacités de régulation sans saturation.
2. **Scénario `Urgences (VTA)`** : Injecte un véhicule de secours à grande vitesse abordant un axe au feu rouge pour démontrer la réactivité de l'onde verte V2I.

---

## 4. Guide des Raccourcis Clavier et Interactions Souris

Pour maximiser l'efficacité de l'opérateur, l'ensemble des opérations d'injection et de sélection est accessible par raccourcis clavier directs :

| Touche / Action | Rôle Opérationnel | Description Pratique |
|:---:|:---|:---|
| <kbd>1</kbd> | **Sélectionner Voiture** | Active le placement d'un véhicule léger de tourisme ($1500\,\text{kg}$, vitesse de consigne $50\,\text{km/h}$). |
| <kbd>2</kbd> | **Sélectionner Poids Lourd** | Active le placement d'un semi-remorque ($25\,\text{t}$, gabarit $12\,\text{m}$, vitesse bridée à $40\,\text{km/h}$). |
| <kbd>3</kbd> | **Sélectionner VTA (Secours)** | Active le placement d'un véhicule prioritaire V2X avec gyrophare actif et demande de priorité d'urgence. |
| <kbd>4</kbd> | **Sélectionner Piéton** | Active le placement d'un piéton traversant sur les bandes protégées ($1.5\,\text{m/s}$). |
| <kbd>5</kbd> | **Sélectionner Cycliste** | Active le placement d'un deux-roues ($90\,\text{kg}$, vitesse de consigne $20\,\text{km/h}$). |
| <kbd>Échap</kbd> | **Annuler Outil en cours** | Désactive immédiatement l'outil de placement et efface l'hologramme fantôme de la scène. |
| <kbd>Clic Gauche</kbd> *(sur route)* | **Placer un usager** | Positionne l'entité sélectionnée sur la voie la plus proche avec orientation automatique. |
| <kbd>Shift</kbd> + <kbd>Clic</kbd> | **Placement Multiple / Rafale** | Maintient l'outil actif après le clic, permettant de semer une file ininterrompue de véhicules. |
| <kbd>Clic Gauche</kbd> *(sur usager)*| **Inspecter une entité** | Sélectionne l'entité ciblée : son identifiant apparaît dans le HUD d'inspection télémétrique. |
| **Boutons Directionnels** | **Ordonner un Virage** | Les boutons *Nord*, *Sud*, *Est*, *Ouest* ordonnent à l'entité sélectionnée de bifurquer à l'intersection. |

---

## 5. HUD Télémétrique d'Inspection en Temps Réel

Lorsqu'un usager de la route est sélectionné d'un clic gauche sur la scène 2D, le bloc télémétrique **HUD** (Head-Up Display) du panneau latéral affiche instantanément ses caractéristiques physiques dynamiques rafraîchies à 60 FPS :

```text
======================================
     HUD TÉLÉMÉTRIQUE OPÉRATEUR
======================================
Identifiant Entité : #8492
Catégorie d'Usager : VOITURE (Tourisme)
Masse du Véhicule  : 1540.2 kg
Vitesse Réelle     : 49.8 km/h (13.8 m/s)
Accélération Nette : +0.45 m/s²
Consigne Moteur    : 1.20 m/s²
Cap Orientationnel : 0.00 rad (Est)
Position (X, Y)    : X=-18.4 m | Y=2.0 m
État du Freinage   : INACTIF
Équipement ABS     : ÉQUIPÉ (Actif)
Usure Pneumatiques : 14.2% (Âge: 3.2 ans)
Force Aérodynamique: 124.6 N
Résistance Roulem. : 226.5 N
======================================
```

Ce panneau permet à l'évaluateur de vérifier le comportement des algorithmes physiques : décélération progressive devant un feu orange/rouge, maintien de la distance d'arrêt de sécurité avec le véhicule qui précède, et accélération fluide lors du passage au vert.

---

## 6. Historique, Visualisation Scientifique et Export CSV

L'application intègre une chaîne d'analyse statistique complète adossée à la base de données relationnelle SQLite.

```
       [Base SQLite : metrics.db]
                   │
                   ▼
       [Dialogue d'Historique] ─── Sélection d'une session de test
                   │
         ┌─────────┴─────────┐
         │                   │
         ▼                   ▼
 [📈 Visualiser]     [📁 Exporter CSV]
 Fenêtre pyqtgraph   Fichier .csv pour
 Courbes Vitesse/    tableurs (Excel, R,
 Densité de trafic   Pandas, Notebooks)
```

### 6.1 Consultation de l'Historique des Simulations
1. Cliquer sur le bouton **`📜 Historique des simulations`** situé au bas du panneau latéral.
2. Une boîte de dialogue modale s'ouvre, interrogeant la table SQLite `simulations`.
3. Chaque ligne récapitule :
   - L'identifiant unique de la session (`ID`).
   - La date et heure de début de session (`Date de Début`).
   - Le scénario exécuté (`Scénario`).
   - La durée totale de simulation en secondes (`Durée (s)`).
   - Le volume d'échantillons de métriques collectés (`Nb Métriques`).

### 6.2 Visualisation Graphique Interactive (`pyqtgraph`)
1. Dans le tableau d'historique, sélectionner une session en cliquant sur sa ligne.
2. Cliquer sur le bouton **`📈 Visualiser les Courbes`** (ou double-cliquer sur la ligne).
3. La fenêtre scientifique `FenetreGraphiques` s'affiche avec deux graphiques temporels synchronisés :
   - **Courbe Supérieure (Cyan)** : Évolution de la vitesse moyenne de la flotte ($\text{km/h}$) au cours du temps.
   - **Courbe Inférieure (Or)** : Nombre de véhicules et usagers présents simultanément sur le carrefour.
4. **Interactivité du tracé** :
   - **Zoom** : Faire défiler la molette de la souris pour zoomer avant/arrière.
   - **Panoramique (Pan)** : Maintenir le clic gauche enfoncé pour déplacer la fenêtre temporelle.
   - **Menu contextuel** : Clic droit sur le graphique pour exporter l'image au format PNG/SVG ou réinitialiser l'échelle des axes.

### 6.3 Exportation des Données au Format CSV
1. Depuis la fenêtre d'historique, sélectionner la simulation désirée.
2. Cliquer sur **`📁 Exporter la sélection en CSV`**.
3. Une boîte de dialogue de sauvegarde s'ouvre : choisir l'emplacement et le nom du fichier (par exemple `rapport_trafic_session_12.csv`).
4. Le fichier généré est structuré comme suit :
   ```csv
   id;timestamp;nb_vehicules;vitesse_moyenne;nb_pietons;nb_incidents
   1;2026-10-19 21:30:15;8;48.50;2;0
   2;2026-10-19 21:30:17;12;46.20;3;0
   3;2026-10-19 21:30:19;16;41.10;4;0
   4;2026-10-19 21:30:21;18;35.80;4;0
   ```
5. Ce format CSV standard peut être directement importé dans Microsoft Excel, LibreOffice Calc, ou chargé dans un script Python d'analyse de données (via `pandas.read_csv`).

---
*Fin du guide utilisateur Esk-2718.*
