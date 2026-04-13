"""
Edge-case tests for the reservation system.

Covers three specific cases:

Case 1 — New user auto-registration

Adding a reservation for a user who does not yet exist in the system.

The booking succeeds with:
    HTTP 201 and the user row can be verified in the database.
    Design decision: explicit pre-registration is not required; the booking
    endpoint is the point of entry for new users.

Case 2 — Cross-bay double-booking prevention

Preventing a user from double-booking a timeslot across bays
 (e.g., a user cannot book Bay A and Bay B for the
 same 11:00 AM slot simultaneously).
  
     A user may not hold two reservations for the same date+timeslot across
    different bays (e.g., Bay 1 AND Bay 2 at 11:00). The second attempt is
    rejected with HTTP 409. The unique constraint on (user_id, bay_id, date,
    timeslot) alone does not cover this; it is enforced by an explicit
    cross-bay count query executed before insert in register().

Case 3 — Out-of-hours timeslot rejection

Blocking timeslot registrations outside valid hours (6:00 AM to 6:00 PM).


    Timeslots outside 06:00–17:00, non-whole-hour times (e.g. "09:30"), and
    malformed strings are all rejected with HTTP 400 before any DB access.
    Enforced in _parse_timeslot(): only integer hours 6–17 pass validation.
    The DB CHECK constraint (timeslot BETWEEN 6 AND 17) is a
    secondary check.
"""

import os
import tempfile
import unittest

# fresh tmp file
_db_file = tempfile.mktemp(suffix=".db")
os.environ["DB_PATH"] = _db_file

from db import init_db, get_conn
from app import register


def _seed_bays(conn):
    conn.executemany(
        "INSERT OR IGNORE INTO bays (name) VALUES (?)",
        [("Bay 1",), ("Bay 2",)],
    )


class TestCase1_NewUserAutoRegistration(unittest.TestCase):
    """
    Case 1: Booking succeeds for an email that has never been seen before.
    """

    def test_new_user_booking_succeeds(self):
        status, body = register({
            "email":    "newuser@example.com",
            "date":     "2026-06-01",
            "timeslot": "10:00",
            "bay_name": "Bay 1",
        })
        self.assertEqual(status, 201, body)
        self.assertEqual(body["email"], "newuser@example.com")

    def test_new_user_exists_in_db_after_booking(self):
        register({
            "email":    "created_on_booking@example.com",
            "date":     "2026-06-01",
            "timeslot": "11:00",
            "bay_name": "Bay 1",
        })
        with get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE email = ?",
                ("created_on_booking@example.com",),
            ).fetchone()
        self.assertIsNotNone(row, "user row should exist after first booking")

    def test_second_booking_by_same_new_user_succeeds(self):
        
        register({
            "email":    "returning@example.com",
            "date":     "2026-06-02",
            "timeslot": "09:00",
            "bay_name": "Bay 1",
        })
        status, body = register({
            "email":    "returning@example.com",
            "date":     "2026-06-02",
            "timeslot": "10:00",   # different slot — allowed
            "bay_name": "Bay 1",
        })
        self.assertEqual(status, 201, body)


