from datetime import datetime, timezone
from app.models import TradeSignal, Direction, Style, MarketState
from app.validation import validate

def s():
    return TradeSignal(
        symbol="XAUUSD",
        direction=Direction.BUY,
        style=Style.INTRADAY,
        timeframe="1h / 15m / 5m",
        entry=100.0,
        stop_loss=98.0,
        tp1=102.5,
        tp2=104.0,
        tp3=106.0,
        rr=2.0,
        confidence=85,
        reason="test",
        confirmations=[],
        market_state=MarketState.BULLISH,
        expected_duration="30 دقيقة - 4 ساعات",
        risk_pct=0.005,
        created_at=datetime.now(timezone.utc),
        setup_id="abc123",
    )

def test_valid():
    ok, reason = validate(s())
    assert ok, reason

def test_bad_symbol():
    x = s()
    x.symbol = "USDJPY"
    ok, _ = validate(x)
    assert not ok
