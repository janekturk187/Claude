import json
import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class Storage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS company_profiles (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker         TEXT NOT NULL,
                    filing_type    TEXT NOT NULL,
                    period         TEXT NOT NULL,
                    revenue_trend  TEXT,
                    margin_trend   TEXT,
                    key_risks      TEXT,
                    key_opportunities TEXT,
                    management_tone TEXT,
                    guidance_direction TEXT,
                    thesis_score   INTEGER,
                    thesis_summary TEXT,
                    raw_response   TEXT,
                    analyzed_at    TEXT NOT NULL,
                    UNIQUE(ticker, filing_type, period)
                );

                CREATE TABLE IF NOT EXISTS earnings_scores (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker          TEXT NOT NULL,
                    period          TEXT NOT NULL,
                    revenue_beat    INTEGER,
                    eps_beat        INTEGER,
                    guidance_dir    TEXT,
                    quality_score   INTEGER,
                    raw_response    TEXT,
                    scored_at       TEXT NOT NULL,
                    UNIQUE(ticker, period)
                );

                CREATE TABLE IF NOT EXISTS thesis_log (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker          TEXT NOT NULL,
                    entered_at      TEXT NOT NULL,
                    thesis_text     TEXT NOT NULL,
                    assumptions     TEXT NOT NULL,
                    status          TEXT DEFAULT 'active',
                    flagged_at      TEXT,
                    flag_reason     TEXT
                );

                CREATE TABLE IF NOT EXISTS macro_snapshots (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    indicator       TEXT NOT NULL,
                    value           REAL,
                    direction       TEXT,
                    snapped_at      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS financials (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker          TEXT NOT NULL,
                    period          TEXT NOT NULL,
                    revenue         REAL,
                    gross_margin    REAL,
                    operating_margin REAL,
                    free_cash_flow  REAL,
                    debt_to_equity  REAL,
                    roe             REAL,
                    fetched_at      TEXT NOT NULL,
                    UNIQUE(ticker, period)
                );
            """)

    def save_company_profile(self, ticker: str, filing_type: str, period: str, analysis: dict):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO company_profiles
                    (ticker, filing_type, period, revenue_trend, margin_trend,
                     key_risks, key_opportunities, management_tone, guidance_direction,
                     thesis_score, thesis_summary, raw_response, analyzed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticker, filing_type, period,
                    analysis.get("revenue_trend"),
                    analysis.get("margin_trend"),
                    json.dumps(analysis.get("key_risks", [])),
                    json.dumps(analysis.get("key_opportunities", [])),
                    analysis.get("management_tone"),
                    analysis.get("guidance_direction"),
                    analysis.get("thesis_score"),
                    analysis.get("thesis_summary"),
                    analysis.get("raw_response"),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def save_earnings_score(self, ticker: str, period: str, score: dict):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO earnings_scores
                    (ticker, period, revenue_beat, eps_beat, guidance_dir,
                     quality_score, raw_response, scored_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticker, period,
                    int(score.get("revenue_beat", False)),
                    int(score.get("eps_beat", False)),
                    score.get("guidance_direction"),
                    score.get("quality_score"),
                    score.get("raw_response"),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def save_thesis(self, ticker: str, thesis_text: str, assumptions: list) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO thesis_log (ticker, entered_at, thesis_text, assumptions)
                VALUES (?, ?, ?, ?)
                """,
                (ticker, datetime.now(timezone.utc).isoformat(),
                 thesis_text, json.dumps(assumptions)),
            )
            return cur.lastrowid

    def flag_thesis(self, thesis_id: int, reason: str):
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE thesis_log SET status='flagged', flagged_at=?, flag_reason=?
                WHERE id=?
                """,
                (datetime.now(timezone.utc).isoformat(), reason, thesis_id),
            )

    def save_macro(self, indicator: str, value: float, direction: str, keep_last: int = 90):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO macro_snapshots (indicator, value, direction, snapped_at) VALUES (?, ?, ?, ?)",
                (indicator, value, direction, datetime.now(timezone.utc).isoformat()),
            )
            # Prune old rows to prevent unbounded table growth
            conn.execute(
                """
                DELETE FROM macro_snapshots
                WHERE indicator = ? AND id NOT IN (
                    SELECT id FROM macro_snapshots
                    WHERE indicator = ?
                    ORDER BY snapped_at DESC
                    LIMIT ?
                )
                """,
                (indicator, indicator, keep_last),
            )

    def save_financials(self, ticker: str, period: str, data: dict):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO financials
                    (ticker, period, revenue, gross_margin, operating_margin,
                     free_cash_flow, debt_to_equity, roe, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticker, period,
                    data.get("revenue"), data.get("gross_margin"),
                    data.get("operating_margin"), data.get("free_cash_flow"),
                    data.get("debt_to_equity"), data.get("roe"),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def has_company_profile(self, ticker: str, filing_type: str, period: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM company_profiles WHERE ticker=? AND filing_type=? AND period=?",
                (ticker, filing_type, period),
            ).fetchone()
            return row is not None

    def has_earnings_score(self, ticker: str, period: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM earnings_scores WHERE ticker=? AND period=?",
                (ticker, period),
            ).fetchone()
            return row is not None

    def has_financials(self, ticker: str, period: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM financials WHERE ticker=? AND period=?",
                (ticker, period),
            ).fetchone()
            return row is not None

    def get_active_theses(self) -> list:
        # Include 'flagged' theses — they are still open positions that need attention.
        # Closing a thesis requires explicitly setting status='closed'.
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM thesis_log WHERE status IN ('active', 'flagged')"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_latest_profile(self, ticker: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM company_profiles WHERE ticker = ? ORDER BY analyzed_at DESC LIMIT 1",
                (ticker,),
            ).fetchone()
            return dict(row) if row else None

    def get_earnings_history(self, ticker: str, n: int = 4) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM earnings_scores WHERE ticker = ? ORDER BY scored_at DESC LIMIT ?",
                (ticker, n),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_latest_macro(self) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT indicator, value, direction, MAX(snapped_at) as snapped_at
                FROM macro_snapshots
                GROUP BY indicator
                ORDER BY indicator
                """
            ).fetchall()
            return [dict(r) for r in rows]
