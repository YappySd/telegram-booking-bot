"""Which reminders are due. Pure logic plus a small async loop."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Iterable

from bot.models import Booking


def due_reminders(
    bookings: Iterable[Booking],
    already_sent: Callable[[int], set[int]],
    now: datetime,
    hours: tuple[int, ...],
) -> list[tuple[Booking, int, set[int]]]:
    """Return (booking, hours_before, all_hours_to_mark) for reminders to send now.

    A threshold counts only if the booking was made before it: a client who books
    for tomorrow morning from the evening should not get a "24 hours" message.
    If several thresholds passed while the bot was down, only the closest is sent.
    """
    result = []
    for booking in bookings:
        if not booking.active or booking.start <= now:
            continue
        sent = already_sent(booking.id)
        due = [
            h for h in hours
            if h not in sent
            and booking.created_at <= booking.start - timedelta(hours=h)
            and now >= booking.start - timedelta(hours=h)
        ]
        if due:
            result.append((booking, min(due), sent | set(due)))
    return result


async def reminder_loop(
    service,
    notify: Callable[[Booking, int], Awaitable[None]],
    *,
    interval: float = 60.0,
) -> None:
    """Check once a minute; a failing notification must not stop the loop."""
    while True:
        try:
            for booking, hours, mark in await asyncio.to_thread(service.reminders_due):
                try:
                    await notify(booking, hours)
                except Exception:  # noqa: BLE001 - one failed message must not block the others
                    pass
                finally:
                    await asyncio.to_thread(service.mark_reminded, booking.id, mark)
        except Exception:  # noqa: BLE001 - keep the loop alive
            pass
        await asyncio.sleep(interval)
