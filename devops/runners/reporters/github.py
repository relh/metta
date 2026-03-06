import os

from devops.runners.reporters.shared import CategorizedJobs, job_status
from devops.stable.function_checks._helpers.llm_eval_harness import LLM_EVAL_TRANSCRIPT_DIR


def report_gh_step_summary(jobs: CategorizedJobs, title: str):
    gh_path = os.environ.get("GITHUB_STEP_SUMMARY")

    if gh_path:
        all_jobs = jobs["failed"] + jobs["passed"] + jobs["skipped"]
        header = f"{len(jobs['passed'])} passed, {len(jobs['failed'])} failed, {len(jobs['skipped'])} skipped"

        md = [
            f"# {title}",
            "",
            f"**Result**: {'PASSED' if not jobs['failed'] else 'FAILED'}",
            f"**Jobs**: {header}",
            "",
            "| Job | Status | Duration |",
            "|-----|--------|----------|",
        ]
        for job in all_jobs:
            duration = f"{job.duration_s:.0f}s" if job.duration_s else "-"
            md.append(f"| {job.name} | {job_status(job)} | {duration} |")

        md.extend(_llm_eval_transcript_sections())

        with open(gh_path, "a") as f:
            f.write("\n".join(md))


def _llm_eval_transcript_sections() -> list[str]:
    if not LLM_EVAL_TRANSCRIPT_DIR.is_dir():
        return []
    transcript_files = sorted(LLM_EVAL_TRANSCRIPT_DIR.glob("*.md"))
    if not transcript_files:
        return []
    sections = ["", "", "## LLM Eval Transcripts", ""]
    for path in transcript_files:
        name = path.stem
        content = path.read_text().strip()
        sections.append(f"<details><summary>{name}</summary>")
        sections.append("")
        sections.append(content)
        sections.append("")
        sections.append("</details>")
        sections.append("")
    return sections
