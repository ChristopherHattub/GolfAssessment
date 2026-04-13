
# Run Instructions:


## Requirements

- Python 3.10+ (uses `match`-free stdlib only; tested on 3.13)
- No third-party packages — stdlib only (`sqlite3`, `http.server`, `json`, `urllib`)

---


## 1. Start the server

```bash
python app.py
```

Expected output:

```
Seeded 3 bays.
Listening on http://localhost:8000
  POST   /reservations                        — register
  DELETE /reservations                        — remove
  GET    /reports/daily?date=&bay=            — Report A
  GET    /reports/monthly?year=&month=        — Report B
```

The server seeds **Bay 1**, **Bay 2**, and **Bay 3** on the first run if the bays
table is empty. To use a different database file, set the `DB_PATH` environment
variable before starting:

```bash
DB_PATH=/tmp/my_golf.db python app.py
```

---

## 2. API reference

### POST /reservations — Register a user for a timeslot

**Body fields**

| Field       | Type   | Required | Notes                                    |
|-------------|--------|----------|------------------------------------------|
| `email`     | string | yes      | Identifies the user; created if new      |
| `date`      | string | yes      | Format: `YYYY-MM-DD`                     |
| `timeslot`  | string | yes      | Whole-hour string: `"06:00"` – `"17:00"` |
| `bay_name`  | string | one of   | e.g. `"Bay 1"`                           |
| `bay_id`    | int    | one of   | Numeric bay ID                           |

**Example**

```bash
curl -s -X POST http://localhost:8000/reservations \
  -H "Content-Type: application/json" \
  -d '{
    "email":    "alice@example.com",
    "date":     "2026-07-14",
    "timeslot": "09:00",
    "bay_name": "Bay 1"
  }' | python -m json.tool
```

**Success response — 201**

```json
{
    "message": "reservation created",
    "email": "alice@example.com",
    "date": "2026-07-14",
    "timeslot": "09:00",
    "bay_id": 1
}
```

**Error responses**

| Status | Reason                                          |
|--------|-------------------------------------------------|
| 400    | Missing/invalid field or out-of-hours timeslot  |
| 404    | Bay not found                                   |
| 409    | Slot full (2 users), duplicate booking, or user already booked this timeslot in another bay |

---

### DELETE /reservations — Remove a user from a timeslot

**Body fields** — same as POST (email, date, timeslot, bay_name or bay_id)

**Example**

```bash
curl -s -X DELETE http://localhost:8000/reservations \
  -H "Content-Type: application/json" \
  -d '{
    "email":    "alice@example.com",
    "date":     "2026-07-14",
    "timeslot": "09:00",
    "bay_name": "Bay 1"
  }' | python -m json.tool
```

**Success response — 200**

```json
{
    "message": "reservation removed",
    "email": "alice@example.com",
    "date": "2026-07-14",
    "timeslot": "09:00",
    "bay_id": 1
}
```

**Error responses**

| Status | Reason                         |
|--------|--------------------------------|
| 400    | Missing/invalid field          |
| 404    | User, bay, or reservation not found |

---

### GET /reports/daily — Report A: Daily Bay Schedule

Returns all 12 timeslots (06:00–17:00) for a given date and bay, including
empty slots.

**Query params**

| Param    | Required | Example       |
|----------|----------|---------------|
| `date`   | yes      | `2026-07-14`  |
| `bay`    | one of   | `Bay+1`       |
| `bay_id` | one of   | `1`           |

**Example**

```bash
curl -s "http://localhost:8000/reports/daily?date=2026-07-14&bay=Bay+1" \
  | python -m json.tool
```

**Response**

```json
{
    "bay_id": 1,
    "bay_name": "Bay 1",
    "date": "2026-07-14",
    "schedule": [
        { "timeslot": "06:00", "users": [] },
        { "timeslot": "07:00", "users": [] },
        { "timeslot": "08:00", "users": [] },
        { "timeslot": "09:00", "users": ["alice@example.com"] },
        { "timeslot": "10:00", "users": [] },
        ...
        { "timeslot": "17:00", "users": [] }
    ]
}
```

---

### GET /reports/monthly — Report B: Monthly Usage Summary

Returns total hours reserved per user for a given month, sorted descending
by hours (tiebreaker: email ascending).

**Query params**

| Param   | Required | Example |
|---------|----------|---------|
| `year`  | yes      | `2026`  |
| `month` | yes      | `7`     |

**Example**

```bash
curl -s "http://localhost:8000/reports/monthly?year=2026&month=7" \
  | python -m json.tool
```

**Response**

```json
{
    "year": 2026,
    "month": 7,
    "usage": [
        { "email": "alice@example.com", "hours": 5 },
        { "email": "bob@example.com",   "hours": 2 }
    ]
}
```

---

## 3. Run the tests

```bash
python test_edge_cases.py
```

Expected output:

```
====================================================================
  RESERVATION SYSTEM — EDGE CASE TEST REPORT
====================================================================

  Case 1 — New user auto-registration
  ------------------------------------------------------------------
    First booking by unknown email returns 201                  PASS
    User row exists in DB after first booking                   PASS
    Same user can book a different slot (row reuse)             PASS

  Case 2 — Cross-bay double-booking prevention
  ------------------------------------------------------------------
    Two users sharing one bay slot → both 201 (capacity=2)      PASS
    User + different slots across bays → both 201               PASS
    User + same slot + different bay → 409                      PASS

  Case 3 — Out-of-hours timeslot rejection
  ------------------------------------------------------------------
    18:00 rejected — after closing                              PASS
    ...
    10:15 rejected — non-whole-hour                             PASS

====================================================================
  17/17 tests passed   [ALL PASSED]
====================================================================
```

Tests use a temporary database file that is created and deleted automatically.
They do not affect `reservations.db`.

To run with standard `unittest` output (e.g. in CI):

```bash
python -m unittest test_edge_cases -v
```

---

## 4. Quick end-to-end walkthrough

```bash
# 1. Start the server
python app.py &

# 2. Book alice into Bay 1 at 09:00
curl -s -X POST http://localhost:8000/reservations \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","date":"2026-07-14","timeslot":"09:00","bay_name":"Bay 1"}'

# 3. Book bob into the same slot (allowed — capacity is 2)
curl -s -X POST http://localhost:8000/reservations \
  -H "Content-Type: application/json" \
  -d '{"email":"bob@example.com","date":"2026-07-14","timeslot":"09:00","bay_name":"Bay 1"}'

# 4. Try to add a third user — should return 409 (full)
curl -s -X POST http://localhost:8000/reservations \
  -H "Content-Type: application/json" \
  -d '{"email":"carol@example.com","date":"2026-07-14","timeslot":"09:00","bay_name":"Bay 1"}'

# 5. View the daily schedule for Bay 1
curl -s "http://localhost:8000/reports/daily?date=2026-07-14&bay=Bay+1" \
  | python -m json.tool

# 6. View July monthly usage summary
curl -s "http://localhost:8000/reports/monthly?year=2026&month=7" \
  | python -m json.tool

# 7. Cancel alice's booking
curl -s -X DELETE http://localhost:8000/reservations \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","date":"2026-07-14","timeslot":"09:00","bay_name":"Bay 1"}'
```
