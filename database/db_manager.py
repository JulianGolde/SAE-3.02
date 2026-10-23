"""Module de gestion de la persistance SQLite pour la simulation de carrefour Esk-2718.

Fournit une interface thread-safe pour enregistrer et consulter les simulations,
les séries temporelles de métriques, les événements discrets et l'historique des feux.
Conforme aux exigences SAÉ 3.02 (Esk-2718) et aux normes d'architecture client-serveur.
"""

import csv
import logging
import os
import sqlite3
import threading
from datetime import datetime

logger = logging.getLogger(__name__)


class LigneResultat(dict):
    """Ligne de résultat SQLite hybride accessible par nom de colonne ou par index positionnel.

    Hérite de dict pour garantir une compatibilité totale avec les accès de type
    row['nb_vehicules'] tout en surchargeant __getitem__ pour autoriser row[3] et row[1:4].
    """

    def __init__(self, colonnes, valeurs):
        """Initialise la ligne avec les noms de colonnes et les valeurs associées.

        Args:
            colonnes (list[str]): Liste ordonnée des noms de colonnes.
            valeurs (tuple | list): Valeurs correspondantes renvoyées par SQLite.
        """
        super().__init__(zip(colonnes, valeurs))
        self._colonnes = list(colonnes)
        self._valeurs = list(valeurs)

    def __getitem__(self, item):
        """Permet l'accès direct par index positionnel, tranche (slice) ou nom de colonne."""
        if isinstance(item, (int, slice)):
            return self._valeurs[item]
        return super().__getitem__(item)


