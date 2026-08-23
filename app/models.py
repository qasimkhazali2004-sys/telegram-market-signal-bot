from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class Style(str, Enum):
    SCALPING = "SCALPING"
    INTRADAY = "INTRADAY"
    SWING = "SWING"

class MarketState(str, Enum):
    STRONG_BULLISH = "Strong Bullish"
    BULLISH = "Bullish"
    NEUTRAL = "Neutral"
    BEARISH = "Bearish"
    STRONG_BEARISH = "Strong Bearish"
    HIGH_VOLATILITY = "High Volatility"
    LOW_VOLATILITY = "Low Volatility"
    CHOPPY = "Choppy / No Trade"

@dataclass
class TradeSignal:
    symbol: str
    direction: Direction
    style: Style
    timeframe: str
    entry: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float | None
    rr: float
    confidence: int
    reason: str
    confirmations: list[str]
    market_state: MarketState
    expected_duration: str
    risk_pct: float
    created_at: datetime
    setup_id: str
    position_size: float | None = None

    @property
    def risk_distance(self) -> float:
        return abs(self.entry - self.stop_loss)

@dataclass
class MonitoringState:
    setup_id: str
    status: str = "WAITING_ENTRY"
    current_stop: float | None = None
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    entry_hit: bool = False
    break_even: bool = False
    invalidated: bool = False

@dataclass
class NewsStatus:
    blocked: bool
    label: str
    reason: str = ""

@dataclass
class ScoreResult:
    total: int
    components: dict[str, int]
    reasons: list[str] = field(default_factory=list)
