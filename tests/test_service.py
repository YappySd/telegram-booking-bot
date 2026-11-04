from datetime import datetime

from bot.service import BookingService
from bot.storage import Storage
from tests.helpers import EARLY, MONDAY, TUESDAY, make_business


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def make_service(now=EARLY, **business):
    clock = Clock(now)
    return BookingService(make_business(**business), Storage(), clock), clock


def book(service, user_id=1, at="10:00", day="2030-01-07", service_id="cut", phone="", name="Anna"):
    return service.book(user_id=user_id, user_name=name, phone=phone, service_id=service_id, day=day, at=at)


def test_successful_booking():
    service, _ = make_service()
    result = book(service, phone="+380 50 123-45-67")
    assert result.ok and result.booking.start == datetime(2030, 1, 7, 10, 0)
    assert result.booking.phone == "+380 50 123-45-67"


def test_booked_slot_disappears_from_the_list():
    service, _ = make_service()
    book(service)
    free = [t.strftime("%H:%M") for t in service.slots("cut", MONDAY)]
    assert "10:00" not in free and "10:30" not in free


def test_second_client_cannot_take_the_same_slot():
    service, _ = make_service()
    assert book(service, user_id=1).ok
    second = book(service, user_id=2)
    assert not second.ok and second.error == "slot_unavailable"


def test_validation_errors():
    service, _ = make_service()
    assert book(service, service_id="nope").error == "unknown_service"
    assert book(service, day="31-01-2030").error == "bad_datetime"
    assert book(service, at="ten").error == "bad_datetime"
    assert book(service, phone="abc").error == "bad_phone"
    assert book(service, at="03:00").error == "slot_unavailable"  # outside working hours
    assert book(service, day="2030-01-13").error == "slot_unavailable"  # Sunday


def test_name_is_cleaned_and_defaulted():
    service, _ = make_service()
    assert book(service, name="  Anna   Lee ").booking.user_name == "Anna Lee"
    assert book(service, user_id=2, at="11:00", name="   ").booking.user_name == "Клиент"


def test_limit_of_active_bookings_per_client():
    service, _ = make_service(max_active_per_user=2)
    assert book(service, at="10:00").ok
    assert book(service, at="11:00").ok
    assert book(service, at="13:00").error == "too_many"


def test_client_can_cancel_only_own_future_booking():
    service, clock = make_service()
    booking = book(service, user_id=1).booking
    assert service.cancel(booking.id, user_id=2).error == "not_found"
    assert service.cancel(booking.id, user_id=1).ok
    assert service.cancel(booking.id, user_id=1).error == "already_cancelled"
    assert "10:00" in [t.strftime("%H:%M") for t in service.slots("cut", MONDAY)]  # freed

    again = book(service, user_id=1).booking
    clock.now = datetime(2030, 1, 7, 10, 30)
    assert service.cancel(again.id, user_id=1).error == "past"


def test_admin_cancel_without_user_id():
    service, _ = make_service()
    booking = book(service, user_id=5).booking
    assert service.cancel(booking.id).ok


def test_day_off_blocks_booking_and_reports_existing_ones():
    service, _ = make_service()
    book(service)
    assert service.set_day_off(MONDAY, True) == 1
    assert book(service, user_id=2, at="11:00").error == "slot_unavailable"
    service.set_day_off(MONDAY, False)
    assert book(service, user_id=2, at="11:00").ok


def test_available_days_only_lists_days_with_slots():
    service, _ = make_service()
    days = service.available_days("cut")
    assert MONDAY in days and TUESDAY in days
    assert all(d.weekday() != 6 for d in days)  # Sundays have no schedule


def test_my_bookings_lists_only_upcoming_active():
    service, clock = make_service()
    first = book(service, user_id=1, at="10:00").booking
    book(service, user_id=1, at="11:00")
    service.cancel(first.id, user_id=1)
    assert [b.start.strftime("%H:%M") for b in service.my_bookings(1)] == ["11:00"]
