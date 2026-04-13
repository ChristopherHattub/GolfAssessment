"""
Golf Simulator Reservation API

POST   /reservations               — register a user for a timeslot
DELETE /reservations               — remove a user from a timeslot
GET    /reports/daily?date=&bay=   — Report A: daily bay schedule
GET    /reports/monthly?year=&month= — Report B: monthly usage summary

Run:  python app.py
"""

import json
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from db import get_conn, init_db
from reports import report_daily_schedule, report_monthly_usage


PORT = 8000
VALID_SLOTS = set(range(6, 18))   # 6–17 inclusive (slot 17 = 17:00–18:00)
BAY_CAPACITY = 2


# Helpers

def _parse_timeslot(ts: str):
    """Convert "09:00" -> 9, or return None on bad input."""
    try:
        hour, minute = ts.split(":")
        if minute != "00":
            return None
        h = int(hour)
        return h if h in VALID_SLOTS else None
    except Exception:
        return None

def _json_response(handler, status: int, body: dict) -> None:
    data = json.dumps(body).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _read_body(handler) -> dict | None:
    length = int(handler.headers.get("Content-Length", 0))
    if not length:
        return {}
    try:
        return json.loads(handler.rfile.read(length))
    except json.JSONDecodeError:
        return None


# Business Logic


def register(payload: dict) -> tuple[int, dict]:
    """
    Required fields: email, date, timeslot, bay_id OR bay_name
    """
    email     = payload.get("email", "").strip()
    date      = payload.get("date", "").strip()
    timeslot  = payload.get("timeslot", "")
    bay_id    = payload.get("bay_id")
    bay_name  = payload.get("bay_name", "").strip()

    # --- validation ---
    if not email:
        return 400, {"error": "email is required"}
    if not date:
        return 400, {"error": "date is required (YYYY-MM-DD)"}

    hour = _parse_timeslot(str(timeslot))
    if hour is None:
        return 400, {"error": "timeslot must be a whole-hour string between 06:00 and 17:00"}

    if not bay_id and not bay_name:
        return 400, {"error": "bay_id or bay_name is required"}

    try:
        with get_conn() as conn:
            conn.execute("INSERT OR IGNORE INTO users (email) VALUES (?)", (email,))
            user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()

            if bay_id:
                bay = conn.execute("SELECT id FROM bays WHERE id = ?", (bay_id,)).fetchone()
            else:
                bay = conn.execute("SELECT id FROM bays WHERE name = ?", (bay_name,)).fetchone()

            if not bay:
                label = f"bay_id {bay_id}" if bay_id else f"bay '{bay_name}'"
                return 404, {"error": f"{label} not found"}
            resolved_bay_id = bay["id"]

            # cross-bay double-booking check: user may not hold any slot at this
            # date+timeslot regardless of which bay it is in
            cross = conn.execute(
                "SELECT COUNT(*) FROM reservations WHERE user_id=? AND date=? AND timeslot=?",
                (user["id"], date, hour),
            ).fetchone()[0]
            if cross > 0:
                return 409, {"error": "user is already booked for this timeslot in another bay"}

            # capacity check
            count = conn.execute(
                "SELECT COUNT(*) FROM reservations WHERE bay_id=? AND date=? AND timeslot=?",
                (resolved_bay_id, date, hour),
            ).fetchone()[0]
            if count >= BAY_CAPACITY:
                return 409, {"error": "timeslot is fully booked (max 2 users)"}

            # insert — UNIQUE constraint catches duplicate user+bay+slot
            conn.execute(
                "INSERT INTO reservations (user_id, bay_id, date, timeslot) VALUES (?,?,?,?)",
                (user["id"], resolved_bay_id, date, hour),
            )

        return 201, {"message": "reservation created", "email": email, "date": date,
                     "timeslot": f"{hour:02d}:00", "bay_id": resolved_bay_id}

    except sqlite3.IntegrityError:
        return 409, {"error": "user already has a reservation for this bay and timeslot"}



