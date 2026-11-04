"""Live checks of the aiogram and aiohttp layers without a real token or network.

aiogram: updates are fed straight into the Dispatcher; a fake session records
the Bot API calls instead of sending them to Telegram.
aiohttp: the real web app runs on a local test server and every /api/* route
is called with initData signed by a dummy token.
"""

import asyncio
import json
import time
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from aiohttp.test_utils import TestClient, TestServer

from bot import keyboards
from bot.handlers import build_router
from bot.service import BookingService
from bot.storage import Storage
from bot.web import create_web_app
from bot.webapp_auth import sign_init_data
from tests.helpers import EARLY, make_business

TOKEN = "123456:TEST-not-a-real-token"
CLIENT_ID = 111
ADMIN_ID = 999


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


class FakeSession(BaseSession):
    """Records Bot API calls instead of sending them."""

    def __init__(self):
        super().__init__()
        self.calls = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, (SendMessage, EditMessageText)):
            return Message(
                message_id=len(self.calls),
                date=datetime.now(),
                chat=Chat(id=getattr(method, "chat_id", None) or CLIENT_ID, type="private"),
                text=method.text,
            )
        return True

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):  # pragma: no cover - not used
        raise NotImplementedError


def make_service():
    return BookingService(make_business(), Storage(), Clock(EARLY))


class Env:
    def __init__(self):
        self.service = make_service()
        self.session = FakeSession()
        self.bot = Bot(TOKEN, session=self.session)
        self.booked, self.cancelled = [], []

        async def on_booked(booking, notify_client=True):
            self.booked.append((booking, notify_client))

        async def on_cancelled(booking, by_client):
            self.cancelled.append((booking, by_client))

        self.on_booked, self.on_cancelled = on_booked, on_cancelled
        self.dp = Dispatcher()
        self.dp.include_router(
            build_router(self.service, frozenset({ADMIN_ID}), "https://example.test/app", on_booked, on_cancelled)
        )
        self._update_id = 0

    def _user(self, user_id):
        return User(id=user_id, is_bot=False, first_name="Anna")

    def _message(self, text, user_id):
        return Message(
            message_id=1,
            date=datetime.now(),
            chat=Chat(id=user_id, type="private"),
            from_user=self._user(user_id),
            text=text,
        )

    async def send(self, text, user_id=CLIENT_ID):
        self._update_id += 1
        self.session.calls.clear()
        message = self._message(text, user_id).as_(self.bot)
        await self.dp.feed_update(self.bot, Update(update_id=self._update_id, message=message))
        return list(self.session.calls)

    async def press(self, data, user_id=CLIENT_ID):
        self._update_id += 1
        self.session.calls.clear()
        callback = CallbackQuery(
            id=str(self._update_id),
            from_user=self._user(user_id),
            chat_instance="x",
            message=self._message("menu", user_id),
            data=data,
        ).as_(self.bot)
        await self.dp.feed_update(self.bot, Update(update_id=self._update_id, callback_query=callback))
        return list(self.session.calls)


def buttons(markup):
    return [b for row in markup.inline_keyboard for b in row]


def run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------ aiogram


def test_router_builds_and_start_replies_with_menu():
    async def scenario():
        env = Env()
        calls = await env.send("/start")
        assert len(calls) == 1 and isinstance(calls[0], SendMessage)
        assert calls[0].reply_markup is not None

    run(scenario())


def test_full_booking_flow_through_buttons():
    async def scenario():
        env = Env()
        calls = await env.send(keyboards.BTN_BOOK)
        svc_button = next(b for b in buttons(calls[0].reply_markup) if (b.callback_data or "").startswith("svc:"))

        calls = await env.press(svc_button.callback_data)
        edit = next(c for c in calls if isinstance(c, EditMessageText))
        day_button = buttons(edit.reply_markup)[0]

        calls = await env.press(day_button.callback_data)
        edit = next(c for c in calls if isinstance(c, EditMessageText))
        time_button = buttons(edit.reply_markup)[0]

        calls = await env.press(time_button.callback_data)
        assert any(isinstance(c, EditMessageText) for c in calls)
        assert any(isinstance(c, AnswerCallbackQuery) for c in calls)
        assert len(env.booked) == 1 and env.booked[0][1] is False

        calls = await env.send(keyboards.BTN_MY)
        assert len(calls) == 1 and calls[0].reply_markup is not None
        cancel_data = buttons(calls[0].reply_markup)[0].callback_data
        await env.press(cancel_data)
        assert len(env.cancelled) == 1 and env.cancelled[0][1] is True

    run(scenario())


