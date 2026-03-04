from __future__ import annotations

from pathlib import Path

from metta.trainingboard.models import ResearchPaperRecord


def load_normalized_records(cache_path: Path) -> list[ResearchPaperRecord]:
    if not cache_path.is_file():
        return []

    records: list[ResearchPaperRecord] = []
    with cache_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            records.append(ResearchPaperRecord.model_validate_json(line))
    return records


def write_normalized_records(cache_path: Path, records: list[ResearchPaperRecord]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(record.model_dump_json())
            handle.write("\n")
