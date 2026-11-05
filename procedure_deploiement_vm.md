# Fiche de Procédure de Déploiement Multi-VM (Debian)
## Projet SAÉ 3.02 — Esk-2718 : Régulation Intelligente de Carrefours & V2X/V2I
### IUT de Colmar — Département Réseaux & Télécommunications

---

| Référence Documentaire | Version | Date d'Édition | Auteur / Groupe | Cible Système |
|:---|:---:|:---:|:---:|:---:|
| **PROC-DEPLOY-VM-01** | **2.0 — Finale** | Octobre 2026 | Julian Golde / Esk-2718 | Debian 11 (Bullseye) / Debian 12 (Bookworm) |

---

## 1. Présentation de l'Architecture Multi-VM

Conformément aux exigences impératives du cahier des charges de la SAÉ 3.02, l'application distribuée **Esk-2718** repose sur une architecture client-serveur stricte répartie sur **deux machines virtuelles Debian indépendantes**. Aucune base de données ni mémoire partagée n'existe entre les deux machines : tous les flux transactionnels et temps réel transitent exclusivement par le réseau via des sockets brutes (TCP/UDP).

```
   ┌────────────────────────────────────────────────────────┐
   │                     VM 1 — SERVEUR                     │
   │               (Centre de Supervision Urbain)           │
   │                                                        │
   │  - Régulateur d'Intersection (Logique V2I des Feux)    │
   │  - Multiplexeur Réseau Asynchrone (select.select)      │
   │  - Base de Données Locale SQLite (metrics.db)          │
   │  - Console de Supervision & Télémétrie                 │
   │                                                        │
   │  IP configurée : 192.168.1.10 (ou écoute sur 0.0.0.0)  │
   └───────────────▲────────────────────────▲───────────────┘
                   │                        │
       Flux TCP    │                        │  Flux UDP
       Port 5000   │                        │  Port 5001 (Serveur)
   (Fiable/Métrique│                        │  Port 5002 (Client)
      /Synchronis.)│                        │  (Alertes VTA / Ack)
                   │                        │
   ┌───────────────▼────────────────────────▼───────────────┐
   │                      VM 2 — CLIENT                     │
   │              (Moteur de Simulation & IHM)              │
   │                                                        │
   │  - Moteur Physique 2D (Euler, Aérodynamique, Adhérence)│
   │  - Interface Graphique PyQt6 (QGraphicsScene 60 FPS)   │
   │  - Panneau Opérateur, HUD & Graphiques (pyqtgraph)     │
   │  - Émetteur d'Alertes Prioritaires V2X (VTA / VTI)     │
   │                                                        │
   │  IP configurée : 192.168.1.20                          │
   └────────────────────────────────────────────────────────┘
```

