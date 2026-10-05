# AGENTS.md

## 1. Project Goal

This project aims to automatically generate work schedules.

The application receives three CSV files describing:

1. People's availability for each time slot.
2. Friendships between people.
3. Members of the board.

Based on these inputs, the program must generate a schedule made of shifts while satisfying the staffing constraints and optimizing the quality of the schedule.

The generator should not simply find any valid schedule. It should find the best possible schedule according to the defined constraints and preferences.

---

## 2. Input Data

### 2.1 Availability CSV

The availability CSV describes whether each person is available during each time slot.

The possible values are:

* `yes`: the person is available.
* `no`: the person is unavailable.
* `maybe`: the person may be available, but should be avoided when a better solution exists.

A `no` availability should be treated as a hard constraint: a person must not be assigned to a shift for which they are unavailable.

A `maybe` availability is strictly reserved for cases of necessity: people who are `maybe` staff only if there are not enough members available with `yes` (to fill the 4 spots or satisfy board presence). Otherwise, they must not staff.

---

### 2.2 Friendships CSV

The friendships CSV contains friendship relationships between people.

Names in this file are expected to be complete.

Friendships should be used to favor assigning friends to the same shifts.

Friendships are a preference, not a hard constraint.

The absence of a friendship relationship does not mean that two people cannot work together.

---

### 2.3 Board Members CSV

The board members CSV contains the list of people who are members of the board.

Names in this file are expected to be complete.

Every shift must contain at least one board member whenever possible.

If no real board member can be assigned to a shift, a placeholder must be used.

---

## 3. Name Matching and Normalization

A critical part of this project is matching people across the different CSV files.

Names are not necessarily written consistently between files.

For example, the availability CSV may contain:

```text
Louis Rodet
louis rodet
Louis
louis.r
louis.r.
louis r
L. Rodet
louisr
```

while the friendship and board CSVs may contain:

```text
Louis Rodet
```

The system must therefore implement robust name normalization and matching.

### Normalization

Before comparing names, the system should:

* remove unnecessary whitespace;
* convert names to lowercase;
* normalize accents;
* normalize or remove punctuation where appropriate;
* normalize separators such as `.`, `_`, `-`, and spaces where appropriate;
* support first-name-only forms;
* support initials;
* support abbreviated names.

For example:

```text
"Louis Rodet"
"louis rodet"
"Louis"
"louis.r"
"L. Rodet"
```

should be recognized as the same person when the available information allows this to be determined safely.

### Ambiguous Matches

The system must never arbitrarily associate two different people.

For example, if multiple people are named `Louis`, the name `Louis` alone is not necessarily sufficient to identify a person.

In ambiguous cases, the system should:

1. use additional information when available;
2. attempt a more precise match;
3. report the ambiguity;
4. never silently choose a person at random.

It is preferable to report an ambiguity than to generate a schedule using an incorrect identity.

---

## 4. Shift Composition

Standard shifts must contain exactly 4 people.

However, the first shift (installation / setup) and the last shift (désinstallation / teardown) require an extra person, for a total of 5 people.

Example (standard shift):

```text
Shift 2
- Alice
- Bob
- Charlie
- David
```

If there are not enough real people to fill a shift, the shift must be completed with placeholder members.

Example:

```text
Shift 1
- Alice
- Bob
- Charlie
- missing member 1
```

Missing members must use the following naming convention:

```text
missing member 1
missing member 2
...
```

---

## 5. Board Presence

Every shift must contain at least one board member.

Example:

```text
Shift 3
- Alice
- Bob
- Charlie
- David

Board member:
- Alice
```

If no real board member is available for a shift, a placeholder must be used:

```text
Shift 3
- Alice
- Bob
- Charlie
- missing board member 1
```

Board placeholders must use the following naming convention:

```text
missing board member 1
missing board member 2
...
```

Board presence is a higher-priority constraint than friendship preferences and other soft preferences.

---

## 6. Staffing Duration and Contiguity

