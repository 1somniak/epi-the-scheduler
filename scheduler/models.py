"""Data models for The Scheduler."""

from dataclasses import dataclass, field
from enum import Enum


class Availability(str, Enum):
    YES = "yes"
    NO = "no"
    MAYBE = "maybe"


@dataclass
class Shift:
    """Represents a time slot / shift."""
    index: int
    name: str
    date_str: str | None = None
    start_time_str: str | None = None
    end_time_str: str | None = None
    start_minutes: int | None = None
    end_minutes: int | None = None
    duration_hours: float = 1.0

    def is_consecutive_to(self, previous: "Shift") -> bool:
        """Determines if this shift directly follows another shift in time."""
        if self.start_minutes is not None and previous.end_minutes is not None:
            return self.start_minutes == previous.end_minutes
        # Fallback to index adjacency
        return self.index == previous.index + 1


@dataclass
class Person:
    """Represents a real person or volunteer."""
    canonical_id: str
    display_name: str
    first_name: str
    last_tokens: list[str] = field(default_factory=list)
    is_board: bool = False
    aliases: set[str] = field(default_factory=set)
    # shift_index -> Availability
    availability: dict[int, Availability] = field(default_factory=dict)
    is_placeholder: bool = False

    @property
    def last_name(self) -> str:
        return "-".join(self.last_tokens)

    def is_available(self, shift_index: int) -> bool:
        return self.availability.get(shift_index) in (Availability.YES, Availability.MAYBE)

    def __hash__(self) -> int:
        return hash(self.canonical_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Person):
            return False
        return self.canonical_id == other.canonical_id

    def __repr__(self) -> str:
        role = "Board" if self.is_board else "Member"
        return f"<Person {self.display_name} ({role})>"


@dataclass
class Friendship:
    """Represents an undirected friendship between two people."""
    person_a: Person
    person_b: Person

    def contains(self, person: Person) -> bool:
        return person == self.person_a or person == self.person_b

    def other(self, person: Person) -> Person | None:
        if person == self.person_a:
            return self.person_b
        if person == self.person_b:
            return self.person_a
        return None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Friendship):
            return False
        return (
            (self.person_a == other.person_a and self.person_b == other.person_b)
            or (self.person_a == other.person_b and self.person_b == other.person_a)
        )

    def __hash__(self) -> int:
        return hash(frozenset({self.person_a.canonical_id, self.person_b.canonical_id}))


@dataclass
class SchedulerConfig:
    """Configurable weights and thresholds for the optimization engine."""
    shift_size: int = 4
    first_last_shift_size: int = 5
    max_consecutive_hours: float = 2.0
    max_consecutive_hours_board: float = 3.0

    def get_shift_size(self, shift_idx: int, total_shifts: int) -> int:
        """Returns the required staffing count for a shift given its index.

        When there are multiple shifts, the first (setup) and last (teardown)
        shifts require an additional person.
        """
        if total_shifts > 1 and (shift_idx == 0 or shift_idx == total_shifts - 1):
            return self.first_last_shift_size
        return self.shift_size

    def get_max_consecutive_hours(self, is_board: bool) -> float:
        """Returns the maximum preferred continuous hours for a person."""
        return self.max_consecutive_hours_board if is_board else self.max_consecutive_hours

    # Penalties for hard constraint relaxations (placeholders)
    weight_missing_board: float = 1_000_000.0
    weight_missing_member: float = 500_000.0

    # Penalties for soft constraint preferences
    weight_consecutive: float = 300.0
    weight_maybe: float = 10_000.0
    weight_first_last_board: float = 50.0
    weight_friendship: float = 30.0
    weight_balance_dev: float = 10.0
    weight_balance_max: float = 20.0
    weight_split_shift: float = 1_000.0

    solver_timeout_sec: int | None = 20
    solver_gap_rel: float = 0.01


@dataclass
class ValidationIssue:
    """A detected error or warning during input validation."""
    level: str  # "ERROR" or "WARNING"
    category: str
    message: str
    file: str | None = None
    row: int | None = None


@dataclass
class InputValidationReport:
    """Report summarizing the input data validation phase."""
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not any(i.level == "ERROR" for i in self.issues)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "ERROR"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "WARNING"]


@dataclass
class AssignedSlot:
    """An assigned slot in a shift, either a real person or a placeholder."""
    name: str
    is_placeholder: bool
    is_board: bool
    person: Person | None = None
    availability_used: str | None = None


@dataclass
class AssignedShift:
    """Represents a scheduled shift with all its assigned members."""
    shift: Shift
    slots: list[AssignedSlot] = field(default_factory=list)

    @property
    def real_people(self) -> list[Person]:
        return [s.person for s in self.slots if s.person is not None]

    @property
    def board_members(self) -> list[Person]:
        return [s.person for s in self.slots if s.person is not None and s.person.is_board]

    @property
    def placeholders(self) -> list[str]:
        return [s.name for s in self.slots if s.is_placeholder]


@dataclass
class ScheduleSolution:
    """The complete schedule produced by the optimizer."""
    shifts: list[AssignedShift]
    status: str
    objective_value: float
    people: list[Person]
    friendships: list[Friendship]
    config: SchedulerConfig


@dataclass
class ScheduleValidationReport:
    """Post-solve validation report certifying constraints and detailing violations."""
    is_valid: bool
    hard_constraint_errors: list[str] = field(default_factory=list)
    soft_constraint_violations: list[str] = field(default_factory=list)
    realized_friendships: list[tuple[str, str, str]] = field(default_factory=list)  # (shift_name, p1, p2)
    workload_summary: dict[str, int] = field(default_factory=dict)  # person_name -> shifts count
    consecutive_violations: list[str] = field(default_factory=list)
    maybe_violations: list[str] = field(default_factory=list)
    board_violations: list[str] = field(default_factory=list)
    split_shift_violations: list[str] = field(default_factory=list)
    placeholder_summary: list[str] = field(default_factory=list)