### 1.1 Rôle et utilité de la VM 1 (Nœud Serveur — Infrastructure & Supervision)
1. **Régulateur intelligent d'intersection (V2I)** : Il détient l'autorité exclusive sur le cycle des feux tricolores. En régime normal, il orchestre les cycles selon les temporisations définies. Dès réception d'un signal d'urgence émis par un véhicule prioritaire, il arbitre le carrefour et force instantanément le passage au vert pour l'axe concerné en sécurisant l'axe perpendiculaire.
2. **Multiplexage réseau asynchrone non-bloquant** : Grâce à l'appel système `select.select()`, il maintient les connexions TCP simultanées de multiples clients de simulation tout en écoutant en continu les paquets UDP entrants sans latence ni gel de processus.
3. **Persistance des métriques et historisation (SQLite3)** : Le serveur alimente une base relationnelle locale (`metrics.db`). Il y enregistre la chronologie des simulations, les séries temporelles de trafic (densité, vitesse moyenne de passage), les événements notables (franchissements, alertes d'urgence) et l'historique complet des basculements de feux.
4. **Légèreté et robustesse headless** : La VM 1 ne requiert aucun serveur d'affichage X11 lourd. Elle fonctionne sous la forme d'un service de contrôle console, minimisant l'empreinte mémoire et garantissant une haute disponibilité.

### 1.2 Rôle et utilité de la VM 2 (Nœud Client — Simulation Dynamique & Poste Opérateur)
1. **Moteur cinématique et dynamique vectoriel** : Exécuté dans un `QThread` haute performance dédié, il calcule toutes les 16 ms (60 Hz) les vecteurs d'accélération, de vitesse et de position de chaque entité mobile en appliquant une intégration d'Euler couplée aux lois de frottement aérodynamique ($F_{aéro}$) et mécanique ($C_{rr}$ modélisé selon la météo et l'état des pneumatiques).
2. **Poste de pilotage et Interface Homme-Machine (PyQt6)** : Offre à l'opérateur du poste de commande une vue graphique 2D temps réel (`QGraphicsView` / `QGraphicsScene`), un panneau de contrôle pour injecter des aléas (météo, virages, scénarios), un affichage télémétrique tête-haute (HUD) et un dialogue d'analyse statistique avec courbes `pyqtgraph`.
3. **Émetteur d'urgences V2X (Véhicules Toutes Alertes — VTA)** : Détecte l'approche des véhicules de secours dans un rayon d'action de 70 mètres du carrefour et émet instantanément des trames UDP `vta_alert` vers le serveur, tout en réceptionnant les acquittements `ack` et les diffusions d'état des feux.
4. **Génération continue et respect du code de la route** : Injecte continuellement des flux de véhicules légers, poids lourds, deux-roues et piétons respectant rigoureusement le code de la route (conduite parfaite).

---

## 2. Prérequis Système et Environnement de Déploiement

### 2.1 Synthèse des prérequis matériels et logiciels
- **Hyperviseur supporté** : KVM / QEMU (`virsh`), Proxmox VE, VirtualBox (≥ 7.0) ou VMware Workstation.
- **Système d'Exploitation** : Debian GNU/Linux 11 (Bullseye) ou 12 (Bookworm) 64 bits.
- **Ressources minimales par VM** :
  - **VM 1 (Serveur)** : 1 vCPU, 1024 Mo RAM, 8 Go disque, 1 interface réseau.
  - **VM 2 (Client IHM)** : 2 vCPUs, 2048 Mo RAM, 10 Go disque, 1 interface réseau, support graphique 2D.
- **Python cible** : Python 3.9 à 3.14 (Python standard Debian avec paquet `python3-venv`).
- **Objectif de déploiement** : Moins de 30 minutes de bout en bout pour un opérateur tiers.

---

## 3. Procédure Pas à Pas de Déploiement (< 30 minutes)

### Étape 1 : Configuration Réseau des Deux Machines Virtuelles (Durée : 5 min)

Pour permettre la communication directe par sockets, les deux VMs doivent appartenir au même domaine de diffusion (sous-réseau IP).

#### Option A : Configuration sous VirtualBox
1. Sur les deux VMs, ouvrir les **Paramètres** -> **Réseau** -> **Adaptateur 1**.
2. Choisir le mode **Réseau privé hôte** (Host-Only Adapter, ex: `vboxnet0`) ou **Accès par pont** (Bridged Adapter) connecté à votre carte réseau physique.
3. Vérifier que le mode promiscuous est réglé sur *Autoriser tout* ou *Autoriser les VMs*.

#### Option B : Configuration sous KVM / virsh
1. Les deux VMs peuvent être attachées au commutateur virtuel par défaut `virsh default` (`virbr0`, sous-réseau `192.168.122.0/24`) ou à un pont isolé (`br0`).
2. Pour vérifier la table des baux DHCP KVM :
   ```bash
   virsh net-dhcp-leases default
   ```

#### Attribution des adresses IP d'exemple retenues dans ce guide
- **VM 1 (Serveur)** : `192.168.1.10/24`
- **VM 2 (Client)** : `192.168.1.20/24`

*(Si vos VMs obtiennent des adresses différentes via DHCP, relevez simplement l'adresse de VM 1 avec la commande `ip -br a` et reportez-la lors de la configuration).*

---

### Étape 2 : Préparation du Système d'Exploitation Debian (Durée : 5 min)

Exécuter les commandes suivantes sur **chacune des deux VMs** (ouvrir une session terminal ou SSH) :

```bash
# 1. Mise à jour des index des dépôts officiels Debian
sudo apt update && sudo apt upgrade -y

# 2. Installation des paquets système indispensables
sudo apt install -y python3 python3-pip python3-venv git iproute2 net-tools curl

# 3. Sur la VM 2 UNIQUEMENT (Installation des bibliothèques C pour PyQt6 et X11)
sudo apt install -y libgl1-mesa-glx libegl1 libxkbcommon-x11-0 \
                    libfontconfig1 libdbus-1-3 libxcb-cursor0 \
                    libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
                    libxcb-randr0 libxcb-render-util0 libxcb-shape0 \
                    libxcb-xfixes0 libx11-xcb1 xauth
```

> **Note relative à l'affichage graphique sur VM 2** : Si vous vous connectez à la VM 2 via SSH depuis votre machine hôte, utilisez l'option `-X` ou `-Y` (`ssh -Y utilisateur@192.168.1.20`) pour activer le déport d'affichage X11, ou connectez-vous directement sur l'environnement de bureau graphique de la VM.

---

### Étape 3 : Récupération du Projet et Création de l'Environnement Virtuel (Durée : 4 min)

Effectuer ces opérations successivement sur **VM 1** puis sur **VM 2** :

```bash
# 1. Positionnement dans le répertoire de travail
cd ~

# 2. Récupération des sources du projet
git clone https://github.com/votre-compte/SAE302-Esk2718.git esk2718
# OU copier le dossier du projet via scp/rsync si déploiement hors-ligne :
# scp -r "SAE 3.02- Développer une application communicante" utilisateur@192.168.1.10:~/esk2718

cd esk2718

# 3. Création d'un environnement virtuel Python dédié et isolé
python3 -m venv venv

# 4. Activation de l'environnement virtuel
source venv/bin/activate

# 5. Mise à jour de pip
pip install --upgrade pip
```

---

### Étape 4 : Installation des Dépendances Logicielles (Durée : 5 min)

Dans l'environnement virtuel activé (`(venv)` affiché dans votre prompt) sur **VM 1** et **VM 2** :

```bash
pip install -r requirements.txt
```

*Contenu installé selon `requirements.txt` strict :*
- `PyQt6` (et ses modules sous-jacents Qt6 et sip)
- `pyqtgraph` (moteur de traçage de courbes scientifiques)
- `numpy` (calcul matriciel haute performance)

Pour certifier la validité de l'installation sur VM 1 ou VM 2, exécuter la suite de tests automatisés :
```bash
python3 run_tests.py
```
> Le script doit retourner : `>>> VERDICT : SUCCÈS INTÉGRAL — 100% DES TESTS SONT VALIDES.`

---

### Étape 5 : Configuration Réseau (Durée : 3 min)

L'adresse IP du serveur ne doit **jamais être codée en dur**. Deux méthodes sont supportées :

#### Méthode A (Recommandée) : Édition du fichier `config.json`
Sur la **VM 2 (Client)**, ouvrir le fichier de configuration avec un éditeur de texte :
```bash
nano config.json
```
Modifier le contenu pour renseigner l'adresse IP réelle de la VM 1 :
```json
{
    "server_ip": "192.168.1.10",
    "server_tcp_port": 5000,
    "server_udp_port": 5001,
    "client_udp_port": 5002
}
```
*(Sauvegarder avec `Ctrl+O`, valider avec `Entrée`, quitter avec `Ctrl+X`).*

Sur la **VM 1 (Serveur)**, le fichier `config.json` peut conserver `"server_ip": "0.0.0.0"` ou `"127.0.0.1"`, la CLI permettant de forcer l'écoute globale.

#### Méthode B : Surcharge directe en Ligne de Commande (CLI)
Il est possible de ne pas modifier `config.json` et de passer directement les adresses et ports en argument lors du lancement (cf. Étape 6).

---

### Étape 6 : Démarrage des Composants (Durée : 3 min)

#### 1. Démarrage du Serveur sur la VM 1
Sur la **VM 1**, exécuter la commande suivante :
```bash
cd ~/esk2718
source venv/bin/activate
python3 src/server_main.py --ip 0.0.0.0 --tcp-port 5000 --udp-port 5001
```

**Affichage attendu dans la console VM 1 :**
```text
====================================================================
  [ESK-2718] SUPERVISION DU CARREFOUR INTELLIGENT (V2X / V2I)
--------------------------------------------------------------------
  Écoute Réseau       : TCP 0.0.0.0:5000 | UDP :5001
  État des Feux       : Nord-Sud = [VERT] | Est-Ouest = [ROUGE]
  Clients Connectés   : 0
      (Aucun client connecté)
  Métriques BDD       : 0 trames enregistrées
  Alertes VTA Reçues  : 0 | Dernière alerte: Aucune
====================================================================
[Serveur] Le carrefour est actif. Appuyez sur [Entrée] ou [Ctrl+C] pour arrêter.
```

#### 2. Démarrage du Client / Simulateur sur la VM 2
Sur la **VM 2**, dans un terminal avec accès à l'affichage graphique X11 :
```bash
cd ~/esk2718
source venv/bin/activate
# Lancement standard (utilise config.json ou surcharge CLI)
python3 src/client_main.py --ip 192.168.1.10 --tcp-port 5000 --udp-port 5001

# ASTUCE : Si l'écran de la VM a une petite résolution, ajouter --windowed :
# python3 src/client_main.py --ip 192.168.1.10 --windowed
```

**Comportement attendu sur VM 2 :**
- L'interface graphique s'ouvre immédiatement en plein écran (ou fenêtre maximisée).
- La scène 2D affiche le carrefour avec ses feux synchronisés sur l'état du serveur.
- La console indique : `[ClientNode] Connexion TCP établie avec succès vers le serveur.`

---

## 4. Grille de Validation (Checklist de Recette Rapide)

L'évaluateur ou le binôme de recette croisée peut certifier le bon fonctionnement en vérifiant les points suivants en moins de 5 minutes :

| # | Test Fonctionnel | Action de l'Évaluateur | Résultat Attendu sur VM 1 | Résultat Attendu sur VM 2 | Statut |
|:---:|:---|:---|:---|:---|:---:|
| **REC-01** | **Établissement TCP** | Lancer VM 1 puis VM 2. | La supervision console affiche : `Clients Connectés : 1 (client_...)`. | La console client affiche : `Connexion TCP établie`. Le voyant d'état est actif. | [ ] |
| **REC-02** | **Synchronisation Feux** | Observer le carrefour pendant 15 s. | Les états des feux alternent périodiquement dans la console. | Les feux tricolores graphiques changent de couleur de façon identique au serveur. | [ ] |
| **REC-03** | **Collecte Métriques** | Laisser tourner la simulation 10 s. | Le compteur `Métriques BDD` s'incrémente toutes les 1 à 2 secondes. | Le client envoie périodiquement le débit et la vitesse moyenne. | [ ] |
| **REC-04** | **Urgence V2I (VTA)** | Appuyer sur la touche `3` et cliquer sur une voie Nord-Sud pour placer un VTA. | `Alertes VTA Reçues` s'incrémente. Message immédiat `[VTA-ALERTE]`. Le feu NS passe instantanément au VERT. | L'ambulance avance prioritairement ; le feu Nord-Sud est au VERT. L'ack UDP est reçu. | [ ] |
| **REC-05** | **Contrôle BDD SQLite** | Exécuter sur VM 1 : `sqlite3 data/metrics.db "SELECT COUNT(*) FROM metriques;"`. | Un nombre supérieur à 0 est retourné (ex: `15`). | Les données ont bien été enregistrées sans blocage. | [ ] |
| **REC-06** | **Dépassement et Code** | Observer les véhicules non-prioritaires. | — | Tous les véhicules s'arrêtent au feu rouge et respectent les distances de sécurité. | [ ] |
| **REC-07** | **Graphiques Historiques** | Sur VM 2, cliquer sur *📜 Historique* puis *📈 Visualiser*. | — | Une fenêtre s'ouvre avec les courbes pyqtgraph de vitesse et densité. | [ ] |
| **REC-08** | **Exportation CSV** | Dans l'historique, cliquer sur *📁 Exporter en CSV*. | — | Le fichier CSV est généré avec les colonnes `timestamp`, `nb_vehicules`, `vitesse_moyenne`. | [ ] |
| **REC-09** | **Tolérance aux pannes** | Couper brutalement VM 2 (`Ctrl+C`). | VM 1 détecte la déconnexion proprement sans crasher : `Client déconnecté. Clients restants: 0`. | Arrêt propre du nœud client. | [ ] |
| **REC-10** | **Reconnexion auto** | Relancer VM 2 après la coupure. | VM 1 réaccepte le client instantanément (`Clients Connectés : 1`). | VM 2 reprend sa synchronisation réseau sans redémarrer le serveur. | [ ] |

---

## 5. Procédure de Dépannage et Diagnostic Réseau

Si une difficulté survient lors de la mise en service, suivre l'arbre de résolution ci-dessous :

### 5.1 Test de connectivité élémentaire (ICMP / Ping)
Depuis la **VM 2**, tester l'accessibilité de la **VM 1** :
```bash
ping -c 4 192.168.1.10
```
- **Si 100% de perte de paquets** :
  1. Vérifier l'adressage IP sur les deux machines avec `ip -br a`.
  2. Vérifier que les interfaces virtuelles sont UP (`sudo ip link set dev eth0 up` ou `enp0s3`).
  3. Vérifier les réglages de l'hyperviseur (les deux VMs doivent être sur le même adaptateur hôte ou le même bridge).

### 5.2 Vérification de l'écoute des ports sur VM 1
Sur la **VM 1**, vérifier que les sockets TCP et UDP sont effectivement ouvertes et en écoute :
```bash
ss -tulpn | grep -E '5000|5001'
```
*Sortie attendue :*
```text
tcp   LISTEN 0      10     0.0.0.0:5000   0.0.0.0:*    users:(("python3",pid=...,fd=...))
udp   UNCONN 0      0      0.0.0.0:5001   0.0.0.0:*    users:(("python3",pid=...,fd=...))
```
- Si la commande ne retourne rien : le script `server_main.py` n'a pas été lancé ou s'est arrêté à la suite d'une erreur de syntaxe ou de liaison. Consulter le fichier `server_fatal_crash.log`.

### 5.3 Diagnostic de pare-feu Linux (UFW / nftables / iptables)
Debian peut bloquer les ports entrants si un pare-feu est actif :
```bash
# Vérification du statut UFW
sudo ufw status

# Si UFW est actif, autoriser expressément les ports du projet :
sudo ufw allow 5000/tcp comment 'Esk-2718 TCP Server'
sudo ufw allow 5001/udp comment 'Esk-2718 UDP Server'
sudo ufw allow 5002/udp comment 'Esk-2718 UDP Client'

# Pour désactiver temporairement UFW à des fins de test :
sudo ufw disable
```

### 5.4 Test de boucle locale (Sanity Check en local sur une seule VM)
Pour valider l'intégrité de la chaîne logicielle indépendamment du réseau physique, vous pouvez exécuter le test en local sur une seule machine :
1. Dans un terminal 1 : `python3 src/server_main.py --ip 127.0.0.1`
2. Dans un terminal 2 : `python3 src/client_main.py --ip 127.0.0.1 --windowed`
Si ce test fonctionne parfaitement, le dysfonctionnement précédent provient exclusivement du routage ou de la configuration réseau de l'hyperviseur.

### 5.5 Résolution des erreurs courantes PyQt6 sous Debian
- **Erreur : `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"`**
  - *Cause* : Des bibliothèques XCB requises par Qt6 sont absentes sur le système Debian minimal.
  - *Solution* : Exécuter la commande d'installation des bibliothèques C mentionnée à l'Étape 2 :
    ```bash
    sudo apt install -y libxcb-cursor0 libxkbcommon-x11-0 libgl1-mesa-glx
    ```
- **Erreur : `Could not connect to any X display`**
  - *Cause* : Le client Python tente d'ouvrir une fenêtre sans serveur graphique actif dans la session shell.
  - *Solution* : Lancer la commande depuis le terminal graphique de la VM, ou exporter la variable d'affichage si SSH : `export DISPLAY=:0`.

---

## 6. Synthèse des Commandes Utiles

| Opération | Machine | Commande |
|:---|:---:|:---|
| **Lancement Serveur standard** | VM 1 | `python3 src/server_main.py` |
| **Lancement Serveur avec IP/ports CLI** | VM 1 | `python3 src/server_main.py --ip 0.0.0.0 --tcp-port 5000 --udp-port 5001` |
| **Lancement Client standard** | VM 2 | `python3 src/client_main.py` |
| **Lancement Client avec IP serveur CLI** | VM 2 | `python3 src/client_main.py --ip 192.168.1.10 --tcp-port 5000` |
| **Lancement Client fenêtré** | VM 2 | `python3 src/client_main.py --ip 192.168.1.10 --windowed` |
| **Exécution suite de tests complète** | VM 1/2 | `python3 run_tests.py` |
| **Contrôle BDD SQLite** | VM 1 | `sqlite3 data/metrics.db "SELECT * FROM metriques ORDER BY id DESC LIMIT 5;"` |
| **Arrêt propre des applications** | VM 1/2 | Touche `Entrée` ou raccourci `Ctrl + C` dans le terminal |

---
*Fin de la fiche de procédure de déploiement Esk-2718.*
