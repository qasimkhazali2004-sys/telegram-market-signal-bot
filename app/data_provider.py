from __future__ import annotations

import asyncio
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

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.twelvedata.com",
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._request_lock = asyncio.Lock()
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(
                total=12,
                connect=4,
                sock_read=10,
            )
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _get(self, endpoint: str, params: dict) -> dict:
        params = {**params, "apikey": self.api_key}
        session = await self._get_session()

        # Short lock only around the actual HTTP request.
        # IMPORTANT: do not sleep here; the previous 8s delay made every
        # market-data request unnecessarily slow.
        async with self._request_lock:
            async with session.get(
                f"{self.base_url}/{endpoint}",
                params=params,
            ) as r:
                try:
                    data = await r.json()
                except Exception:
                    text = await r.text()
                    raise RuntimeError(
                        f"Provider returned invalid JSON (HTTP {r.status}): {text[:300]}"
                    )

        if r.status == 429:
            raise RuntimeError(
                "Provider rate limit reached (HTTP 429). "
                "Try again after a short pause."
            )

        if r.status >= 400:
            raise RuntimeError(
                f"Provider HTTP {r.status}: {data}"
            )

        if isinstance(data, dict) and data.get("status") == "error":
            raise RuntimeError(
                str(data.get("message") or data)
            )

        return data

    async def candles(
        self,
        symbol: str,
        interval: str,
        limit: int = 300,
    ) -> pd.DataFrame:
        data = await self._get(
            "time_series",
            {
                "symbol": self.MAP[symbol],
                "interval": interval,
                "outputsize": min(int(limit), 220),
                "format": "JSON",
            },
        )

        rows = data.get("values")
        if not rows:
            raise RuntimeError(
                f"لا توجد شموع: {symbol}/{interval}"
            )

        df = pd.DataFrame(rows)
        df["datetime"] = pd.to_datetime(
            df["datetime"],
            utc=True,
        )

        for col in ("open", "high", "low", "close", "volume"):
            if col in df:
                df[col] = pd.to_numeric(
                    df[col],
                    errors="coerce",
                )

        if "volume" not in df:
            df["volume"] = 0.0

        return df.sort_values(
            "datetime"
        ).reset_index(drop=True)

    async def snapshot(self, symbol: str) -> Snapshot:
        data = await self._get(
            "quote",
            {"symbol": self.MAP[symbol]},
        )

        raw_timestamp = (
            data.get("last_quote_at")
            or data.get("timestamp")
        )

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
            raise RuntimeError(
                f"لا يوجد وقت موثوق للسعر: {symbol}"
            )

        return Snapshot(
            symbol=symbol,
            last=float(data["close"]),
            bid=float(data["bid"]) if data.get("bid") else None,
            ask=float(data["ask"]) if data.get("ask") else None,
            timestamp=quote_timestamp,
        )

    async def close(self):
        if self._session is not None and not self._session.closed:
            await self._session.close()
