"""CSV loading and initial input validation.

Implements Sections 2 and 12 of AGENTS.md:
- Availability CSV loading & validation
- Board members CSV loading
- Friendship CSV loading
- Validation of values (yes/no/maybe), missing files, missing persons, duplicate entries
"""

import csv
import os
import re

from scheduler.models import (
    Availability,
    Friendship,
    InputValidationReport,
    Person,
    Shift,
    ValidationIssue,
)
from scheduler.normalizer import AmbiguousNameError, IdentityResolver, clean_string


def parse_shift_header(header: str, index: int) -> Shift:
    """Parses date, time, and duration from a shift column header."""
    time_match = re.search(
        r"(\d{4}-\d{2}-\d{2})?\s*\(?(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\)?",
        header,
    )
    if time_match:
        date_str = time_match.group(1)
        sh, sm = int(time_match.group(2)), int(time_match.group(3))
        eh, em = int(time_match.group(4)), int(time_match.group(5))
        s_min = sh * 60 + sm
        e_min = eh * 60 + em
        # If end is earlier than start (e.g. overnight), add 24 hours
        if e_min < s_min:
            e_min += 24 * 60
        duration = max(0.5, (e_min - s_min) / 60.0)
        return Shift(
            index=index,
            name=header.strip(),
            date_str=date_str,
            start_time_str=f"{sh:02d}:{sm:02d}",
            end_time_str=f"{eh:02d}:{em:02d}",
            start_minutes=s_min,
            end_minutes=e_min,
            duration_hours=duration,
        )
    return Shift(index=index, name=header.strip(), duration_hours=1.0)


