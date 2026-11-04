"""Plain data classes shared by every module."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Service:
    id: str
    title: str
    minutes: int
    price: int
    emoji: str = "•"


@dataclass(frozen=True)
class Booking:
    id: int
    user_id: int
    user_name: str
    phone: str
    service_id: str
    start: datetime  # naive local time of the business
    minutes: int
    status: str  # "active" | "cancelled"
    created_at: datetime

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.minutes)

    @property
    def active(self) -> bool:
        return self.status == "active"
