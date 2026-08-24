from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from app.config import Settings, SYMBOL_PRIORITY
from app.models import Style
from app.engine import SignalEngine, ScanResult


log = logging.getLogger(__name__)


def keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 صفقة انتظار دخول",
                    callback_data="trade_menu",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎯 صفقة دخول مباشر",
                    callback_data="direct_menu",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚡ سكالبينج",
                    callback_data="scalp_menu",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📈 الأداء",
                    callback_data="metrics",
                )
            ],
        ]
    )


def asset_keyboard(mode: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🥇 الذهب - XAUUSD",
                    callback_data=f"{mode}:XAUUSD",
                ),
                InlineKeyboardButton(
                    text="₿ بيتكوين - BTCUSDT",
                    callback_data=f"{mode}:BTCUSDT",
                ),
                InlineKeyboardButton(
                    text="💶 يورو/دولار - EURUSD",
                    callback_data=f"{mode}:EURUSD",
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


class TelegramApp:
    def __init__(self, settings: Settings):
        self.s = settings
        self.engine = SignalEngine(settings)
        self.bot = Bot(
            settings.telegram_bot_token,
            default=DefaultBotProperties(
                parse_mode=ParseMode.HTML
            ),
        )
        self.dp = Dispatcher()

        # setup_id -> original Telegram message info
        self.signal_messages: dict[str, tuple[int, int, str]] = {}

        self._wire()

    def _is_admin(self, msg: Message) -> bool:
        return bool(
            msg.from_user
            and msg.from_user.id in self.s.admin_ids
        )

    async def _run_scan(
        self,
        q: CallbackQuery,
        *,
        style: Style,
        mode: str,
    ):
        _, symbol, timeframe = q.data.split(":", 2)
        await q.answer()
        await q.message.edit_text("⏳ جاري تحليل السوق...")

        result: ScanResult = await self.engine.scan(
            style,
            selected_symbol=symbol,
            timeframe=timeframe,
            mode=mode,
        )

        await q.message.edit_text(
            result.text,
            reply_markup=keyboard(),
        )

        if result.setup_id:
            self.signal_messages[result.setup_id] = (
                q.message.chat.id,
                q.message.message_id,
                result.text,
            )

    def _append_event(self, original: str, event_text: str) -> str:
        if event_text in original:
            return original
        return original + f"\n\n{event_text}"

    async def _monitor_loop(self):
        while True:
            try:
                async for event in self.engine.monitor_once():
                    mapping = self.signal_messages.get(event.setup_id)
                    if not mapping:
                        continue

                    chat_id, message_id, original = mapping
                    updated = self._append_event(
                        original,
                        event.message,
                    )

                    try:
                        await self.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=updated,
                            reply_markup=keyboard(),
                        )
                    except Exception:
                        # If a message cannot be edited anymore, keep the
                        # monitoring state alive and send a concise event.
                        await self.bot.send_message(
                            chat_id,
                            event.message,
                            reply_markup=keyboard(),
                        )

                    self.signal_messages[event.setup_id] = (
                        chat_id,
                        message_id,
                        updated,
                    )

            except Exception:
                log.exception("background monitor failed")

            await asyncio.sleep(5)

    def _wire(self):
        @self.dp.message(Command("start"))
        async def start(msg: Message):
            await msg.answer(
                "أهلاً بك.\n"
                "اختر طريقة الدخول التي تريدها، ثم الأصل والفريم.",
                reply_markup=keyboard(),
            )

        @self.dp.callback_query(F.data == "trade_menu")
        async def trade_menu(q: CallbackQuery):
            await q.answer()
            await q.message.edit_text(
                "📊 <b>صفقة انتظار دخول</b>\n\nاختر الأصل:",
                reply_markup=asset_keyboard("trade"),
            )

        @self.dp.callback_query(F.data == "direct_menu")
        async def direct_menu(q: CallbackQuery):
            await q.answer()
            await q.message.edit_text(
                "🎯 <b>صفقة دخول مباشر</b>\n\n"
                "هذه الطريقة تعتبر الصفقة مفعّلة مباشرة بعد التحليل.\n"
                "اختر الأصل:",
                reply_markup=asset_keyboard("direct"),
            )

        @self.dp.callback_query(F.data == "scalp_menu")
        async def scalp_menu(q: CallbackQuery):
            await q.answer()
            await q.message.edit_text(
                "⚡ <b>سكالبينج</b>\n\nاختر الأصل:",
                reply_markup=asset_keyboard("scalp"),
            )

        @self.dp.callback_query(F.data.startswith("trade_tf:"))
        async def trade_timeframe(q: CallbackQuery):
            await self._run_scan(
                q,
                style=Style.INTRADAY,
                mode="PENDING",
            )

        @self.dp.callback_query(F.data.startswith("direct_tf:"))
        async def direct_timeframe(q: CallbackQuery):
            await self._run_scan(
                q,
                style=Style.INTRADAY,
                mode="DIRECT",
            )

        @self.dp.callback_query(F.data.startswith("scalp_tf:"))
        async def scalp_timeframe(q: CallbackQuery):
            await self._run_scan(
                q,
                style=Style.SCALPING,
                mode="PENDING",
            )

        @self.dp.callback_query(F.data.startswith("trade:"))
        async def trade_asset(q: CallbackQuery):
            await q.answer()
            symbol = q.data.split(":", 1)[1]
            await q.message.edit_text(
                f"📊 {symbol}\n\nاختر الفريم:",
                reply_markup=timeframe_keyboard("trade", symbol),
            )

        @self.dp.callback_query(F.data.startswith("direct:"))
        async def direct_asset(q: CallbackQuery):
            await q.answer()
            symbol = q.data.split(":", 1)[1]
            await q.message.edit_text(
                f"🎯 {symbol}\n\nاختر الفريم للدخول المباشر:",
                reply_markup=timeframe_keyboard("direct", symbol),
            )

        @self.dp.callback_query(F.data.startswith("scalp:"))
        async def scalp_asset(q: CallbackQuery):
            await q.answer()
            symbol = q.data.split(":", 1)[1]
            await q.message.edit_text(
                f"⚡ سكالبينج — {symbol}\n\nاختر الفريم:",
                reply_markup=timeframe_keyboard("scalp", symbol),
            )

        @self.dp.callback_query(F.data == "home")
        async def home(q: CallbackQuery):
            await q.answer()
            await q.message.edit_text(
                "اختر طريقة الدخول:",
                reply_markup=keyboard(),
            )

        @self.dp.callback_query(F.data == "metrics")
        async def metrics(q: CallbackQuery):
            if q.from_user.id not in self.s.admin_ids:
                await q.answer(
                    "هذا الخيار للمشرف فقط.",
                    show_alert=True,
                )
                return

            await q.answer()
            await q.message.edit_text(
                self.engine.metrics_text(),
                reply_markup=keyboard(),
            )

        @self.dp.message(Command("minconfidence"))
        async def minconfidence(msg: Message):
            if not self._is_admin(msg):
                return await msg.answer("هذا الأمر للمشرف فقط.")

            parts = msg.text.split()
            if len(parts) != 2:
                return await msg.answer(
                    f"القيمة الحالية: {self.s.min_confidence}/100\n"
                    "استخدم: /minconfidence 85"
                )

            v = int(parts[1])
            if not 0 <= v <= 100:
                return await msg.answer(
                    "القيمة يجب أن تكون بين 0 و100."
                )

            self.s.min_confidence = v
            await msg.answer(
                f"تم تحديث الحد الأدنى إلى {v}/100."
            )

        @self.dp.message(Command("risk"))
        async def risk(msg: Message):
            if not self._is_admin(msg):
                return await msg.answer("هذا الأمر للمشرف فقط.")

            parts = msg.text.split()
            if len(parts) != 2:
                return await msg.answer(
                    f"المخاطرة الحالية: "
                    f"{self.s.risk_per_trade * 100:.2f}%\n"
                    "استخدم: /risk 0.5"
                )

            v = float(parts[1])
            if not 0 < v <= 1:
                return await msg.answer(
                    "المجال المسموح: 0.01% إلى 1%."
                )

            self.s.risk_per_trade = v / 100
            await msg.answer(
                f"تم تحديث المخاطرة إلى {v:.2f}%."
            )

        @self.dp.message(Command("newsfilter"))
        async def newsfilter(msg: Message):
            if not self._is_admin(msg):
                return await msg.answer("هذا الأمر للمشرف فقط.")

            parts = msg.text.split()
            if len(parts) != 2 or parts[1] not in ("on", "off"):
                return await msg.answer(
                    "استخدم: /newsfilter on أو /newsfilter off"
                )

            self.s.news_filter_enabled = parts[1] == "on"
            from app.news import (
                FailClosedNewsProvider,
                DisabledNewsProvider,
            )

            self.engine.news = (
                FailClosedNewsProvider()
                if self.s.news_filter_enabled
                else DisabledNewsProvider()
            )

            await msg.answer(
                "فلتر الأخبار مفعل. عند عدم توفر مصدر موثوق سيتم منع الدخول."
                if self.s.news_filter_enabled
                else "فلتر الأخبار معطل."
            )

    async def run(self):
        monitor_task = asyncio.create_task(
            self._monitor_loop()
        )
        try:
            await self.dp.start_polling(self.bot)
        finally:
            monitor_task.cancel()
            await self.bot.session.close()
