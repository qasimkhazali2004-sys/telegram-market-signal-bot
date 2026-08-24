from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.config import Settings, SYMBOL_PRIORITY
from app.data_provider import TwelveDataProvider
from app.database import Database
from app.models import Style
from app.formatter import no_trade, scalping_none
from app.monitor import PositionMonitor
from app.strategy import analyze_single
from app.validation import validate

log = logging.getLogger(__name__)


class SignalEngine:
    def __init__(self, settings: Settings):
        self.s = settings
        self.db = Database(settings.db_path)
        self.provider = TwelveDataProvider(settings.twelve_data_api_key)
        self.monitor = PositionMonitor(
            self.provider,
            self.db,
            settings.breakeven_r,
        )

    async def scan(
        self,
        style: Style,
        selected_symbol: str | None = None,
        timeframe: str | None = None,
    ) -> str:
        symbol = selected_symbol if selected_symbol in SYMBOL_PRIORITY else SYMBOL_PRIORITY[0]
        tf = timeframe or (
            self.s.timeframes["scalping" if style == Style.SCALPING else "intraday"]
            .split(",")[0]
            .strip()
        )

        try:
            # One market-data request only. This is the main speed fix.
            candles = await asyncio.wait_for(
                self.provider.candles(symbol, tf, 220),
                timeout=9,
            )
        except asyncio.TimeoutError:
            log.error("market data timeout on %s %s", symbol, tf)
            return (
                "⚠️ تعذر جلب بيانات السوق بسرعة.\n"
                "أعد المحاولة بعد لحظات."
            )
        except Exception:
            log.exception("market data failed on %s %s", symbol, tf)
            return "⚠️ تعذر جلب بيانات السوق حاليًا."

        try:
            # Attach selected timeframe for the strategy/formatter.
            try:
                candles.timeframe = tf
            except Exception:
                pass

            signal = analyze_single(
                symbol,
                candles,
                style,
                self.s.risk_per_trade,
                self.s.account_balance,
                self.s.value_per_price_unit,
            )
            signal.timeframe = tf

            ok, reason = validate(signal, self.s.max_signal_age_seconds)
            if not ok:
                log.warning("validation rejected %s: %s", symbol, reason)
                return "⚠️ تعذر بناء إشارة صالحة من بيانات السوق الحالية."

            # No daily trade cap.
            self.db.save(signal)

            return (
                "⏳ <b>إشارة بانتظار الدخول</b>\n\n"
                f"🎯 الدخول: {signal.entry}\n"
                f"🛑 وقف الخسارة: {signal.stop_loss}\n"
                f"✅ الهدف 1: {signal.tp1}\n"
                f"✅ الهدف 2: {signal.tp2}\n"
                f"✅ الهدف 3: {signal.tp3}\n"
                f"📊 الثقة: {signal.confidence}/100\n"
                f"⏱️ الفريم: {tf}\n"
                "انتظر وصول السعر إلى منطقة الدخول."
            )
        except Exception:
            log.exception("single timeframe analysis failed")
            return "⚠️ حدث خطأ أثناء بناء الإشارة."

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
