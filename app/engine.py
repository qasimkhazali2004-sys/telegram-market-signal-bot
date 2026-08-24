from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.config import Settings, SYMBOL_PRIORITY
from app.data_provider import TwelveDataProvider
from app.database import Database
from app.models import Style
from app.news import DisabledNewsProvider, FailClosedNewsProvider
from app.strategy import analyze
from app.validation import validate
from app.formatter import no_trade, scalping_none
from app.monitor import PositionMonitor

log = logging.getLogger(__name__)


class SignalEngine:
    def __init__(self, settings: Settings):
        self.s = settings
        self.db = Database(settings.db_path)
        self.provider = TwelveDataProvider(settings.twelve_data_api_key)
        self.news = (
            FailClosedNewsProvider()
            if settings.news_filter_enabled
            else DisabledNewsProvider()
        )
        self.monitor = PositionMonitor(
            self.provider,
            self.db,
            settings.breakeven_r,
        )

    def _timeframes_for_scan(
        self,
        style: Style,
        selected_timeframe: str | None,
    ) -> list[str]:
        """Return the 3 analysis frames, using the user's chosen frame as LTF."""
        default_key = "scalping" if style == Style.SCALPING else "intraday"
        configured = [
            x.strip()
            for x in self.s.timeframes[default_key].split(",")
            if x.strip()
        ]

        if not selected_timeframe:
            return configured[:3]

        # Keep the strategy's multi-timeframe structure:
        # HTF -> MTF -> selected timeframe (LTF / execution frame).
        frame_map = {
            "4h": ["4h", "1h", "15min"],
            "1h": ["4h", "1h", "15min"],
            "15min": ["1h", "15min", "5min"],
            "5min": ["15min", "5min", "1min"],
            "1min": ["15min", "5min", "1min"],
        }

        frames = frame_map.get(selected_timeframe)
        if frames is None:
            log.warning("unsupported selected timeframe: %s", selected_timeframe)
            return configured[:3]

        return frames

    async def scan(
        self,
        style: Style,
        selected_symbol: str | None = None,
        timeframe: str | None = None,
    ) -> str:

        tf = self._timeframes_for_scan(style, timeframe)
        if len(tf) < 3:
            log.error("not enough configured timeframes: %s", tf)
            return scalping_none() if style == Style.SCALPING else no_trade()

        if selected_symbol in SYMBOL_PRIORITY:
            symbols = [selected_symbol]
        else:
            symbols = [SYMBOL_PRIORITY[0]]

        for symbol in symbols:
            try:
                snap = await self.provider.snapshot(symbol)

                quote_age = (
                    datetime.now(timezone.utc) - snap.timestamp
                ).total_seconds()

                max_quote_age = 900 if style == Style.INTRADAY else 300
                if quote_age > max_quote_age:
                    log.info(
                        "market closed/stale quote for %s: %.0fs old",
                        symbol,
                        quote_age,
                    )
                    continue

                news = await self.news.status(
                    symbol,
                    self.s.news_block_minutes,
                )
                if news.blocked:
                    continue

                frames = await asyncio.wait_for(
                    asyncio.gather(
                        *(self.provider.candles(symbol, interval, 220) for interval in tf)
                    ),
                    timeout=12,
                )

                signal = analyze(
                    symbol,
                    frames[0],
                    frames[1],
                    frames[2],
                    style,
                    self.s.min_confidence,
                    self.s.risk_per_trade,
                    self.s.account_balance,
                    self.s.value_per_price_unit,
                    snap.spread_pct,
                    self.s.max_spread_pct,
                )
                if signal is None:
                    continue

                # The strategy currently labels signals with its built-in
                # multi-timeframe preset. Expose the user's selected execution
                # timeframe in Telegram without changing the strategy logic.
                if timeframe:
                    signal.timeframe = timeframe

                ok, reason = validate(
                    signal,
                    self.s.max_signal_age_seconds,
                )
                if not ok:
                    log.info(
                        "validation rejected %s: %s",
                        symbol,
                        reason,
                    )
                    continue

                if self.db.duplicate(signal.setup_id):
                    continue

                self.db.save(signal)
                return (
                    "⏳ <b>إشارة بانتظار الدخول</b>\n\n"
                    f"🎯 الدخول: {signal.entry}\n"
                    f"🛑 وقف الخسارة: {signal.stop_loss}\n"
                    f"✅ الهدف 1: {signal.tp1}\n"
                    f"✅ الهدف 2: {signal.tp2}\n"
                    f"✅ الهدف 3: {signal.tp3}\n"
                    f"📊 الثقة: {signal.confidence}/100\n"
                    f"⏱️ الفريم: {signal.timeframe}\n"
                    "انتظر وصول السعر إلى منطقة الدخول، ثم سيتم تفعيلها."
                )

            except asyncio.TimeoutError:
                log.error("scan timeout on %s", symbol)
            except Exception:
                log.exception("scan error on %s", symbol)

        return scalping_none() if style == Style.SCALPING else no_trade()

    async def monitor_once(self):
        for item in self.db.active():
            try:
                event = await self.monitor.check(item)
                if event:
                    yield event
            except Exception:
                log.exception("monitor error %s", item["setup_id"])

    def metrics_text(self) -> str:
        m = self.db.metrics()
        if not m.get("trades"):
            return "📊 لا توجد نتائج مغلقة بعد."

        pf = (
            "غير متاح"
            if m["profit_factor"] is None
            else f"{m['profit_factor']:.2f}"
        )

        return (
            "📊 <b>أداء النظام</b>\n\n"
            f"عدد الصفقات: <b>{m['trades']}</b>\n"
            f"نسبة الفوز: <b>{m['win_rate'] * 100:.1f}%</b>\n"
            f"نسبة الخسارة: <b>{m['loss_rate'] * 100:.1f}%</b>\n"
            f"Profit Factor: <b>{pf}</b>\n"
            f"Average R: <b>{m['average_r']:.2f}</b>\n"
            f"Expectancy: <b>{m['expectancy']:.2f}R</b>\n"
            f"Max Drawdown: <b>{m['max_drawdown_r']:.2f}R</b>"
        )
