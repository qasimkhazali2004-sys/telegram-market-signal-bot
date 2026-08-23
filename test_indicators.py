import pandas as pd
from app.indicators import enrich

def test_enrich():
    df = pd.DataFrame({
        "open": range(1, 301),
        "high": [x + 1 for x in range(1, 301)],
        "low": [x - 1 for x in range(1, 301)],
        "close": range(1, 301),
        "volume": [100] * 300,
    })
    out = enrich(df)
    assert out["ema200"].notna().sum() > 0
    assert out["atr"].notna().sum() > 0
