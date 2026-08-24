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
from app.news import DisabledNewsProvider, FailClosedNewsProvider
from app.strategy import analyze
from app.validation import validate
from app.monitor import PositionMonitor
from app.state_store import PendingStateStore


log = logging.getLogger(__name__)


@dataclass
class ScanResult:
    text: str
    setup_id: str | None = None
    mode: str | None = None


class SignalEngine:
    def __init__(self, settings: Settings):
        global _ACTIVE_SETTINGS
        _ACTIVE_SETTINGS = settings
        self.s = settings
        # KEEP the user's existing database.py / sqlite schema.
        self.db = Database(settings.db_path)
        self.states = PendingStateStore()
        self.provider = TwelveDataProvider(settings.twelve_data_api_key)
        self.news = (
            FailClosedNewsProvider()
            if settings.news_filter_enabled
            else DisabledNewsProvider()
        )
        self.monitor = PositionMonitor(
            self.provider,
            self.states,
            settings.breakeven_r,
        )
        self.display_tz = ZoneInfo(
            os.getenv("BOT_TIMEZONE", "UTC")
        )

    @staticmethod
    def _timeframes_for_scan(
        style: Style,
        selected_timeframe: str | None,
    ) -> list[str]:
        mapping = {
            "4h": ["4h", "1h", "15min"],
            "1h": ["4h", "1h", "15min"],
            "15min": ["1h", "15min", "5min"],
            "5min": ["15min", "5min", "1min"],
            "1min": ["15min", "5min", "1min"],
        }

        if selected_timeframe in mapping:
            return mapping[selected_timeframe]

        key = "scalping" if style == Style.SCALPING else "intraday"
        return [
            x.strip()
            for x in settings_placeholder(key).split(",")
            if x.strip()
        ][:3]

    @staticmethod
    def _expiry_delta(timeframe: str) -> timedelta:
        return {
            "1min": timedelta(minutes=1),
            "5min": timedelta(minutes=5),
            "15min": timedelta(minutes=15),
            "1h": timedelta(hours=1),
            "4h": timedelta(hours=4),
        }.get(timeframe, timedelta(minutes=15))

    @staticmethod
    def _fmt_price(value: float) -> str:
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
        title = (
            f"🎯 <b>صفقة دخول مباشر — {signal.timeframe}</b>"
            if mode == "DIRECT"
            else f"🔔 <b>توصية — {signal.timeframe}</b>"
        )
        side = "🟢 شراء" if signal.direction.value == "BUY" else "🔴 بيع"

        text = (
            f"{title}\n\n"
            f"{side}\n"
            f"🎯 الدخول: {self._fmt_price(signal.entry)}\n"
            f"🛑 وقف الخسارة: {self._fmt_price(signal.stop_loss)}\n"
            f"✅ جني الأرباح 1: {self._fmt_price(signal.tp1)}\n"
            f"✅ جني الأرباح 2: {self._fmt_price(signal.tp2)}\n"
            f"✅ جني الأرباح 3: {self._fmt_price(signal.tp3)}\n"
            f"📊 R:R = 1:{signal.rr:.2f}\n"
            f"✅ الثقة: {signal.confidence}%\n"
        )

        if mode == "DIRECT":
            text += (
                "\n⚡ <b>دخول مباشر: الصفقة مفعّلة الآن.</b>"
            )
        else:
            local = expires_at.astimezone(self.display_tz)
            text += (
                f"\n⏳ <b>تنتهي:</b> "
                f"{local.strftime('%Y-%m-%d %H:%M:%S')}\n"
                "إذا لم يصل السعر للدخول قبل انتهاء المدة، تُلغى التوصية."
            )

        return text

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
            frames_tf = self._timeframes_for_scan(style, tf)
            if len(frames_tf) != 3:
                return ScanResult("⚠️ الفريم غير مدعوم.")

            snap = await asyncio.wait_for(
                self.provider.snapshot(symbol),
                timeout=5,
            )

            news = await asyncio.wait_for(
                self.news.status(
                    symbol,
                    self.s.news_block_minutes,
                ),
                timeout=5,
            )
            if news.blocked:
                return ScanResult("⚠️ توجد فترة أخبار محجوبة حاليًا.")

            frames = await asyncio.wait_for(
                asyncio.gather(
                    *(
                        self.provider.candles(symbol, interval, 220)
                        for interval in frames_tf
                    )
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
                return ScanResult(
                    "⚠️ لا توجد إشارة مكتملة الشروط حاليًا."
                )

            # Show the user's chosen execution timeframe.
            signal.timeframe = tf

            ok, reason = validate(
                signal,
                self.s.max_signal_age_seconds,
            )
            if not ok:
                return ScanResult(
                    f"⚠️ الإشارة رُفضت في التحقق: {reason}"
                )

            if self.db.duplicate(signal.setup_id):
                return ScanResult(
                    "ℹ️ توجد إشارة مشابهة حديثة لهذا الأصل والفريم."
                )

            now = datetime.now(timezone.utc)

            if mode == "DIRECT":
                self.db.save(signal)
                self.states.create(
                    setup_id=signal.setup_id,
                    symbol=signal.symbol,
                    direction=signal.direction.value,
                    entry=signal.entry,
                    stop_loss=signal.stop_loss,
                    tp1=signal.tp1,
                    tp2=signal.tp2,
                    tp3=signal.tp3,
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
                    signal.setup_id,
                    "DIRECT",
                )

            expires = now + self._expiry_delta(tf)

            self.db.save(signal)
            self.states.create(
                setup_id=signal.setup_id,
                symbol=signal.symbol,
                direction=signal.direction.value,
                entry=signal.entry,
                stop_loss=signal.stop_loss,
                tp1=signal.tp1,
                tp2=signal.tp2,
                tp3=signal.tp3,
                mode="PENDING",
                status="WAITING_ENTRY",
                expires_at=expires.isoformat(),
            )

            return ScanResult(
                self._format_signal(
                    signal,
                    mode="PENDING",
                    expires_at=expires,
                ),
                signal.setup_id,
                "PENDING",
            )

        except asyncio.TimeoutError:
            log.error("scan timeout on %s %s", symbol, tf)
            return ScanResult(
                "⚠️ التحليل أخذ وقتًا أطول من المتوقع.\n"
                "جرّب مرة ثانية."
            )
        except Exception:
            log.exception("scan error on %s %s", symbol, tf)
            return ScanResult(
                "⚠️ حدث خطأ أثناء التحليل."
            )

    async def monitor_once(self):
        for item in self.states.get_active():
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


# Helper avoids reading Settings before object construction in the static method.
_ACTIVE_SETTINGS: Settings | None = None

def settings_placeholder(key: str) -> str:
    if _ACTIVE_SETTINGS is None:
        return {
            "intraday": "1h,15min,5min",
            "scalping": "15min,5min,1min",
        }[key]
    return _ACTIVE_SETTINGS.timeframes[key]
