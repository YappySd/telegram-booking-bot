"""Entry point:  python -m bot.main"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

from bot import keyboards, texts
from bot.config import ConfigError, load_business, load_settings
from bot.handlers import build_router
from bot.reminders import reminder_loop
from bot.service import BookingService
from bot.storage import Storage
from bot.web import create_web_app

log = logging.getLogger("booking")


async def amain() -> None:
    settings = load_settings()
    business = load_business(settings.business_path)
    storage = Storage(settings.db_path)
    tz = settings.timezone
    service = BookingService(business, storage, lambda: datetime.now(tz).replace(tzinfo=None))

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    async def safe_send(chat_id: int, text: str, **kwargs) -> None:
        try:
            await bot.send_message(chat_id, text, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a blocked user must not break the flow
            log.warning("Не удалось отправить сообщение %s: %s", chat_id, type(exc).__name__)

    async def on_booked(booking, notify_client: bool = True) -> None:
        if notify_client:
            await safe_send(booking.user_id, texts.booked_client(booking, business))
        for admin_id in settings.admin_ids:
            await safe_send(admin_id, texts.booked_admin(booking, business), reply_markup=keyboards.admin_booking_kb(booking))

    async def on_cancelled(booking, by_client: bool) -> None:
        for admin_id in settings.admin_ids:
            await safe_send(admin_id, texts.cancelled_admin(booking, business, by_client))
        if not by_client:
            await safe_send(booking.user_id, texts.cancelled_client(booking, business))

    async def notify_reminder(booking, hours: int) -> None:
        await safe_send(booking.user_id, texts.reminder(booking, business, hours))

    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(service, settings.admin_ids, settings.webapp_url, on_booked, on_cancelled))

    runner = None
    if settings.webapp_url:
        runner = web.AppRunner(create_web_app(service, settings.bot_token, on_booked, on_cancelled))
        await runner.setup()
        await web.TCPSite(runner, settings.host, settings.port).start()
        log.info("Mini App слушает %s:%s", settings.host, settings.port)

    reminders = asyncio.create_task(reminder_loop(service, notify_reminder))
    log.info("Бот запущен: %s, администраторов: %s", business.name, len(settings.admin_ids))
    try:
        await dispatcher.start_polling(bot)
    finally:
        reminders.cancel()
        if runner:
            await runner.cleanup()
        await bot.session.close()
        storage.close()


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    try:
        asyncio.run(amain())
    except ConfigError as exc:
        sys.exit(f"Ошибка настройки: {exc}")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
