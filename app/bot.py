from __future__ import annotations
import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from app.config import Settings, SYMBOL_PRIORITY
from app.models import Style
from app.engine import SignalEngine

log = logging.getLogger(__name__)

def keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 صفقة أو توصية", callback_data="trade_menu")],
        [InlineKeyboardButton(text="⚡ سكالبينج", callback_data="scalp_menu")],
        [InlineKeyboardButton(text="📈 الأداء", callback_data="metrics")],
    ])

def asset_keyboard(mode: str):
    def timeframe_keyboard(mode: str, symbol: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="1 دقيقة",
                    callback_data=f"{mode}_tf:{symbol}:1min",
                ),
                InlineKeyboardButton(
                    text="5 دقائق",
                    callback_data=f"{mode}_tf:{symbol}:5min",
                ),
                InlineKeyboardButton(
                    text="15 دقيقة",
                    callback_data=f"{mode}_tf:{symbol}:15min",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="1 ساعة",
                    callback_data=f"{mode}_tf:{symbol}:1h",
                ),
                InlineKeyboardButton(
                    text="4 ساعات",
                    callback_data=f"{mode}_tf:{symbol}:4h",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ رجوع",
                    callback_data="home",
                ),
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🥇 الذهب — XAUUSD", callback_data=f"{mode}:XAUUSD")],
        [InlineKeyboardButton(text="₿ بيتكوين — BTCUSDT", callback_data=f"{mode}:BTCUSDT")],
        [InlineKeyboardButton(text="💶 يورو/دولار — EURUSD", callback_data=f"{mode}:EURUSD")],
        [InlineKeyboardButton(text="↩️ رجوع", callback_data="home")],
    ])

