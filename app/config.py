from __future__ import annotations
from dataclasses import dataclass, field
import os
from dotenv import load_dotenv

load_dotenv()

ALLOWED_SYMBOLS = ("XAUUSD", "BTCUSDT", "EURUSD")
SYMBOL_PRIORITY = ("XAUUSD", "BTCUSDT", "EURUSD")

@dataclass
class Settings:
    telegram_bot_token: str
    admin_ids: set[int]
    target_chat_id: int | None
    twelve_data_api_key: str
    min_confidence: int = 80
    risk_per_trade: float = 0.005
    max_spread_pct: float = 0.0015
    max_signal_age_seconds: int = 30
    scan_seconds: int = 60
    news_filter_enabled: bool = False
    news_block_minutes: int = 15
    trailing_stop_enabled: bool = True
    breakeven_r: float = 1.0
    account_balance: float | None = None
    value_per_price_unit: float | None = None
    db_path: str = "data/bot.sqlite3"
    log_level: str = "INFO"
    timeframes: dict[str, str] = field(default_factory=lambda: {
        "intraday": "1h,15min,5min",
        "scalping": "15min,5min,1min",
    })

    @classmethod
    def from_env(cls) -> "Settings":
        ids = {
            int(x.strip()) for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")
            if x.strip()
        }
        target = os.getenv("TARGET_CHAT_ID", "").strip()
        balance = os.getenv("ACCOUNT_BALANCE", "").strip()
        vppu = os.getenv("VALUE_PER_PRICE_UNIT", "").strip()
        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            admin_ids=ids,
            target_chat_id=int(target) if target else None,
            twelve_data_api_key=os.getenv("TWELVE_DATA_API_KEY", ""),
            min_confidence=int(os.getenv("MIN_CONFIDENCE", "80")),
            risk_per_trade=float(os.getenv("RISK_PER_TRADE", "0.005")),
            max_spread_pct=float(os.getenv("MAX_SPREAD_PCT", "0.0015")),
            max_signal_age_seconds=int(os.getenv("MAX_SIGNAL_AGE_SECONDS", "30")),
            scan_seconds=int(os.getenv("SCAN_SECONDS", "60")),
            news_filter_enabled=os.getenv("NEWS_FILTER_ENABLED", "false").lower() == "true",
            news_block_minutes=int(os.getenv("NEWS_BLOCK_MINUTES", "15")),
            trailing_stop_enabled=os.getenv("TRAILING_STOP_ENABLED", "true").lower() == "true",
            breakeven_r=float(os.getenv("BREAKEVEN_R", "1.0")),
            account_balance=float(balance) if balance else None,
            value_per_price_unit=float(vppu) if vppu else None,
            db_path=os.getenv("DB_PATH", "data/bot.sqlite3"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )

    def validate(self) -> None:
        if not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN غير مضبوط")
        if not self.twelve_data_api_key:
            raise ValueError("TWELVE_DATA_API_KEY غير مضبوط")
        if not self.admin_ids:
            raise ValueError("ADMIN_TELEGRAM_IDS غير مضبوط")
        if not 0 < self.risk_per_trade <= 0.01:
            raise ValueError("RISK_PER_TRADE يجب أن يكون بين >0 و1%")
        if not 0 <= self.min_confidence <= 100:
            raise ValueError("MIN_CONFIDENCE يجب أن يكون بين 0 و100")
        if self.scan_seconds < 15:
            raise ValueError("SCAN_SECONDS يجب أن يكون >= 15")
