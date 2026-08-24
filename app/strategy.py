from __future__ import annotations

from datetime import datetime, timezone
import hashlib

from app.indicators import enrich, structure
from app.models import TradeSignal, Direction, Style, MarketState
from app.risk import position_size


def analyze_single(
    symbol: str,
    candles,
    style: Style,
    risk_pct: float,
    account_balance: float | None,
    value_per_price_unit: float | None,
) -> TradeSignal:
    if len(candles) < 220:
        raise ValueError("not enough candles")

    df = enrich(candles)
    s = structure(df)
    last = df.iloc[-1]

    close = float(last["close"])
    atr = float(last["atr"])
    if close <= 0 or atr <= 0:
        raise ValueError("invalid market data")

    ema20 = float(last["ema20"])
    ema50 = float(last["ema50"])
    ema200 = float(last["ema200"])
    rsi = float(last["rsi"])
    macd_hist = float(last["macd_hist"])
    vwap = float(last["vwap"]) if last["vwap"] == last["vwap"] else close
    vol = float(last["volume"])
    vol_ma = float(last["volume_ma20"]) if last["volume_ma20"] == last["volume_ma20"] else vol

    # Always choose the better directional side of the selected timeframe.
    bull_points = 0
    bear_points = 0

    if ema20 >= ema50:
        bull_points += 2
    else:
        bear_points += 2

    if ema50 >= ema200:
        bull_points += 2
    else:
        bear_points += 2

    if rsi >= 50:
        bull_points += 2
    else:
        bear_points += 2

    if macd_hist >= 0:
        bull_points += 2
    else:
        bear_points += 2

    if close >= vwap:
        bull_points += 1
    else:
        bear_points += 1

    direction = Direction.BUY if bull_points >= bear_points else Direction.SELL

    support = float(s["support"])
    resistance = float(s["resistance"])

    # Use current price as execution level, then build deterministic ATR targets.
    entry = close
    risk_distance = max(atr * 1.25, abs(entry - support) if direction == Direction.BUY else abs(resistance - entry))
    risk_distance = max(risk_distance, atr * 0.80)

    if direction == Direction.BUY:
        stop = entry - risk_distance
        tp1 = entry + risk_distance * 1.20
        tp2 = entry + risk_distance * 2.00
        tp3 = entry + risk_distance * 3.00
    else:
        stop = entry + risk_distance
        tp1 = entry - risk_distance * 1.20
        tp2 = entry - risk_distance * 2.00
        tp3 = entry - risk_distance * 3.00

    rr2 = 2.0

    score = 50
    score += min(15, abs(bull_points - bear_points) * 4)

    if (direction == Direction.BUY and close >= vwap) or (direction == Direction.SELL and close <= vwap):
        score += 8

    if (direction == Direction.BUY and rsi >= 52) or (direction == Direction.SELL and rsi <= 48):
        score += 8

    if (direction == Direction.BUY and macd_hist >= 0) or (direction == Direction.SELL and macd_hist <= 0):
        score += 7

    if vol_ma > 0 and vol >= vol_ma * 0.85:
        score += 5

    confidence = max(55, min(98, int(score)))

    if direction == Direction.BUY:
        market_state = (
            MarketState.STRONG_BULLISH
            if ema20 > ema50 > ema200
            else MarketState.BULLISH
            if ema20 > ema50
            else MarketState.NEUTRAL
        )
    else:
        market_state = (
            MarketState.STRONG_BEARISH
            if ema20 < ema50 < ema200
            else MarketState.BEARISH
            if ema20 < ema50
            else MarketState.NEUTRAL
        )

    confirmations = [
        "تحليل الفريم المختار مباشرة",
        "اتجاه EMA 20 / 50 / 200",
        "RSI",
        "MACD",
        "ATR لإدارة الوقف والأهداف",
        "أفضل اتجاه متاح حاليًا",
    ]

    if vol_ma > 0 and vol >= vol_ma * 0.85:
        confirmations.append("الحجم متوافق مع المتوسط")

    if vwap == vwap and (
        (direction == Direction.BUY and close >= vwap)
        or (direction == Direction.SELL and close <= vwap)
    ):
        confirmations.append("تأكيد VWAP")

    timeframe_label = {
        "1min": "1 دقيقة",
        "5min": "5 دقائق",
        "15min": "15 دقيقة",
        "1h": "1 ساعة",
        "4h": "4 ساعات",
    }

    # The caller stores the exact selected timeframe on the signal.
    tf = getattr(candles, "timeframe", None) or "selected"

    expected = "5-30 دقيقة" if style == Style.SCALPING else "30 دقيقة - 4 ساعات"
    key = f"{symbol}:{direction.value}:{round(entry, 5)}:{tf}:{confidence}"
    setup_id = hashlib.sha256(key.encode()).hexdigest()[:20]

    return TradeSignal(
        symbol=symbol,
        direction=direction,
        style=style,
        timeframe=tf,
        entry=entry,
        stop_loss=stop,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
        rr=rr2,
        confidence=confidence,
        reason="أفضل فرصة متاحة على الفريم الذي اختاره المستخدم",
        confirmations=confirmations,
        market_state=market_state,
        expected_duration=expected,
        risk_pct=risk_pct,
        created_at=datetime.now(timezone.utc),
        setup_id=setup_id,
        position_size=position_size(
            account_balance,
            risk_pct,
            entry,
            stop,
            value_per_price_unit,
        ),
    )
