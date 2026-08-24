from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.data_provider import TwelveDataProvider
from app.database import Database
from app.models import Direction


@dataclass
class MonitorEvent:
    setup_id: str
    message: str
    status: str


class PositionMonitor:
    def __init__(
        self,
        provider: TwelveDataProvider,
        db: Database,
        breakeven_r: float = 1.0,
    ):
        self.provider = provider
        self.db = db
        self.breakeven_r = breakeven_r

    @staticmethod
    def _expired(expires_at: str | None) -> bool:
        if not expires_at:
            return False

        try:
            expiry = datetime.fromisoformat(expires_at)
        except (TypeError, ValueError):
            return False

        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)

        return datetime.now(timezone.utc) >= expiry

    async def check(self, item: dict) -> MonitorEvent | None:
        setup_id = item["setup_id"]
        direction = item["direction"]
        status = item["status"]

        # Pending trade: expiry is checked before asking for the quote.
        # Once expired, it must never become an active trade.
        if status == "WAITING_ENTRY":
            if self._expired(item.get("expires_at")):
                self.db.update_status(setup_id, "INVALIDATED")
                return MonitorEvent(
                    setup_id,
                    "⏰ <b>انتهت مدة الصفقة</b>\n"
                    "لم يصل السعر إلى منطقة الدخول قبل انتهاء المدة.\n"
                    "❌ تم إلغاء التوصية — NO TRADE.",
                    "EXPIRED",
                )

        snap = await self.provider.snapshot(item["symbol"])
        price = float(snap.last)

        entry = float(item["entry"])
        stop = float(item["stop_loss"])
        tp1 = float(item["tp1"])
        tp2 = float(item["tp2"])
        tp3 = (
            float(item["tp3"])
            if item.get("tp3") is not None
            else None
        )

        # -------------------------
        # Waiting for entry
        # -------------------------
        if status == "WAITING_ENTRY":
            # BUY limit/support entry: current price comes down to entry.
            if direction == Direction.BUY.value and price <= entry:
                self.db.update_status(setup_id, "ENTRY_HIT")
                return MonitorEvent(
                    setup_id,
                    "🎯 <b>تم تفعيل الدخول</b>\n"
                    f"السعر الحالي: {price}",
                    "ENTRY_HIT",
                )

            # SELL limit/resistance entry: current price rises to entry.
            if direction == Direction.SELL.value and price >= entry:
                self.db.update_status(setup_id, "ENTRY_HIT")
                return MonitorEvent(
                    setup_id,
                    "🎯 <b>تم تفعيل الدخول</b>\n"
                    f"السعر الحالي: {price}",
                    "ENTRY_HIT",
                )

            return None

        # -------------------------
        # Active BUY
        # -------------------------
        if direction == Direction.BUY.value:
            # SL below entry.
            if price <= stop:
                self.db.result(
                    setup_id,
                    "LOSS",
                    -1.0,
                    0.0,
                )
                return MonitorEvent(
                    setup_id,
                    "❌ <b>تم ضرب وقف الخسارة</b>",
                    "LOSS",
                )

            if price >= tp1 and status == "ENTRY_HIT":
                self.db.update_status(setup_id, "TP1_HIT")
                return MonitorEvent(
                    setup_id,
                    "✅ <b>TP1 HIT</b>",
                    "TP1",
                )

            if price >= tp2 and status in ("ENTRY_HIT", "TP1_HIT"):
                self.db.update_status(setup_id, "TP2_HIT")
                return MonitorEvent(
                    setup_id,
                    "✅ <b>TP2 HIT</b>",
                    "TP2",
                )

            if (
                tp3 is not None
                and price >= tp3
                and status in ("ENTRY_HIT", "TP1_HIT", "TP2_HIT")
            ):
                self.db.result(
                    setup_id,
                    "WIN",
                    3.0,
                    0.0,
                )
                return MonitorEvent(
                    setup_id,
                    "✅ <b>TP3 HIT — الصفقة مكتملة</b>",
                    "TP3",
                )

            return None

        # -------------------------
        # Active SELL
        # -------------------------
        if direction == Direction.SELL.value:
            # SL above entry.
            if price >= stop:
                self.db.result(
                    setup_id,
                    "LOSS",
                    -1.0,
                    0.0,
                )
                return MonitorEvent(
                    setup_id,
                    "❌ <b>تم ضرب وقف الخسارة</b>",
                    "LOSS",
                )

            if price <= tp1 and status == "ENTRY_HIT":
                self.db.update_status(setup_id, "TP1_HIT")
                return MonitorEvent(
                    setup_id,
                    "✅ <b>TP1 HIT</b>",
                    "TP1",
                )

            if price <= tp2 and status in ("ENTRY_HIT", "TP1_HIT"):
                self.db.update_status(setup_id, "TP2_HIT")
                return MonitorEvent(
                    setup_id,
                    "✅ <b>TP2 HIT</b>",
                    "TP2",
                )

            if (
                tp3 is not None
                and price <= tp3
                and status in ("ENTRY_HIT", "TP1_HIT", "TP2_HIT")
            ):
                self.db.result(
                    setup_id,
                    "WIN",
                    3.0,
                    0.0,
                )
                return MonitorEvent(
                    setup_id,
                    "✅ <b>TP3 HIT — الصفقة مكتملة</b>",
                    "TP3",
                )

        return None
