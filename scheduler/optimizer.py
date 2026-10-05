"""Optimization engine using PuLP / MILP solver.

Implements Sections 4, 5, 6, 7, 8, 9, 10, 11, and 16 of AGENTS.md:
- Shift composition (4 people per shift)
- Hard constraint on 'no' availability
- Hard constraint on board presence (with placeholders if needed)
- Soft constraints: maybe penalty, consecutive staffing (> 2h),
  first/last shift board presence (>= 2), friendships bonus, workload balance
- Generation of placeholders: 'missing member N', 'missing board member N'
"""


import pulp

from scheduler.models import (
    AssignedShift,
    AssignedSlot,
    Availability,
    Friendship,
    Person,
    SchedulerConfig,
    ScheduleSolution,
    Shift,
)


class ScheduleOptimizer:
    """Builds and solves the MILP constraint optimization model for scheduling."""

    def __init__(
        self,
        shifts: list[Shift],
        people: list[Person],
        friendships: list[Friendship],
        config: SchedulerConfig | None = None,
        verbose: bool = False,
    ):
        self.shifts = sorted(shifts, key=lambda s: s.index)
        self.people = people
        self.friendships = friendships
        self.config = config or SchedulerConfig()
        self.verbose = verbose

    def solve(self) -> ScheduleSolution:
        """Constructs the MILP problem, solves it, and returns the solution."""
        cfg = self.config
        prob = pulp.LpProblem("StaffingSchedule", pulp.LpMinimize)

        # Active people who submitted at least one non-no availability
        active_people = [
            p for p in self.people
            if any(p.availability.get(s.index) in (Availability.YES, Availability.MAYBE) for s in self.shifts)
        ]
        # If nobody active, we still proceed so placeholders can fill the schedule
        candidate_people = active_people if active_people else self.people

        # 1. Decision variables: x[p, s] in {0, 1}
        # Hard constraint: Never create x[p, s] if availability is 'no'
        x: dict[tuple[Person, int], pulp.LpVariable] = {}
        for p in candidate_people:
            for s in self.shifts:
                avail = p.availability.get(s.index, Availability.NO)
                if avail != Availability.NO:
                    var_name = f"x_{p.canonical_id}_{s.index}"
                    x[p, s.index] = pulp.LpVariable(var_name, cat="Binary")

        # 2. Placeholders per shift (Missing board member and missing general member)
        missing_board: dict[int, pulp.LpVariable] = {}
        missing_member: dict[int, pulp.LpVariable] = {}
        for s in self.shifts:
            missing_board[s.index] = pulp.LpVariable(
                f"missing_board_{s.index}", lowBound=0, upBound=cfg.shift_size, cat="Integer"
            )
            missing_member[s.index] = pulp.LpVariable(
                f"missing_member_{s.index}", lowBound=0, upBound=cfg.shift_size, cat="Integer"
            )

        # 3. Hard Constraint: Exactly shift_size (4) people per shift
        for s in self.shifts:
            prob += (
                pulp.lpSum(x.get((p, s.index), 0) for p in candidate_people)
                + missing_board[s.index]
                + missing_member[s.index]
                == cfg.shift_size,
                f"ShiftSize_{s.index}",
            )

        # 4. Hard Constraint: Every shift must contain at least 1 board member (real or placeholder)
        for s in self.shifts:
            prob += (
                pulp.lpSum(x.get((p, s.index), 0) for p in candidate_people if p.is_board)
                + missing_board[s.index]
                >= 1,
                f"BoardPresence_{s.index}",
            )

        # 5. Soft Constraint: First and last shift board member preference (preferably >= 2)
        first_last_shortfall: list[pulp.LpVariable] = []
        if len(self.shifts) >= 1:
            special_shifts = [self.shifts[0]]
            if len(self.shifts) > 1:
                special_shifts.append(self.shifts[-1])

            for s in special_shifts:
                shortfall = pulp.LpVariable(f"board_pref_shortfall_{s.index}", lowBound=0)
                prob += (
                    pulp.lpSum(x.get((p, s.index), 0) for p in candidate_people if p.is_board)
                    + shortfall
                    >= 2,
                    f"FirstLastBoardPref_{s.index}",
                )
                first_last_shortfall.append(shortfall)

        # 6. Soft Constraint: Consecutive staffing duration (> max_consecutive_hours)
        consec_penalty_vars: list[pulp.LpVariable] = []
        # Find consecutive windows whose total duration exceeds max_consecutive_hours
        for i in range(len(self.shifts)):
            window = [self.shifts[i]]
            current_duration = self.shifts[i].duration_hours
            for j in range(i + 1, len(self.shifts)):
                if not self.shifts[j].is_consecutive_to(self.shifts[j - 1]):
                    break
                window.append(self.shifts[j])
                current_duration += self.shifts[j].duration_hours
                if current_duration > cfg.max_consecutive_hours:
                    # Minimal violating window found
                    w_indices = [s_w.index for s_w in window]
                    for p in candidate_people:
                        # If person cannot even staff all shifts in window, skip
                        if any((p, s_idx) not in x for s_idx in w_indices):
                            continue
                        c_var = pulp.LpVariable(
                            f"consec_{p.canonical_id}_{w_indices[0]}_{w_indices[-1]}", lowBound=0
                        )
                        # sum(x) <= len(window) - 1 + c_var
                        prob += (
                            pulp.lpSum(x[p, s_idx] for s_idx in w_indices)
                            <= len(window) - 1 + c_var
                        )
                        consec_penalty_vars.append(c_var)
                    break

        # 7. Soft Preference: Contiguous hours (strictly avoid split shifts)
        split_penalty_vars: list[pulp.LpVariable] = []
        for p in candidate_people:
            for i in range(len(self.shifts) - 2):
                si = self.shifts[i].index
                si1 = self.shifts[i + 1].index
                for k in range(i + 2, len(self.shifts)):
                    sk = self.shifts[k].index
                    sp_var = pulp.LpVariable(f"split_{p.canonical_id}_{si}_{sk}", lowBound=0)
                    prob += x.get((p, si), 0) - x.get((p, si1), 0) + x.get((p, sk), 0) <= 1 + sp_var
                    split_penalty_vars.append(sp_var)

        # 8. Soft Preference: Friendships
        # Only active if both friends are candidate people
        friend_vars: list[pulp.LpVariable] = []
        for friendship in self.friendships:
            p1, p2 = friendship.person_a, friendship.person_b
            if p1 not in candidate_people or p2 not in candidate_people:
                continue
            for s in self.shifts:
                if (p1, s.index) in x and (p2, s.index) in x:
                    f_var = pulp.LpVariable(
                        f"friend_{p1.canonical_id}_{p2.canonical_id}_{s.index}",
                        lowBound=0,
                        upBound=1,
                    )
                    prob += f_var <= x[p1, s.index]
                    prob += f_var <= x[p2, s.index]
                    friend_vars.append(f_var)

        # 9. Soft Preference: Workload balance (Minimizing maximum individual workload)
        max_workload_var = pulp.LpVariable("max_workload", lowBound=0)
        for p in candidate_people:
            total_p = pulp.lpSum(x.get((p, s.index), 0) for s in self.shifts)
            prob += max_workload_var >= total_p

        # 10. Soft Preference: "maybe" availability penalty
        maybe_assigned_vars: list[pulp.LpVariable] = [
            x[p, s.index]
            for p in candidate_people
            for s in self.shifts
            if (p, s.index) in x and p.availability.get(s.index) == Availability.MAYBE
        ]

        # 11. Total Objective function
        objective = (
            cfg.weight_missing_board * pulp.lpSum(missing_board.values())
            + cfg.weight_missing_member * pulp.lpSum(missing_member.values())
            + cfg.weight_consecutive * pulp.lpSum(consec_penalty_vars)
            + cfg.weight_split_shift * pulp.lpSum(split_penalty_vars)
            + cfg.weight_maybe * pulp.lpSum(maybe_assigned_vars)
            + cfg.weight_first_last_board * pulp.lpSum(first_last_shortfall)
            + cfg.weight_balance_max * max_workload_var
            - cfg.weight_friendship * pulp.lpSum(friend_vars)
        )
        prob += objective

        # Solve
        solver = pulp.PULP_CBC_CMD(
            msg=1 if self.verbose else 0,
            timeLimit=cfg.solver_timeout_sec,
            gapRel=cfg.solver_gap_rel,
        )
        prob.solve(solver)

        status_str = pulp.LpStatus[prob.status]
        if status_str not in ("Optimal", "Not Solved"):
            # IfCBC returned something strange, check if we got a solution anyway
            pass

        # Construct AssignedShift objects
        assigned_shifts: list[AssignedShift] = []
        for s in self.shifts:
            slots: list[AssignedSlot] = []

            # 1. Real people assigned
            assigned_people = [
                p for p in candidate_people
                if (p, s.index) in x and pulp.value(x[p, s.index]) is not None and pulp.value(x[p, s.index]) > 0.5
            ]

            # Sort real people: Board members first, then by name
            assigned_people.sort(key=lambda p: (not p.is_board, p.display_name))

            for p in assigned_people:
                avail_used = p.availability.get(s.index, Availability.NO).value
                slots.append(
                    AssignedSlot(
                        name=p.display_name,
                        is_placeholder=False,
                        is_board=p.is_board,
                        person=p,
                        availability_used=avail_used,
                    )
                )

            # 2. Placeholders: Board placeholders
            val_mb = round(pulp.value(missing_board[s.index]) or 0)
            for i in range(val_mb):
                slots.append(
                    AssignedSlot(
                        name=f"missing board member {i + 1}",
                        is_placeholder=True,
                        is_board=True,
                        person=None,
                    )
                )

            # 3. Placeholders: General member placeholders
            val_mm = round(pulp.value(missing_member[s.index]) or 0)
            for i in range(val_mm):
                slots.append(
                    AssignedSlot(
                        name=f"missing member {i + 1}",
                        is_placeholder=True,
                        is_board=False,
                        person=None,
                    )
                )

            assigned_shifts.append(AssignedShift(shift=s, slots=slots))

        return ScheduleSolution(
            shifts=assigned_shifts,
            status=status_str,
            objective_value=float(pulp.value(prob.objective) or 0.0),
            people=candidate_people,
            friendships=self.friendships,
            config=cfg,
        )
