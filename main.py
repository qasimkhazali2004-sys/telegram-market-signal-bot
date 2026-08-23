import os, asyncio, logging
import aiohttp
import pandas as pd
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TWELVE_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
MIN_CONFIDENCE = int(os.getenv("MIN_CONFIDENCE", "80"))

SYMBOLS = [("XAUUSD", "XAU/USD"), ("BTCUSDT", "BTC/USD"), ("EURUSD", "EUR/USD")]

def keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 صفقة أو توصية", callback_data="trade")],
        [InlineKeyboardButton(text="⚡ سكالبينج", callback_data="scalp")],
    ])

async def candles(symbol, interval, limit=250):
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol, "interval": interval, "outputsize": limit,
        "apikey": TWELVE_KEY, "format": "JSON"
    }
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params) as r:
            data = await r.json()
            if r.status >= 400 or not data.get("values"):
                raise RuntimeError(str(data))
    df = pd.DataFrame(data["values"]).sort_values("datetime")
    for c in ["open","high","low","close","volume"]:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "volume" not in df:
        df["volume"] = 0.0
    return df.reset_index(drop=True)

def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    d = s.diff()
    gain = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = gain / loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))

def atr(df, n=14):
    prev = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev).abs(),
        (df["low"] - prev).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def build_signal(symbol, htf, mtf, ltf, scalp):
    if min(len(htf), len(mtf), len(ltf)) < 220:
        return None

    for df in (htf, mtf, ltf):
        df["ema20"] = ema(df["close"], 20)
        df["ema50"] = ema(df["close"], 50)
        df["ema200"] = ema(df["close"], 200)
        df["rsi"] = rsi(df["close"])
        df["atr"] = atr(df)

    h, m, l = htf.iloc[-1], mtf.iloc[-1], ltf.iloc[-1]
    buy = h.ema20 > h.ema50 > h.ema200 and m.ema20 > m.ema50 and l.rsi >= 52
    sell = h.ema20 < h.ema50 < h.ema200 and m.ema20 < m.ema50 and l.rsi <= 48
    if not (buy or sell):
        return None

    direction = "BUY" if buy else "SELL"
    entry = float(l.close)
    a = float(l.atr)
    if a <= 0:
        return None

    recent_high = float(ltf.high.tail(20).max())
    recent_low = float(ltf.low.tail(20).min())

    if direction == "BUY":
        sl = min(recent_low - 0.15*a, entry - 1.5*a)
        risk = entry - sl
        tp1, tp2, tp3 = entry + 1.2*risk, entry + 2*risk, entry + 3*risk
    else:
        sl = max(recent_high + 0.15*a, entry + 1.5*a)
        risk = sl - entry
        tp1, tp2, tp3 = entry - 1.2*risk, entry - 2*risk, entry - 3*risk

    confidence = 85 if ((direction=="BUY" and l.rsi >= 55) or (direction=="SELL" and l.rsi <= 45)) else 80
    if confidence < MIN_CONFIDENCE:
        return None

    return {
        "symbol": symbol, "direction": direction, "entry": entry, "sl": sl,
        "tp1": tp1, "tp2": tp2, "tp3": tp3, "confidence": confidence,
        "style": "سكالبينج" if scalp else "تداول يومي",
        "tf": "15m/5m/1m" if scalp else "1h/15m/5m",
        "duration": "5-30 دقيقة" if scalp else "30 دقيقة - 4 ساعات",
        "market": "صاعد" if direction == "BUY" else "هابط"
    }

def price(x):
    return f"{x:.5f}".rstrip("0").rstrip(".")

def render(s):
    d = "شراء" if s["direction"] == "BUY" else "بيع"
    return (
        "🚨 <b>إشارة تداول</b>\n\n"
        f"📊 الأصل: <b>{s['symbol']}</b>\n"
        f"📈 الاتجاه: <b>{d}</b>\n"
        f"⚡ النمط: <b>{s['style']}</b>\n\n"
        f"🎯 الدخول: <b>{price(s['entry'])}</b>\n"
        f"🛑 وقف الخسارة: <b>{price(s['sl'])}</b>\n"
        f"✅ الهدف 1: <b>{price(s['tp1'])}</b>\n"
        f"✅ الهدف 2: <b>{price(s['tp2'])}</b>\n"
        f"✅ الهدف 3: <b>{price(s['tp3'])}</b>\n\n"
        f"📐 العائد مقابل المخاطرة: <b>1:2.00</b>\n"
        f"🔥 درجة الثقة: <b>{s['confidence']}/100</b>\n"
        f"📊 الاتجاه العام: <b>{s['market']}</b>\n"
        f"⏱ المدة المتوقعة: <b>{s['duration']}</b>\n"
        f"🕒 الأطر: <b>{s['tf']}</b>\n\n"
        "⚠️ إشارة احتمالية وليست ضماناً للربح."
    )

async def scan(scalp=False):
    intervals = ("15min", "5min", "1min") if scalp else ("1h", "15min", "5min")
    for name, provider_symbol in SYMBOLS:
        try:
            h, m, l = await asyncio.gather(
                candles(provider_symbol, intervals[0]),
                candles(provider_symbol, intervals[1]),
                candles(provider_symbol, intervals[2]),
            )
            sig = build_signal(name, h, m, l, scalp)
            if sig:
                return render(sig)
        except Exception:
            logging.exception("scan failed for %s", name)
    return "🟡 <b>لا توجد صفقة</b>\n\nالسوق غير واضح حالياً أو شروط الدخول غير مكتملة.\nالقرار: <b>NO TRADE</b>."

async def main():
    if not BOT_TOKEN or not TWELVE_KEY:
        raise RuntimeError("ضع TELEGRAM_BOT_TOKEN و TWELVE_DATA_API_KEY في متغيرات Railway")

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    @dp.message(Command("start"))
    async def start(message: Message):
        await message.answer(
            "أهلاً بك.\nأراقب الذهب أولاً ثم Bitcoin وEURUSD فقط.",
            reply_markup=keyboard()
        )

    @dp.callback_query(F.data == "trade")
    async def trade(q: CallbackQuery):
        await q.message.edit_text(await scan(False), reply_markup=keyboard())
        await q.answer()

    @dp.callback_query(F.data == "scalp")
    async def scalp(q: CallbackQuery):
        await q.message.edit_text(await scan(True), reply_markup=keyboard())
        await q.answer()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