class TestCase2_CrossBayDoubleBooking(unittest.TestCase):
    """
    Case 2: A user cannot hold the same date+timeslot in two different bays.
    The first booking succeeds; the second is rejected with 409.
    """

    def test_same_user_same_slot_different_bay_blocked(self):
        status1, body1 = register({
            "email":    "doublebooker@example.com",
            "date":     "2026-06-10",
            "timeslot": "11:00",
            "bay_name": "Bay 1",
        })
        self.assertEqual(status1, 201, body1)

        status2, body2 = register({
            "email":    "doublebooker@example.com",
            "date":     "2026-06-10",
            "timeslot": "11:00",
            "bay_name": "Bay 2",   # different bay, same slot
        })
        self.assertEqual(status2, 409, body2)
        self.assertIn("already booked", body2["error"])

    def test_same_user_different_slots_different_bays_allowed(self):
        status1, _ = register({
            "email":    "multibay@example.com",
            "date":     "2026-06-10",
            "timeslot": "08:00",
            "bay_name": "Bay 1",
        })
        status2, _ = register({
            "email":    "multibay@example.com",
            "date":     "2026-06-10",
            "timeslot": "09:00",
            "bay_name": "Bay 2",
        })
        self.assertEqual(status1, 201)
        self.assertEqual(status2, 201)

    def test_different_users_same_slot_same_bay_allowed(self):
        # two distinct users may share a bay slot (capacity = 2)
        status1, _ = register({
            "email":    "user_a@example.com",
            "date":     "2026-06-11",
            "timeslot": "14:00",
            "bay_name": "Bay 1",
        })
        status2, _ = register({
            "email":    "user_b@example.com",
            "date":     "2026-06-11",
            "timeslot": "14:00",
            "bay_name": "Bay 1",
        })
        self.assertEqual(status1, 201)
        self.assertEqual(status2, 201)


class TestCase3_OutOfHoursRejection(unittest.TestCase):
    """
    Case 3: Only whole-hour timeslots between 06:00 and 17:00 (inclusive) are
    accepted. Anything outside that range, or with non-zero minutes, is
    rejected with 400 before any database access occurs.
    """

    def _try(self, timeslot: str):
        return register({
            "email":    "anyhour@example.com",
            "date":     "2026-06-20",
            "timeslot": timeslot,
            "bay_name": "Bay 1",
        })

    # --- boundary: valid extremes ---
    def test_earliest_valid_slot(self):
        status, body = self._try("06:00")
        self.assertEqual(status, 201, body)

    def test_latest_valid_slot(self):
        status, body = register({
            "email":    "lateslot@example.com",
            "date":     "2026-06-20",
            "timeslot": "17:00",
            "bay_name": "Bay 1",
        })
        self.assertEqual(status, 201, body)

    # --- too early ---
    def test_before_opening_05(self):
        status, body = self._try("05:00")
        self.assertEqual(status, 400, body)

    def test_midnight(self):
        status, body = self._try("00:00")
        self.assertEqual(status, 400, body)

    # --- too late ---
    def test_after_last_slot_18(self):
        status, body = self._try("18:00")
        self.assertEqual(status, 400, body)

    def test_after_last_slot_23(self):
        status, body = self._try("23:00")
        self.assertEqual(status, 400, body)

    # --- non-whole-hour ---
    def test_half_hour(self):
        status, body = self._try("09:30")
        self.assertEqual(status, 400, body)

    def test_quarter_hour(self):
        status, body = self._try("10:15")
        self.assertEqual(status, 400, body)

    # --- malformed ---
    def test_empty_string(self):
        status, body = self._try("")
        self.assertEqual(status, 400, body)

    def test_plain_integer_string(self):
        status, body = self._try("9")
        self.assertEqual(status, 400, body)

    def test_nonsense_string(self):
        status, body = self._try("morning")
        self.assertEqual(status, 400, body)

# Test runner setup

def setUpModule():
    init_db()
    with get_conn() as conn:
        _seed_bays(conn)


def tearDownModule():
    try:
        os.unlink(_db_file)
    except OSError:
        pass


# Custom runner — grouped output with per-test descriptions