Ideally, a standard volunteer should not staff for more than 2 consecutive hours.

However, board members may staff for up to 3 consecutive hours in order to ensure continuous board presence across the event and prevent split shifts.

The generator should avoid assignments exceeding these thresholds:

```text
Shift 1: Alice
Shift 2: Alice
Shift 3: Alice
```

when Alice is a standard volunteer, or more than 3 consecutive hours when Alice is a board member.

### Contiguous Hours

Working hours for any individual must be contiguous:

* If someone works 2 hours (or multiple shifts), they must be assigned to consecutive hours (e.g. 14:00 - 16:00, not 12:00 - 13:00 and 17:00 - 18:00).
* Split shifts (working, stopping, and returning later in the day) should be strictly avoided.

### Flexible Duration

Not everyone is required to work 2 hours if there are enough available people:

* A person may work 1 hour if sufficient staff is available.
* A person may work 0 hours if staffing needs are already met without them.

This is a preference rather than an absolute constraint.

If no satisfactory solution exists, this preference may be violated in order to satisfy higher-priority constraints.

---

## 7. First and Last Shifts

The first and last shifts are special.

They correspond to setup (installation) and teardown (désinstallation) and require an additional person (5 people instead of 4).

Additionally, they should preferably contain at least two board members.

For example:

```text
First shift (Installation):
- Board member
- Board member
- Member
- Member
- Member
```

and:

```text
Last shift (Désinstallation):
- Board member
- Board member
- Member
- Member
- Member
```

This board presence preference is a preference, not a hard constraint.

If this conflicts with a higher-priority constraint, it may be violated.

---

## 8. Friendships

The generator should favor assigning friends to the same shift.

For example, if:

```text
Alice <-> Bob
Alice <-> Charlie
```

then a shift containing:

```text
Alice
Bob
Charlie
David
```

should be considered better than:

```text
Alice
David
Eve
Frank
```

assuming all other constraints are equivalent.

Friendships must never override higher-priority constraints, especially:

* `no` availability;
* exactly 4 people per shift;
* board member presence.

If friendships are represented as directed relationships in the input data, the implementation should preserve the semantics of the input format. If they are intended to be undirected, the model should treat `Alice <-> Bob` as a mutual friendship.

---

## 9. Constraint Priority

Not all constraints have the same importance.

The generator should use a clear hierarchy between hard constraints and soft preferences.

### Hard Constraints

These constraints must be respected whenever possible:

1. Every shift contains the required number of people (5 for first and last shifts for installation/désinstallation, 4 for standard shifts).
2. A person with `no` availability must not be assigned to that shift.
3. Every shift must contain at least one board member.
4. If a shift cannot be filled with enough real people, use `missing member N` placeholders.
5. If a shift cannot contain a real board member, use `missing board member N`.

### Soft Constraints

Once the hard constraints are satisfied, the generator should optimize the following preferences:

1. `maybe` availability is used strictly in case of necessity (insufficient `yes` members to staff the shift); otherwise people with `maybe` must not staff.
2. Avoid having a person staff for more than 2 consecutive hours.
3. Ensure hours are contiguous when working multiple shifts (strictly avoid split shifts).
4. Prefer at least two board members in the first shift.
5. Prefer at least two board members in the last shift.
6. Maximize friendships within shifts.
7. Balance the total workload between people as much as possible.

The exact weighting of these preferences should be configurable.

---

## 10. Optimization Objective

The scheduling problem should be treated as a constraint optimization problem.

Rather than simply checking whether a schedule is valid, the system should assign costs or penalties to undesirable situations.

Conceptually:

```text
total cost =
    penalty for "maybe" availability
  + penalty for excessive consecutive staffing (> 2h)
  + penalty for non-contiguous staffing (split shifts)
  + penalty for missing board members
  + penalty for first shift board preference violation
  + penalty for last shift board preference violation
  - bonus for friendships
  - bonus for workload balance
```

