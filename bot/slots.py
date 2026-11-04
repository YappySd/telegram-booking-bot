"""Free-slot calculation. Pure functions: no I/O, easy to test."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Iterable

from bot.config import Business
from bot.models import Booking, Service


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Half-open intervals: back-to-back bookings do not overlap."""
    return a_start < b_end and b_start < a_end


def free_slots(
    business: Business,
    day: date,
    service: Service,
    bookings: Iterable[Booking],
    now: datetime,
    days_off: frozenset[date] = frozenset(),
) -> list[time]:
    """Start times on `day` where `service` fits.

    A slot must lie inside a working window, avoid breaks, keep the buffer
    to neighbouring bookings and start no earlier than now + min_lead.
    """
    today = now.date()
    if day < today or day > today + timedelta(days=business.horizon_days) or day in days_off:
        return []

    earliest = now + timedelta(minutes=business.min_lead_minutes)
    buffer = timedelta(minutes=business.buffer_minutes)
    duration = timedelta(minutes=service.minutes)
    step = timedelta(minutes=business.step_minutes)

    blocked = [(b.start - buffer, b.end + buffer) for b in bookings if b.active and b.start.date() == day]
    blocked += [(datetime.combine(day, s), datetime.combine(day, e)) for s, e in business.breaks]

    result: list[time] = []
    for window_start, window_end in business.hours_for(day.weekday()):
        cursor = datetime.combine(day, window_start)
        limit = datetime.combine(day, window_end)
        while cursor + duration <= limit:
            end = cursor + duration
            if cursor >= earliest and not any(overlaps(cursor, end, b0, b1) for b0, b1 in blocked):
                result.append(cursor.time())
            cursor += step
    return result