_TEST_LABELS = {
    # Case 1
    "test_new_user_booking_succeeds":
        "First booking by unknown email returns 201",
    "test_new_user_exists_in_db_after_booking":
        "User row exists in DB after first booking",
    "test_second_booking_by_same_new_user_succeeds":
        "Same user can book a different slot (row reuse)",
    # Case 2
    "test_same_user_same_slot_different_bay_blocked":
        "User + same slot + different bay → 409",
    "test_same_user_different_slots_different_bays_allowed":
        "User + different slots across bays → both 201",
    "test_different_users_same_slot_same_bay_allowed":
        "Two users sharing one bay slot → both 201 (capacity=2)",
    # Case 3
    "test_earliest_valid_slot":
        "06:00 is accepted (lower boundary)",
    "test_latest_valid_slot":
        "17:00 is accepted (upper boundary)",
    "test_before_opening_05":
        "05:00 rejected — before opening",
    "test_midnight":
        "00:00 rejected — before opening",
    "test_after_last_slot_18":
        "18:00 rejected — after closing",
    "test_after_last_slot_23":
        "23:00 rejected — after closing",
    "test_half_hour":
        "09:30 rejected — non-whole-hour",
    "test_quarter_hour":
        "10:15 rejected — non-whole-hour",
    "test_empty_string":
        "Empty string rejected — malformed",
    "test_plain_integer_string":
        '"9" rejected — missing colon/minutes',
    "test_nonsense_string":
        '"morning" rejected — malformed',
}

_SECTION_HEADERS = {
    "TestCase1_NewUserAutoRegistration":
        "Case 1 — New user auto-registration",
    "TestCase2_CrossBayDoubleBooking":
        "Case 2 — Cross-bay double-booking prevention",
    "TestCase3_OutOfHoursRejection":
        "Case 3 — Out-of-hours timeslot rejection",
}


class _GroupedResult(unittest.TestResult):
    """Collects results; prints them grouped by test class at the end."""

    def __init__(self):
        super().__init__()
        # class_name -> list of (method_name, outcome, err_str)
        self._by_class: dict[str, list] = {}
        self._order: list[str] = []

    def _record(self, test, outcome, err_str=None):
        cls = type(test).__name__
        if cls not in self._by_class:
            self._by_class[cls] = []
            self._order.append(cls)
        self._by_class[cls].append((test._testMethodName, outcome, err_str))

    def addSuccess(self, test):
        self._record(test, "PASS")

    def addFailure(self, test, err):
        self._record(test, "FAIL", self._fmt(err))

    def addError(self, test, err):
        self._record(test, "ERROR", self._fmt(err))

    def addSkip(self, test, reason):
        self._record(test, "SKIP", reason)

    @staticmethod
    def _fmt(err):
        import traceback
        return traceback.format_exception(*err)[-1].strip()

    def print_report(self):
        W = 68
        total = passed = failed = 0

        print()
        print("=" * W)
        print("  RESERVATION SYSTEM — EDGE CASE TEST REPORT")
        print("=" * W)

        for cls in self._order:
            header = _SECTION_HEADERS.get(cls, cls)
            print(f"\n  {header}")
            print("  " + "-" * (W - 2))

            for method, outcome, err in self._by_class[cls]:
                label = _TEST_LABELS.get(method, method)
                marker = "PASS" if outcome == "PASS" else outcome
                # right-align the outcome tag in the line
                gap = W - 4 - len(label) - len(marker)
                gap = max(1, gap)
                print(f"    {label}{' ' * gap}{marker}")
                if err:
                    for line in err.splitlines():
                        print(f"      | {line}")
                total += 1
                if outcome == "PASS":
                    passed += 1
                else:
                    failed += 1

        print()
        print("=" * W)
        status_label = "ALL PASSED" if failed == 0 else f"{failed} FAILED"
        summary = f"  {passed}/{total} tests passed   [{status_label}]"
        print(summary)
        print("=" * W)
        print()


def _run_grouped():
    setUpModule()
    try:
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        for cls in (
            TestCase1_NewUserAutoRegistration,
            TestCase2_CrossBayDoubleBooking,
            TestCase3_OutOfHoursRejection,
        ):
            suite.addTests(loader.loadTestsFromTestCase(cls))

        result = _GroupedResult()
        suite.run(result)
        result.print_report()
        return result
    finally:
        tearDownModule()


if __name__ == "__main__":
    import sys
    result = _run_grouped()
    sys.exit(0 if result.wasSuccessful() else 1)
