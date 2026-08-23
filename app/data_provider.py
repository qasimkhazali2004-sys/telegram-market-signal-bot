from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import aiohttp
import pandas as pd

@dataclass(frozen=True)
class Snapshot:
    symbol: str
    last: float
    bid: float | None
    ask: float | None
    timestamp: datetime

    @property
    def spread_pct(self) -> float | None:
        if self.bid is None or self.ask is None or self.last <= 0:
            return None
        return abs(self.ask - self.bid) / self.last

class TwelveDataProvider:
    MAP = {
        "XAUUSD": "XAU/USD",
        "BTCUSDT": "BTC/USD",
        "EURUSD": "EUR/USD",
    }

    def __init__(self, api_key: str, base_url: str = "https://api.twelvedata.com"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def _get(self, endpoint: str, params: dict) -> dict:
        params = {**params, "apikey": self.api_key}
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{self.base_url}/{endpoint}", params=params) as r:
                data = await r.json()
                if r.status >= 400:
                    raise RuntimeError(f"Provider HTTP {r.status}: {data}")
                return data

    async def candles(self, symbol: str, interval: str, limit: int = 300) -> pd.DataFrame:
        data = await self._get("time_series", {
            "symbol": self.MAP[symbol],
            "interval": interval,
            "outputsize": limit,
            "format": "JSON",
        })
        rows = data.get("values")
        if not rows:
            raise RuntimeError(f"لا توجد شموع: {symbol}/{interval}")
        df = pd.DataFrame(rows)
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        for col in ("open", "high", "low", "close", "volume"):
            if col in df:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "volume" not in df:
            df["volume"] = 0.0
        return df.sort_values("datetime").reset_index(drop=True)

    async def snapshot(self, symbol: str) -> Snapshot:
        data = await self._get(
            "quote",
            {"symbol": self.MAP[symbol]},
        )

        raw_timestamp = data.get("timestamp")

        if raw_timestamp:
            quote_timestamp = datetime.fromtimestamp(
                int(raw_timestamp),
                tz=timezone.utc,
            )
        elif data.get("datetime"):
            quote_timestamp = pd.to_datetime(
                data["datetime"],
                utc=True,
            ).to_pydatetime()
        else:
            raise RuntimeError(f"لا يوجد وقت موثوق للسعر: {symbol}")

        return Snapshot(
            symbol=symbol,
            last=float(data["close"]),
            bid=float(data["bid"]) if data.get("bid") else None,
            ask=float(data["ask"]) if data.get("ask") else None,
            timestamp=quote_timestamp,
        )
