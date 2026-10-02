import sqlite3
import os

class DBManager:
    def __init__(self, db_path="metrics.db"):
        self.db_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        c = self.conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                vehicle_count INTEGER,
                avg_speed REAL
            )
        ''')
        self.conn.commit()

    def insert_metric(self, count, speed):
        c = self.conn.cursor()
        c.execute('INSERT INTO metrics (vehicle_count, avg_speed) VALUES (?, ?)', (count, speed))
        self.conn.commit()
