from pathlib import Path

from devops.runners.reporters.shared import CategorizedJobs


def print_failed_logs(jobs: CategorizedJobs, tail_lines: int = 50) -> None:
    if not jobs["failed"]:
        return None

    print("\n" + "=" * 60)
    print("Failed Job Logs")
    print("=" * 60)
    for job in jobs["failed"]:
        print(f"\n--- {job.name} ---")
        if job.acceptance_failures:
            print("Acceptance criteria failures:")
            for failure in job.acceptance_failures:
                print(f"  - {failure}")
            print()
        if job.logs_path and Path(job.logs_path).exists():
            lines = Path(job.logs_path).read_text().splitlines()
            for line in lines[-tail_lines:]:
                print(line)
        elif job.error:
            print(job.error)
        else:
            print("(no logs available)")
