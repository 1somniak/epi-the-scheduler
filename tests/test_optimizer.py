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

    def test_maybe_not_assigned_when_sufficient_yes(self):
        """When enough YES members are available, people with maybe must NOT staff."""
        board = Person(canonical_id="admin", display_name="Admin", first_name="admin", is_board=True)
        board.availability[0] = Availability.YES

        p1 = Person(canonical_id="p1", display_name="Person1", first_name="p1", is_board=False)
        p2 = Person(canonical_id="p2", display_name="Person2", first_name="p2", is_board=False)
        p3 = Person(canonical_id="p3", display_name="Person3", first_name="p3", is_board=False)
        for p in [p1, p2, p3]:
            p.availability[0] = Availability.YES

        # Maybe person available
        pmaybe = Person(canonical_id="pm", display_name="MaybeGuy", first_name="pm", is_board=False)
        pmaybe.availability[0] = Availability.MAYBE

        optimizer = ScheduleOptimizer(shifts=[self.shift1], people=[board, p1, p2, p3, pmaybe], friendships=[])
        solution = optimizer.solve()

        assigned_names = [s.name for s in solution.shifts[0].slots]
        self.assertNotIn("MaybeGuy", assigned_names, "Maybe person must not staff when enough YES members exist!")
        self.assertIn("Admin", assigned_names)
        self.assertIn("Person1", assigned_names)
        self.assertIn("Person2", assigned_names)
        self.assertIn("Person3", assigned_names)

    def test_maybe_assigned_only_when_necessary(self):
        """When there are not enough YES members (shortage), maybe person is assigned to avoid placeholder."""
        board = Person(canonical_id="admin", display_name="Admin", first_name="admin", is_board=True)
        board.availability[0] = Availability.YES

        p1 = Person(canonical_id="p1", display_name="Person1", first_name="p1", is_board=False)
        p2 = Person(canonical_id="p2", display_name="Person2", first_name="p2", is_board=False)
        p1.availability[0] = Availability.YES
        p2.availability[0] = Availability.YES

        # Only 3 YES people, 1 MAYBE person -> Necessity!
        pmaybe = Person(canonical_id="pm", display_name="MaybeGuy", first_name="pm", is_board=False)
        pmaybe.availability[0] = Availability.MAYBE

        optimizer = ScheduleOptimizer(shifts=[self.shift1], people=[board, p1, p2, pmaybe], friendships=[])
        solution = optimizer.solve()

        assigned_names = [s.name for s in solution.shifts[0].slots]
        self.assertIn("MaybeGuy", assigned_names, "Maybe person must staff in case of necessity!")
        self.assertNotIn("missing member 1", assigned_names)

    def test_maybe_board_assigned_when_no_yes_board(self):
        """When 4 volunteers are YES but NO board member is YES, a MAYBE board member must be used."""
        v1 = Person(canonical_id="v1", display_name="Vol1", first_name="v1", is_board=False)
        v2 = Person(canonical_id="v2", display_name="Vol2", first_name="v2", is_board=False)
        v3 = Person(canonical_id="v3", display_name="Vol3", first_name="v3", is_board=False)
        v4 = Person(canonical_id="v4", display_name="Vol4", first_name="v4", is_board=False)
        for v in [v1, v2, v3, v4]:
            v.availability[0] = Availability.YES

        # Board member with MAYBE
        b_maybe = Person(canonical_id="b_maybe", display_name="BoardMaybe", first_name="bm", is_board=True)
        b_maybe.availability[0] = Availability.MAYBE

        optimizer = ScheduleOptimizer(shifts=[self.shift1], people=[v1, v2, v3, v4, b_maybe], friendships=[])
        solution = optimizer.solve()

        assigned_names = [s.name for s in solution.shifts[0].slots]
        self.assertIn("BoardMaybe", assigned_names, "Board maybe member must staff to satisfy board presence!")
        self.assertNotIn("missing board member 1", assigned_names)

    def test_first_and_last_shift_size_five(self):
        """First shift (installation) and last shift (teardown) must contain 5 people, middle shifts 4."""
        shifts = [self.shift1, self.shift2, self.shift3]
        board = Person(canonical_id="admin", display_name="Admin", first_name="admin", is_board=True)
        for s in shifts:
            board.availability[s.index] = Availability.YES

        # Total slots: 5 + 4 + 5 = 14 slots
        # Create enough volunteers so everyone works without exceeding 2h
        volunteers = [
            Person(canonical_id=f"v_{i}", display_name=f"Vol{i}", first_name=f"v{i}", is_board=False)
            for i in range(15)
        ]
        for v in volunteers:
            for s in shifts:
                v.availability[s.index] = Availability.YES

        cfg = SchedulerConfig(shift_size=4, first_last_shift_size=5)
        optimizer = ScheduleOptimizer(shifts=shifts, people=[board] + volunteers, friendships=[], config=cfg)
        solution = optimizer.solve()

        self.assertEqual(len(solution.shifts), 3)
        self.assertEqual(len(solution.shifts[0].slots), 5, "First shift (installation) must have 5 people")
        self.assertEqual(len(solution.shifts[1].slots), 4, "Middle shift must have 4 people")
        self.assertEqual(len(solution.shifts[2].slots), 5, "Last shift (teardown) must have 5 people")

        val_report = validate_solution(solution)
        self.assertTrue(val_report.is_valid, f"Validation errors: {val_report.hard_constraint_errors}")

    def test_board_members_max_consecutive_three_hours(self):
        """Board members can staff for 3 consecutive hours without warnings when max_consecutive_hours_board=3.0."""
        shifts = [self.shift1, self.shift2, self.shift3]
        board = Person(canonical_id="admin", display_name="Admin", first_name="admin", is_board=True)
        for s in shifts:
            board.availability[s.index] = Availability.YES

        # Provide enough volunteers so board could work 3 shifts if needed
        volunteers = [
            Person(canonical_id=f"v_{i}", display_name=f"Vol{i}", first_name=f"v{i}", is_board=False)
            for i in range(12)
        ]
        for v in volunteers:
            for s in shifts:
                v.availability[s.index] = Availability.YES

        cfg = SchedulerConfig(
            shift_size=4,
            first_last_shift_size=4,
            max_consecutive_hours=2.0,
            max_consecutive_hours_board=3.0,
            weight_split_shift=1000.0,
        )
        optimizer = ScheduleOptimizer(shifts=shifts, people=[board] + volunteers, friendships=[], config=cfg)
        solution = optimizer.solve()

        val_report = validate_solution(solution)
        # Check that no board member received a consecutive violation for 3h
        board_consec_violations = [v for v in val_report.consecutive_violations if "Admin" in v]
        self.assertEqual(len(board_consec_violations), 0, "Board member should not receive violation for 3h")


if __name__ == "__main__":
    unittest.main()


