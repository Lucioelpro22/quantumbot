"""In-memory adapter for synthetic fixtures; no production path is opened."""
import json
import sqlite3
from datetime import datetime, timezone

from operational_policy import require_operational_access


class QuantDatabaseManager:
    def __init__(self, db_path=None):
        if db_path != ":memory:":
            require_operational_access("persistent_trading_database")
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE partials (position_key TEXT PRIMARY KEY, symbol TEXT,
                                   side TEXT, entry REAL);
            CREATE TABLE decisions (id INTEGER PRIMARY KEY, timestamp TEXT, payload TEXT);
            CREATE TABLE executions (id INTEGER PRIMARY KEY, payload TEXT);
        """)

    def get_partial_closed_positions(self):
        return {row[0] for row in self.conn.execute("SELECT position_key FROM partials")}

    def set_position_partial_closed(self, position_key, symbol, side, entry):
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO partials VALUES (?,?,?,?)",
                              (position_key, symbol, side, entry))

    def save_decision(self, symbol, regime, direction, total_score, ml_probability,
                      is_allowed, reason, signals, weights):
        payload = dict(symbol=symbol, regime=regime, direction=direction,
                       total_score=total_score, ml_probability=ml_probability,
                       is_allowed=is_allowed, reason=reason, weights=weights,
                       signals=[s.model_dump(mode="json") if hasattr(s, "model_dump") else s
                                for s in signals])
        with self.conn:
            self.conn.execute("INSERT INTO decisions(timestamp,payload) VALUES (?,?)",
                              (datetime.now(timezone.utc).isoformat(), json.dumps(payload)))

    def get_recent_decisions(self, limit=5):
        if type(limit) is not int or not 0 <= limit <= 1000:
            raise ValueError("Invalid decision limit")
        return [{**json.loads(row["payload"]), "id": row["id"], "timestamp": row["timestamp"]}
                for row in self.conn.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,))]

    def save_trade_execution(self, execution):
        with self.conn:
            self.conn.execute("INSERT INTO executions(payload) VALUES (?)", (json.dumps(execution),))

    def close(self):
        self.conn.close()
