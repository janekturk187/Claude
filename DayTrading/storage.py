import sqlite3
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class Storage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS bars (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker      TEXT NOT NULL,
                    timestamp   TEXT NOT NULL,
                    resolution  TEXT NOT NULL,
                    open        REAL,
                    high        REAL,
                    low         REAL,
                    close       REAL,
                    volume      INTEGER,
                    vwap        REAL,
                    UNIQUE(ticker, timestamp, resolution)
                );

                CREATE TABLE IF NOT EXISTS news_events (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker          TEXT NOT NULL,
                    headline        TEXT,
                    sentiment_score INTEGER,
                    confidence      INTEGER,
                    event_type      TEXT,
                    received_at     TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS signals (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker          TEXT NOT NULL,
                    direction       TEXT NOT NULL,
                    close           REAL,
                    sentiment_score REAL,
                    sentiment_delta REAL,
                    near_gap        INTEGER,
                    signal_strength TEXT,
                    generated_at    TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trades (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker          TEXT NOT NULL,
                    direction       TEXT NOT NULL,
                    entry_price     REAL,
                    exit_price      REAL,
                    stop_price      REAL,
                    target_price    REAL,
                    qty             REAL,
                    status          TEXT DEFAULT 'open',
                    pnl             REAL,
                    opened_at       TEXT NOT NULL,
                    closed_at       TEXT
                );
            """)

    def save_bar(self, ticker: str, timestamp: str, resolution: str, o, h, l, c, volume, vwap=None):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO bars
                    (ticker, timestamp, resolution, open, high, low, close, volume, vwap)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ticker, timestamp, resolution, o, h, l, c, volume, vwap),
            )

    def save_news_event(self, ticker: str, headline: str, sentiment: int, confidence: int, event_type: str):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO news_events (ticker, headline, sentiment_score, confidence, event_type, received_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ticker, headline, sentiment, confidence, event_type, datetime.now(timezone.utc).isoformat()),
            )

    def save_signal(self, signal: dict):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO signals
                    (ticker, direction, close, sentiment_score, sentiment_delta,
                     near_gap, signal_strength, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal["ticker"], signal["direction"], signal.get("close"),
                    signal.get("sentiment_score"), signal.get("sentiment_delta"),
                    int(signal.get("near_gap", False)), signal.get("signal_strength"),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def open_trade(self, ticker: str, direction: str, entry: float, stop: float,
                   target: float, qty: float) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO trades (ticker, direction, entry_price, stop_price, target_price, qty, opened_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (ticker, direction, entry, stop, target, qty, datetime.now(timezone.utc).isoformat()),
            )
            return cur.lastrowid

    def close_trade(self, trade_id: int, exit_price: float, pnl: float):
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE trades SET exit_price=?, pnl=?, status='closed', closed_at=?
                WHERE id=?
                """,
                (exit_price, pnl, datetime.now(timezone.utc).isoformat(), trade_id),
            )

    def get_recent_news(self, ticker: str, minutes: int = 30) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT sentiment_score, confidence FROM news_events
                WHERE ticker = ? AND received_at > datetime('now', ? || ' minutes')
                ORDER BY received_at DESC
                """,
                (ticker, f"-{minutes}"),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_open_trades(self) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status = 'open'"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_daily_pnl(self) -> float:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(pnl), 0) FROM trades
                WHERE status = 'closed' AND closed_at > date('now')
                """
            ).fetchone()
            return row[0]
