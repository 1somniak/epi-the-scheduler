"""Unit tests for the reporting engine and inverted schedule matrix."""

import io
import os
import tempfile
import unittest

from scheduler.models import (
    AssignedShift,
    AssignedSlot,
    Person,
    SchedulerConfig,
    ScheduleSolution,
    ScheduleValidationReport,
    Shift,
)
from scheduler.reporter import (
    ScheduleReporter,
    export_matrix_csv,
    export_report_txt,
)


class TestScheduleReporter(unittest.TestCase):
    def setUp(self):
        self.shift1 = Shift(index=0, name="2026-10-07 (10:00 - 11:00)", start_time_str="10:00", end_time_str="11:00")
        self.shift2 = Shift(index=1, name="2026-10-07 (11:00 - 12:00)", start_time_str="11:00", end_time_str="12:00")

        self.alice = Person(canonical_id="alice", display_name="Alice", first_name="alice", is_board=True)
        self.bob = Person(canonical_id="bob", display_name="Bob", first_name="bob", is_board=False)
        self.charlie = Person(canonical_id="charlie", display_name="Charlie", first_name="charlie", is_board=False)

        # Shift 1: Alice, Bob
        ashift1 = AssignedShift(
            shift=self.shift1,
            slots=[
                AssignedSlot(name="Alice", is_placeholder=False, is_board=True, person=self.alice),
                AssignedSlot(name="Bob", is_placeholder=False, is_board=False, person=self.bob),
            ],
        )

        # Shift 2: Alice, Charlie (with maybe)
        ashift2 = AssignedShift(
            shift=self.shift2,
            slots=[
                AssignedSlot(name="Alice", is_placeholder=False, is_board=True, person=self.alice),
                AssignedSlot(
                    name="Charlie",
                    is_placeholder=False,
                    is_board=False,
                    person=self.charlie,
                    availability_used="maybe",
                ),
            ],
        )

        self.solution = ScheduleSolution(
            shifts=[ashift1, ashift2],
            status="Optimal",
            objective_value=0.0,
            people=[self.alice, self.bob, self.charlie],
            friendships=[],
            config=SchedulerConfig(),
        )

        self.val_report = ScheduleValidationReport(
            is_valid=True,
            workload_summary={"Alice": 2, "Bob": 1, "Charlie": 1},
        )

    def test_print_schedule_plain(self):
        """Tests that plain text output contains the inverted presence matrix."""
        reporter = ScheduleReporter()
        # Force plain text
        out = io.StringIO()
        import sys
        old_stdout = sys.stdout
        try:
            sys.stdout = out
            reporter._print_schedule_plain(self.solution, self.val_report)
        finally:
            sys.stdout = old_stdout

        output = out.getvalue()
        self.assertIn("Planning individuel des présences", output)
        self.assertIn("Alice", output)
        self.assertIn("Bob", output)
        self.assertIn("Charlie", output)
        self.assertIn("[X]", output)
        self.assertIn("[ ]", output)
        self.assertIn("[M]", output)

    def test_print_schedule_rich(self):
        """Tests that Rich output runs cleanly without errors."""
        reporter = ScheduleReporter()
        if reporter.console:
            # Test that it executes without raising exceptions
            reporter._print_schedule_rich(self.solution, self.val_report)

    def test_export_matrix_csv(self):
        """Tests exporting inverted schedule to CSV."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".csv") as tmp:
            tmp_path = tmp.name

        try:
            export_matrix_csv(self.solution, tmp_path)
            with open(tmp_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("Person,Role,2026-10-07 (10:00 - 11:00),2026-10-07 (11:00 - 12:00),Total Shifts,Total Hours", content)
            self.assertIn("Alice,Board,X,X,2,2.0", content)
            self.assertIn("Bob,Volunteer,X,,1,1.0", content)
            self.assertIn("Charlie,Volunteer,,X (maybe),1,1.0", content)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_export_report_txt(self):
        """Tests exporting text report with presence matrix included."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt") as tmp:
            tmp_path = tmp.name

        try:
            export_report_txt(self.solution, self.val_report, tmp_path)
            with open(tmp_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("PLANNING INDIVIDUEL DES PRÉSENCES (PERSONNES × SHIFTS)", content)
            self.assertIn("Alice", content)
            self.assertIn("[X]", content)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
