"""Stdlib mirror of bot/web.py routes, backed by the real BookingService + initData validation."""
import json, sys, time, threading, tempfile, os
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from bot import texts
from bot.config import load_business
from bot.service import BookingService, parse_day
from bot.storage import Storage
from bot.webapp_auth import InitDataError, validate_init_data, sign_init_data

TOKEN = "123456789:" + "A" * 35
biz = load_business(os.path.join(ROOT, "business.example.json"))
svc = BookingService(biz, Storage(os.path.join(tempfile.mkdtemp(), "t.db")), lambda: datetime.now())
W = os.path.join(ROOT, "webapp")
STATUS = {"unknown_service":404,"not_found":404,"slot_unavailable":409,"slot_taken":409,"too_many":409,"already_cancelled":409,"past":409}
def bj(b):
    s = biz.service(b.service_id)
    return {"id": b.id, "service": s.title if s else b.service_id, "date": b.start.date().isoformat(), "time": b.start.strftime("%H:%M"), "minutes": b.minutes}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, obj=None, body=None, ctype="application/json"):
        data = body if body is not None else json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def err(self, code, status=None): self.send(status or STATUS.get(code, 400), {"error": code, "message": texts.error_text(code)})
    def route(self, method):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if not u.path.startswith("/api/"):
            name = "index.html" if u.path == "/" else u.path.lstrip("/")
            try: data = open(os.path.join(W, name), "rb").read()
            except OSError: return self.send(404, {})
            return self.send(200, body=data, ctype={"html":"text/html","js":"application/javascript","css":"text/css"}.get(name.rsplit(".",1)[-1], "text/plain"))
        if u.path == "/api/config":
            return self.send(200, {"name": biz.name, "currency": biz.currency, "services": [{"id": s.id, "title": s.title, "minutes": s.minutes, "price": s.price, "emoji": s.emoji} for s in biz.services]})
        try: user = validate_init_data(self.headers.get("X-Telegram-Init-Data", ""), TOKEN)
        except InitDataError: return self.err("unauthorized", 401)
        body = {}
        if method == "POST":
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if u.path == "/api/days": return self.send(200, {"days": [d.isoformat() for d in svc.available_days(q.get("service", ""))]})
        if u.path == "/api/slots":
            d = parse_day(q.get("date", ""))
            if d is None: return self.err("bad_datetime")
            return self.send(200, {"slots": [t.strftime("%H:%M") for t in svc.slots(q.get("service", ""), d)]})
        if u.path == "/api/book":
            r = svc.book(user_id=int(user["id"]), user_name=str(body.get("name") or user.get("first_name") or ""), phone=str(body.get("phone") or ""), service_id=str(body.get("service") or ""), day=str(body.get("date") or ""), at=str(body.get("time") or ""))
            return self.err(r.error or "bad_datetime") if not r.ok else self.send(200, {"ok": True, "booking": bj(r.booking)})
        if u.path == "/api/my": return self.send(200, {"bookings": [bj(b) for b in svc.my_bookings(int(user["id"]))]})
        if u.path == "/api/cancel":
            r = svc.cancel(int(body.get("id")), user_id=int(user["id"]))
            return self.err(r.error or "not_found") if not r.ok else self.send(200, {"ok": True})
        self.send(404, {})
    def do_GET(self): self.route("GET")
    def do_POST(self): self.route("POST")

def init_data(uid=42, name="Ярослав"):
    return sign_init_data({"auth_date": str(int(time.time())), "query_id": "AAH", "user": json.dumps({"id": uid, "first_name": name}, ensure_ascii=False)}, TOKEN)

if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", 8765), H)
    print(init_data(), flush=True)
    srv.serve_forever()
