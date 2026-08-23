from __future__ import annotations
import logging
from app.config import Settings
from app.logging_setup import setup_logging
from app.bot import TelegramApp

async def run():
    settings = Settings.from_env()
    settings.validate()
    setup_logging(settings.log_level)
    logging.getLogger(__name__).info("starting trading signal bot")
    await TelegramApp(settings).run()
