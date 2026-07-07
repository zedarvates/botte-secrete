"""
Cron job — Dashboard notification hooks.

Scheduled via:
    cronjob create --schedule "*/30 * * * *" --prompt "Run dashboard notification hook" --skills dashboard

Sends a summary to the origin chat every 30 minutes.
"""

from skills.dashboard.api import load_metrics
from skills.auto_memory.hook import memory_stats


def main():
    m = load_metrics()
    ms = memory_stats()

    summary = (
        f"📊 Botte Secrète Dashboard Update\n"
        f"Tests: {m.get('tests_passed', 0)} | "
        f"Lignes gagnées: {m.get('lines_saved', 0)} | "
        f"Avoidable: {m.get('avoidable_pct', 0):.1f}%\n"
        f"Mémoire: {ms.get('total_entries', 0)} entries stored\n"
        f"Run `python3 -m skills.dashboard.api` to view live."
    )
    print(summary)


if __name__ == "__main__":
    main()