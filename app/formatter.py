from app.models import TradeSignal

DIR = {"BUY": "شراء", "SELL": "بيع"}
STYLE = {"SCALPING": "سكالبينج", "INTRADAY": "تداول يومي", "SWING": "تداول متوسط/متأرجح"}

def p(x):
    return f"{x:.5f}".rstrip("0").rstrip(".")

def signal_message(s: TradeSignal) -> str:
    tp3 = f"\n✅ الهدف 3: <b>{p(s.tp3)}</b>" if s.tp3 is not None else ""
    size = (
        f"\n📦 حجم الصفقة المحسوب: <b>{s.position_size:.4f}</b>"
        if s.position_size is not None else
        "\n📦 حجم الصفقة: <b>غير محسوب — بيانات العقد/الحساب غير متوفرة</b>"
    )
    confirms = "\n".join(f"- {x}" for x in s.confirmations)
    return (
        "🚨 <b>إشارة تداول</b>\n\n"
        f"📊 الأصل: <b>{s.symbol}</b>\n"
        f"📈 الاتجاه: <b>{DIR[s.direction.value]}</b>\n"
        f"⚡ النمط: <b>{STYLE[s.style.value]}</b>\n\n"
        f"🎯 الدخول: <b>{p(s.entry)}</b>\n"
        f"🛑 وقف الخسارة: <b>{p(s.stop_loss)}</b>\n"
        f"✅ الهدف 1: <b>{p(s.tp1)}</b>\n"
        f"✅ الهدف 2: <b>{p(s.tp2)}</b>{tp3}\n\n"
        f"📐 العائد مقابل المخاطرة: <b>1:{s.rr:.2f}</b>\n"
        f"🔥 درجة الثقة: <b>{s.confidence}/100</b>\n"
        f"📊 حالة السوق: <b>{s.market_state.value}</b>\n"
        f"📌 سبب الدخول: <b>{s.reason}</b>\n"
        f"🕒 الأطر: <b>{s.timeframe}</b>\n"
        f"⏱ المدة المتوقعة: <b>{s.expected_duration}</b>\n"
        f"⚠️ المخاطرة: <b>{s.risk_pct*100:.2f}%</b>{size}\n\n"
        f"🧠 <b>التأكيدات:</b>\n{confirms}\n\n"
        "⚠️ إشارة احتمالية وليست ضماناً للربح."
    )

def no_trade(reason="شروط الدخول غير مكتملة."):
    return f"🟡 <b>لا توجد صفقة</b>\n\n{reason}\nالقرار: <b>NO TRADE</b>."

def scalping_none():
    return "🟡 <b>لا توجد صفقة سكالبينج</b>\n\nلا توجد فرصة قصيرة المدى تستوفي الشروط حالياً.\nالقرار: <b>NO TRADE</b>."

def event_message(text: str) -> str:
    return text
