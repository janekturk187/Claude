import json
import os
from dataclasses import dataclass, field


@dataclass
class ClaudeConfig:
    model: str
    max_tokens: int


@dataclass
class FMPConfig:
    api_key: str


@dataclass
class FREDConfig:
    api_key: str


@dataclass
class AnalysisConfig:
    earnings_lookback_quarters: int
    risk_factor_lookback_years: int
    min_thesis_score: int


@dataclass
class ScheduleConfig:
    earnings_check_interval_hours: int
    macro_refresh_interval_hours: int
    weekly_report_day: str


@dataclass
class Config:
    claude: ClaudeConfig
    fmp: FMPConfig
    fred: FREDConfig
    tickers: list
    analysis: AnalysisConfig
    schedule: ScheduleConfig
    db_path: str
    reports_dir: str
    log_level: str


def load_config(path: str = "config.json") -> Config:
    try:
        with open(path) as f:
            d = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Config not found: '{path}' — run from LongTerm/")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in '{path}': {e}")

    cfg = Config(
        claude=ClaudeConfig(**d["claude"]),
        fmp=FMPConfig(**d["fmp"]),
        fred=FREDConfig(**d["fred"]),
        tickers=d["watchlist"]["tickers"],
        analysis=AnalysisConfig(**d["analysis"]),
        schedule=ScheduleConfig(**d["schedule"]),
        db_path=d["database"]["path"],
        reports_dir=d["reports"]["output_dir"],
        log_level=d.get("log_level", "INFO"),
    )
    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    errors = []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        errors.append("ANTHROPIC_API_KEY environment variable is not set")
    if "YOUR_FMP_API_KEY" in cfg.fmp.api_key:
        errors.append("fmp.api_key is not set — get a free key at financialmodelingprep.com")
    if "YOUR_FRED_API_KEY" in cfg.fred.api_key:
        errors.append("fred.api_key is not set — get a free key at fred.stlouisfed.org/docs/api")
    if not cfg.tickers:
        errors.append("watchlist.tickers cannot be empty")
    if errors:
        raise ValueError("Config validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
