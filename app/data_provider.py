from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

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

        # Prevent the monitor from hammering the quote endpoint.
        self._snapshot_cache: dict[str, tuple[datetime, Snapshot]] = {}
        self._snapshot_ttl = timedelta(seconds=12)

        # Backoff after a provider rate-limit response.
        self._rate_limited_until: datetime | None = None
        self._backoff_seconds = 5

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(
                total=15,
                connect=4,
                sock_read=10,
            )
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _get(self, endpoint: str, params: dict) -> dict:
        now = datetime.now(timezone.utc)

        if (
            self._rate_limited_until is not None
            and now < self._rate_limited_until
        ):
            wait = (
                self._rate_limited_until - now
            ).total_seconds()
            raise RuntimeError(
                f"Provider rate limited; retry in {max(1, int(wait))}s."
            )

        params = {**params, "apikey": self.api_key}
        session = await self._get_session()

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
                        f"Provider returned invalid JSON (HTTP {r.status}): "
                        f"{text[:300]}"
                    )

        if r.status == 429:
            # Do not keep retrying immediately. Let the caller fall back to
            # cached data where possible, then try again after a short pause.
            self._rate_limited_until = (
                datetime.now(timezone.utc)
                + timedelta(seconds=self._backoff_seconds)
            )
            self._backoff_seconds = min(
                60,
                max(5, self._backoff_seconds * 2),
            )
            raise RuntimeError(
                "Provider rate limit reached (HTTP 429)."
            )

        # Successful request: slowly relax the backoff.
        self._backoff_seconds = 5

        if r.status >= 400:
            raise RuntimeError(
                f"Provider HTTP {r.status}: {data}"
            )

        if (
            isinstance(data, dict)
            and data.get("status") == "error"
        ):
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
        now = datetime.now(timezone.utc)
        cached = self._snapshot_cache.get(symbol)

        if cached is not None:
            cached_at, snap = cached
            if now - cached_at <= self._snapshot_ttl:
                return snap

        try:
            data = await self._get(
                "quote",
                {"symbol": self.MAP[symbol]},
            )
        except Exception:
            # During a rate-limit window, use a fresh-enough quote instead of
            # breaking the monitor loop.
            if cached is not None:
                return cached[1]
            raise

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

        snap = Snapshot(
            symbol=symbol,
            last=float(data["close"]),
            bid=float(data["bid"]) if data.get("bid") else None,
            ask=float(data["ask"]) if data.get("ask") else None,
            timestamp=quote_timestamp,
        )

        self._snapshot_cache[symbol] = (now, snap)
        return snap

    async def close(self):
        if self._session is not None and not self._session.closed:
            await self._session.close()
