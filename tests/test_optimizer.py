"""Unit tests for the optimization model and edge cases from Section 16 of AGENTS.md."""

import unittest

from scheduler.models import Availability, Friendship, Person, SchedulerConfig, Shift
from scheduler.optimizer import ScheduleOptimizer
from scheduler.validator import validate_solution


class TestScheduleOptimizer(unittest.TestCase):
    def setUp(self):
        self.shift1 = Shift(index=0, name="Shift 1", duration_hours=1.0)
        self.shift2 = Shift(index=1, name="Shift 2", duration_hours=1.0)
        self.shift3 = Shift(index=2, name="Shift 3", duration_hours=1.0)

    def test_section_16_not_enough_people(self):
        """Shift with only 2 available people should produce 2 missing member placeholders."""
        alice = Person(canonical_id="alice", display_name="Alice", first_name="alice", is_board=True)
        bob = Person(canonical_id="bob", display_name="Bob", first_name="bob", is_board=False)
        alice.availability[0] = Availability.YES
        bob.availability[0] = Availability.YES

        optimizer = ScheduleOptimizer(shifts=[self.shift1], people=[alice, bob], friendships=[])
        solution = optimizer.solve()

        assigned_shift = solution.shifts[0]
        # Must have exactly 4 entries
        self.assertEqual(len(assigned_shift.slots), 4)

        real_names = [s.name for s in assigned_shift.slots if not s.is_placeholder]
        placeholder_names = [s.name for s in assigned_shift.slots if s.is_placeholder]

        self.assertIn("Alice", real_names)
        self.assertIn("Bob", real_names)
        self.assertIn("missing member 1", placeholder_names)
        self.assertIn("missing member 2", placeholder_names)

        val_report = validate_solution(solution)
        self.assertTrue(val_report.is_valid)

    def test_section_16_no_available_board_member(self):
        """Shift with 3 real volunteers but no board member should use 'missing board member 1'."""
        alice = Person(canonical_id="alice", display_name="Alice", first_name="alice", is_board=False)
        bob = Person(canonical_id="bob", display_name="Bob", first_name="bob", is_board=False)
        charlie = Person(canonical_id="charlie", display_name="Charlie", first_name="charlie", is_board=False)
        david = Person(canonical_id="david", display_name="David", first_name="david", is_board=False)

        for p in [alice, bob, charlie, david]:
            p.availability[0] = Availability.YES

        optimizer = ScheduleOptimizer(shifts=[self.shift1], people=[alice, bob, charlie, david], friendships=[])
        solution = optimizer.solve()

        assigned_shift = solution.shifts[0]
        self.assertEqual(len(assigned_shift.slots), 4)

        placeholder_names = [s.name for s in assigned_shift.slots if s.is_placeholder]
        self.assertIn("missing board member 1", placeholder_names)

        # 3 real volunteers + 1 missing board member = 4
        self.assertEqual(len(assigned_shift.real_people), 3)

        val_report = validate_solution(solution)
        self.assertTrue(val_report.is_valid)

    def test_section_16_zero_available_people(self):
        """Shift with 0 available people must produce 4 placeholders (1 board, 3 members)."""
        optimizer = ScheduleOptimizer(shifts=[self.shift1], people=[], friendships=[])
        solution = optimizer.solve()

        assigned_shift = solution.shifts[0]
        self.assertEqual(len(assigned_shift.slots), 4)

        placeholder_names = [s.name for s in assigned_shift.slots if s.is_placeholder]
        self.assertIn("missing board member 1", placeholder_names)
        self.assertIn("missing member 1", placeholder_names)
        self.assertIn("missing member 2", placeholder_names)
        self.assertIn("missing member 3", placeholder_names)

        val_report = validate_solution(solution)
        self.assertTrue(val_report.is_valid)

    def test_no_availability_is_strictly_enforced(self):
        """A person with 'no' availability must never be assigned."""
        alice = Person(canonical_id="alice", display_name="Alice", first_name="alice", is_board=True)
        alice.availability[0] = Availability.NO

        optimizer = ScheduleOptimizer(shifts=[self.shift1], people=[alice], friendships=[])
        solution = optimizer.solve()

        assigned_shift = solution.shifts[0]
        real_names = [s.name for s in assigned_shift.slots if not s.is_placeholder]
        self.assertNotIn("Alice", real_names)

    def test_friendships_preference(self):
        """Optimizer favors assigning friends together when possibilities exist."""
        # 6 people, shift size 4, 1 board member
        board_p = Person(canonical_id="admin", display_name="Admin", first_name="admin", is_board=True)
        board_p.availability[0] = Availability.YES

        p1 = Person(canonical_id="f1", display_name="Friend1", first_name="f1", is_board=False)
        p2 = Person(canonical_id="f2", display_name="Friend2", first_name="f2", is_board=False)
        p3 = Person(canonical_id="p3", display_name="Other1", first_name="p3", is_board=False)
        p4 = Person(canonical_id="p4", display_name="Other2", first_name="p4", is_board=False)
        p5 = Person(canonical_id="p5", display_name="Other3", first_name="p5", is_board=False)

        for p in [p1, p2, p3, p4, p5]:
            p.availability[0] = Availability.YES

        friendship = Friendship(person_a=p1, person_b=p2)
        optimizer = ScheduleOptimizer(
            shifts=[self.shift1],
            people=[board_p, p1, p2, p3, p4, p5],
            friendships=[friendship],
            config=SchedulerConfig(weight_friendship=50.0),
        )
        solution = optimizer.solve()
        assigned_shift = solution.shifts[0]
        real_names = [s.name for s in assigned_shift.slots if not s.is_placeholder]

        self.assertIn("Friend1", real_names)
        self.assertIn("Friend2", real_names)

    def test_empty_friendships_solves_cleanly(self):
        """Verify solver completes fast and produces a valid schedule when friendships list is empty."""
        board_p = Person(canonical_id="admin", display_name="Admin", first_name="admin", is_board=True)
        board_p.availability[0] = Availability.YES
        p1 = Person(canonical_id="p1", display_name="Person1", first_name="p1", is_board=False)
        p2 = Person(canonical_id="p2", display_name="Person2", first_name="p2", is_board=False)
        p3 = Person(canonical_id="p3", display_name="Person3", first_name="p3", is_board=False)
        for p in [p1, p2, p3]:
            p.availability[0] = Availability.YES

        optimizer = ScheduleOptimizer(shifts=[self.shift1], people=[board_p, p1, p2, p3], friendships=[])
        solution = optimizer.solve()
        self.assertEqual(solution.status, "Optimal")
        self.assertEqual(len(solution.shifts[0].slots), 4)
        report = validate_solution(solution)
        self.assertTrue(report.is_valid)

    def test_contiguous_shifts_preference(self):
        """Verify that a person working 2 shifts gets contiguous shifts without split shifts."""
        # 3 shifts of 1 hour
        shifts = [self.shift1, self.shift2, self.shift3]
        board = Person(canonical_id="admin", display_name="Admin", first_name="admin", is_board=True)
        for s in shifts:
            board.availability[s.index] = Availability.YES

        alice = Person(canonical_id="alice", display_name="Alice", first_name="alice", is_board=False)
        for s in shifts:
            alice.availability[s.index] = Availability.YES

        # Others available only for 1 shift each to fill slots
        others = [
            Person(canonical_id=f"o_{i}", display_name=f"Other{i}", first_name=f"o{i}", is_board=False)
            for i in range(10)
        ]
        # Distribute others so Alice works exactly 2 shifts
        # Shift 1 needs 2 others, Shift 2 needs 2 others, Shift 3 needs 3 others -> total 12 slots, admin works 3
        # Give alice incentive to work 2 shifts
        for s in shifts:
            for o in others:
                o.availability[s.index] = Availability.YES

        optimizer = ScheduleOptimizer(shifts=shifts, people=[board, alice] + others, friendships=[])
        solution = optimizer.solve()

        # Check shifts worked by Alice
        alice_shifts = [
            a_s.shift.index for a_s in solution.shifts
            if any(slot.person == alice for slot in a_s.slots)
        ]
        if len(alice_shifts) == 2:
            self.assertEqual(abs(alice_shifts[1] - alice_shifts[0]), 1, "Alice shifts must be contiguous!")

        report = validate_solution(solution)
        self.assertEqual(len(report.split_shift_violations), 0, "No split shift violations expected!")


if __name__ == "__main__":
    unittest.main()
