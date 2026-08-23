    import os
import asyncio
import logging
import aiohttp
import pandas as pd

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("market-bot")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TWELVE_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
MIN_CONFIDENCE = int(os.getenv("MIN_CONFIDENCE", "80"))

SYMBOLS = [
    ("XAUUSD", "XAU/USD"),
    ("BTCUSDT", "BTC/USD"),
    ("EURUSD", "EUR/USD"),
]

def keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 صفقة أو توصية", callback_data="trade")],
        [InlineKeyboardButton(text="⚡ سكالبينج", callback_data="scalp")],
    ])

async def candles(symbol, interval, limit=250):
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": limit,
        "apikey": TWELVE_KEY,
        "format": "JSON",
    }
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params) as response:
            data = await response.json()
            if response.status >= 400 or not data.get("values"):
                raise RuntimeError(f"خطأ بيانات السوق: {data}")

    df = pd.DataFrame(data["values"]).sort_values("datetime")
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" not in df:
        df["volume"] = 0.0
    return df.reset_index(drop=True)

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))

def atr(df, period=14):
    previous_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()

def build_signal(symbol, htf, mtf, ltf, scalping):
    if min(len(htf), len(mtf), len(ltf)) < 220:
        return None

    for df in (htf, mtf, ltf):
        df["ema20"] = ema(df["close"], 20)
        df["ema50"] = ema(df["close"], 50)
        df["ema200"] = ema(df["close"], 200)
        df["rsi"] = rsi(df["close"])
        df["atr"] = atr(df)

    h = htf.iloc[-1]
    m = mtf.iloc[-1]
    l = ltf.iloc[-1]

    bullish = (
        h.ema20 > h.ema50 > h.ema200
        and m.ema20 > m.ema50
        and l.rsi >= 52
    )
    bearish = (
        h.ema20 < h.ema50 < h.ema200
        and m.ema20 < m.ema50
        and l.rsi <= 48
    )

    if not (bullish or bearish):
        return None

    direction = "BUY" if bullish else "SELL"
    entry = float(l.close)
    atr_value = float(l.atr)
    if atr_value <= 0:
        return None

    recent_high = float(ltf["high"].tail(20).max())
    recent_low = float(ltf["low"].tail(20).min())

    if direction == "BUY":
        stop = min(recent_low - 0.15 * atr_value, entry - 1.5 * atr_value)
        risk = entry - stop
        tp1 = entry + 1.2 * risk
        tp2 = entry + 2.0 * risk
        tp3 = entry + 3.0 * risk
    else:
        stop = max(recent_high + 0.15 * atr_value, entry + 1.5 * atr_value)
        risk = stop - entry
        tp1 = entry - 1.2 * risk
        tp2 = entry - 2.0 * risk
        tp3 = entry - 3.0 * risk

    confidence = 85 if (
        (direction == "BUY" and l.rsi >= 55)
        or (direction == "SELL" and l.rsi <= 45)
    ) else 80

    if confidence < MIN_CONFIDENCE:
        return None

    return {
        "symbol": symbol,
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "confidence": confidence,
        "style": "سكالبينج" if scalping else "تداول يومي",
        "timeframe": "15m / 5m / 1m" if scalping else "1h / 15m / 5m",
        "duration": "5-30 دقيقة" if scalping else "30 دقيقة - 4 ساعات",
        "market": "صاعد" if direction == "BUY" else "هابط",
    }

def price(value):
    return f"{value:.5f}".rstrip("0").rstrip(".")

def render(signal):
    direction_ar = "شراء" if signal["direction"] == "BUY" else "بيع"

    return (
        "🚨 <b>إشارة تداول</b>\n\n"
        f"📊 الأصل: <b>{signal['symbol']}</b>\n"
        f"📈 الاتجاه: <b>{direction_ar}</b>\n"
        f"⚡ النمط: <b>{signal['style']}</b>\n\n"
        f"🎯 الدخول: <b>{price(signal['entry'])}</b>\n"
        f"🛑 وقف الخسارة: <b>{price(signal['stop'])}</b>\n"
        f"✅ الهدف 1: <b>{price(signal['tp1'])}</b>\n"
        f"✅ الهدف 2: <b>{price(signal['tp2'])}</b>\n"
        f"✅ الهدف 3: <b>{price(signal['tp3'])}</b>\n\n"
        "📐 العائد مقابل المخاطرة: <b>1:2.00</b>\n"
        f"🔥 درجة الثقة: <b>{signal['confidence']}/100</b>\n"
        f"📊 الاتجاه العام: <b>{signal['market']}</b>\n"
        f"⏱ المدة المتوقعة: <b>{signal['duration']}</b>\n"
        f"🕒 الأطر: <b>{signal['timeframe']}</b>\n\n"
        "🧠 <b>التأكيدات:</b>\n"
        "- اتجاه الإطار الأعلى متوافق\n"
        "- توافق EMA 20 / 50 / 200\n"
        "- تأكيد الزخم عبر RSI\n"
        "- وقف الخسارة مبني على ATR والهيكل\n\n"
        "⚠️ هذه إشارة احتمالية وليست ضماناً للربح."
    )

async def scan(scalping=False):
    intervals = (
        ("15min", "5min", "1min")
        if scalping
        else ("1h", "15min", "5min")
    )

    for display_symbol, provider_symbol in SYMBOLS:
        try:
            htf, mtf, ltf = await asyncio.gather(
                candles(provider_symbol, intervals[0]),
                candles(provider_symbol, intervals[1]),
                candles(provider_symbol, intervals[2]),
            )
            signal = build_signal(
                display_symbol, htf, mtf, ltf, scalping
            )
            if signal:
                return render(signal)
        except Exception:
            log.exception("فشل تحليل %s", display_symbol)

    if scalping:
        return (
            "🟡 <b>لا توجد صفقة سكالبينج</b>\n\n"
            "لا توجد فرصة قصيرة المدى تستوفي الشروط حالياً.\n"
            "القرار: <b>NO TRADE</b>."
        )

    return (
        "🟡 <b>لا توجد صفقة</b>\n\n"
        "السوق غير واضح حالياً أو شروط الدخول غير مكتملة.\n"
        "القرار: <b>NO TRADE</b>."
    )

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("المتغير TELEGRAM_BOT_TOKEN غير موجود")
    if not TWELVE_KEY:
        raise RuntimeError("المتغير TWELVE_DATA_API_KEY غير موجود")

    bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()

    @dp.message(Command("start"))
    async def start(message: Message):
        await message.answer(
            "أهلاً بك.\n"
            "أراقب الذهب أولاً ثم Bitcoin وEURUSD فقط.\n"
            "لا يتم إجبار النظام على إصدار صفقة.",
            reply_markup=keyboard(),
        )

    @dp.callback_query(F.data == "trade")
    async def trade(callback: CallbackQuery):
        await callback.message.edit_text(
            await scan(False),
            reply_markup=keyboard(),
        )
        await callback.answer()

    @dp.callback_query(F.data == "scalp")
    async def scalp(callback: CallbackQuery):
        await callback.message.edit_text(
            await scan(True),
            reply_markup=keyboard(),
        )
        await callback.answer()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
