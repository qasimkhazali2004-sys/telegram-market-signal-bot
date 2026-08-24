from __future__ import annotations
from datetime import datetime, timezone
from app.models import TradeSignal


def validate(signal: TradeSignal, max_age_seconds: int = 30) -> tuple[bool, str]:
    allowed = {"XAUUSD", "BTCUSDT", "EURUSD"}

    if signal.symbol not in allowed:
        return False, "asset_not_allowed"

    if signal.entry <= 0 or signal.stop_loss <= 0:
        return False, "invalid_price"

    if signal.direction.value == "BUY":
        if not (signal.stop_loss < signal.entry < signal.tp1 <= signal.tp2):
            return False, "invalid_buy_levels"
    else:
        if not (signal.stop_loss > signal.entry > signal.tp1 >= signal.tp2):
            return False, "invalid_sell_levels"

    # RR is kept as a quality metric, not a hard rejection gate.
    # This prevents valid directional setups from becoming NO TRADE
    # solely because RR is below the preferred 1.5 threshold.
    if signal.rr <= 0:
        return False, "invalid_rr"

    if not 0 <= signal.confidence <= 100:
        return False, "invalid_confidence"

    age = (datetime.now(timezone.utc) - signal.created_at).total_seconds()
    if age > max_age_seconds:
        return False, "stale_signal"

    if signal.position_size is not None and signal.position_size <= 0:
        return False, "invalid_position_size"

    return True, "ok"
