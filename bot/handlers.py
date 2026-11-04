"""Telegram handlers (aiogram 3). All rules live in BookingService."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

from bot import keyboards, texts
from bot.service import BookingService, parse_day, parse_time


def build_router(service: BookingService, admin_ids: frozenset[int], webapp_url: str | None, on_booked, on_cancelled) -> Router:
    router = Router()
    business = service.business

    def is_admin(user_id: int) -> bool:
        return user_id in admin_ids

    # ------------------------------------------------------------ client

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        await message.answer(texts.welcome(business), reply_markup=keyboards.main_menu())

    @router.message(F.text == keyboards.BTN_BOOK)
    async def book_menu(message: Message) -> None:
        await message.answer(texts.CHOOSE_HOW, reply_markup=keyboards.book_entry(webapp_url, business))

    @router.message(F.text == keyboards.BTN_PRICES)
    async def prices(message: Message) -> None:
        await message.answer(texts.price_list(business))

    @router.message(F.text == keyboards.BTN_MY)
    async def my_bookings(message: Message) -> None:
        items = await asyncio.to_thread(service.my_bookings, message.from_user.id)
        if not items:
            await message.answer(texts.NO_BOOKINGS)
            return
        for booking in items:
            await message.answer(texts.booking_line(booking, business), reply_markup=keyboards.my_booking_kb(booking))

    @router.callback_query(F.data == "back:book")
    async def back_to_services(callback: CallbackQuery) -> None:
        await callback.message.edit_text(texts.CHOOSE_HOW, reply_markup=keyboards.book_entry(webapp_url, business))
        await callback.answer()

    @router.callback_query(F.data.startswith("svc:"))
    async def pick_service(callback: CallbackQuery) -> None:
        service_id = callback.data.split(":", 1)[1]
        days = await asyncio.to_thread(service.available_days, service_id)
        if not days:
            await callback.message.edit_text(texts.NO_DAYS)
        else:
            await callback.message.edit_text(texts.CHOOSE_DAY, reply_markup=keyboards.days_kb(service_id, days))
        await callback.answer()

    @router.callback_query(F.data.startswith("day:"))
    async def pick_day(callback: CallbackQuery) -> None:
        _, service_id, raw_day = callback.data.split(":", 2)
        day = parse_day(raw_day)
        slots = await asyncio.to_thread(service.slots, service_id, day) if day else []
        if not slots:
            await callback.answer(texts.NO_SLOTS, show_alert=True)
            return
        await callback.message.edit_text(
            f"<b>{texts.fmt_day(day)}</b>\nВыберите время:", reply_markup=keyboards.times_kb(service_id, day, slots)
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("t:"))
    async def pick_time(callback: CallbackQuery) -> None:
        _, service_id, raw_day, raw_time = callback.data.split(":", 3)
        at = parse_time(f"{raw_time[:2]}:{raw_time[2:]}")
        user = callback.from_user
        result = await asyncio.to_thread(
            lambda: service.book(
                user_id=user.id,
                user_name=user.full_name,
                phone="",
                service_id=service_id,
                day=raw_day,
                at=at or "",
            )
        )
        if not result.ok:
            await callback.answer(texts.error_text(result.error), show_alert=True)
            return
        await callback.message.edit_text(texts.booked_client(result.booking, business))
        await callback.answer("Готово")
        await on_booked(result.booking, notify_client=False)  # confirmation is already shown in this chat

    @router.callback_query(F.data.startswith("cx:"))
    async def client_cancel(callback: CallbackQuery) -> None:
        booking_id = int(callback.data.split(":", 1)[1])
        result = await asyncio.to_thread(lambda: service.cancel(booking_id, user_id=callback.from_user.id))
        if not result.ok:
            await callback.answer(texts.error_text(result.error), show_alert=True)
            return
        await callback.message.edit_text("Запись отменена.")
        await callback.answer()
        await on_cancelled(result.booking, True)

    # ------------------------------------------------------------- admin

    async def guard(message: Message) -> bool:
        if not is_admin(message.from_user.id):
            await message.answer(texts.NOT_ADMIN)
            return False
        return True

    async def show_day(message: Message, day: date) -> None:
        items = await asyncio.to_thread(service.day_bookings, day)
        await message.answer(texts.day_schedule(day, items, business))

    @router.message(Command("admin"))
    async def admin_help(message: Message) -> None:
        if await guard(message):
            await message.answer(texts.ADMIN_HELP)

    @router.message(Command("today"))
    async def today(message: Message) -> None:
        if await guard(message):
            await show_day(message, service.now().date())

    @router.message(Command("tomorrow"))
    async def tomorrow(message: Message) -> None:
        if await guard(message):
            await show_day(message, service.now().date() + timedelta(days=1))

    @router.message(Command("day"))
    async def day_cmd(message: Message, command: CommandObject) -> None:
        if not await guard(message):
            return
        day = parse_day((command.args or "").strip())
        if day is None:
            await message.answer(texts.BAD_ARGUMENT)
            return
        await show_day(message, day)

    @router.message(Command("cancel"))
    async def cancel_cmd(message: Message, command: CommandObject) -> None:
        if not await guard(message):
            return
        arg = (command.args or "").strip()
        if not arg.isdigit():
            await message.answer("Формат: /cancel 12")
            return
        result = await asyncio.to_thread(service.cancel, int(arg))
        if not result.ok:
            await message.answer(texts.error_text(result.error))
            return
        await message.answer(f"Запись №{arg} отменена.")
        await on_cancelled(result.booking, False)

    @router.message(Command("dayoff"))
    async def dayoff(message: Message, command: CommandObject) -> None:
        if not await guard(message):
            return
        day = parse_day((command.args or "").strip())
        if day is None:
            await message.answer(texts.BAD_ARGUMENT)
            return
        existing = await asyncio.to_thread(service.set_day_off, day, True)
        note = f" Внимание: на этот день уже есть записей: {existing}. Они не отменены." if existing else ""
        await message.answer(f"День {day.isoformat()} закрыт для записи.{note}")

    @router.message(Command("dayon"))
    async def dayon(message: Message, command: CommandObject) -> None:
        if not await guard(message):
            return
        day = parse_day((command.args or "").strip())
        if day is None:
            await message.answer(texts.BAD_ARGUMENT)
            return
        await asyncio.to_thread(service.set_day_off, day, False)
        await message.answer(f"День {day.isoformat()} снова открыт.")

    @router.callback_query(F.data.startswith("acx:"))
    async def admin_cancel(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id):
            await callback.answer(texts.NOT_ADMIN, show_alert=True)
            return
        booking_id = int(callback.data.split(":", 1)[1])
        result = await asyncio.to_thread(service.cancel, booking_id)
        if not result.ok:
            await callback.answer(texts.error_text(result.error), show_alert=True)
            return
        await callback.message.edit_text(f"Запись №{booking_id} отменена.")
        await callback.answer()
        await on_cancelled(result.booking, False)

    return router
