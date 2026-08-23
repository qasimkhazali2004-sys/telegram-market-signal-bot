from __future__ import annotations
from pathlib import Path
import sqlite3
import json
from datetime import date
from app.models import TradeSignal

class Database:
    def __init__(self, path: str):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(p, check_same_thread=False)
        self.init()

    def init(self):
        c = self.conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS signals (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          setup_id TEXT UNIQUE,
          created_at TEXT NOT NULL,
          symbol TEXT NOT NULL,
          direction TEXT NOT NULL,
          style TEXT NOT NULL,
          timeframe TEXT NOT NULL,
          entry REAL NOT NULL,
          stop_loss REAL NOT NULL,
          tp1 REAL NOT NULL,
          tp2 REAL NOT NULL,
          tp3 REAL,
          rr REAL NOT NULL,
          confidence INTEGER NOT NULL,
          reason TEXT,
          confirmations TEXT,
          market_state TEXT,
          risk_pct REAL NOT NULL,
          position_size REAL,
          status TEXT DEFAULT 'WAITING_ENTRY',
          result TEXT,
          r_multiple REAL,
          duration_minutes REAL
        )""")
        self.conn.commit()

    def daily_count(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM signals WHERE substr(created_at,1,10)=?",
            (date.today().isoformat(),)
        ).fetchone()
        return int(row[0])

    def duplicate(self, setup_id: str, hours: int = 8) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM signals WHERE setup_id=? AND datetime(created_at)>=datetime('now', ?)",
            (setup_id, f"-{hours} hours"),
        ).fetchone()
        return row is not None

    def save(self, s: TradeSignal):
        self.conn.execute("""
        INSERT OR IGNORE INTO signals
        (setup_id,created_at,symbol,direction,style,timeframe,entry,stop_loss,tp1,tp2,tp3,rr,
         confidence,reason,confirmations,market_state,risk_pct,position_size)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            s.setup_id, s.created_at.isoformat(), s.symbol, s.direction.value,
            s.style.value, s.timeframe, s.entry, s.stop_loss, s.tp1, s.tp2, s.tp3,
            s.rr, s.confidence, s.reason, json.dumps(s.confirmations, ensure_ascii=False),
            s.market_state.value, s.risk_pct, s.position_size
        ))
        self.conn.commit()

    def active(self) -> list[dict]:
        rows = self.conn.execute(
            """SELECT setup_id,symbol,direction,entry,stop_loss,tp1,tp2,tp3,status
               FROM signals WHERE status NOT IN ('CLOSED','SL_HIT','INVALIDATED')"""
        ).fetchall()
        keys = ["setup_id","symbol","direction","entry","stop_loss","tp1","tp2","tp3","status"]
        return [dict(zip(keys, r)) for r in rows]

    def update_status(self, setup_id: str, status: str):
        self.conn.execute("UPDATE signals SET status=? WHERE setup_id=?", (status, setup_id))
        self.conn.commit()

    def result(self, setup_id: str, result: str, r_multiple: float, duration_minutes: float):
        self.conn.execute(
            "UPDATE signals SET result=?,r_multiple=?,duration_minutes=?,status='CLOSED' WHERE setup_id=?",
            (result, r_multiple, duration_minutes, setup_id)
        )
        self.conn.commit()

    def metrics(self) -> dict:
        rows = self.conn.execute(
            "SELECT result,r_multiple,style FROM signals WHERE result IS NOT NULL"
        ).fetchall()
        if not rows:
            return {"trades": 0}
        rs = [float(r[1]) for r in rows]
        wins = sum(r > 0 for r in rs)
        gross_profit = sum(r for r in rs if r > 0)
        gross_loss = -sum(r for r in rs if r < 0)
        equity = peak = max_dd = 0.0
        for r in rs:
            equity += r
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
        return {
            "trades": len(rs),
            "win_rate": wins / len(rs),
            "loss_rate": 1 - wins / len(rs),
            "profit_factor": gross_profit / gross_loss if gross_loss else None,
            "average_r": sum(rs) / len(rs),
            "expectancy": sum(rs) / len(rs),
            "max_drawdown_r": max_dd,
        }
