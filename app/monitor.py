from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.data_provider import TwelveDataProvider
from app.state_store import PendingStateStore


@dataclass
class MonitorEvent:
    setup_id: str
    message: str
    status: str


class PositionMonitor:
    def __init__(
        self,
        provider: TwelveDataProvider,
        state_store: PendingStateStore,
        breakeven_r: float = 1.0,
    ):
        self.provider = provider
        self.states = state_store
        self.breakeven_r = breakeven_r

    async def check(self, item: dict) -> MonitorEvent | None:
        if item["status"] == "WAITING_ENTRY" and item.get("expires_at"):
            expires_at = datetime.fromisoformat(item["expires_at"])
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            if datetime.now(timezone.utc) >= expires_at:
                self.states.status(item["setup_id"], "EXPIRED")
                return MonitorEvent(
                    item["setup_id"],
                    "⏰ <b>انتهت مدة التوصية</b>\n"
                    "لم يصل السعر إلى الدخول قبل انتهاء المدة.",
                    "EXPIRED",
                )

        snap = await self.provider.snapshot(item["symbol"])
        price = float(snap.last)

        entry = float(item["entry"])
        stop = float(item["stop_loss"])
        tp1 = float(item["tp1"])
        tp2 = float(item["tp2"])
        tp3 = float(item["tp3"]) if item["tp3"] is not None else None

        direction = item["direction"]
        status = item["status"]

        if status == "WAITING_ENTRY":
            hit = (
                price >= entry
                if direction == "BUY"
                else price <= entry
            )
            if hit:
                self.states.status(item["setup_id"], "ENTRY_HIT")
                return MonitorEvent(
                    item["setup_id"],
                    f"🎯 <b>تم تفعيل الدخول</b>\nالسعر: {price:.5f}",
                    "ENTRY_HIT",
                )
            return None

        if direction == "BUY":
            if price <= stop:
                self.states.status(item["setup_id"], "SL_HIT")
                return MonitorEvent(
                    item["setup_id"],
                    "🛑 <b>SL HIT</b>",
                    "SL_HIT",
                )

            if price >= tp3 if tp3 is not None else False:
                self.states.status(item["setup_id"], "TP3_HIT")
                return MonitorEvent(
                    item["setup_id"],
                    "✅ <b>TP3 HIT — الصفقة مكتملة</b>",
                    "TP3_HIT",
                )

            if price >= tp2 and status in ("ENTRY_HIT", "TP1_HIT"):
                self.states.status(item["setup_id"], "TP2_HIT")
                return MonitorEvent(
                    item["setup_id"],
                    "✅ <b>TP2 HIT</b>",
                    "TP2_HIT",
                )

            if price >= tp1 and status == "ENTRY_HIT":
                self.states.status(item["setup_id"], "TP1_HIT")
                return MonitorEvent(
                    item["setup_id"],
                    "✅ <b>TP1 HIT</b>",
                    "TP1_HIT",
                )

        else:
            if price >= stop:
                self.states.status(item["setup_id"], "SL_HIT")
                return MonitorEvent(
                    item["setup_id"],
                    "🛑 <b>SL HIT</b>",
                    "SL_HIT",
                )

            if price <= tp3 if tp3 is not None else False:
                self.states.status(item["setup_id"], "TP3_HIT")
                return MonitorEvent(
                    item["setup_id"],
                    "✅ <b>TP3 HIT — الصفقة مكتملة</b>",
                    "TP3_HIT",
                )

            if price <= tp2 and status in ("ENTRY_HIT", "TP1_HIT"):
                self.states.status(item["setup_id"], "TP2_HIT")
                return MonitorEvent(
                    item["setup_id"],
                    "✅ <b>TP2 HIT</b>",
                    "TP2_HIT",
                )

            if price <= tp1 and status == "ENTRY_HIT":
                self.states.status(item["setup_id"], "TP1_HIT")
                return MonitorEvent(
                    item["setup_id"],
                    "✅ <b>TP1 HIT</b>",
                    "TP1_HIT",
                )

        return None
