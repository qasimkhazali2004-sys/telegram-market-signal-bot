from __future__ import annotations
from datetime import datetime, timezone
import hashlib
from app.indicators import enrich, structure
from app.models import TradeSignal, Direction, Style, MarketState
from app.risk import make_stop, make_targets, rr, position_size
from app.scoring import build_score

def _market_state(df, struct):
    atr_val = float(df["atr"].iloc[-1])
    close = float(df["close"].iloc[-1])
    atr_pct = atr_val / close if close else 0.0
    if atr_pct > 0.02:
        return MarketState.HIGH_VOLATILITY
    if atr_pct < 0.002:
        return MarketState.LOW_VOLATILITY
    if struct["bias"] == "BULLISH":
        return MarketState.BULLISH
    if struct["bias"] == "BEARISH":
        return MarketState.BEARISH
    return MarketState.NEUTRAL

def analyze(
    symbol: str,
    htf,
    mtf,
    ltf,
    style: Style,
    min_confidence: int,
    risk_pct: float,
    account_balance: float | None,
    value_per_price_unit: float | None,
    spread_pct: float | None,
    max_spread_pct: float,
) -> TradeSignal | None:
    if min(len(htf), len(mtf), len(ltf)) < 220:
        return None

    h, m, l = enrich(htf), enrich(mtf), enrich(ltf)
    hs, ms, ls = structure(h), structure(m), structure(l)
    H, M, L = h.iloc[-1], m.iloc[-1], l.iloc[-1]

    state = _market_state(h, hs)
    if state == MarketState.HIGH_VOLATILITY:
        return None

    if spread_pct is not None and spread_pct > max_spread_pct:
        return None

    bull = (
        H["ema20"] > H["ema50"] > H["ema200"]
        and M["ema20"] > M["ema50"]
    )
    bear = (
        H["ema20"] < H["ema50"] < H["ema200"]
        and M["ema20"] < M["ema50"]
    )
    if not (bull or bear):
        return None

    direction = Direction.BUY if bull else Direction.SELL
    if (direction == Direction.BUY and ls["bias"] == "BEARISH") or (
        direction == Direction.SELL and ls["bias"] == "BULLISH"
    ):
        return None

    momentum_ok = (
        (direction == Direction.BUY and L["rsi"] >= 52 and L["macd_hist"] > 0)
        or (direction == Direction.SELL and L["rsi"] <= 48 and L["macd_hist"] < 0)
    )
    if not momentum_ok:
        return None

    vol_ok = True if L["volume_ma20"] <= 0 else L["volume"] >= L["volume_ma20"] * 0.9
    vwap_ok = True if L["vwap"] != L["vwap"] else (
        (direction == Direction.BUY and L["close"] >= L["vwap"])
        or (direction == Direction.SELL and L["close"] <= L["vwap"])
    )
    candle_ok = (direction == Direction.BUY and L["close"] > L["open"]) or (
        direction == Direction.SELL and L["close"] < L["open"]
    )

    entry = float(L["close"])
    atr_value = float(L["atr"])
    if atr_value <= 0:
        return None

    structural_extreme = ls["support"] if direction == Direction.BUY else ls["resistance"]
    stop = make_stop(
        entry, atr_value,
        ls["support"], ls["resistance"],
        direction.value
    )
    sr_target = ls["resistance"] if direction == Direction.BUY else ls["support"]
    tp1, tp2, tp3 = make_targets(entry, stop, atr_value, direction.value, sr_target)
    rr2 = rr(entry, stop, tp2, direction.value)
    if rr2 < 1.5:
        return None

    score = build_score({
        "trend": 20 if bull or bear else 0,
        "structure": 15 if (
            (direction == Direction.BUY and hs["bias"] == "BULLISH")
            or (direction == Direction.SELL and hs["bias"] == "BEARISH")
        ) else 10,
        "sr": 12 if abs(entry - structural_extreme) <= 1.5 * atr_value else 8,
        "momentum": 10 if momentum_ok else 0,
        "volume": 10 if vol_ok else 5,
        "breakout_retest": 10 if (
            (direction == Direction.BUY and (ms["breakout_up"] or entry > ms["resistance"]))
            or (direction == Direction.SELL and (ms["breakout_down"] or entry < ms["support"]))
        ) else 7,
        "entry_confirmation": 10 if candle_ok and vwap_ok else 6 if candle_ok else 0,
        "risk_reward": 10 if rr2 >= 2 else 7 if rr2 >= 1.5 else 0,
    })

    if score.total < min_confidence:
        return None

    expected = "5-30 دقيقة" if style == Style.SCALPING else "30 دقيقة - 4 ساعات"
    timeframe = "15m / 5m / 1m" if style == Style.SCALPING else "1h / 15m / 5m"
    market_state = (
        MarketState.STRONG_BULLISH if direction == Direction.BUY and hs["bias"] == "BULLISH"
        else MarketState.STRONG_BEARISH if direction == Direction.SELL and hs["bias"] == "BEARISH"
        else state
    )

    confirmations = [
        "اتجاه الإطار الأعلى متوافق",
        "توافق EMA 20 / 50 / 200",
        "تأكيد RSI وMACD",
        "وقف الخسارة مبني على ATR والهيكل",
        f"العائد مقابل المخاطرة: 1:{rr2:.2f}",
    ]
    if vol_ok:
        confirmations.append("الحجم متوافق مع متوسطه")
    if vwap_ok:
        confirmations.append("تأكيد VWAP")
    if candle_ok:
        confirmations.append("تأكيد شمعة الدخول")

    key = f"{symbol}:{direction.value}:{round(entry,6)}:{timeframe}:{score.total}"
    setup_id = hashlib.sha256(key.encode()).hexdigest()[:20]
    pos = position_size(account_balance, risk_pct, entry, stop, value_per_price_unit)

    return TradeSignal(
        symbol=symbol,
        direction=direction,
        style=style,
        timeframe=timeframe,
        entry=entry,
        stop_loss=stop,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
        rr=rr2,
        confidence=score.total,
        reason="توافق اتجاه + هيكل + زخم + تأكيد دخول",
        confirmations=confirmations,
        market_state=market_state,
        expected_duration=expected,
        risk_pct=risk_pct,
        created_at=datetime.now(timezone.utc),
        setup_id=setup_id,
        position_size=pos,
    )