Hard constraints must have sufficiently high priority that they are not sacrificed to improve soft preferences.

A suitable optimization approach may include:

* integer linear programming;
* CP-SAT;
* constraint programming;
* another appropriate optimization solver.

The implementation should choose the approach that best fits the project's architecture and dependencies.

---

## 11. Placeholder Members

Two types of placeholders may be generated.

### Missing Member

Use:

```text
missing member 1
missing member 2
...
```

when a shift cannot be filled with enough real people.

### Missing Board Member

Use:

```text
missing board member 1
missing board member 2
...
```

when a shift cannot contain a real board member.

Placeholders are not real people.

They must not:

* participate in friendship calculations;
* contribute to workload calculations;
* be treated as available or unavailable;
* appear in real-person statistics.

---

## 12. Data Validation

The program must validate all input data before generating a schedule.

It should detect at least:

* unknown names;
* ambiguous name matches;
* people present in one file but missing from another;
* invalid CSV rows;
* invalid availability values;
* duplicate entries;
* empty files;
* shifts that cannot be properly staffed.

Unknown availability values must be rejected.

Only the following values are valid:

```text
yes
no
maybe
```

Data errors and ambiguities must be clearly reported.

The program must never silently modify ambiguous input data.

---

## 13. Recommended Architecture

The code should clearly separate the different responsibilities.

A recommended architecture is:

```text
CSV loading
    |
    v
Data validation
    |
    v
Name normalization / identity resolution
    |
    v
Constraint model construction
    |
    v
Optimization
    |
    v
Solution validation
    |
    v
Schedule generation
```

The name-resolution system should be independent from the scheduling engine.

The optimization engine should not contain CSV parsing logic.

---

## 14. Solution Validation

After generating a schedule, the program must automatically validate it.

Validation should check at least:

* every shift contains exactly 4 entries;
* no real person is assigned to a `no` availability slot;
* every shift contains at least one real board member or a `missing board member N` placeholder;
* placeholders are correctly named;
* consecutive staffing durations are correctly calculated;
* contiguity of working hours is verified (split shifts flagged);
* friendship scores are correctly calculated;
* workload distribution is correctly calculated.

The program should also produce a report explaining why the solution is not perfect.

Example:

```text
Schedule generated with 3 soft-constraint violations:

- 1 "maybe" availability used
- Alice staffs for 3 consecutive hours
- The last shift contains only 1 board member
```

---

## 15. Development Principles

When modifying the project:

* preserve the separation between parsing, normalization, optimization, and schedule generation;
* avoid arbitrary heuristics when a requirement can be expressed as a constraint;
* make optimization weights configurable rather than hard-coding them throughout the codebase;
* add tests for edge cases;
* never hide ambiguous data;
* prefer explainable and reproducible solutions;
* document every new constraint added to the system.

Constraints and preference weights should be centralized whenever possible so that their priorities can easily be adjusted.

---

## 16. Important Edge Cases

The program must correctly handle cases such as:

### Not enough people

```text
Shift 1
- Alice
- Bob
- missing member 1
- missing member 2
```

### No available board member

```text
Shift 2
- Alice
- Bob
- Charlie
- missing board member 1
```

### Only one available person

```text
Shift 3
- Alice
- missing member 1
- missing member 2
- missing member 3
```

### No available person

```text
Shift 4
- missing member 1
- missing member 2
- missing member 3
- missing member 4
```

In the last case, the system must explicitly report that the shift cannot be staffed with real people.

If board presence is also required, the implementation must make sure that the representation of the missing board member does not violate the requirement of exactly 4 entries per shift.

---

## 17. General Principle

The goal is not merely to generate a valid schedule.

The goal is to generate the best possible schedule given the available data.

Hard constraints must always take priority over soft preferences.

When all constraints cannot be satisfied simultaneously, the system must:

1. generate the best possible schedule;
2. use the required placeholders;
3. report which constraints could not be satisfied;
4. never silently modify or invent input data.
