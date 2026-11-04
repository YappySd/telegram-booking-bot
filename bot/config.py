"""Settings from the environment and the business description from business.json."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

from bot.models import Service


class ConfigError(ValueError):
    pass


def _parse_time(value: str) -> time:
    try:
        hours, minutes = value.split(":")
        return time(int(hours), int(minutes))
    except (ValueError, AttributeError) as exc:
        raise ConfigError(f"Неверное время '{value}', нужен формат ЧЧ:ММ") from exc


def _parse_windows(raw, label: str) -> tuple[tuple[time, time], ...]:
    windows = []
    for pair in raw:
        if len(pair) != 2:
            raise ConfigError(f"{label}: ожидается пара [начало, конец]")
        start, end = _parse_time(pair[0]), _parse_time(pair[1])
        if start >= end:
            raise ConfigError(f"{label}: начало {pair[0]} должно быть раньше конца {pair[1]}")
        windows.append((start, end))
    return tuple(sorted(windows))


@dataclass(frozen=True)
class Business:
    name: str
    currency: str
    step_minutes: int
    buffer_minutes: int
    min_lead_minutes: int
    horizon_days: int
    reminder_hours: tuple[int, ...]
    max_active_per_user: int
    schedule: dict[int, tuple[tuple[time, time], ...]]
    breaks: tuple[tuple[time, time], ...]
    services: tuple[Service, ...]

    def service(self, service_id: str) -> Service | None:
        for item in self.services:
            if item.id == service_id:
                return item
        return None

    def hours_for(self, weekday: int) -> tuple[tuple[time, time], ...]:
        return self.schedule.get(weekday, ())


def parse_business(data: dict) -> Business:
    step = int(data.get("step_minutes", 30))
    if not 5 <= step <= 120:
        raise ConfigError("step_minutes должен быть от 5 до 120")

    services = []
    seen = set()
    for item in data.get("services", []):
        service = Service(
            id=str(item["id"]),
            title=str(item["title"]),
            minutes=int(item["minutes"]),
            price=int(item["price"]),
            emoji=str(item.get("emoji", "•")),
        )
        if service.minutes <= 0 or service.price < 0:
            raise ConfigError(f"Услуга '{service.id}': длительность и цена заданы неверно")
        if service.id in seen:
            raise ConfigError(f"Повторяющийся id услуги: {service.id}")
        seen.add(service.id)
        services.append(service)
    if not services:
        raise ConfigError("В business.json нет ни одной услуги")

    schedule = {}
    for key, windows in data.get("schedule", {}).items():
        weekday = int(key)
        if not 0 <= weekday <= 6:
            raise ConfigError("День недели в schedule должен быть от 0 (пн) до 6 (вс)")
        schedule[weekday] = _parse_windows(windows, f"schedule[{key}]")

    return Business(
        name=str(data.get("name", "Студия")),
        currency=str(data.get("currency", "")),
        step_minutes=step,
        buffer_minutes=int(data.get("buffer_minutes", 0)),
        min_lead_minutes=int(data.get("min_lead_minutes", 60)),
        horizon_days=int(data.get("horizon_days", 14)),
        reminder_hours=tuple(sorted({int(h) for h in data.get("reminders_hours", [24, 2])}, reverse=True)),
        max_active_per_user=int(data.get("max_active_per_user", 3)),
        schedule=schedule,
        breaks=_parse_windows(data.get("breaks", []), "breaks"),
        services=tuple(services),
    )


def load_business(path: str | Path) -> Business:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Файл {path} не найден. Скопируйте business.example.json в business.json") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Файл {path} содержит неверный JSON: {exc}") from exc
    return parse_business(raw)


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    webapp_url: str | None
    timezone: ZoneInfo
    db_path: str
    business_path: str
    host: str
    port: int

    def __repr__(self) -> str:  # never leak the token into logs
        return f"Settings(admins={len(self.admin_ids)}, webapp={'on' if self.webapp_url else 'off'}, tz={self.timezone.key})"


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env

    token = env.get("BOT_TOKEN", "").strip()
    if not token or ":" not in token:
        raise ConfigError("Не задан BOT_TOKEN (токен от @BotFather) в файле .env")

    try:
        admins = frozenset(int(x) for x in env.get("ADMIN_IDS", "").replace(" ", "").split(",") if x)
    except ValueError as exc:
        raise ConfigError("ADMIN_IDS: перечислите числовые Telegram id через запятую") from exc

    webapp_url = env.get("WEBAPP_URL", "").strip().rstrip("/") or None
    if webapp_url and not webapp_url.startswith("https://"):
        raise ConfigError("WEBAPP_URL должен начинаться с https:// (Telegram не открывает Mini App по http)")

    try:
        tz = ZoneInfo(env.get("TIMEZONE", "Europe/Kyiv"))
    except Exception as exc:
        raise ConfigError("TIMEZONE: неизвестный часовой пояс (пример: Europe/Kyiv)") from exc

    try:
        port = int(env.get("PORT", "8080"))
    except ValueError as exc:
        raise ConfigError("PORT должен быть числом") from exc

    return Settings(
        bot_token=token,
        admin_ids=admins,
        webapp_url=webapp_url,
        timezone=tz,
        db_path=env.get("DB_PATH", "booking.db"),
        business_path=env.get("BUSINESS_PATH", "business.json"),
        host=env.get("HOST", "0.0.0.0"),
        port=port,
    )