def remove(payload: dict) -> tuple[int, dict]:
    """
    Required fields: email, date, timeslot, bay_id OR bay_name
    """
    email    = payload.get("email", "").strip()
    date     = payload.get("date", "").strip()
    timeslot = payload.get("timeslot", "")
    bay_id   = payload.get("bay_id")
    bay_name = payload.get("bay_name", "").strip()

    if not email:
        return 400, {"error": "email is required"}
    if not date:
        return 400, {"error": "date is required (YYYY-MM-DD)"}

    hour = _parse_timeslot(str(timeslot))
    if hour is None:
        return 400, {"error": "timeslot must be a whole-hour string between 06:00 and 17:00"}

    if not bay_id and not bay_name:
        return 400, {"error": "bay_id or bay_name is required"}

    with get_conn() as conn:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if not user:
            return 404, {"error": "user not found"}

        if bay_id:
            bay = conn.execute("SELECT id FROM bays WHERE id = ?", (bay_id,)).fetchone()
        else:
            bay = conn.execute("SELECT id FROM bays WHERE name = ?", (bay_name,)).fetchone()
        if not bay:
            return 404, {"error": "bay not found"}

        cursor = conn.execute(
            "DELETE FROM reservations WHERE user_id=? AND bay_id=? AND date=? AND timeslot=?",
            (user["id"], bay["id"], date, hour),
        )
        if cursor.rowcount == 0:
            return 404, {"error": "reservation not found"}

    return 200, {"message": "reservation removed", "email": email, "date": date,
                 "timeslot": f"{hour:02d}:00", "bay_id": bay["id"]}



# HTTP Handling 

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):  
        print(f"  {self.command} {self.path} -> {args[0] if args else ''}")

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        def qs_get(key):
            vals = qs.get(key)
            return vals[0] if vals else None

        if parsed.path == "/reports/daily":
            date     = qs_get("date")
            bay_id   = qs_get("bay_id")
            bay_name = qs_get("bay")
            if not date:
                return _json_response(self, 400, {"error": "date query param required (YYYY-MM-DD)"})
            if not bay_id and not bay_name:
                return _json_response(self, 400, {"error": "bay or bay_id query param required"})
            try:
                result = report_daily_schedule(
                    date,
                    bay_id=int(bay_id) if bay_id else None,
                    bay_name=bay_name,
                )
                _json_response(self, 200, result)
            except ValueError as e:
                _json_response(self, 404, {"error": str(e)})

        elif parsed.path == "/reports/monthly":
            year  = qs_get("year")
            month = qs_get("month")
            if not year or not month:
                return _json_response(self, 400, {"error": "year and month query params required"})
            try:
                result = report_monthly_usage(int(year), int(month))
                _json_response(self, 200, result)
            except (ValueError, TypeError):
                _json_response(self, 400, {"error": "year and month must be integers"})

        else:
            _json_response(self, 404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/reservations":
            body = _read_body(self)
            if body is None:
                return _json_response(self, 400, {"error": "invalid JSON"})
            status, resp = register(body)
            _json_response(self, status, resp)
        else:
            _json_response(self, 404, {"error": "not found"})

    def do_DELETE(self):
        if self.path == "/reservations":
            body = _read_body(self)
            if body is None:
                return _json_response(self, 400, {"error": "invalid JSON"})
            status, resp = remove(body)
            _json_response(self, status, resp)
        else:
            _json_response(self, 404, {"error": "not found"})



# Entry Start



if __name__ == "__main__":
    init_db()

    # Seed bays if the table is empty
    with get_conn() as conn:
        if conn.execute("SELECT COUNT(*) FROM bays").fetchone()[0] == 0:
            conn.executemany("INSERT INTO bays (name) VALUES (?)",
                             [("Bay 1",), ("Bay 2",), ("Bay 3",)])
            print("Seeded 3 bays.")

    server = HTTPServer(("", PORT), Handler)
    print(f"Listening on http://localhost:{PORT}")
    print("  POST   /reservations                        — register")
    print("  DELETE /reservations                        — remove")
    print("  GET    /reports/daily?date=&bay=            — Report A")
    print("  GET    /reports/monthly?year=&month=        — Report B")
    server.serve_forever()
