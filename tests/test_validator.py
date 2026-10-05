"""Unit tests for loader and validator error handling."""

import os
import tempfile
import unittest

from scheduler.loader import DataLoader
from scheduler.models import (
    AssignedShift,
    AssignedSlot,
    SchedulerConfig,
    ScheduleSolution,
    Shift,
)
from scheduler.validator import validate_solution


class TestDataLoader(unittest.TestCase):
    def test_missing_files_reported_as_errors(self):
        loader = DataLoader()
        loader.load_board("non_existent_board.csv")
        self.assertFalse(loader.report.is_valid)
        self.assertTrue(any(i.category == "FILE_NOT_FOUND" for i in loader.report.issues))

    def test_invalid_availability_reported_as_error(self):
        loader = DataLoader()
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv") as tmp:
            tmp.write('#,"Date","Name (optional)","Unique Code",Country,"Shift 1"\n')
            tmp.write('1,"2026-10-04",Alice,-,fr,invalid_value\n')
            tmp_path = tmp.name

        try:
            _shifts, _people = loader.load_availability(tmp_path)
            self.assertFalse(loader.report.is_valid)
            self.assertTrue(any(i.category == "INVALID_AVAILABILITY" for i in loader.report.issues))
        finally:
            os.remove(tmp_path)


class TestSolutionValidator(unittest.TestCase):
    def test_hard_constraint_failure_detection(self):
        shift = Shift(index=0, name="Shift 1")
        # Only 3 slots instead of 4
        slots = [
            AssignedSlot(name="Alice", is_placeholder=False, is_board=True),
            AssignedSlot(name="Bob", is_placeholder=False, is_board=False),
            AssignedSlot(name="Charlie", is_placeholder=False, is_board=False),
        ]
        assigned_shift = AssignedShift(shift=shift, slots=slots)
        solution = ScheduleSolution(
            shifts=[assigned_shift],
            status="Optimal",
            objective_value=0.0,
            people=[],
            friendships=[],
            config=SchedulerConfig(shift_size=4),
        )
        report = validate_solution(solution)
        self.assertFalse(report.is_valid)
        self.assertTrue(any("expected exactly 4" in err for err in report.hard_constraint_errors))


if __name__ == "__main__":
    unittest.main()
