from __future__ import annotations
from dataclasses import dataclass

@dataclass
class RiskOutput:
    rr: float
    position_size: float | None
    reason: str

def rr(entry: float, stop: float, target: float, direction: str) -> float:
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    reward = (target - entry) if direction == "BUY" else (entry - target)
    return reward / risk if reward > 0 else 0.0

def position_size(
    balance: float | None,
    risk_pct: float,
    entry: float,
    stop: float,
    value_per_price_unit: float | None,
) -> float | None:
    if balance is None or value_per_price_unit is None:
        return None
    per_unit_loss = abs(entry - stop) * value_per_price_unit
    if per_unit_loss <= 0:
        return None
    return (balance * risk_pct) / per_unit_loss

def make_stop(entry: float, atr_value: float, structure_low: float, structure_high: float, direction: str) -> float:
    if direction == "BUY":
        return min(structure_low - 0.20 * atr_value, entry - 1.5 * atr_value)
    return max(structure_high + 0.20 * atr_value, entry + 1.5 * atr_value)

def make_targets(entry: float, stop: float, atr_value: float, direction: str, sr_target: float):
    risk = abs(entry - stop)
    if direction == "BUY":
        tp1 = max(entry + 1.2 * risk, min(sr_target, entry + 1.5 * atr_value))
        tp2 = max(entry + 2.0 * risk, entry + 2.0 * atr_value)
        tp3 = max(entry + 3.0 * risk, entry + 3.0 * atr_value)
    else:
        tp1 = min(entry - 1.2 * risk, max(sr_target, entry - 1.5 * atr_value))
        tp2 = min(entry - 2.0 * risk, entry - 2.0 * atr_value)
        tp3 = min(entry - 3.0 * risk, entry - 3.0 * atr_value)
    return tp1, tp2, tp3
