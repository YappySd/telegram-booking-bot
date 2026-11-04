"""HTTP API and static files for the Mini App (aiohttp)."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from aiohttp import web

from bot import texts
from bot.service import BookingService, parse_day
from bot.webapp_auth import InitDataError, validate_init_data

log = logging.getLogger(__name__)

WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"
STATUS = {
    "unknown_service": 404,
    "not_found": 404,
    "slot_unavailable": 409,
    "slot_taken": 409,
    "too_many": 409,
    "already_cancelled": 409,
    "past": 409,
}


def _error(code: str, status: int | None = None) -> web.Response:
    return web.json_response({"error": code, "message": texts.error_text(code)}, status=status or STATUS.get(code, 400))


def _booking_json(booking, business) -> dict:
    service = business.service(booking.service_id)
    return {
        "id": booking.id,
        "service": service.title if service else booking.service_id,
        "date": booking.start.date().isoformat(),
        "time": booking.start.strftime("%H:%M"),
        "minutes": booking.minutes,
    }


def create_web_app(service: BookingService, bot_token: str, on_booked, on_cancelled) -> web.Application:
    business = service.business

    @web.middleware
    async def no_store(request: web.Request, handler):
        response = await handler(request)
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def authenticate(request: web.Request) -> dict:
        return validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), bot_token)

    async def read_json(request: web.Request) -> dict:
        try:
            data = await request.json()
        except (json.JSONDecodeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    async def config(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "name": business.name,
                "currency": business.currency,
                "services": [
                    {"id": s.id, "title": s.title, "minutes": s.minutes, "price": s.price, "emoji": s.emoji}
                    for s in business.services
                ],
            }
        )

    async def days(request: web.Request) -> web.Response:
        try:
            authenticate(request)
        except InitDataError:
            return _error("unauthorized", 401)
        result = await asyncio.to_thread(service.available_days, request.query.get("service", ""))
        return web.json_response({"days": [d.isoformat() for d in result]})

    async def slots(request: web.Request) -> web.Response:
        try:
            authenticate(request)
        except InitDataError:
            return _error("unauthorized", 401)
        day = parse_day(request.query.get("date", ""))
        if day is None:
            return _error("bad_datetime")
        result = await asyncio.to_thread(service.slots, request.query.get("service", ""), day)
        return web.json_response({"slots": [t.strftime("%H:%M") for t in result]})

    async def book(request: web.Request) -> web.Response:
        try:
            user = authenticate(request)
        except InitDataError:
            return _error("unauthorized", 401)
        data = await read_json(request)
        name = str(data.get("name") or user.get("first_name") or "")
        result = await asyncio.to_thread(
            lambda: service.book(
                user_id=int(user["id"]),
                user_name=name,
                phone=str(data.get("phone") or ""),
                service_id=str(data.get("service") or ""),
                day=str(data.get("date") or ""),
                at=str(data.get("time") or ""),
            )
        )
        if not result.ok:
            return _error(result.error or "bad_datetime")
        await on_booked(result.booking)
        return web.json_response({"ok": True, "booking": _booking_json(result.booking, business)})

    async def my(request: web.Request) -> web.Response:
        try:
            user = authenticate(request)
        except InitDataError:
            return _error("unauthorized", 401)
        items = await asyncio.to_thread(service.my_bookings, int(user["id"]))
        return web.json_response({"bookings": [_booking_json(b, business) for b in items]})

    async def cancel(request: web.Request) -> web.Response:
        try:
            user = authenticate(request)
        except InitDataError:
            return _error("unauthorized", 401)
        data = await read_json(request)
        try:
            booking_id = int(data.get("id"))
        except (TypeError, ValueError):
            return _error("not_found")
        result = await asyncio.to_thread(lambda: service.cancel(booking_id, user_id=int(user["id"])))
        if not result.ok:
            return _error(result.error or "not_found")
        await on_cancelled(result.booking, True)
        return web.json_response({"ok": True})

    async def index(_: web.Request) -> web.FileResponse:
        return web.FileResponse(WEBAPP_DIR / "index.html")

    app = web.Application(middlewares=[no_store])
    app.router.add_get("/api/config", config)
    app.router.add_get("/api/days", days)
    app.router.add_get("/api/slots", slots)
    app.router.add_post("/api/book", book)
    app.router.add_get("/api/my", my)
    app.router.add_post("/api/cancel", cancel)
    app.router.add_get("/", index)
    app.router.add_static("/", WEBAPP_DIR, show_index=False)
    return app
