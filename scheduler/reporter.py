"""Schedule presentation and reporting engine.

Generates beautiful terminal views using Rich (or plain text fallback)
and exports clean CSV and text reports.
"""

import csv
from typing import Optional

from scheduler.models import (
    InputValidationReport,
    ScheduleSolution,
    ScheduleValidationReport,
)

try:
    from rich.box import ROUNDED
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


class ScheduleReporter:
    """Renders schedule solutions and validation reports to terminal or files."""

    def __init__(self, console: Optional["Console"] = None):
        if HAS_RICH:
            self.console = console or Console()
        else:
            self.console = None

    def print_input_validation(self, report: InputValidationReport) -> None:
        """Displays input validation issues (errors and warnings)."""
        if not report.issues:
            return

        if HAS_RICH and self.console:
            table = Table(title="Input Data Validation Notices", box=ROUNDED, header_style="bold magenta")
            table.add_column("Level", style="bold", width=10)
            table.add_column("Category", style="cyan", width=22)
            table.add_column("Details", style="white")

            for issue in report.issues:
                style = "bold red" if issue.level == "ERROR" else "bold yellow"
                table.add_row(f"[{style}]{issue.level}[/{style}]", issue.category, issue.message)

            self.console.print(table)
            self.console.print()
        else:
            print("\n--- Input Data Validation Notices ---")
            for issue in report.issues:
                print(f"[{issue.level}] ({issue.category}) {issue.message}")
            print()

    def print_schedule(
        self, solution: ScheduleSolution, val_report: ScheduleValidationReport
    ) -> None:
        """Prints the full schedule and performance summary."""
        if HAS_RICH and self.console:
            self._print_schedule_rich(solution, val_report)
        else:
            self._print_schedule_plain(solution, val_report)

    def _print_schedule_rich(
        self, solution: ScheduleSolution, val_report: ScheduleValidationReport
    ) -> None:
        assert self.console is not None
        # Title Banner
        self.console.print()
        banner_text = Text("✨ THE SCHEDULER - OPTIMIZED WORK SCHEDULE ✨", style="bold cyan")
        self.console.print(Panel(banner_text, border_style="cyan", expand=False))

        # Main Schedule Table
        table = Table(
            title="Generated Shifts & Assignments",
            box=ROUNDED,
            header_style="bold white on blue",
            show_lines=True,
        )
        max_slots = max(
            (len(s.slots) for s in solution.shifts),
            default=solution.config.first_last_shift_size,
        )
        table.add_column("Shift / Time", style="bold white", width=26)
        for i in range(max_slots):
            table.add_column(f"Member {i + 1}", width=20)

        for assigned_shift in solution.shifts:
            shift_title = assigned_shift.shift.name
            slot_cells = []

            for slot in assigned_shift.slots:
                if slot.is_placeholder:
                    if "board" in slot.name:
                        slot_cells.append(f"[bold red]⚠️ {slot.name}[/bold red]")
                    else:
                        slot_cells.append(f"[bold magenta]❓ {slot.name}[/bold magenta]")
                elif slot.is_board:
                    tag = " (maybe)" if slot.availability_used == "maybe" else ""
                    color = "yellow" if slot.availability_used == "maybe" else "cyan"
                    slot_cells.append(f"[{color}]⭐ {slot.name}{tag}[/{color}]")
                else:
                    tag = " (maybe)" if slot.availability_used == "maybe" else ""
                    color = "yellow" if slot.availability_used == "maybe" else "green"
                    slot_cells.append(f"[{color}]👤 {slot.name}{tag}[/{color}]")

            while len(slot_cells) < max_slots:
                slot_cells.append("[dim]-[/dim]")

            table.add_row(shift_title, *slot_cells[:max_slots])

        self.console.print(table)
        self.console.print()

        # Solution Quality & Validation Report
        status_color = "green" if val_report.is_valid else "red"
        status_text = "PASSED (All hard constraints satisfied)" if val_report.is_valid else "FAILED (Hard constraints violated)"

        report_lines = [f"[bold {status_color}]Hard Constraints Status: {status_text}[/bold {status_color}]"]
        if val_report.hard_constraint_errors:
            for err in val_report.hard_constraint_errors:
                report_lines.append(f"  [bold red]❌ {err}[/bold red]")

        report_lines.append("")
        if not val_report.soft_constraint_violations:
            report_lines.append("[bold green]🌟 Perfect Schedule: 0 soft-constraint violations![/bold green]")
        else:
            report_lines.append(
                f"[bold yellow]Schedule generated with {len(val_report.soft_constraint_violations)} soft-constraint violation(s):[/bold yellow]"
            )
            for viol in val_report.soft_constraint_violations:
                report_lines.append(f"  • {viol}")

        if val_report.realized_friendships:
            report_lines.append("")
            report_lines.append(
                f"[bold green]🤝 Realized Friendships ({len(val_report.realized_friendships)}):[/bold green]"
            )
            for s_name, f1, f2 in val_report.realized_friendships:
                report_lines.append(f"  • {f1} <-> {f2} in '{s_name}'")

        self.console.print(
            Panel("\n".join(report_lines), title="Validation & Quality Report", border_style="blue")
        )
        self.console.print()

        # Workload Distribution Table
        w_table = Table(title="Workload Distribution", box=ROUNDED, header_style="bold cyan")
        w_table.add_column("Person", style="bold white")
        w_table.add_column("Role", justify="center", width=12)
        w_table.add_column("Shifts Worked", justify="center", width=14)
        w_table.add_column("Hours", justify="center", width=10)

        for p in sorted(solution.people, key=lambda x: (not x.is_board, -val_report.workload_summary.get(x.display_name, 0), x.display_name)):
            shifts_cnt = val_report.workload_summary.get(p.display_name, 0)
            role = "[cyan]Board[/cyan]" if p.is_board else "[green]Volunteer[/green]"
            w_table.add_row(p.display_name, role, str(shifts_cnt), f"{shifts_cnt:.1f}h")

        self.console.print(w_table)
        self.console.print()

    def _print_schedule_plain(
        self, solution: ScheduleSolution, val_report: ScheduleValidationReport
    ) -> None:
        print("=" * 70)
        print("THE SCHEDULER - OPTIMIZED WORK SCHEDULE")
        print("=" * 70)

        for assigned_shift in solution.shifts:
            print(f"\n--- {assigned_shift.shift.name} ---")
            for slot in assigned_shift.slots:
                tag = " (Board)" if slot.is_board else ""
                if slot.is_placeholder:
                    print(f"  * [PLACEHOLDER] {slot.name}")
                else:
                    m_tag = " [MAYBE]" if slot.availability_used == "maybe" else ""
                    print(f"  * {slot.name}{tag}{m_tag}")

        print("\n" + "=" * 70)
        print(f"Validation Status: {'PASSED' if val_report.is_valid else 'FAILED'}")
        if val_report.soft_constraint_violations:
            print(f"\nSchedule generated with {len(val_report.soft_constraint_violations)} soft-constraint violations:")
            for v in val_report.soft_constraint_violations:
                print(f"  - {v}")
        else:
            print("\nSchedule generated with 0 soft-constraint violations (Perfect solution)!")

        print("\nWorkload summary:")
        for p_name, count in sorted(val_report.workload_summary.items(), key=lambda item: -item[1]):
            print(f"  {p_name:25}: {count} shift(s)")
        print("=" * 70)


