"""
Storage - SQLite event log and media management
"""
import sqlite3
import os
import json
import logging
from datetime import datetime, timedelta
from threading import Lock

logger = logging.getLogger("plutoclaw.storage")


class Storage:
    def __init__(self, db_path: str = "data/plutoclaw.db", media_path: str = "media"):
        self.db_path = db_path
        self.media_path = media_path
        self.lock = Lock()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        os.makedirs(f"{media_path}/snapshots", exist_ok=True)
        os.makedirs(f"{media_path}/clips", exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT NOT NULL,
                    agent       TEXT NOT NULL,
                    event_type  TEXT NOT NULL,
                    camera_id   TEXT,
                    location    TEXT,
                    confidence  REAL,
                    count       INTEGER DEFAULT 1,
                    details     TEXT,
                    snapshot    TEXT,
                    message     TEXT
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT NOT NULL,
                    channel     TEXT NOT NULL,
                    recipient   TEXT,
                    message     TEXT,
                    status      TEXT DEFAULT 'sent'
                );

                CREATE TABLE IF NOT EXISTS sensor_logs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT NOT NULL,
                    sensor_id   TEXT NOT NULL,
                    sensor_name TEXT,
                    value       REAL,
                    unit        TEXT
                );

                CREATE TABLE IF NOT EXISTS inventory (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id     TEXT NOT NULL UNIQUE,
                    item_name   TEXT NOT NULL,
                    quantity    REAL NOT NULL DEFAULT 0,
                    unit        TEXT DEFAULT 'pcs',
                    min_stock   REAL DEFAULT 0,
                    location    TEXT DEFAULT '',
                    updated_at  TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);
                CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent);
                CREATE INDEX IF NOT EXISTS idx_sensor_ts ON sensor_logs(timestamp);
                CREATE INDEX IF NOT EXISTS idx_inv_item ON inventory(item_id);
            """)
        logger.info(f"✅ Database ready: {self.db_path}")

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def log_event(self, agent: str, event_type: str, camera_id: str = None,
                  location: str = None, confidence: float = None,
                  count: int = 1, details: dict = None,
                  snapshot: str = None, message: str = None):
        """Save event to database"""
        with self.lock:
            with self._conn() as conn:
                conn.execute("""
                    INSERT INTO events
                    (timestamp, agent, event_type, camera_id, location, confidence, count, details, snapshot, message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now().isoformat(),
                    agent, event_type, camera_id, location,
                    confidence, count,
                    json.dumps(details) if details else None,
                    snapshot, message
                ))

    def log_alert(self, channel: str, recipient: str, message: str, status: str = "sent"):
        """Save log of sent alert"""
        with self.lock:
            with self._conn() as conn:
                conn.execute("""
                    INSERT INTO alerts (timestamp, channel, recipient, message, status)
                    VALUES (?, ?, ?, ?, ?)
                """, (datetime.now().isoformat(), channel, recipient, message, status))

    def log_sensor(self, sensor_id: str, sensor_name: str, value: float, unit: str = ""):
        """Save sensor data"""
        with self.lock:
            with self._conn() as conn:
                conn.execute("""
                    INSERT INTO sensor_logs (timestamp, sensor_id, sensor_name, value, unit)
                    VALUES (?, ?, ?, ?, ?)
                """, (datetime.now().isoformat(), sensor_id, sensor_name, value, unit))

    def get_recent_events(self, limit: int = 50, agent: str = None) -> list:
        """Get recent events"""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            if agent:
                rows = conn.execute(
                    "SELECT * FROM events WHERE agent=? ORDER BY timestamp DESC LIMIT ?",
                    (agent, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(r) for r in rows]

    def get_daily_summary(self, date: str = None) -> dict:
        """Daily event summary for LLM reporting"""
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        with self._conn() as conn:
            conn.row_factory = sqlite3.Row

            # Count per agent
            agent_counts = conn.execute("""
                SELECT agent, event_type, COUNT(*) as count
                FROM events
                WHERE timestamp LIKE ?
                GROUP BY agent, event_type
                ORDER BY count DESC
            """, (f"{date}%",)).fetchall()

            # Total alerts
            alert_count = conn.execute("""
                SELECT COUNT(*) as count FROM alerts WHERE timestamp LIKE ?
            """, (f"{date}%",)).fetchone()

        return {
            "date": date,
            "agent_summary": [dict(r) for r in agent_counts],
            "total_alerts": alert_count["count"] if alert_count else 0
        }

    # ── Inventory ──────────────────────────────────────────────────────────────
    def inventory_upsert(self, item_id: str, item_name: str, quantity: float,
                         unit: str = "pcs", min_stock: float = 0, location: str = ""):
        """Create or update inventory item"""
        now = datetime.now().isoformat()
        with self.lock:
            with self._conn() as conn:
                conn.execute("""
                    INSERT INTO inventory (item_id, item_name, quantity, unit, min_stock, location, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(item_id) DO UPDATE SET
                        item_name  = excluded.item_name,
                        quantity   = excluded.quantity,
                        unit       = excluded.unit,
                        min_stock  = excluded.min_stock,
                        location   = excluded.location,
                        updated_at = excluded.updated_at
                """, (item_id, item_name, quantity, unit, min_stock, location, now))

    def inventory_adjust(self, item_id: str, delta: float) -> float:
        """Add/subtract item qty (delta can be negative). Returns new qty."""
        now = datetime.now().isoformat()
        with self.lock:
            with self._conn() as conn:
                conn.execute("""
                    UPDATE inventory SET quantity = MAX(0, quantity + ?), updated_at = ?
                    WHERE item_id = ?
                """, (delta, now, item_id))
                row = conn.execute(
                    "SELECT quantity FROM inventory WHERE item_id = ?", (item_id,)
                ).fetchone()
                return row[0] if row else 0.0

    def inventory_get_all(self) -> list:
        """Return all inventory items"""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM inventory ORDER BY item_name"
            ).fetchall()
            return [dict(r) for r in rows]

    def inventory_get_low_stock(self) -> list:
        """Return items where qty < min_stock"""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM inventory WHERE min_stock > 0 AND quantity < min_stock ORDER BY item_name"
            ).fetchall()
            return [dict(r) for r in rows]

    def inventory_delete(self, item_id: str):
        """Delete item from inventory"""
        with self.lock:
            with self._conn() as conn:
                conn.execute("DELETE FROM inventory WHERE item_id = ?", (item_id,))

    def cleanup_old_media(self, max_days: int = 30):
        """Delete old snapshots/clips"""
        cutoff = datetime.now() - timedelta(days=max_days)
        for folder in ["snapshots", "clips"]:
            path = os.path.join(self.media_path, folder)
            if not os.path.exists(path):
                continue
            for fname in os.listdir(path):
                fpath = os.path.join(path, fname)
                fmtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                if fmtime < cutoff:
                    os.remove(fpath)
                    logger.debug(f"Deleted old media: {fpath}")

    def get_stats(self) -> dict:
        """Brief statistics for dashboard"""
        with self._conn() as conn:
            total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            today = datetime.now().strftime("%Y-%m-%d")
            today_events = conn.execute(
                "SELECT COUNT(*) FROM events WHERE timestamp LIKE ?", (f"{today}%",)
            ).fetchone()[0]
            total_alerts = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]

        return {
            "total_events": total_events,
            "today_events": today_events,
            "total_alerts": total_alerts
        }
