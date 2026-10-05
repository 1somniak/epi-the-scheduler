#!/usr/bin/env python3
"""Main entry point for The Scheduler CLI."""

import argparse
import os
import sys

from scheduler.loader import DataLoader
from scheduler.models import SchedulerConfig
from scheduler.normalizer import IdentityResolver
from scheduler.optimizer import ScheduleOptimizer
from scheduler.reporter import ScheduleReporter, export_report_txt, export_schedule_csv
from scheduler.validator import validate_solution


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="The Scheduler: Generates an optimal work schedule from availability, board members, and friendships.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Input CSV files
    parser.add_argument(
        "-d", "--dispo",
        default="assets/dispo.csv",
        help="Path to availability CSV file",
    )
    parser.add_argument(
        "-b", "--bureau",
        default="assets/bureau.csv",
        help="Path to board members CSV file",
    )
    parser.add_argument(
        "-f", "--friends",
        default="assets/friends.csv",
        help="Path to friendships CSV file",
    )

    # Output options
    parser.add_argument(
        "-o", "--output",
        help="Path to output CSV file for the generated schedule",
    )
    parser.add_argument(
        "--export-txt",
        help="Path to export full schedule and report as a text file",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate input CSV files without generating a schedule",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output from solver and loader",
    )

    # Configurable optimization parameters (Section 9, 10, 15 of AGENTS.md)
    parser.add_argument(
        "--shift-size",
        type=int,
        default=4,
        help="Number of people per shift",
    )
    parser.add_argument(
        "--max-consec-hours",
        type=float,
        default=2.0,
        help="Maximum continuous hours of staffing preferred per person",
    )
    parser.add_argument(
        "--w-maybe",
        type=float,
        default=100.0,
        help="Penalty weight for using 'maybe' availability",
    )
    parser.add_argument(
        "--w-consecutive",
        type=float,
        default=500.0,
        help="Penalty weight for exceeding maximum consecutive hours",
    )
    parser.add_argument(
        "--w-split",
        type=float,
        default=300.0,
        help="Penalty weight for non-contiguous staffing (split shifts)",
    )
    parser.add_argument(
        "--w-first-last-board",
        type=float,
        default=50.0,
        help="Penalty weight for fewer than 2 board members on first/last shift",
    )
    parser.add_argument(
        "--w-friendship",
        type=float,
        default=30.0,
        help="Bonus weight for assigning friends to the same shift",
    )
    parser.add_argument(
        "--w-balance-dev",
        type=float,
        default=10.0,
        help="Weight for workload balance deviation penalty",
    )
    parser.add_argument(
        "--w-balance-max",
        type=float,
        default=20.0,
        help="Weight for maximum individual workload penalty",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reporter = ScheduleReporter()

    # 1. Initialize Name Resolver & Data Loader
    resolver = IdentityResolver()
    loader = DataLoader(resolver=resolver)

    # Check file existence with clear warnings if default assets not in cwd
    for path, name in [(args.bureau, "Board"), (args.dispo, "Availability"), (args.friends, "Friendships")]:
        if not os.path.exists(path):
            print(f"Error: {name} file not found at '{path}'.", file=sys.stderr)
            return 1

    # 2. Load inputs in order: Board members -> Availability -> Friendships
    loader.load_board(args.bureau)
    shifts, people = loader.load_availability(args.dispo)
    friendships = loader.load_friendships(args.friends)

    # 3. Report input validation findings
    reporter.print_input_validation(loader.report)

    if not loader.report.is_valid:
        print("Input validation failed with critical errors. Aborting schedule generation.", file=sys.stderr)
        return 1

    if args.validate_only:
        print("Input validation completed successfully.")
        return 0

    if not shifts:
        print("Error: No shifts to schedule.", file=sys.stderr)
        return 1

    # 4. Build configuration
    config = SchedulerConfig(
        shift_size=args.shift_size,
        max_consecutive_hours=args.max_consec_hours,
        weight_maybe=args.w_maybe,
        weight_consecutive=args.w_consecutive,
        weight_split_shift=args.w_split,
        weight_first_last_board=args.w_first_last_board,
        weight_friendship=args.w_friendship,
        weight_balance_dev=args.w_balance_dev,
        weight_balance_max=args.w_balance_max,
    )

    # 5. Optimize Schedule
    optimizer = ScheduleOptimizer(
        shifts=shifts,
        people=people,
        friendships=friendships,
        config=config,
        verbose=args.verbose,
    )
    solution = optimizer.solve()

    # 6. Validate Solution
    val_report = validate_solution(solution)

    # 7. Print Schedule & Reports
    reporter.print_schedule(solution, val_report)

    # 8. Export files if requested
    if args.output:
        export_schedule_csv(solution, args.output)
        print(f"Schedule exported to CSV: '{args.output}'")

    if args.export_txt:
        export_report_txt(solution, val_report, args.export_txt)
        print(f"Full report exported to TXT: '{args.export_txt}'")

    return 0 if val_report.is_valid else 2


if __name__ == "__main__":
    sys.exit(main())
