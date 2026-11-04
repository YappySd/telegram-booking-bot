"""All user-facing text in one place."""

from __future__ import annotations

import html
from datetime import date

from bot.config import Business
from bot.models import Booking

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]

ERRORS = {
    "unknown_service": "Такой услуги нет.",
    "bad_datetime": "Не удалось разобрать дату или время.",
    "bad_phone": "Телефон указан неверно. Пример: +380 50 123-45-67.",
    "too_many": "У вас уже максимум активных записей. Отмените одну или дождитесь визита.",
    "slot_unavailable": "Это время недоступно. Выберите другое.",
    "slot_taken": "Это время только что заняли. Выберите другое.",
    "not_found": "Запись не найдена.",
    "already_cancelled": "Эта запись уже отменена.",
    "past": "Прошедшую запись отменить нельзя.",
    "unauthorized": "Откройте запись через кнопку в чате с ботом.",
}


def error_text(code: str | None) -> str:
    return ERRORS.get(code or "", "Что-то пошло не так. Попробуйте ещё раз.")


def fmt_day(day: date) -> str:
    return f"{WEEKDAYS[day.weekday()].capitalize()}, {day.day} {MONTHS[day.month - 1]}"


def fmt_when(booking: Booking) -> str:
    return f"{fmt_day(booking.start.date())}, {booking.start:%H:%M}"


def e(value: str) -> str:
    return html.escape(value, quote=False)


def welcome(business: Business) -> str:
    return (
        f"Здравствуйте! Это запись в <b>{e(business.name)}</b>.\n"
        "Выберите удобное время за пару нажатий, а за день и за пару часов до визита я напомню о записи."
    )


def price_list(business: Business) -> str:
    lines = ["<b>Услуги и цены</b>", ""]
    for s in business.services:
        lines.append(f"{s.emoji} {e(s.title)}: {s.price} {business.currency}, {s.minutes} мин")
    return "\n".join(lines)


def booking_line(booking: Booking, business: Business) -> str:
    service = business.service(booking.service_id)
    title = service.title if service else booking.service_id
    return f"{e(title)}, {fmt_when(booking)}"


def booked_client(booking: Booking, business: Business) -> str:
    return f"✅ <b>Вы записаны</b>\n{booking_line(booking, business)}\n\nЕсли планы изменятся, отмените запись в разделе «Мои записи»."


def booked_admin(booking: Booking, business: Business) -> str:
    phone = f"\nТелефон: {e(booking.phone)}" if booking.phone else ""
    return (
        f"🆕 <b>Новая запись №{booking.id}</b>\n{booking_line(booking, business)}\n"
        f"Клиент: {e(booking.user_name)}{phone}"
    )


def cancelled_admin(booking: Booking, business: Business, by_client: bool) -> str:
    who = "клиентом" if by_client else "мастером"
    return f"❌ Запись №{booking.id} отменена {who}\n{booking_line(booking, business)}\nКлиент: {e(booking.user_name)}"


def cancelled_client(booking: Booking, business: Business) -> str:
    return f"Ваша запись отменена мастером:\n{booking_line(booking, business)}\nВыберите другое время в разделе «Записаться»."


def reminder(booking: Booking, business: Business, hours: int) -> str:
    when = "завтра" if hours >= 24 else f"через {hours} ч"
    return f"⏰ Напоминаю: {when} у вас запись.\n{booking_line(booking, business)}"


def service_title(booking: Booking, business: Business) -> str:
    service = business.service(booking.service_id)
    return service.title if service else booking.service_id


def day_schedule(day: date, bookings: list[Booking], business: Business) -> str:
    if not bookings:
        return f"<b>{fmt_day(day)}</b>\nЗаписей нет."
    lines = [f"<b>{fmt_day(day)}</b>"]
    for b in bookings:
        phone = f", {e(b.phone)}" if b.phone else ""
        lines.append(f"№{b.id} {b.start:%H:%M}-{b.end:%H:%M} {e(service_title(b, business))}: {e(b.user_name)}{phone}")
    return "\n".join(lines)


NO_BOOKINGS = "У вас нет предстоящих записей."
NO_DAYS = "Свободных дат пока нет. Загляните позже."
NO_SLOTS = "На этот день свободного времени не осталось."
CHOOSE_HOW = "Выберите, как записаться:"
CHOOSE_DAY = "Выберите день:"
NOT_ADMIN = "Эта команда только для администратора."
BAD_ARGUMENT = "Не понял дату. Формат: ГГГГ-ММ-ДД, например 2030-01-07."
ADMIN_HELP = (
    "<b>Команды мастера</b>\n"
    "/today: записи на сегодня\n"
    "/tomorrow: записи на завтра\n"
    "/day 2030-01-07: записи на дату\n"
    "/cancel 12: отменить запись №12\n"
    "/dayoff 2030-01-07: закрыть день\n"
    "/dayon 2030-01-07: снова открыть день"
)
