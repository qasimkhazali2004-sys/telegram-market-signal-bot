from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import os

from app.config import Settings, SYMBOL_PRIORITY
from app.data_provider import TwelveDataProvider
from app.database import Database
from app.models import Style
from app.formatter import no_trade, scalping_none
from app.monitor import PositionMonitor
from app.strategy import analyze_single
from app.validation import validate


log = logging.getLogger(__name__)


@dataclass
class ScanResult:
    text: str
    setup_id: str | None = None
    mode: str | None = None


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
        self.display_tz = ZoneInfo(os.getenv("BOT_TIMEZONE", "UTC"))

    @staticmethod
    def _expiry_delta(timeframe: str) -> timedelta:
        mapping = {
            "1min": timedelta(minutes=1),
            "5min": timedelta(minutes=5),
            "15min": timedelta(minutes=15),
            "1h": timedelta(hours=1),
            "4h": timedelta(hours=4),
        }
        return mapping.get(timeframe, timedelta(minutes=15))

    @staticmethod
    def _fmt_price(value: float) -> str:
        # Keep Telegram output clean without floating-point tails.
        if abs(value) >= 1000:
            return f"{value:.2f}"
        if abs(value) >= 100:
            return f"{value:.3f}"
        return f"{value:.5f}".rstrip("0").rstrip(".")

    def _format_signal(
        self,
        signal,
        *,
        mode: str,
        expires_at: datetime | None,
    ) -> str:
        direct = mode == "DIRECT"
        header = (
            f"🎯 <b>صفقة دخول مباشر — {signal.timeframe}</b>"
            if direct
            else f"🔔 <b>توصية — {signal.timeframe}</b>"
        )

        action = "🟢 شراء" if signal.direction.value == "BUY" else "🔴 بيع"
        body = (
            f"{header}\n\n"
            f"{action}\n"
            f"🎯 الدخول: {self._fmt_price(signal.entry)}\n"
            f"🛑 وقف الخسارة: {self._fmt_price(signal.stop_loss)}\n"
            f"✅ جني الأرباح 1: {self._fmt_price(signal.tp1)}\n"
            f"✅ جني الأرباح 2: {self._fmt_price(signal.tp2)}\n"
            f"✅ جني الأرباح 3: {self._fmt_price(signal.tp3)}\n"
            f"📊 R:R = 1:{signal.rr:.2f}\n"
            f"✅ الثقة: {signal.confidence}%\n"
        )

        if direct:
            body += "\n⚡ <b>دخول مباشر: يتم اعتبار الصفقة مفعّلة الآن.</b>"
        else:
            local_expiry = expires_at.astimezone(self.display_tz)
            body += (
                f"\n⏳ <b>تنتهي:</b> {local_expiry.strftime('%Y-%m-%d %H:%M:%S')}"
                f"\nإذا لم يصل السعر إلى الدخول قبل هذا الوقت، يتم إلغاء التوصية."
            )

        return body

    async def scan(
        self,
        style: Style,
        selected_symbol: str | None = None,
        timeframe: str | None = None,
        mode: str = "PENDING",
    ) -> ScanResult:
        symbol = (
            selected_symbol
            if selected_symbol in SYMBOL_PRIORITY
            else SYMBOL_PRIORITY[0]
        )
        tf = timeframe or (
            self.s.timeframes[
                "scalping" if style == Style.SCALPING else "intraday"
            ]
            .split(",")[0]
            .strip()
        )

        try:
            candles = await asyncio.wait_for(
                self.provider.candles(symbol, tf, 220),
                timeout=9,
            )
        except asyncio.TimeoutError:
            log.error("market data timeout on %s %s", symbol, tf)
            return ScanResult(
                "⚠️ تعذر جلب بيانات السوق بسرعة.\nأعد المحاولة بعد لحظات."
            )
        except Exception:
            log.exception("market data failed on %s %s", symbol, tf)
            return ScanResult("⚠️ تعذر جلب بيانات السوق حاليًا.")

        try:
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

            ok, reason = validate(
                signal,
                self.s.max_signal_age_seconds,
            )
            if not ok:
                log.warning(
                    "validation rejected %s: %s",
                    symbol,
                    reason,
                )
                return ScanResult(
                    "⚠️ تعذر بناء إشارة صالحة من بيانات السوق الحالية."
                )

            if self.db.duplicate(signal.setup_id):
                return ScanResult(
                    "ℹ️ توجد إشارة مشابهة حديثة لهذا الأصل والفريم."
                )

            now = datetime.now(timezone.utc)

            if mode == "DIRECT":
                self.db.save(
                    signal,
                    mode="DIRECT",
                    status="ENTRY_HIT",
                    expires_at=None,
                )
                return ScanResult(
                    self._format_signal(
                        signal,
                        mode="DIRECT",
                        expires_at=None,
                    ),
                    setup_id=signal.setup_id,
                    mode="DIRECT",
                )

            expires_at = now + self._expiry_delta(tf)
            self.db.save(
                signal,
                mode="PENDING",
                status="WAITING_ENTRY",
                expires_at=expires_at.isoformat(),
            )

            return ScanResult(
                self._format_signal(
                    signal,
                    mode="PENDING",
                    expires_at=expires_at,
                ),
                setup_id=signal.setup_id,
                mode="PENDING",
            )

        except Exception:
            log.exception("single timeframe analysis failed")
            return ScanResult("⚠️ حدث خطأ أثناء بناء الإشارة.")

    async def monitor_once(self):
        for item in self.db.active():
            try:
                event = await self.monitor.check(item)
                if event:
                    yield event
            except Exception:
                log.exception(
                    "monitor error %s",
                    item["setup_id"],
                )

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
