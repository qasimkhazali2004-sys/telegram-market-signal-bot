from __future__ import annotations
import asyncio
import logging
import hashlib
from datetime import datetime, timezone
from app.config import Settings, SYMBOL_PRIORITY
from app.data_provider import TwelveDataProvider
from app.database import Database
from app.models import Style
from app.news import DisabledNewsProvider, FailClosedNewsProvider
from app.strategy import analyze
from app.validation import validate
from app.formatter import signal_message, no_trade, scalping_none
from app.monitor import PositionMonitor

log = logging.getLogger(__name__)

class SignalEngine:
    def __init__(self, settings: Settings):
        self.s = settings
        self.db = Database(settings.db_path)
        self.provider = TwelveDataProvider(settings.twelve_data_api_key)
        self.news = (
            FailClosedNewsProvider() if settings.news_filter_enabled
            else DisabledNewsProvider()
        )
        self.monitor = PositionMonitor(self.provider, self.db, settings.breakeven_r)

    async def scan(self, style: Style, selected_symbol: str | None = None) -> str:
        if self.db.daily_count() >= self.s.max_daily_trades:
            return no_trade("تم بلوغ الحد الأقصى للإشارات اليومية.")

        tf = self.s.timeframes["scalping" if style == Style.SCALPING else "intraday"].split(",")

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
        
                news = await self.news.status(symbol, self.s.news_block_minutes)
                if news.blocked:
                    continue
        
                frames = await asyncio.gather(
                *(self.provider.candles(symbol, x, 300) for x in tf)
        )
                signal = analyze(
                    symbol, frames[0], frames[1], frames[2], style,
                    self.s.min_confidence, self.s.risk_per_trade,
                    self.s.account_balance, self.s.value_per_price_unit,
                    snap.spread_pct, self.s.max_spread_pct
                )
                if signal is None:
                    continue

                ok, reason = validate(signal, self.s.max_signal_age_seconds)
                if not ok:
                    log.info("validation rejected %s: %s", symbol, reason)
                    continue

                if self.db.duplicate(signal.setup_id):
                    continue

                self.db.save(signal)
                return signal_message(signal)

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
        pf = "غير متاح" if m["profit_factor"] is None else f"{m['profit_factor']:.2f}"
        return (
            "📊 <b>أداء النظام</b>\n\n"
            f"عدد الصفقات: <b>{m['trades']}</b>\n"
            f"نسبة الفوز: <b>{m['win_rate']*100:.1f}%</b>\n"
            f"نسبة الخسارة: <b>{m['loss_rate']*100:.1f}%</b>\n"
            f"Profit Factor: <b>{pf}</b>\n"
            f"Average R: <b>{m['average_r']:.2f}</b>\n"
            f"Expectancy: <b>{m['expectancy']:.2f}R</b>\n"
            f"Max Drawdown: <b>{m['max_drawdown_r']:.2f}R</b>"
        )