class DBManager:
    """Gestionnaire thread-safe de base de données SQLite locale pour Esk-2718.

    Gère le schéma relationnel complet (simulations, metriques, evenements, historique_feux)
    avec support des accès concurrents multi-threads via un verrou threading.Lock().
    """

    def __init__(self, db_path: str = "metrics.db"):
        """Initialise la connexion SQLite et configure le verrou d'accès concurrent.

        Args:
            db_path (str): Nom du fichier ou chemin vers la base de données.
                           Utiliser ':memory:' pour les tests unitaires isolés.
        """
        self._verrou = threading.Lock()
        self._simulation_courante_id = None

        if db_path == ":memory:":
            self.db_path = ":memory:"
        elif os.path.isabs(db_path):
            self.db_path = db_path
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        else:
            repertoire_data = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "data")
            )
            os.makedirs(repertoire_data, exist_ok=True)
            self.db_path = os.path.join(repertoire_data, db_path)
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        logger.info(f"[DBManager] Initialisation de la base SQLite : {self.db_path}")
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        """Initialise le schéma relationnel complet de la base de données SQLite."""
        with self._verrou:
            cursor = self.conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON;")

            # Table des sessions de simulation
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS simulations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date_debut DATETIME DEFAULT CURRENT_TIMESTAMP,
                    scenario TEXT,
                    duree_secondes REAL DEFAULT 0.0
                )
                """
            )

            # Table des séries temporelles de métriques
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS metriques (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    simulation_id INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    nb_vehicules INTEGER,
                    vitesse_moyenne REAL,
                    nb_pietons INTEGER DEFAULT 0,
                    nb_incidents INTEGER DEFAULT 0,
                    FOREIGN KEY (simulation_id) REFERENCES simulations(id)
                )
                """
            )

            # Table des événements discrets (alertes VTA, météo, forçage feux, freinages)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS evenements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    simulation_id INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    type_evenement TEXT,
                    description TEXT,
                    pos_x REAL,
                    pos_y REAL,
                    FOREIGN KEY (simulation_id) REFERENCES simulations(id)
                )
                """
            )

            # Table d'historique des cycles et états des feux tricolores
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS historique_feux (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    simulation_id INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    feu_ns INTEGER,
                    feu_eo INTEGER,
                    FOREIGN KEY (simulation_id) REFERENCES simulations(id)
                )
                """
            )

            # Table héritée conservée pour stricte rétro-compatibilité avec d'anciens nœuds
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    vehicle_count INTEGER,
                    avg_speed REAL
                )
                """
            )

            self.conn.commit()

    @property
    def simulation_courante_id(self) -> int | None:
        """Retourne l'identifiant unique de la simulation actuellement active."""
        return self._simulation_courante_id

    @simulation_courante_id.setter
    def simulation_courante_id(self, sim_id: int | None):
        """Définit l'identifiant unique de la simulation active."""
        self._simulation_courante_id = int(sim_id) if sim_id is not None else None

    def creer_simulation(self, scenario: str = "Standard") -> int:
        """Crée un nouvel enregistrement de simulation dans la table simulations.

        Args:
            scenario (str): Nom ou descriptif du scénario de circulation.

        Returns:
            int: L'identifiant unique généré pour cette nouvelle simulation.
        """
        nom_scenario = str(scenario).strip() if scenario else "Standard"
        with self._verrou:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO simulations (scenario, duree_secondes) VALUES (?, 0.0)",
                (nom_scenario,),
            )
            self.conn.commit()
            sim_id = cursor.lastrowid
            self._simulation_courante_id = sim_id
            logger.info(f"[DBManager] Nouvelle simulation créée #{sim_id} ('{nom_scenario}')")
            return sim_id

    def mettre_a_jour_duree(self, sim_id: int | None, duree_secondes: float) -> bool:
        """Met à jour la durée totale écoulée pour une simulation donnée.

        Args:
            sim_id (int | None): Identifiant de la simulation à actualiser.
            duree_secondes (float): Durée totale écoulée en secondes.

        Returns:
            bool: True si la mise à jour a réussi, False sinon.
        """
        if sim_id is None:
            return False
        with self._verrou:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE simulations SET duree_secondes = ? WHERE id = ?",
                (max(0.0, float(duree_secondes)), int(sim_id)),
            )
            self.conn.commit()
            return cursor.rowcount > 0

    def insert_metrique(
        self,
        sim_id: int | None,
        nb_vehicules: int,
        vitesse_moy: float,
        nb_pietons: int = 0,
        nb_incidents: int = 0,
    ) -> int:
        """Insère une mesure de métrique dans la table metriques.

        Args:
            sim_id (int | None): Identifiant de la simulation (utilise la courante si None).
            nb_vehicules (int): Nombre de véhicules présents sur le carrefour.
            vitesse_moy (float): Vitesse moyenne constatée (km/h).
            nb_pietons (int): Nombre de piétons actifs.
            nb_incidents (int): Nombre total ou incrément d'incidents constatés.

        Returns:
            int: Identifiant de la ligne insérée.
        """
        target_sim_id = sim_id if sim_id is not None else self._simulation_courante_id
        with self._verrou:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO metriques (simulation_id, nb_vehicules, vitesse_moyenne, nb_pietons, nb_incidents)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    target_sim_id,
                    max(0, int(nb_vehicules)),
                    max(0.0, float(vitesse_moy)),
                    max(0, int(nb_pietons)),
                    max(0, int(nb_incidents)),
                ),
            )
            # Rétro-compatibilité miroir avec la table legacy 'metrics'
            try:
                cursor.execute(
                    "INSERT INTO metrics (vehicle_count, avg_speed) VALUES (?, ?)",
                    (max(0, int(nb_vehicules)), max(0.0, float(vitesse_moy))),
                )
            except Exception:
                pass
            self.conn.commit()
            return cursor.lastrowid

    def insert_evenement(
        self,
        sim_id: int | None,
        type_evt: str,
        description: str = "",
        pos_x: float = 0.0,
        pos_y: float = 0.0,
    ) -> int:
        """Enregistre un événement discret au sein de la simulation.

        Args:
            sim_id (int | None): Identifiant de la simulation (utilise la courante si None).
            type_evt (str): Type ou catégorie de l'événement (ex: 'ALERTE_VTA', 'METEO', 'INCIDENT').
            description (str): Détails textuels complémentaires.
            pos_x (float): Coordonnée X de l'événement.
            pos_y (float): Coordonnée Y de l'événement.

        Returns:
            int: Identifiant de la ligne insérée.
        """
        target_sim_id = sim_id if sim_id is not None else self._simulation_courante_id
        px = float(pos_x) if pos_x is not None else 0.0
        py = float(pos_y) if pos_y is not None else 0.0
        with self._verrou:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO evenements (simulation_id, type_evenement, description, pos_x, pos_y)
                VALUES (?, ?, ?, ?, ?)
                """,
                (target_sim_id, str(type_evt), str(description), px, py),
            )
            self.conn.commit()
            return cursor.lastrowid

    def insert_etat_feux(self, sim_id: int | None, feu_ns: int, feu_eo: int) -> int:
        """Enregistre l'état des feux tricolores (Nord/Sud et Est/Ouest).

        Args:
            sim_id (int | None): Identifiant de la simulation (utilise la courante si None).
            feu_ns (int | Enum): État numérique du feu Nord/Sud (1=VERT, 2=ORANGE, 3=ROUGE).
            feu_eo (int | Enum): État numérique du feu Est/Ouest (1=VERT, 2=ORANGE, 3=ROUGE).

        Returns:
            int: Identifiant de la ligne insérée.
        """
        target_sim_id = sim_id if sim_id is not None else self._simulation_courante_id
        val_ns = getattr(feu_ns, "value", feu_ns)
        val_eo = getattr(feu_eo, "value", feu_eo)
        with self._verrou:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO historique_feux (simulation_id, feu_ns, feu_eo)
                VALUES (?, ?, ?)
                """,
                (target_sim_id, int(val_ns), int(val_eo)),
            )
            self.conn.commit()
            return cursor.lastrowid

    def get_metriques_simulation(self, sim_id: int | None = None) -> list[LigneResultat]:
        """Récupère l'ensemble des métriques d'une simulation sous forme de liste de résultats.

        Args:
            sim_id (int | None): Identifiant de la simulation ciblée.
                                Si None, récupère toutes les métriques de la base.

        Returns:
            list[LigneResultat]: Liste des enregistrements trouvés.
        """
        colonnes = [
            "id",
            "simulation_id",
            "timestamp",
            "nb_vehicules",
            "vitesse_moyenne",
            "nb_pietons",
            "nb_incidents",
        ]
        with self._verrou:
            cursor = self.conn.cursor()
            if sim_id is not None:
                cursor.execute(
                    """
                    SELECT id, simulation_id, timestamp, nb_vehicules, vitesse_moyenne, nb_pietons, nb_incidents
                    FROM metriques
                    WHERE simulation_id = ?
                    ORDER BY id ASC
                    """,
                    (int(sim_id),),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, simulation_id, timestamp, nb_vehicules, vitesse_moyenne, nb_pietons, nb_incidents
                    FROM metriques
                    ORDER BY id ASC
                    """
                )
            lignes = cursor.fetchall()
            return [LigneResultat(colonnes, ligne) for ligne in lignes]

    def get_evenements_simulation(self, sim_id: int | None = None) -> list[LigneResultat]:
        """Récupère les événements enregistrés pour une simulation donnée ou pour l'ensemble.

        Args:
            sim_id (int | None): Identifiant de la simulation (toutes si None).

        Returns:
            list[LigneResultat]: Liste des événements discrets trouvés.
        """
        colonnes = ["id", "simulation_id", "timestamp", "type_evenement", "description", "pos_x", "pos_y"]
        with self._verrou:
            cursor = self.conn.cursor()
            if sim_id is not None:
                cursor.execute(
                    """
                    SELECT id, simulation_id, timestamp, type_evenement, description, pos_x, pos_y
                    FROM evenements
                    WHERE simulation_id = ?
                    ORDER BY id ASC
                    """,
                    (int(sim_id),),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, simulation_id, timestamp, type_evenement, description, pos_x, pos_y
                    FROM evenements
                    ORDER BY id ASC
                    """
                )
            lignes = cursor.fetchall()
            return [LigneResultat(colonnes, ligne) for ligne in lignes]

    def get_historique_feux(self, sim_id: int | None = None) -> list[LigneResultat]:
        """Récupère l'historique des états de feux enregistrés.

        Args:
            sim_id (int | None): Identifiant de la simulation (tous si None).

        Returns:
            list[LigneResultat]: Liste des transitions de feux tricolores.
        """
        colonnes = ["id", "simulation_id", "timestamp", "feu_ns", "feu_eo"]
        with self._verrou:
            cursor = self.conn.cursor()
            if sim_id is not None:
                cursor.execute(
                    """
                    SELECT id, simulation_id, timestamp, feu_ns, feu_eo
                    FROM historique_feux
                    WHERE simulation_id = ?
                    ORDER BY id ASC
                    """,
                    (int(sim_id),),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, simulation_id, timestamp, feu_ns, feu_eo
                    FROM historique_feux
                    ORDER BY id ASC
                    """
                )
            lignes = cursor.fetchall()
            return [LigneResultat(colonnes, ligne) for ligne in lignes]

    def get_historique_simulations(self) -> list[LigneResultat]:
        """Récupère la liste de toutes les simulations enregistrées par ordre antéchronologique.

        Inclut le décompte direct des métriques associées via une jointure SQL optimisée
        afin d'éviter le problème des requêtes N+1 lors de l'affichage dans l'IHM.

        Returns:
            list[LigneResultat]: Liste contenant les métadonnées de chaque simulation.
        """
        colonnes = ["id", "date_debut", "scenario", "duree_secondes", "nb_metriques"]
        with self._verrou:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT s.id, s.date_debut, s.scenario, COALESCE(s.duree_secondes, 0.0), COUNT(m.id) as nb_metriques
                FROM simulations s
                LEFT JOIN metriques m ON s.id = m.simulation_id
                GROUP BY s.id
                ORDER BY s.id DESC
                """
            )
            lignes = cursor.fetchall()
            return [LigneResultat(colonnes, ligne) for ligne in lignes]

    def exporter_csv(self, sim_id: int | None, chemin_fichier: str) -> bool:
        """Exporte les métriques d'une simulation au format CSV standard (séparateur virgule).

        Args:
            sim_id (int | None): Identifiant de la simulation à exporter (None pour toutes).
            chemin_fichier (str): Chemin du fichier CSV de sortie.

        Returns:
            bool: True si l'export a réussi avec succès, False sinon.
        """
        if not chemin_fichier:
            return False

        try:
            metriques = self.get_metriques_simulation(sim_id)
            dossier_destination = os.path.dirname(os.path.abspath(chemin_fichier))
            if dossier_destination:
                os.makedirs(dossier_destination, exist_ok=True)

            with open(chemin_fichier, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=",")
                # En-tête standardisée
                writer.writerow([
                    "id",
                    "simulation_id",
                    "timestamp",
                    "nb_vehicules",
                    "vitesse_moyenne",
                    "nb_pietons",
                    "nb_incidents",
                ])
                for m in metriques:
                    writer.writerow([
                        m["id"],
                        m["simulation_id"],
                        m["timestamp"],
                        m["nb_vehicules"],
                        m["vitesse_moyenne"],
                        m["nb_pietons"],
                        m["nb_incidents"],
                    ])
            logger.info(f"[DBManager] Export CSV réussi ({len(metriques)} lignes) -> {chemin_fichier}")
            return True
        except Exception as e:
            logger.error(f"[DBManager] Erreur lors de l'export CSV vers {chemin_fichier}: {e}", exc_info=True)
            return False

    def insert_metric(self, count: int, speed: float) -> None:
        """Insère une métrique dans la base de données.

        Conserve la compatibilité ascendante stricte avec les appels legacy de server_node.py.
        Alimente à la fois la table 'metrics' et le schéma enrichi 'metriques'.

        Args:
            count (int): Nombre de véhicules.
            speed (float): Vitesse moyenne constatée.
        """
        with self._verrou:
            cursor = self.conn.cursor()
            # Insertion dans l'ancienne table pour rétro-compatibilité
            cursor.execute(
                "INSERT INTO metrics (vehicle_count, avg_speed) VALUES (?, ?)",
                (int(count), float(speed)),
            )
            # Insertion miroir dans le nouveau schéma enrichi
            cursor.execute(
                """
                INSERT INTO metriques (simulation_id, nb_vehicules, vitesse_moyenne, nb_pietons, nb_incidents)
                VALUES (?, ?, ?, 0, 0)
                """,
                (self._simulation_courante_id, int(count), float(speed)),
            )
            self.conn.commit()

    def fermer(self):
        """Ferme la connexion SQLite de manière sécurisée."""
        with self._verrou:
            try:
                self.conn.close()
                logger.info("[DBManager] Connexion SQLite fermée proprement.")
            except Exception as e:
                logger.warning(f"[DBManager] Erreur lors de la fermeture SQLite: {e}")

    def close(self):
        """Alias pour fermer() conforme aux conventions standard."""
        self.fermer()
