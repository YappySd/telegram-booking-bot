from datetime import datetime, timedelta

from bot.slots import free_slots, overlaps
from tests.helpers import EARLY, MONDAY, SUNDAY, TUESDAY, booking, make_business, times


def slots(service_id="cut", day=MONDAY, bookings=(), now=EARLY, days_off=frozenset(), **business):
    b = make_business(**business)
    return free_slots(b, day, b.service(service_id), list(bookings), now, days_off)


def test_full_day_respects_working_hours_and_service_length():
    # Monday 10:00-14:00, break 12:00-12:30, one-hour service, step 30.
    # 11:00-12:00 ends exactly when the break starts (allowed); 11:30 and 12:00 hit the break.
    assert times(slots()) == ["10:00", "10:30", "11:00", "12:30", "13:00"]


def test_short_service_fits_more_slots():
    assert times(slots("quick")) == ["10:00", "10:30", "11:00", "11:30", "12:30", "13:00", "13:30"]


def test_two_working_windows_on_one_day():
    assert times(slots("quick", day=TUESDAY)) == ["10:00", "10:30", "11:00", "11:30", "15:00", "15:30", "16:00", "16:30"]


def test_day_without_schedule_has_no_slots():
    assert slots(day=SUNDAY) == []


def test_booking_blocks_overlapping_slots_but_not_back_to_back():
    taken = booking(datetime(2030, 1, 7, 10, 30), 60)  # 10:30-11:30
    # one-hour service: 10:00-11:00 overlaps, 11:30-12:30 runs into the break
    assert times(slots(bookings=[taken])) == ["12:30", "13:00"]
    result = times(slots("quick", bookings=[taken]))
    assert "10:00" in result  # 10:00-10:30 ends exactly when the booking starts
    assert "10:30" not in result and "11:00" not in result
    assert "11:30" in result  # starts exactly when the booking ends


def test_cancelled_booking_does_not_block():
    cancelled = booking(datetime(2030, 1, 7, 10, 0), 60, status="cancelled")
    assert "10:00" in times(slots(bookings=[cancelled]))


def test_buffer_keeps_distance_between_bookings():
    taken = booking(datetime(2030, 1, 7, 10, 0), 60)
    assert "11:00" not in times(slots("quick", bookings=[taken], buffer_minutes=30))
    assert "11:30" in times(slots("quick", bookings=[taken], buffer_minutes=30))


def test_min_lead_time_hides_near_slots():
    now = datetime(2030, 1, 7, 9, 30)  # lead 60 min -> earliest 10:30
    assert times(slots("quick", now=now))[0] == "10:30"


def test_past_days_and_far_future_are_empty():
    now = datetime(2030, 1, 8, 6, 0)
    assert slots(day=MONDAY, now=now) == []
    far = MONDAY + timedelta(days=60)
    assert slots(day=far, now=EARLY) == []


def test_day_off_removes_all_slots():
    assert slots(days_off=frozenset([MONDAY])) == []


def test_service_that_never_fits_gives_no_slots():
    b = make_business(schedule={"0": [["10:00", "10:30"]]}, breaks=[])
    assert free_slots(b, MONDAY, b.service("cut"), [], EARLY) == []


def test_overlaps_is_half_open():
    a = datetime(2030, 1, 7, 10, 0)
    b = datetime(2030, 1, 7, 11, 0)
    c = datetime(2030, 1, 7, 12, 0)
    assert not overlaps(a, b, b, c)
    assert overlaps(a, c, b, c)
