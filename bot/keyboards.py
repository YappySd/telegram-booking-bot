"""Keyboards. Callback data formats are documented next to each builder."""

from __future__ import annotations

from datetime import date, time

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from bot import texts
from bot.config import Business
from bot.models import Booking

BTN_BOOK = "📅 Записаться"
BTN_MY = "🗂 Мои записи"
BTN_PRICES = "💈 Услуги и цены"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_BOOK)], [KeyboardButton(text=BTN_MY), KeyboardButton(text=BTN_PRICES)]],
        resize_keyboard=True,
    )


def book_entry(webapp_url: str | None, business: Business) -> InlineKeyboardMarkup:
    """Mini App button (if configured) plus the chat flow. Data: svc:<service_id>"""
    rows = []
    if webapp_url:
        rows.append([InlineKeyboardButton(text="✨ Открыть запись", web_app=WebAppInfo(url=webapp_url))])
    for s in business.services:
        rows.append([InlineKeyboardButton(text=f"{s.emoji} {s.title} · {s.price} {business.currency}", callback_data=f"svc:{s.id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def days_kb(service_id: str, days: list[date]) -> InlineKeyboardMarkup:
    """Data: day:<service_id>:<YYYY-MM-DD>"""
    buttons = [InlineKeyboardButton(text=texts.fmt_day(d), callback_data=f"day:{service_id}:{d.isoformat()}") for d in days[:12]]
    rows = [buttons[i : i + 3] for i in range(0, len(buttons), 3)]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back:book")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def times_kb(service_id: str, day: date, slots: list[time]) -> InlineKeyboardMarkup:
    """Data: t:<service_id>:<YYYY-MM-DD>:<HHMM>"""
    buttons = [
        InlineKeyboardButton(text=f"{t:%H:%M}", callback_data=f"t:{service_id}:{day.isoformat()}:{t:%H%M}")
        for t in slots
    ]
    rows = [buttons[i : i + 4] for i in range(0, len(buttons), 4)]
    rows.append([InlineKeyboardButton(text="⬅️ Другой день", callback_data=f"svc:{service_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_booking_kb(booking: Booking) -> InlineKeyboardMarkup:
    """Data: cx:<booking_id>"""
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отменить запись", callback_data=f"cx:{booking.id}")]])


def admin_booking_kb(booking: Booking) -> InlineKeyboardMarkup:
    """Data: acx:<booking_id>"""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Отменить", callback_data=f"acx:{booking.id}")]]
    )
