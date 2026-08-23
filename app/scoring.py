from app.models import ScoreResult

def build_score(parts: dict[str, int]) -> ScoreResult:
    weights = {
        "trend": 20,
        "structure": 15,
        "sr": 15,
        "momentum": 10,
        "volume": 10,
        "breakout_retest": 10,
        "entry_confirmation": 10,
        "risk_reward": 10,
    }
    out = {}
    for key, weight in weights.items():
        out[key] = max(0, min(weight, int(parts.get(key, 0))))
    return ScoreResult(total=sum(out.values()), components=out, reasons=[])

def classification(score: int) -> str:
    if score >= 90:
        return "ممتازة جداً"
    if score >= 80:
        return "قوية"
    if score >= 70:
        return "مقبولة بحذر"
    return "NO TRADE"
