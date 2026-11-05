# Documentation V2X / V2I et Base de Données

Ce document décrit l'architecture réseau et la gestion des données de la simulation Esk-2718.

## 1. Architecture V2X et V2I

La simulation repose sur une architecture de communication décentralisée permettant aux véhicules et à l'infrastructure d'échanger des informations en temps réel.

### V2I (Vehicle-to-Infrastructure)
- Les véhicules communiquent avec l'intersection (les feux tricolores, les capteurs) pour annoncer leur approche.
- L'infrastructure répond en ajustant les cycles de feux, notamment pour accorder la priorité aux véhicules d'urgence (VTA).

### V2X (Vehicle-to-Everything)
- Les véhicules partagent leurs données télémétriques (vitesse, cap, position) avec les autres véhicules.
- Cela permet un comportement coopératif : freinage d'urgence anticipé, évitement de collisions et gestion des dépassements.

## 2. Communication par Sockets

Le projet utilise des sockets TCP/IP pour scinder la simulation en un client (affichage et physique locale) et un serveur (supervision, base de données et synchronisation globale).

- **ClientNode** (`src/network/client_node.py`) : Envoie périodiquement l'état des entités locales au serveur et reçoit les commandes globales (changement de feux, alertes VTA).
- **ServerNode** (`src/network/server_node.py`) : Centralise les connexions, agrège les métriques de trafic, gère l'état global de l'intersection et sauvegarde les événements dans la base de données.

Les données transitent sérialisées au format JSON, assurant légèreté et interopérabilité.

## 3. Gestion de la Base de Données (SQLite)

Le serveur maintient une base de données locale (SQLite) pour historiser la simulation. Cela permet des analyses a posteriori (ex: densité moyenne, temps d'attente, efficacité des feux).

### Structure
- **Table `metrics`** : Sauvegarde régulière (ex: toutes les secondes) du nombre de véhicules, vitesse moyenne, etc.
- **Table `events`** : Enregistre les événements ponctuels (ex: passage au rouge d'un véhicule, déclenchement d'une urgence VTA).

### Accès
Les appels à la base de données (ex: via `db_manager.py`) sont asynchrones ou exécutés dans un thread dédié pour ne pas bloquer la boucle réseau principale.
