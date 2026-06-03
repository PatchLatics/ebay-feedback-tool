#!/usr/bin/env python3
"""
eBay Feedback Tool — CLI entry point.

Runs inside your real Brave browser profile so eBay sees a trusted session.
Close Brave before running.

Usage:
    python main.py            # Submit feedback for all pending items
    python main.py --dry-run  # Preview messages without submitting
    python main.py --headed   # Keep the Brave window visible while running
"""

import argparse
import os
import sys

from rich.console import Console
from rich.table import Table
from rich import box

from ebay_feedback import run, RunSummary

console = Console()


def _print_summary(summary: RunSummary, dry_run: bool) -> None:
    console.print()

    if dry_run:
        console.print(
            f"[bold yellow]Dry run complete.[/bold yellow] "
            f"{summary.total} item(s) found — nothing was submitted."
        )
        return

    if summary.total == 0:
        console.print("[bold green]Nothing to do.[/bold green] No pending feedback items found.")
        return

    colour = "green" if summary.failed == 0 else "yellow"
    console.print(
        f"[bold {colour}]Done.[/bold {colour}] "
        f"[green]{summary.succeeded} succeeded[/green]  "
        f"[red]{summary.failed} failed[/red]  "
        f"(of {summary.total} total)"
    )

    if not summary.results:
        return

    table = Table(box=box.SIMPLE_HEAD, show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Item", no_wrap=False)
    table.add_column("Status", width=8)
    table.add_column("Detail")

    for i, r in enumerate(summary.results, 1):
        if r.success:
            status = "[green]✓ OK[/green]"
            detail = f'[dim]"{r.message}"[/dim]'
        else:
            status = "[red]✗ ERR[/red]"
            detail = f"[red]{r.error}[/red]"
        table.add_row(str(i), r.title or r.item_id, status, detail)

    console.print(table)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automatically leave positive eBay feedback for all pending orders."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be posted without actually submitting anything.",
    )
    parser.add_argument(
        "--headed", action="store_true",
        help="Show the browser window while running.",
    )
    args = parser.parse_args()

    headless_env = os.getenv("HEADLESS", "true").lower() not in ("false", "0", "no")
    headless = False if args.headed else headless_env

    console.rule("[bold blue]eBay Feedback Tool[/bold blue]")

    if args.dry_run:
        console.print("[yellow]Dry-run mode — no feedback will actually be submitted.[/yellow]")

    console.print()

    try:
        summary = run(headless=headless, dry_run=args.dry_run)
    except (FileNotFoundError, RuntimeError) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(1)

    _print_summary(summary, args.dry_run)

    sys.exit(0 if summary.failed == 0 else 1)


if __name__ == "__main__":
    main()
