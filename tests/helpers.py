from datetime import datetime, time

from bot.config import parse_business
from bot.models import Booking

BUSINESS_DATA = {
    "name": "Test",
    "currency": "₴",
    "step_minutes": 30,
    "buffer_minutes": 0,
    "min_lead_minutes": 60,
    "horizon_days": 14,
    "reminders_hours": [24, 2],
    "max_active_per_user": 3,
    "schedule": {"0": [["10:00", "14:00"]], "1": [["10:00", "12:00"], ["15:00", "17:00"]], "6": []},
    "breaks": [["12:00", "12:30"]],
    "services": [
        {"id": "cut", "title": "Cut", "minutes": 60, "price": 500},
        {"id": "quick", "title": "Quick", "minutes": 30, "price": 200},
    ],
}


def make_business(**overrides):
    data = {**BUSINESS_DATA, **overrides}
    return parse_business(data)


# 2030-01-07 is a Monday, 2030-01-08 a Tuesday, 2030-01-13 a Sunday.
MONDAY = datetime(2030, 1, 7).date()
TUESDAY = datetime(2030, 1, 8).date()
SUNDAY = datetime(2030, 1, 13).date()
EARLY = datetime(2030, 1, 7, 6, 0)  # well before opening on Monday


def booking(start, minutes=60, *, id=1, user_id=1, status="active", service_id="cut", created=None):
    return Booking(
        id=id,
        user_id=user_id,
        user_name="Test",
        phone="",
        service_id=service_id,
        start=start,
        minutes=minutes,
        status=status,
        created_at=created or datetime(2029, 12, 1, 9, 0),
    )


def times(values):
    return [t.strftime("%H:%M") for t in values]
