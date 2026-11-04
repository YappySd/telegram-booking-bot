"""SQLite storage. The double-booking check and the insert are one transaction."""

from __future__ import annotations

import sqlite3
import threading
from datetime import date, datetime, timedelta

from bot.models import Booking, Service
from bot.slots import overlaps

_ISO_MIN = "%Y-%m-%dT%H:%M"
_ISO_SEC = "%Y-%m-%dT%H:%M:%S"

SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    user_name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    service_id TEXT NOT NULL,
    start TEXT NOT NULL,
    minutes INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    reminded TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_bookings_start ON bookings(start);
CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id);
CREATE TABLE IF NOT EXISTS days_off (day TEXT PRIMARY KEY);
"""


def _to_booking(row: sqlite3.Row) -> Booking:
    return Booking(
        id=row["id"],
        user_id=row["user_id"],
        user_name=row["user_name"],
        phone=row["phone"],
        service_id=row["service_id"],
        start=datetime.strptime(row["start"], _ISO_MIN),
        minutes=row["minutes"],
        status=row["status"],
        created_at=datetime.strptime(row["created_at"], _ISO_SEC),
    )


class Storage:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------ bookings

    def add_if_free(
        self,
        *,
        user_id: int,
        user_name: str,
        phone: str,
        service: Service,
        start: datetime,
        buffer_minutes: int,
        now: datetime,
    ) -> Booking | None:
        """Insert the booking unless it collides with another one. None = slot taken."""
        end = start + timedelta(minutes=service.minutes)
        buffer = timedelta(minutes=buffer_minutes)
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                rows = self._conn.execute(
                    "SELECT * FROM bookings WHERE status = 'active' AND substr(start, 1, 10) = ?",
                    (start.date().isoformat(),),
                ).fetchall()
                for row in rows:
                    other = _to_booking(row)
                    if overlaps(start, end, other.start - buffer, other.end + buffer):
                        self._conn.execute("ROLLBACK")
                        return None
                cursor = self._conn.execute(
                    "INSERT INTO bookings (user_id, user_name, phone, service_id, start, minutes, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, user_name, phone, service.id, start.strftime(_ISO_MIN),
                     service.minutes, now.strftime(_ISO_SEC)),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            return self.get(cursor.lastrowid)

    def get(self, booking_id: int) -> Booking | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        return _to_booking(row) if row else None

    def for_day(self, day: date, *, active_only: bool = True) -> list[Booking]:
        query = "SELECT * FROM bookings WHERE substr(start, 1, 10) = ?"
        if active_only:
            query += " AND status = 'active'"
        with self._lock:
            rows = self._conn.execute(query + " ORDER BY start", (day.isoformat(),)).fetchall()
        return [_to_booking(r) for r in rows]

    def upcoming_for_user(self, user_id: int, now: datetime) -> list[Booking]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM bookings WHERE user_id = ? AND status = 'active' AND start >= ? ORDER BY start",
                (user_id, now.strftime(_ISO_MIN)),
            ).fetchall()
        return [_to_booking(r) for r in rows]

    def active_in_range(self, start: datetime, end: datetime) -> list[Booking]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM bookings WHERE status = 'active' AND start >= ? AND start < ? ORDER BY start",
                (start.strftime(_ISO_MIN), end.strftime(_ISO_MIN)),
            ).fetchall()
        return [_to_booking(r) for r in rows]

    def cancel(self, booking_id: int) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE bookings SET status = 'cancelled' WHERE id = ? AND status = 'active'", (booking_id,)
            )
        return cursor.rowcount == 1

    # ----------------------------------------------------------- reminders

    def reminded(self, booking_id: int) -> set[int]:
        with self._lock:
            row = self._conn.execute("SELECT reminded FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        if not row or not row["reminded"]:
            return set()
        return {int(x) for x in row["reminded"].split(",")}

    def mark_reminded(self, booking_id: int, hours: set[int]) -> None:
        value = ",".join(str(h) for h in sorted(hours, reverse=True))
        with self._lock:
            self._conn.execute("UPDATE bookings SET reminded = ? WHERE id = ?", (value, booking_id))

    # ------------------------------------------------------------ days off

    def days_off(self) -> frozenset[date]:
        with self._lock:
            rows = self._conn.execute("SELECT day FROM days_off").fetchall()
        return frozenset(date.fromisoformat(r["day"]) for r in rows)

    def set_day_off(self, day: date, off: bool) -> None:
        with self._lock:
            if off:
                self._conn.execute("INSERT OR IGNORE INTO days_off (day) VALUES (?)", (day.isoformat(),))
            else:
                self._conn.execute("DELETE FROM days_off WHERE day = ?", (day.isoformat(),))