class TelegramApp:
    def __init__(self, settings: Settings):
        self.s = settings
        self.engine = SignalEngine(settings)
        self.bot = Bot(
            settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.dp = Dispatcher()
        self._wire()

    def _is_admin(self, msg: Message) -> bool:
        return bool(msg.from_user and msg.from_user.id in self.s.admin_ids)

    def _wire(self):
        @self.dp.message(Command("start"))
        async def start(msg: Message):
            await msg.answer(
                "أهلاً بك.\n"
                "اختر نوع التحليل ثم الأصل الذي تريد تحليله.\n"
                "الأصول المسموحة فقط: الذهب، Bitcoin، EURUSD.\n"
                "إذا لم تكتمل الشروط فالقرار يكون: NO TRADE.",
                reply_markup=keyboard()
            )

        @self.dp.callback_query(F.data.startswith("trade_tf:"))
async def trade_timeframe(q: CallbackQuery):
    _, symbol, timeframe = q.data.split(":", 2)

    await q.message.edit_text(
        "⏳ جاري تحليل السوق...",
    )

    text = await self.engine.scan(
        Style.INTRADAY,
        selected_symbol=symbol,
        timeframe=timeframe,
    )

    await q.message.edit_text(
        text,
        reply_markup=keyboard(),
    )
    await q.answer()

        @self.dp.callback_query(F.data.startswith("scalp_tf:"))
async def scalp_timeframe(q: CallbackQuery):
    _, symbol, timeframe = q.data.split(":", 2)

    await q.message.edit_text(
        "⏳ جاري تحليل السوق...",
    )

    text = await self.engine.scan(
        Style.SCALPING,
        selected_symbol=symbol,
        timeframe=timeframe,
    )

    await q.message.edit_text(
        text,
        reply_markup=keyboard(),
    )
    await q.answer()

        @self.dp.callback_query(F.data.startswith("trade:"))
        async def trade_asset(q: CallbackQuery):
            symbol = q.data.split(":", 1)[1]
            await q.message.edit_text(
    f"📊 الأصل: {symbol}\n\nاختر الفريم الذي تريد التحليل عليه:",
    reply_markup=timeframe_keyboard("trade", symbol),
)
await q.answer()

        @self.dp.callback_query(F.data.startswith("scalp:"))
        async def scalp_asset(q: CallbackQuery):
            symbol = q.data.split(":", 1)[1]
            await q.message.edit_text(
                "⏳ جاري تحليل الأصل المختار فقط...",
                reply_markup=asset_keyboard("scalp")
            )
            await q.message.edit_text(
    f"⚡ سكالبينج — {symbol}\n\nاختر الفريم الذي تريد التحليل عليه:",
    reply_markup=timeframe_keyboard("scalp", symbol),
)
await q.answer()

        @self.dp.callback_query(F.data == "home")
        async def home(q: CallbackQuery):
            await q.message.edit_text(
                "اختر نوع التحليل:",
                reply_markup=keyboard()
            )
            await q.answer()

        @self.dp.callback_query(F.data == "metrics")
        async def metrics(q: CallbackQuery):
            if q.from_user.id not in self.s.admin_ids:
                await q.answer("هذا الخيار للمشرف فقط.", show_alert=True)
                return
            await q.message.edit_text(self.engine.metrics_text(), reply_markup=keyboard())
            await q.answer()

        @self.dp.message(Command("metrics"))
        async def metrics_cmd(msg: Message):
            if not self._is_admin(msg):
                return await msg.answer("هذا الأمر للمشرف فقط.")
            await msg.answer(self.engine.metrics_text())

        @self.dp.message(Command("minconfidence"))
        async def minconfidence(msg: Message):
            if not self._is_admin(msg):
                return await msg.answer("هذا الأمر للمشرف فقط.")
            parts = msg.text.split()
            if len(parts) != 2:
                return await msg.answer(f"القيمة الحالية: {self.s.min_confidence}/100\nاستخدم: /minconfidence 85")
            v = int(parts[1])
            if not 0 <= v <= 100:
                return await msg.answer("القيمة يجب أن تكون بين 0 و100.")
            self.s.min_confidence = v
            await msg.answer(f"تم تحديث الحد الأدنى إلى {v}/100.")

        @self.dp.message(Command("maxtrades"))
        async def maxtrades(msg: Message):
            if not self._is_admin(msg):
                return await msg.answer("هذا الأمر للمشرف فقط.")
            parts = msg.text.split()
            if len(parts) != 2:
                return await msg.answer(f"الحد اليومي الحالي: {self.s.max_daily_trades}\nاستخدم: /maxtrades 5")
            v = int(parts[1])
            if v < 1:
                return await msg.answer("يجب أن يكون الحد أكبر من صفر.")
            self.s.max_daily_trades = v
            await msg.answer(f"تم تحديث الحد اليومي إلى {v}.")

        @self.dp.message(Command("risk"))
        async def risk(msg: Message):
            if not self._is_admin(msg):
                return await msg.answer("هذا الأمر للمشرف فقط.")
            parts = msg.text.split()
            if len(parts) != 2:
                return await msg.answer(f"المخاطرة الحالية: {self.s.risk_per_trade*100:.2f}%\nاستخدم: /risk 0.5")
            v = float(parts[1])
            if not 0 < v <= 1:
                return await msg.answer("المجال المسموح: 0.01% إلى 1%.")
            self.s.risk_per_trade = v / 100
            await msg.answer(f"تم تحديث المخاطرة إلى {v:.2f}%.")

        @self.dp.message(Command("newsfilter"))
        async def newsfilter(msg: Message):
            if not self._is_admin(msg):
                return await msg.answer("هذا الأمر للمشرف فقط.")
            parts = msg.text.split()
            if len(parts) != 2 or parts[1] not in ("on","off"):
                return await msg.answer("استخدم: /newsfilter on أو /newsfilter off")
            self.s.news_filter_enabled = parts[1] == "on"
            from app.news import FailClosedNewsProvider, DisabledNewsProvider
            self.engine.news = FailClosedNewsProvider() if self.s.news_filter_enabled else DisabledNewsProvider()
            await msg.answer(
                "فلتر الأخبار مفعل. عند عدم توفر مصدر موثوق سيتم منع الدخول."
                if self.s.news_filter_enabled else
                "فلتر الأخبار معطل."
            )

        @self.dp.message(Command("status"))
        async def status(msg: Message):
            if not self._is_admin(msg):
                return await msg.answer("هذا الأمر للمشرف فقط.")
            await msg.answer(
                "🟢 <b>حالة النظام</b>\n\n"
                f"الأصول: {', '.join(SYMBOL_PRIORITY)}\n"
                f"Confidence: {self.s.min_confidence}/100\n"
                f"Risk: {self.s.risk_per_trade*100:.2f}%\n"
                f"الحد اليومي: {self.s.max_daily_trades}\n"
                f"فلتر الأخبار: {'مفعل' if self.s.news_filter_enabled else 'معطل'}"
            )

    async def scan_loop(self):
        if not self.s.target_chat_id:
            return
        while True:
            try:
                text = await self.engine.scan(Style.INTRADAY)
                if not text.startswith("🟡"):
                    await self.bot.send_message(self.s.target_chat_id, text)
                async for event in self.engine.monitor_once():
                    await self.bot.send_message(self.s.target_chat_id, event.message)
            except Exception:
                log.exception("background scan failed")
            await asyncio.sleep(self.s.scan_seconds)

    async def run(self):
        tasks = [asyncio.create_task(self.scan_loop())]
        try:
            await self.dp.start_polling(self.bot)
        finally:
            for t in tasks:
                t.cancel()
            await self.bot.session.close()
