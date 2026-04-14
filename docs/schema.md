# Database Schema — Golf Simulator Reservation System

## Overview

Three tables: `users`, `bays`, `reservations`.
The `reservations` table joins them all,  the`(bay_id, date, timeslot, user_id)` prevents duplicate bookings, and a check constraint enforces the 2-user-per-slot capacity limit at the application layer (enforced via query before insert).

---

## Tables

### `users`

| Column       | Type         | Constraints              |
|--------------|--------------|--------------------------|
| `id`         | INTEGER      | PRIMARY KEY, AUTOINCREMENT |
| `email`      | VARCHAR(255) | NOT NULL, UNIQUE         |

- Identified by email; no password or auth fields in scope.

---

### `bays`

| Column | Type         | Constraints              |
|--------|--------------|--------------------------|
| `id`   | INTEGER      | PRIMARY KEY, AUTOINCREMENT |
| `name` | VARCHAR(50)  | NOT NULL, UNIQUE         |


---

### `reservations`

| Column      | Type        | Constraints                                      |
|-------------|-------------|--------------------------------------------------|
| `id`        | INTEGER     | PRIMARY KEY, AUTOINCREMENT                       |
| `user_id`   | INTEGER     | NOT NULL, FOREIGN KEY → `users(id)`              |
| `bay_id`    | INTEGER     | NOT NULL, FOREIGN KEY → `bays(id)`               |
| `date`      | DATE        | NOT NULL (format: YYYY-MM-DD)                    |
| `timeslot`  | SMALLINT    | NOT NULL (valid values: 6–17 representing hour)  |

#### Constraints

- **UNIQUE** `(user_id, bay_id, date, timeslot)` — a user cannot book the same bay/slot twice.
- **CHECK** `timeslot BETWEEN 6 AND 17` — slots run 06:00–17:00 (last slot starts at 17:00, ends 18:00).
- **Capacity rule** (enforced at application layer before INSERT): `COUNT(*) WHERE bay_id = ? AND date = ? AND timeslot = ?` must be `< 2`.

---

## Rules Summary

| Rule |                     
|------|------------------------------------------|
| Slots are 1 hour, whole-hour only | `timeslot` stored as integer hour; no minutes |
| Slots run 06:00–18:00 (12 slots/day) | `CHECK (timeslot BETWEEN 6 AND 17)` |
| Max 2 users per bay/slot | Pre-insert count query at application layer |
| No duplicate user+bay+slot booking 
| User may book multiple slots per day 

---

## Notes

- timeslot is stored as a SMALLINT hour value (6–17) rather than a TIME or string to keep comparisons and conversions simple and remove
invalid minute values entirely.
- Capacity (max 2) cannot be expressed as a single-row SQL constraint; requires a count check before insert.
