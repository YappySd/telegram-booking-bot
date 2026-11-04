from datetime import datetime, timedelta

from bot.reminders import due_reminders
from tests.helpers import booking

START = datetime(2030, 1, 7, 12, 0)


def run(now, bookings, sent=None, hours=(24, 2)):
    sent = sent or {}
    return due_reminders(bookings, lambda bid: sent.get(bid, set()), now, hours)


def test_nothing_due_far_ahead():
    assert run(START - timedelta(hours=30), [booking(START)]) == []


def test_day_before_reminder():
    result = run(START - timedelta(hours=23, minutes=30), [booking(START)])
    assert [(b.id, h, mark) for b, h, mark in result] == [(1, 24, {24})]


def test_two_hour_reminder_after_day_reminder():
    result = run(START - timedelta(hours=1, minutes=50), [booking(START)], sent={1: {24}})
    assert [(h, mark) for _, h, mark in result] == [(2, {24, 2})]


def test_no_repeat_once_sent():
    assert run(START - timedelta(hours=1), [booking(START)], sent={1: {24, 2}}) == []


def test_late_booking_skips_thresholds_that_were_already_past():
    created = START - timedelta(hours=5)  # booked 5h before: the 24h message makes no sense
    result = run(START - timedelta(hours=1, minutes=50), [booking(START, created=created)])
    assert [(h, mark) for _, h, mark in result] == [(2, {2})]


def test_if_bot_was_down_only_the_closest_reminder_is_sent():
    result = run(START - timedelta(hours=1), [booking(START)])
    assert [(h, mark) for _, h, mark in result] == [(2, {24, 2})]


def test_cancelled_and_past_bookings_are_ignored():
    assert run(START - timedelta(hours=1), [booking(START, status="cancelled")]) == []
    assert run(START + timedelta(minutes=1), [booking(START)]) == []