def test_admin_commands_are_guarded():
    async def scenario():
        env = Env()
        calls = await env.send("/today", user_id=CLIENT_ID)
        assert len(calls) == 1 and "/today" not in calls[0].text
        calls = await env.send("/today", user_id=ADMIN_ID)
        assert len(calls) == 1
        calls = await env.send("/dayoff 2030-01-08", user_id=ADMIN_ID)
        assert "2030-01-08" in calls[0].text
        calls = await env.send("/cancel abc", user_id=ADMIN_ID)
        assert "/cancel 12" in calls[0].text

    run(scenario())


def test_prices_and_unknown_day_button():
    async def scenario():
        env = Env()
        calls = await env.send(keyboards.BTN_PRICES)
        assert len(calls) == 1
        calls = await env.press("day:cut:not-a-date")
        assert isinstance(calls[0], AnswerCallbackQuery) and calls[0].show_alert

    run(scenario())


# ------------------------------------------------------------------ aiohttp


def init_data(user_id=CLIENT_ID, token=TOKEN):
    fields = {
        "auth_date": str(int(time.time())),
        "query_id": "q",
        "user": json.dumps({"id": user_id, "first_name": "Anna"}),
    }
    return sign_init_data(fields, token)


async def web_client(env):
    app = create_web_app(env.service, TOKEN, env.on_booked, env.on_cancelled)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


def test_all_api_routes_with_signed_init_data():
    async def scenario():
        env = Env()
        client = await web_client(env)
        headers = {"X-Telegram-Init-Data": init_data()}
        try:
            resp = await client.get("/api/config")
            config = await resp.json()
            assert resp.status == 200 and config["services"]
            assert resp.headers["Cache-Control"] == "no-store"

            resp = await client.get("/api/days", params={"service": "cut"}, headers=headers)
            days = (await resp.json())["days"]
            assert resp.status == 200 and days

            resp = await client.get("/api/slots", params={"service": "cut", "date": days[0]}, headers=headers)
            slots = (await resp.json())["slots"]
            assert resp.status == 200 and slots

            body = {"service": "cut", "date": days[0], "time": slots[0], "phone": "+380 50 123-45-67"}
            resp = await client.post("/api/book", json=body, headers=headers)
            booked = await resp.json()
            assert resp.status == 200 and booked["ok"] and booked["booking"]["time"] == slots[0]
            assert len(env.booked) == 1

            resp = await client.post("/api/book", json=body, headers={"X-Telegram-Init-Data": init_data(222)})
            assert resp.status == 409

            resp = await client.get("/api/my", headers=headers)
            mine = (await resp.json())["bookings"]
            assert [b["id"] for b in mine] == [booked["booking"]["id"]]

            resp = await client.post("/api/cancel", json={"id": mine[0]["id"]}, headers=headers)
            assert resp.status == 200 and len(env.cancelled) == 1

            resp = await client.post("/api/cancel", json={"id": "x"}, headers=headers)
            assert resp.status == 404

            resp = await client.get("/api/slots", params={"service": "cut", "date": "bad"}, headers=headers)
            assert resp.status == 400

            resp = await client.post("/api/book", data="not json", headers=headers)
            assert resp.status in (400, 404, 409)
        finally:
            await client.close()

    run(scenario())


def test_api_rejects_missing_or_forged_init_data():
    async def scenario():
        env = Env()
        client = await web_client(env)
        try:
            for headers in ({}, {"X-Telegram-Init-Data": init_data(token="654321:other-token")}):
                for method, path in (("get", "/api/days"), ("get", "/api/slots"), ("get", "/api/my"),
                                     ("post", "/api/book"), ("post", "/api/cancel")):
                    resp = await getattr(client, method)(path, headers=headers)
                    assert resp.status == 401, (path, headers)
        finally:
            await client.close()

    run(scenario())


def test_static_index_is_served():
    async def scenario():
        env = Env()
        client = await web_client(env)
        try:
            resp = await client.get("/")
            assert resp.status == 200 and "<html" in (await resp.text()).lower()
            resp = await client.get("/app.js")
            assert resp.status == 200
        finally:
            await client.close()

    run(scenario())


def test_main_module_imports():
    import bot.main  # noqa: F401  - catches wrong aiogram import paths
