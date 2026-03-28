import json
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
class Config:
    alpaca: AlpacaConfig
    polygon: PolygonConfig
    claude: ClaudeConfig
    tickers: list
    risk: RiskConfig
    signal: SignalConfig
    trading_hours: TradingHoursConfig
    db_path: str
    log_level: str


def load_config(path: str = "config.json") -> Config:
    try:
        with open(path) as f:
            d = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Config not found: '{path}' — run from DayTrading/")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in '{path}': {e}")

    cfg = Config(
        alpaca=AlpacaConfig(**d["alpaca"]),
        polygon=PolygonConfig(**d["polygon"]),
        claude=ClaudeConfig(**d["claude"]),
        tickers=d["watchlist"]["tickers"],
        risk=RiskConfig(**d["risk"]),
        signal=SignalConfig(**d["signal"]),
        trading_hours=TradingHoursConfig(**d["trading_hours"]),
        db_path=d["database"]["path"],
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