def export_schedule_csv(solution: ScheduleSolution, filepath: str) -> None:
    """Exports the generated schedule to a clean CSV format."""
    max_slots = max(
        (len(s.slots) for s in solution.shifts),
        default=solution.config.first_last_shift_size,
    )
    headers = ["Shift"] + [f"Slot {i + 1}" for i in range(max_slots)] + ["Board Members", "Placeholders"]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for a_shift in solution.shifts:
            slot_names = [s.name for s in a_shift.slots]
            while len(slot_names) < max_slots:
                slot_names.append("")
            board_names = [s.name for s in a_shift.slots if s.is_board and not s.is_placeholder]
            placeholders = [s.name for s in a_shift.slots if s.is_placeholder]
            writer.writerow([
                a_shift.shift.name,
                *slot_names[:max_slots],
                "; ".join(board_names),
                "; ".join(placeholders),
            ])


def export_report_txt(solution: ScheduleSolution, report: ScheduleValidationReport, filepath: str) -> None:
    """Exports full schedule and validation report to a plain text file."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("THE SCHEDULER - GENERATED SCHEDULE & VALIDATION REPORT\n")
        f.write("=" * 70 + "\n\n")

        for a_shift in solution.shifts:
            f.write(f"Shift: {a_shift.shift.name}\n")
            for slot in a_shift.slots:
                role = "Board" if slot.is_board else "Member"
                ph = " (Placeholder)" if slot.is_placeholder else ""
                maybe = " [MAYBE AVAILABILITY]" if slot.availability_used == "maybe" else ""
                f.write(f"  - {slot.name} [{role}]{ph}{maybe}\n")
            f.write("\n")

        f.write("=" * 70 + "\n")
        f.write("VALIDATION REPORT\n")
        f.write("=" * 70 + "\n")
        f.write(f"Hard constraints satisfied: {report.is_valid}\n")
        if report.hard_constraint_errors:
            f.write("Errors:\n")
            f.writelines(f"  ! {err}\n" for err in report.hard_constraint_errors)

        f.write(f"\nSoft-constraint violations ({len(report.soft_constraint_violations)}):\n")
        f.writelines(f"  * {viol}\n" for viol in report.soft_constraint_violations)

        f.write(f"\nRealized Friendships ({len(report.realized_friendships)}):\n")
        f.writelines(f"  * {f1} <-> {f2} in {s_name}\n" for s_name, f1, f2 in report.realized_friendships)

        f.write("\nWorkload Distribution:\n")
        f.writelines(f"  {name:25}: {count} shifts ({count:.1f}h)\n" for name, count in sorted(report.workload_summary.items(), key=lambda x: -x[1]))
