"""Solution validation and compliance verification.

Implements Section 14 of AGENTS.md:
- Verifies every shift has exactly 4 entries
- Verifies no real person is assigned to a 'no' slot
- Verifies board presence in every shift
- Verifies correct placeholder naming
- Calculates and verifies consecutive durations, friendship scores, and workload
- Produces a detailed report of soft-constraint violations
"""

import re

from scheduler.models import (
    AssignedShift,
    Availability,
    Person,
    ScheduleSolution,
    ScheduleValidationReport,
)


def validate_solution(solution: ScheduleSolution) -> ScheduleValidationReport:
    """Validates the generated schedule against hard and soft constraints."""
    hard_errors: list[str] = []
    soft_violations: list[str] = []
    maybe_violations: list[str] = []
    consec_violations: list[str] = []
    board_violations: list[str] = []
    placeholder_summary: list[str] = []
    realized_friendships: list[tuple[str, str, str]] = []

    # 1. Hard check: Shift composition & valid slots
    total_shifts = len(solution.shifts)
    for i, assigned_shift in enumerate(solution.shifts):
        s = assigned_shift.shift
        slots = assigned_shift.slots
        expected_size = solution.config.get_shift_size(i, total_shifts)

        if len(slots) != expected_size:
            hard_errors.append(
                f"Shift '{s.name}' has {len(slots)} entries (expected exactly {expected_size})."
            )

        # Check placeholder names format
        for slot in slots:
            if slot.is_placeholder and not re.match(r"^missing (board )?member \d+$", slot.name):
                hard_errors.append(
                    f"Shift '{s.name}' has improperly named placeholder: '{slot.name}'."
                )

        # Check 'no' availability
        for slot in slots:
            if not slot.is_placeholder and slot.person:
                p = slot.person
                avail = p.availability.get(s.index, Availability.NO)
                if avail == Availability.NO:
                    hard_errors.append(
                        f"CRITICAL: Person '{p.display_name}' assigned to '{s.name}' despite 'no' availability!"
                    )
                elif avail == Availability.MAYBE:
                    msg = f"'{p.display_name}' assigned with 'maybe' availability in shift '{s.name}'"
                    maybe_violations.append(msg)
                    soft_violations.append(msg)

        # Check board presence
        board_count = sum(1 for slot in slots if slot.is_board)
        if board_count < 1:
            hard_errors.append(
                f"Shift '{s.name}' does not contain any board member or board placeholder."
            )

        # Record placeholders if any
        if assigned_shift.placeholders:
            p_msg = f"Shift '{s.name}' required {len(assigned_shift.placeholders)} placeholder(s): {', '.join(assigned_shift.placeholders)}"
            placeholder_summary.append(p_msg)
            soft_violations.append(p_msg)

    # 2. Check first & last shift board member preference (>= 2)
    if solution.shifts:
        first_shift = solution.shifts[0]
        first_board_count = len(first_shift.board_members)
        if first_board_count < 2:
            msg = f"The first shift ('{first_shift.shift.name}') contains only {first_board_count} board member(s) (preference: >= 2)"
            board_violations.append(msg)
            soft_violations.append(msg)

        if len(solution.shifts) > 1:
            last_shift = solution.shifts[-1]
            last_board_count = len(last_shift.board_members)
            if last_board_count < 2:
                msg = f"The last shift ('{last_shift.shift.name}') contains only {last_board_count} board member(s) (preference: >= 2)"
                board_violations.append(msg)
                soft_violations.append(msg)

    # 3. Check consecutive hours for every real person
    for p in solution.people:
        allowed_max = solution.config.get_max_consecutive_hours(p.is_board)
        current_chain: list[AssignedShift] = []
        for i, a_shift in enumerate(solution.shifts):
            p_in_shift = any(slot.person == p for slot in a_shift.slots)
            if p_in_shift:
                if not current_chain:
                    current_chain = [a_shift]
                else:
                    prev_shift = current_chain[-1].shift
                    if a_shift.shift.is_consecutive_to(prev_shift):
                        current_chain.append(a_shift)
                    else:
                        # Chain ended, evaluate it
                        _evaluate_chain(current_chain, p, allowed_max, consec_violations, soft_violations)
                        current_chain = [a_shift]
            else:
                if current_chain:
                    _evaluate_chain(current_chain, p, allowed_max, consec_violations, soft_violations)
                    current_chain = []
        if current_chain:
            _evaluate_chain(current_chain, p, allowed_max, consec_violations, soft_violations)

    # 4. Check contiguity (strictly avoid split shifts)
    split_violations: list[str] = []
    for p in solution.people:
        worked_indices = [
            i for i, a_shift in enumerate(solution.shifts)
            if any(slot.person == p for slot in a_shift.slots)
        ]
        if len(worked_indices) >= 2:
            for idx in range(len(worked_indices) - 1):
                curr_shift = solution.shifts[worked_indices[idx]].shift
                next_shift = solution.shifts[worked_indices[idx + 1]].shift
                if not next_shift.is_consecutive_to(curr_shift):
                    msg = (
                        f"'{p.display_name}' has non-contiguous staffing "
                        f"(split shift between '{curr_shift.name}' and '{next_shift.name}')"
                    )
                    split_violations.append(msg)
                    soft_violations.append(msg)
                    break

    # 5. Friendships score
    for friendship in solution.friendships:
        p1, p2 = friendship.person_a, friendship.person_b
        for a_shift in solution.shifts:
            assigned_people = a_shift.real_people
            if p1 in assigned_people and p2 in assigned_people:
                realized_friendships.append((a_shift.shift.name, p1.display_name, p2.display_name))

    # 6. Workload summary
    workload: dict[str, int] = {}
    for p in solution.people:
        count = sum(1 for a_shift in solution.shifts if p in a_shift.real_people)
        workload[p.display_name] = count

    is_valid = len(hard_errors) == 0

    return ScheduleValidationReport(
        is_valid=is_valid,
        hard_constraint_errors=hard_errors,
        soft_constraint_violations=soft_violations,
        realized_friendships=realized_friendships,
        workload_summary=workload,
        consecutive_violations=consec_violations,
        maybe_violations=maybe_violations,
        board_violations=board_violations,
        split_shift_violations=split_violations,
        placeholder_summary=placeholder_summary,
    )


def _evaluate_chain(
    chain: list[AssignedShift],
    person: Person,
    max_consec: float,
    consec_violations: list[str],
    soft_violations: list[str],
) -> None:
    """Helper to check if a continuous chain of shifts exceeds max consecutive hours."""
    total_dur = sum(a.shift.duration_hours for a in chain)
    if total_dur > max_consec:
        start_t = chain[0].shift.start_time_str or f"Shift {chain[0].shift.index + 1}"
        end_t = chain[-1].shift.end_time_str or f"Shift {chain[-1].shift.index + 1}"
        msg = (
            f"'{person.display_name}' staffs for {total_dur:.1f} consecutive hours "
            f"({start_t} - {end_t}, {len(chain)} shifts) exceeding preference of {max_consec:.1f}h"
        )
        consec_violations.append(msg)
        soft_violations.append(msg)
