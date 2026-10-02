# Architecture Réseau et Threads - SAE 3.02

Ce document résume la conception technique de la séparation Client / Serveur de la simulation de carrefour, implémentée avec des sockets bruts et la gestion multi-thread via PyQt6 et Python natif.

## 1. Topologie Réseau

Le système est désormais divisé en deux entités distinctes qui peuvent tourner sur des machines séparées (ex: 2 VMs Debian) :

*   **Le Serveur (server_main.py)** : C'est le chef d'orchestre. Il gère l'état global du trafic (les feux tricolores), autorise les passages d'urgence et stocke les statistiques.
*   **Le Client (client_main.py)** : C'est l'interface utilisateur. Il affiche la simulation 2D, exécute la physique locale (moteur cinématique) et informe le serveur des événements d'urgence.

### Protocoles Utilisés
*   **TCP (Transmission Control Protocol) - Port 5000** : Utilisé pour les flux nécessitant une fiabilité absolue.
    *   *Serveur -> Client* : État des feux tricolores.
    *   *Client -> Serveur* : Envoi des métriques (nombre de véhicules, vitesse moyenne) pour l'enregistrement SQLite3.
*   **UDP (User Datagram Protocol) - Port 5001** : Utilisé pour les flux nécessitant une faible latence (alertes d'urgence).
    *   *Client -> Serveur* : Requête de forçage de feu au vert par un VTA (Véhicule de Transport Aménagé / Prioritaire). Pour pallier la perte de paquets UDP, l'alerte est envoyée en rafale (toutes les 200ms) tant que le VTA est dans la zone.

## 2. Gestion des Threads (Concurrence)

Afin d'éviter le blocage de l'interface graphique (GUI) et garantir un temps réel fluide, le programme utilise intensivement le multithreading.

### Sur le Client
1.  **Thread Principal (Main GUI Thread)** : Gère exclusivement PyQt6 (`CarrefourScene`, clics souris, rafraîchissement des boutons).
2.  **Thread Physique (`MoteurSimulation` étendant `QThread`)** : Calcule les positions d'Euler (accélération, freinage, cap) toutes les 16ms (60 FPS). Il n'interagit jamais directement avec l'UI, mais émet un signal `tick_simulation`.
3.  **Thread Réseau (`ClientNode` étendant `threading.Thread`)** : Boucle infinie non-bloquante avec `select.select()` qui écoute simultanément les sockets TCP et UDP entrants, et parse les flux JSON sans geler la simulation.

### Sur le Serveur
1.  **Thread Principal** : Initialise la configuration et bloque sur un `.join()` en attendant l'arrêt manuel.
2.  **Thread Réseau & Simulation (`ServerNode`)** : Maintient le cycle des feux via `IntersectionManager` et gère le multiplexage des sockets avec `select.select()`.

## 3. Fiabilité et Tolérance aux Pannes

*   **Bufferisation TCP** : La réception `socket.recv(1024)` ne garantit pas la réception d'un JSON complet (morcellement). Le serveur et le client stockent les flux dans des buffers textuels et découpent les requêtes uniquement lorsqu'un saut de ligne `\n` est détecté.
*   **Crash Windows Loop** : Si un socket est fermé de manière inopinée, Windows génère des exceptions `OSError` ou `ValueError` (sur `fileno()`). Celles-ci sont explicitement capturées dans les boucles `select` pour fermer proprement les sockets fantômes et relancer une tentative de reconnexion automatique sans faire planter les applications.