class DataLoader:
    """Loads and validates CSV files for the scheduler."""

    def __init__(self, resolver: IdentityResolver | None = None):
        self.resolver = resolver or IdentityResolver()
        self.report = InputValidationReport()

    def load_board(self, filepath: str) -> list[Person]:
        """Loads the board members CSV."""
        if not os.path.exists(filepath):
            self.report.issues.append(
                ValidationIssue(
                    level="ERROR",
                    category="FILE_NOT_FOUND",
                    message=f"Board file not found: '{filepath}'",
                    file=filepath,
                )
            )
            return []

        board_members: list[Person] = []
        with open(filepath, "r", encoding="utf-8-sig") as f:
            lines = [line.strip() for line in f if line.strip()]

        if not lines:
            self.report.issues.append(
                ValidationIssue(
                    level="ERROR",
                    category="EMPTY_FILE",
                    message=f"Board file '{filepath}' is empty.",
                    file=filepath,
                )
            )
            return []

        # Check if first line is a header like 'name' or 'nom'
        first_line_clean = clean_string(lines[0])
        start_idx = 0
        if first_line_clean in ("name", "nom", "member", "board", "board member", "bureau"):
            start_idx = 1

        seen_names: set[str] = set()
        for row_idx, line in enumerate(lines[start_idx:], start=start_idx + 1):
            # In case it's a CSV row with quotes/commas
            reader = csv.reader([line])
            parts = next(reader)
            if not parts or not parts[0].strip():
                continue
            name = parts[0].strip()

            c_name = clean_string(name)
            if c_name in seen_names:
                self.report.issues.append(
                    ValidationIssue(
                        level="WARNING",
                        category="DUPLICATE_ENTRY",
                        message=f"Duplicate entry for board member '{name}' in '{filepath}'.",
                        file=filepath,
                        row=row_idx,
                    )
                )
                continue
            seen_names.add(c_name)

            try:
                person = self.resolver.register_person(name, is_board=True)
                board_members.append(person)
            except AmbiguousNameError as e:
                self.report.issues.append(
                    ValidationIssue(
                        level="ERROR",
                        category="AMBIGUOUS_NAME",
                        message=str(e),
                        file=filepath,
                        row=row_idx,
                    )
                )

        return board_members

    def load_availability(self, filepath: str) -> tuple[list[Shift], list[Person]]:
        """Loads the availability CSV containing shifts and volunteer responses."""
        if not os.path.exists(filepath):
            self.report.issues.append(
                ValidationIssue(
                    level="ERROR",
                    category="FILE_NOT_FOUND",
                    message=f"Availability file not found: '{filepath}'",
                    file=filepath,
                )
            )
            return [], []

        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                self.report.issues.append(
                    ValidationIssue(
                        level="ERROR",
                        category="EMPTY_FILE",
                        message=f"Availability file '{filepath}' is empty.",
                        file=filepath,
                    )
                )
                return [], []

        if not header:
            self.report.issues.append(
                ValidationIssue(
                    level="ERROR",
                    category="INVALID_CSV",
                    message=f"Availability file '{filepath}' has an empty header row.",
                    file=filepath,
                )
            )
            return [], []

        # Find Name column
        name_col_idx = -1
        for idx, col in enumerate(header):
            cleaned = clean_string(col)
            if "name" in cleaned or "nom" in cleaned:
                name_col_idx = idx
                break
        if name_col_idx == -1:
            # Fallback to column index 2 (standard Doodle / When2meet export) or 0
            name_col_idx = 2 if len(header) > 2 else 0

        # Identify shift columns: columns containing time ranges or after metadata
        shift_col_indices: list[int] = []
        for idx in range(len(header)):
            if idx == name_col_idx:
                continue
            col_header = header[idx]
            col_clean = clean_string(col_header)
            # Exclude known metadata columns
            if col_clean in ("#", "id", "date (utc)", "unique code (optional)", "country", "date", "email"):
                continue
            shift_col_indices.append(idx)

        if not shift_col_indices:
            self.report.issues.append(
                ValidationIssue(
                    level="ERROR",
                    category="NO_SHIFTS",
                    message=f"No shift/time slot columns identified in '{filepath}'.",
                    file=filepath,
                )
            )
            return [], []

        shifts: list[Shift] = [
            parse_shift_header(header[col_idx], shift_idx)
            for shift_idx, col_idx in enumerate(shift_col_indices)
        ]

        # Read rows
        people_loaded: list[Person] = []
        seen_people: set[str] = set()

        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for row_idx, row in enumerate(reader, start=2):
                if not row or not any(field.strip() for field in row):
                    continue

                if name_col_idx >= len(row):
                    self.report.issues.append(
                        ValidationIssue(
                            level="ERROR",
                            category="INVALID_ROW",
                            message=f"Row {row_idx} is missing the Name column.",
                            file=filepath,
                            row=row_idx,
                        )
                    )
                    continue

                raw_name = row[name_col_idx].strip()
                if not raw_name:
                    continue

                try:
                    person = self.resolver.resolve(raw_name)
                    if person is None:
                        # Register as volunteer
                        person = self.resolver.register_person(raw_name, is_board=False)
                except AmbiguousNameError as e:
                    self.report.issues.append(
                        ValidationIssue(
                            level="ERROR",
                            category="AMBIGUOUS_NAME",
                            message=str(e),
                            file=filepath,
                            row=row_idx,
                        )
                    )
                    continue

                if person.canonical_id in seen_people:
                    self.report.issues.append(
                        ValidationIssue(
                            level="WARNING",
                            category="DUPLICATE_SUBMISSION",
                            message=f"Duplicate response for '{person.display_name}' in '{filepath}'. Overwriting availability.",
                            file=filepath,
                            row=row_idx,
                        )
                    )
                else:
                    seen_people.add(person.canonical_id)
                    people_loaded.append(person)

                # Parse availability for each shift
                for shift_idx, col_idx in enumerate(shift_col_indices):
                    if col_idx < len(row):
                        raw_val = row[col_idx].strip().lower()
                    else:
                        raw_val = "no"

                    if raw_val in ("yes", "oui", "y", "o", "true", "1"):
                        avail = Availability.YES
                    elif raw_val in ("no", "non", "n", "false", "0"):
                        avail = Availability.NO
                    elif raw_val in ("maybe", "peut-etre", "peut-être", "m", "?"):
                        avail = Availability.MAYBE
                    else:
                        self.report.issues.append(
                            ValidationIssue(
                                level="ERROR",
                                category="INVALID_AVAILABILITY",
                                message=(
                                    f"Invalid availability value '{raw_val}' for '{person.display_name}' "
                                    f"in shift '{shifts[shift_idx].name}'. Must be 'yes', 'no', or 'maybe'."
                                ),
                                file=filepath,
                                row=row_idx,
                            )
                        )
                        avail = Availability.NO

                    person.availability[shift_idx] = avail

        # Check for board members who did not submit availability
        for registered_person in self.resolver.people:
            if registered_person.is_board and registered_person.canonical_id not in seen_people:
                self.report.issues.append(
                    ValidationIssue(
                        level="WARNING",
                        category="MISSING_AVAILABILITY",
                        message=f"Board member '{registered_person.display_name}' is missing from availability CSV.",
                        file=filepath,
                    )
                )

        return shifts, people_loaded

    def load_friendships(self, filepath: str) -> list[Friendship]:
        """Loads the friendships CSV."""
        if not os.path.exists(filepath):
            self.report.issues.append(
                ValidationIssue(
                    level="ERROR",
                    category="FILE_NOT_FOUND",
                    message=f"Friendships file not found: '{filepath}'",
                    file=filepath,
                )
            )
            return []

        friendships: list[Friendship] = []
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = [r for r in reader if r and any(cell.strip() for cell in r)]

        if not rows:
            self.report.issues.append(
                ValidationIssue(
                    level="WARNING",
                    category="EMPTY_FILE",
                    message=f"Friendships file '{filepath}' is empty.",
                    file=filepath,
                )
            )
            return []

        # Check if first row is header
        start_idx = 0
        if len(rows[0]) >= 2:
            r0_clean = [clean_string(c) for c in rows[0][:2]]
            if any("friend" in c or "person" in c or "ami" in c for c in r0_clean):
                start_idx = 1

        seen_pairs: set[frozenset[str]] = set()

        for row_idx, row in enumerate(rows[start_idx:], start=start_idx + 1):
            if len(row) < 2:
                self.report.issues.append(
                    ValidationIssue(
                        level="WARNING",
                        category="INVALID_ROW",
                        message=f"Friendships row {row_idx} has fewer than 2 names: {row}.",
                        file=filepath,
                        row=row_idx,
                    )
                )
                continue

            name_a, name_b = row[0].strip(), row[1].strip()
            if not name_a or not name_b:
                continue

            try:
                p_a = self.resolver.resolve(name_a)
            except AmbiguousNameError as e:
                self.report.issues.append(
                    ValidationIssue(
                        level="ERROR",
                        category="AMBIGUOUS_NAME",
                        message=str(e),
                        file=filepath,
                        row=row_idx,
                    )
                )
                p_a = None

            try:
                p_b = self.resolver.resolve(name_b)
            except AmbiguousNameError as e:
                self.report.issues.append(
                    ValidationIssue(
                        level="ERROR",
                        category="AMBIGUOUS_NAME",
                        message=str(e),
                        file=filepath,
                        row=row_idx,
                    )
                )
                p_b = None

            if p_a is None:
                self.report.issues.append(
                    ValidationIssue(
                        level="WARNING",
                        category="PERSON_NOT_FOUND",
                        message=f"Person '{name_a}' in friendships CSV is missing from availability CSV.",
                        file=filepath,
                        row=row_idx,
                    )
                )
            if p_b is None:
                self.report.issues.append(
                    ValidationIssue(
                        level="WARNING",
                        category="PERSON_NOT_FOUND",
                        message=f"Person '{name_b}' in friendships CSV is missing from availability CSV.",
                        file=filepath,
                        row=row_idx,
                    )
                )

            if p_a and p_b:
                pair_key = frozenset({p_a.canonical_id, p_b.canonical_id})
                if p_a == p_b:
                    self.report.issues.append(
                        ValidationIssue(
                            level="WARNING",
                            category="SELF_FRIENDSHIP",
                            message=f"Self-friendship for '{p_a.display_name}' ignored.",
                            file=filepath,
                            row=row_idx,
                        )
                    )
                    continue
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                friendships.append(Friendship(person_a=p_a, person_b=p_b))

        return friendships
