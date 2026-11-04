import threading
from datetime import datetime

from bot.storage import Storage
from tests.helpers import make_business

NOW = datetime(2030, 1, 1, 9, 0, 0)
START = datetime(2030, 1, 7, 10, 0)


def add(storage, business, user_id=1, start=START, service_id="cut", buffer=0):
    return storage.add_if_free(
        user_id=user_id,
        user_name="Anna",
        phone="",
        service=business.service(service_id),
        start=start,
        buffer_minutes=buffer,
        now=NOW,
    )


def test_add_and_read_back():
    business = make_business()
    storage = Storage()
    booking = add(storage, business)
    assert booking is not None and booking.id == 1
    assert booking.start == START and booking.end == datetime(2030, 1, 7, 11, 0)
    assert storage.get(1).user_name == "Anna"


def test_overlapping_booking_is_rejected():
    business = make_business()
    storage = Storage()
    assert add(storage, business) is not None
    assert add(storage, business, user_id=2, start=datetime(2030, 1, 7, 10, 30)) is None
    assert add(storage, business, user_id=2, start=datetime(2030, 1, 7, 11, 0)) is not None  # back-to-back is fine


def test_buffer_is_enforced_by_the_database_too():
    business = make_business()
    storage = Storage()
    assert add(storage, business, buffer=30) is not None
    assert add(storage, business, user_id=2, start=datetime(2030, 1, 7, 11, 0), buffer=30) is None


def test_cancelled_slot_can_be_booked_again():
    business = make_business()
    storage = Storage()
    first = add(storage, business)
    assert storage.cancel(first.id) is True
    assert storage.cancel(first.id) is False  # already cancelled
    assert add(storage, business, user_id=2) is not None


def test_concurrent_requests_for_one_slot_produce_exactly_one_booking():
    business = make_business()
    storage = Storage()
    results = []

    def worker(user_id):
        results.append(add(storage, business, user_id=user_id))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, 21)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(1 for r in results if r is not None) == 1
    assert len(storage.for_day(START.date())) == 1


def test_upcoming_for_user_and_day_queries():
    business = make_business()
    storage = Storage()
    add(storage, business, user_id=1)
    add(storage, business, user_id=2, start=datetime(2030, 1, 7, 13, 0))
    assert [b.user_id for b in storage.for_day(START.date())] == [1, 2]
    assert [b.user_id for b in storage.upcoming_for_user(1, NOW)] == [1]
    assert storage.upcoming_for_user(1, datetime(2030, 1, 8)) == []


def test_days_off_roundtrip():
    storage = Storage()
    day = datetime(2030, 1, 9).date()
    storage.set_day_off(day, True)
    storage.set_day_off(day, True)  # idempotent
    assert storage.days_off() == frozenset([day])
    storage.set_day_off(day, False)
    assert storage.days_off() == frozenset()


def test_reminded_flags():
    business = make_business()
    storage = Storage()
    booking = add(storage, business)
    assert storage.reminded(booking.id) == set()
    storage.mark_reminded(booking.id, {24, 2})
    assert storage.reminded(booking.id) == {24, 2}


def test_data_survives_reopening_the_file(tmp_path):
    business = make_business()
    path = str(tmp_path / "b.db")
    first = Storage(path)
    add(first, business)
    first.close()
    assert Storage(path).get(1).user_name == "Anna"
