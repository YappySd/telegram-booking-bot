"""Booking use-cases: validation, rules and storage in one place.

Handlers (Telegram) and the web API both call this class, so the rules
live in exactly one spot.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Callable

from bot.config import Business
from bot.models import Booking, Service
from bot.reminders import due_reminders
from bot.slots import free_slots
from bot.storage import Storage

PHONE_RE = re.compile(r"^\+?[0-9 ()\-]{7,20}$")


@dataclass(frozen=True)
class BookResult:
    ok: bool
    booking: Booking | None = None
    error: str | None = None


def parse_day(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def parse_time(value: str) -> time | None:
    try:
        hours, minutes = str(value).split(":")
        return time(int(hours), int(minutes))
    except (TypeError, ValueError):
        return None


class BookingService:
    def __init__(self, business: Business, storage: Storage, clock: Callable[[], datetime]) -> None:
        self.business = business
        self.storage = storage
        self._clock = clock  # returns naive local time of the business

    def now(self) -> datetime:
        return self._clock()

    # ------------------------------------------------------------- queries

    def services(self) -> tuple[Service, ...]:
        return self.business.services

    def available_days(self, service_id: str) -> list[date]:
        """Days in the booking horizon that still have at least one free slot."""
        service = self.business.service(service_id)
        if service is None:
            return []
        today = self.now().date()
        days = []
        for offset in range(self.business.horizon_days + 1):
            day = date.fromordinal(today.toordinal() + offset)
            if self.slots(service_id, day):
                days.append(day)
        return days

    def slots(self, service_id: str, day: date) -> list[time]:
        service = self.business.service(service_id)
        if service is None:
            return []
        return free_slots(
            self.business,
            day,
            service,
            self.storage.for_day(day),
            self.now(),
            self.storage.days_off(),
        )

    # ------------------------------------------------------------ commands

    def book(
        self,
        *,
        user_id: int,
        user_name: str,
        phone: str,
        service_id: str,
        day: str | date,
        at: str | time,
    ) -> BookResult:
        service = self.business.service(service_id)
        if service is None:
            return BookResult(False, error="unknown_service")

        day_value = day if isinstance(day, date) else parse_day(day)
        time_value = at if isinstance(at, time) else parse_time(at)
        if day_value is None or time_value is None:
            return BookResult(False, error="bad_datetime")

        phone = (phone or "").strip()
        if phone and not PHONE_RE.match(phone):
            return BookResult(False, error="bad_phone")
        name = " ".join((user_name or "").split())[:60] or "Клиент"

        now = self.now()
        if len(self.storage.upcoming_for_user(user_id, now)) >= self.business.max_active_per_user:
            return BookResult(False, error="too_many")

        if time_value not in self.slots(service_id, day_value):
            return BookResult(False, error="slot_unavailable")

        booking = self.storage.add_if_free(
            user_id=user_id,
            user_name=name,
            phone=phone,
            service=service,
            start=datetime.combine(day_value, time_value),
            buffer_minutes=self.business.buffer_minutes,
            now=now,
        )
        if booking is None:
            return BookResult(False, error="slot_taken")
        return BookResult(True, booking=booking)

    def my_bookings(self, user_id: int) -> list[Booking]:
        return self.storage.upcoming_for_user(user_id, self.now())

    def cancel(self, booking_id: int, *, user_id: int | None = None) -> BookResult:
        """Client cancel (user_id given) or admin cancel (user_id=None)."""
        booking = self.storage.get(booking_id)
        if booking is None or (user_id is not None and booking.user_id != user_id):
            return BookResult(False, error="not_found")
        if not booking.active:
            return BookResult(False, error="already_cancelled")
        if booking.start <= self.now():
            return BookResult(False, error="past")
        self.storage.cancel(booking_id)
        return BookResult(True, booking=self.storage.get(booking_id))

    # --------------------------------------------------------------- admin

    def day_bookings(self, day: date) -> list[Booking]:
        return self.storage.for_day(day)

    def set_day_off(self, day: date, off: bool) -> int:
        """Mark a day off. Returns how many active bookings already exist on it."""
        self.storage.set_day_off(day, off)
        return len(self.storage.for_day(day)) if off else 0

    # ----------------------------------------------------------- reminders

    def reminders_due(self):
        now = self.now()
        horizon = max(self.business.reminder_hours, default=0)
        upcoming = self.storage.active_in_range(now, now + timedelta(hours=horizon + 1))
        return due_reminders(upcoming, self.storage.reminded, now, self.business.reminder_hours)

    def mark_reminded(self, booking_id: int, hours: set[int]) -> None:
        self.storage.mark_reminded(booking_id, hours)
