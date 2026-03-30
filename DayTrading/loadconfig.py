import json
import os
from dataclasses import dataclass, field


@dataclass
class AlpacaConfig:
    api_key: str
    secret_key: str
    paper: bool
    base_url: str


@dataclass
class PolygonConfig:
    api_key: str


@dataclass
class ClaudeConfig:
    model: str
    max_tokens: int


@dataclass
class RiskConfig:
    max_position_pct: float
    max_daily_loss_pct: float
    max_open_positions: int
    reward_risk_ratio: float
    news_blackout_minutes: int


@dataclass
class SignalConfig:
    min_sentiment_score: int
    min_confidence: int
    min_relative_volume: float
    session_sentiment_window: int


@dataclass
class TradingHoursConfig:
    start: str
    midday_pause_start: str
    midday_pause_end: str
    end: str
    timezone: str


@dataclass
class ScreeningConfig:
    universe: list
    max_picks: int
    min_gap_pct: float
    min_avg_daily_volume: int
    min_price: float
    max_price: float
    use_dynamic_universe: bool
    dynamic_top: int
    min_rvol: float
    max_per_sector: int
    news_catalyst_check: bool


@dataclass
class Config:
    alpaca: AlpacaConfig
    polygon: PolygonConfig
    claude: ClaudeConfig
    tickers: list
    risk: RiskConfig
    signal: SignalConfig
    trading_hours: TradingHoursConfig
    screening: ScreeningConfig
    db_path: str
    reports_dir: str
    log_level: str


def load_config(path: str = "config.json") -> Config:
    try:
        with open(path) as f:
            d = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Config not found: '{path}' — run from DayTrading/")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in '{path}': {e}")

    alpaca_raw = d["alpaca"]

    # watchlist.json written by the screener overrides config tickers for the session
    tickers = d["watchlist"]["tickers"]
    _WATCHLIST_FILE = "watchlist.json"
    if os.path.exists(_WATCHLIST_FILE):
        try:
            with open(_WATCHLIST_FILE) as wf:
                wdata = json.load(wf)
            if wdata.get("tickers"):
                tickers = wdata["tickers"]
        except (json.JSONDecodeError, KeyError):
            pass  # corrupted file — fall back to config

    screening_raw = d.get("screening", {})
    cfg = Config(
        alpaca=AlpacaConfig(
            api_key=os.environ.get("ALPACA_API_KEY") or alpaca_raw["api_key"],
            secret_key=os.environ.get("ALPACA_SECRET_KEY") or alpaca_raw["secret_key"],
            paper=alpaca_raw["paper"],
            base_url=alpaca_raw["base_url"],
        ),
        polygon=PolygonConfig(
            api_key=os.environ.get("POLYGON_API_KEY") or d["polygon"]["api_key"],
        ),
        claude=ClaudeConfig(**d["claude"]),
        tickers=tickers,
        risk=RiskConfig(**d["risk"]),
        signal=SignalConfig(**d["signal"]),
        trading_hours=TradingHoursConfig(**d["trading_hours"]),
        screening=ScreeningConfig(
            universe=screening_raw.get("universe", []),
            max_picks=screening_raw.get("max_picks", 5),
            min_gap_pct=screening_raw.get("min_gap_pct", 2.0),
            min_avg_daily_volume=screening_raw.get("min_avg_daily_volume", 500_000),
            min_price=screening_raw.get("min_price", 5.0),
            max_price=screening_raw.get("max_price", 500.0),
            use_dynamic_universe=screening_raw.get("use_dynamic_universe", True),
            dynamic_top=screening_raw.get("dynamic_top", 50),
            min_rvol=screening_raw.get("min_rvol", 0.0),
            max_per_sector=screening_raw.get("max_per_sector", 2),
            news_catalyst_check=screening_raw.get("news_catalyst_check", True),
        ),
        db_path=d["database"]["path"],
        reports_dir=d["reports"]["output_dir"],
        log_level=d.get("log_level", "INFO"),
    )

    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    errors = []
    if "YOUR_ALPACA_API_KEY" in cfg.alpaca.api_key:
        errors.append("alpaca.api_key is not set")
    if "YOUR_ALPACA_SECRET_KEY" in cfg.alpaca.secret_key:
        errors.append("alpaca.secret_key is not set")
    if "YOUR_POLYGON_API_KEY" in cfg.polygon.api_key:
        errors.append("polygon.api_key is not set")
    if not cfg.tickers:
        errors.append("watchlist.tickers cannot be empty")
    if cfg.risk.max_position_pct <= 0 or cfg.risk.max_position_pct > 0.25:
        errors.append("risk.max_position_pct must be between 0 and 0.25")
    if cfg.risk.max_daily_loss_pct <= 0 or cfg.risk.max_daily_loss_pct > 0.10:
        errors.append("risk.max_daily_loss_pct must be between 0 and 0.10")
    if errors:
        raise ValueError("Config validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
