"""
Reports

report_daily_schedule(date, bay_id_or_name) -> Report A
report_monthly_usage(year, month)           -> Report B
"""



from db import get_conn

ALL_SLOTS = list(range(6, 18))  # 6–17 inclusive


def report_daily_schedule(date: str, bay_id: int = None, bay_name: str = None) -> dict:
    """
    Report A — Daily Bay Schedule

    Returns every slot from 06:00–17:00 for the given date and bay,
    including empty slots. Each slot lists booked user emails.

    Args:
        date:     "YYYY-MM-DD"
        bay_id:   integer bay id  (one of bay_id / bay_name required)
        bay_name: bay name string

    Returns:
        {
            "bay_id": int,
            "bay_name": str,
            "date": str,
            "schedule": [
                {"timeslot": "06:00", "users": ["alice@x.com"]},
                {"timeslot": "07:00", "users": []},
                ...
            ]
        }
    """
    if not bay_id and not bay_name:
        raise ValueError("bay_id or bay_name is required")

    with get_conn() as conn:
        if bay_id:
            bay = conn.execute("SELECT id, name FROM bays WHERE id = ?", (bay_id,)).fetchone()
        else:
            bay = conn.execute("SELECT id, name FROM bays WHERE name = ?", (bay_name,)).fetchone()

        if not bay:
            raise ValueError("bay not found")

        rows = conn.execute(
            """
            SELECT r.timeslot, u.email
            FROM reservations r
            JOIN users u ON u.id = r.user_id
            WHERE r.bay_id = ? AND r.date = ?
            ORDER BY r.timeslot
            """,
            (bay["id"], date),
        ).fetchall()

    # Group booked emails by slot
    booked: dict[int, list[str]] = {h: [] for h in ALL_SLOTS}
    for row in rows:
        booked[row["timeslot"]].append(row["email"])

    schedule = [
        {"timeslot": f"{h:02d}:00", "users": booked[h]}
        for h in ALL_SLOTS
    ]

    return {
        "bay_id":   bay["id"],
        "bay_name": bay["name"],
        "date":     date,
        "schedule": schedule,
    }


def report_monthly_usage(year: int, month: int) -> dict:
    """
    Report B — Monthly Usage Summary

    Returns total hours reserved per user for the given month,
    sorted descending by hours then ascending by email as a tiebreaker.

    Each reservation = 1 hour (attendance assumed on booking).

    Args:
        year:  e.g. 2026
        month: 1–12

    Returns:
        {
            "year": int,
            "month": int,
            "usage": [
                {"email": "alice@x.com", "hours": 5},
                {"email": "bob@x.com",   "hours": 2},
                ...
            ]
        }
    """
    # Zero-pad month : "2026-05-%"
    prefix = f"{year}-{month:02d}-%"

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT u.email, COUNT(*) AS hours
            FROM reservations r
            JOIN users u ON u.id = r.user_id
            WHERE r.date LIKE ?
            GROUP BY u.id
            ORDER BY hours DESC, u.email ASC
            """,
            (prefix,),
        ).fetchall()

    return {
        "year":  year,
        "month": month,
        "usage": [{"email": row["email"], "hours": row["hours"]} for row in rows],
    }
