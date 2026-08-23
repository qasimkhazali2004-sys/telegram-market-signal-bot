from __future__ import annotations
from dataclasses import dataclass
from app.data_provider import TwelveDataProvider
from app.database import Database
from app.models import Direction

@dataclass
class MonitorEvent:
    setup_id: str
    message: str
    status: str

class PositionMonitor:
    def __init__(self, provider: TwelveDataProvider, db: Database, breakeven_r: float = 1.0):
        self.provider = provider
        self.db = db
        self.breakeven_r = breakeven_r

    async def check(self, item: dict) -> MonitorEvent | None:
                snap = await self.provider.snapshot(item["symbol"])

            price = snap.last
            entry = float(item["entry"])
            stop = float(item["stop_loss"])
            tp1 = float(item["tp1"])
            tp2 = float(item["tp2"])
            tp3 = float(item["tp3"]) if item["tp3"] is not None else None
        
            direction = item["direction"]
            status = item["status"]
            setup_id = item["setup_id"]
        
        # Entry activation
        if status == "WAITING_ENTRY":
            if direction == Direction.BUY.value and price >= entry:
                self.db.update_status(setup_id, "ENTRY_HIT")
                return MonitorEvent(
                    setup_id,
                    "🎯 <b>تم تفعيل الدخول</b>",
                    "ENTRY_HIT",
                )
    
            if direction == Direction.SELL.value and price <= entry:
                self.db.update_status(setup_id, "ENTRY_HIT")
                return MonitorEvent(
                    setup_id,
                    "🎯 <b>تم تفعيل الدخول</b>",
                    "ENTRY_HIT",
                )
    
            
    
        # BUY
        if direction == Direction.BUY.value:
    
            # Stop loss
            if price <= stop:
                self.db.result(setup_id, "LOSS", -1.0, 0.0)
                return MonitorEvent(
                    setup_id,
                    "❌ <b>ضرب وقف الخسارة</b>",
                    "LOSS",
                )
    
            # TP1 + Break-even
            if price >= tp1 and status == "ENTRY_HIT":
                new_stop = entry
                if new_stop > stop:
                    self.db.update_stop(setup_id, new_stop)
    
                
                    self.db.update_status(setup_id, "TP1_HIT")
                                    return MonitorEvent(
                                        setup_id,
                                        "✅ <b>TP1 HIT</b> — تم نقل الوقف إلى نقطة الدخول",
                                        "TP1",
                                    )
                        
            # TP2 + profit protection
            if price >= tp2 and status in ("ENTRY_HIT", "TP1_HIT"):
                new_stop = tp1
                if new_stop > stop:
                    self.db.update_stop(setup_id, new_stop)
    
                self.db.update_status(setup_id, "TP2_HIT")
    
                return MonitorEvent(
                    setup_id,
                    "✅ <b>TP2 HIT</b> — تم تأمين جزء من الربح",
                    "TP2",
                )
    
            # TP3 / final target
            if tp3 is not None and price >= tp3:
                self.db.result(setup_id, "WIN", 3.0, 0.0)
                return MonitorEvent(
                    setup_id,
                    "✅ <b>TP3 HIT</b>",
                    "TP3",
                )
    
        # SELL
        else:
    
            # Stop loss
            if price >= stop:
                self.db.result(setup_id, "LOSS", -1.0, 0.0)
                return MonitorEvent(
                    setup_id,
                    "❌ <b>ضرب وقف الخسارة</b>",
                    "LOSS",
                )
    
            # TP1 + Break-even
            if price <= tp1 and status == "ENTRY_HIT":
                new_stop = entry
                if new_stop < stop:
                    self.db.update_stop(setup_id, new_stop)
    
                self.db.update_status(setup_id, "TP1_HIT")
    
                return MonitorEvent(
                    setup_id,
                    "✅ <b>TP1 HIT</b> — تم نقل الوقف إلى نقطة الدخول",
                    "TP1",
                )
    
            # TP2 + profit protection
            if price <= tp2 and status in ("ENTRY_HIT", "TP1_HIT"):
                new_stop = tp1
                if new_stop < stop:
                    self.db.update_stop(setup_id, new_stop)
    
                self.db.update_status(setup_id, "TP2_HIT")
    
                return MonitorEvent(
                    setup_id,
                    "✅ <b>TP2 HIT</b> — تم تأمين جزء من الربح",
                    "TP2",
                )
    
            # TP3 / final target
            if tp3 is not None and price <= tp3:
                self.db.result(setup_id, "WIN", 3.0, 0.0)
                return MonitorEvent(
                    setup_id,
                    "✅ <b>TP3 HIT</b>",
                    "TP3",
                )
    
        return None
