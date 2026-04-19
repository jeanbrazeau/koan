# evals/dataset.py
# Loads benchmark fixtures as an Inspect AI MemoryDataset.
#
# Cases are enumerated by discover_cases, which walks
# fixtures/<f>/tasks/<t>/cases/*.md. Each case file defines one Sample
# whose id is "<fixture>/<task>/<case>". Directories without a task.md
# or without a cases/ subdir are skipped silently.

from pathlib import Path

from inspect_ai.dataset import MemoryDataset, Sample

from evals.cases import discover_cases


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_dataset(fixtures_dir: Path = FIXTURES_DIR) -> MemoryDataset:
    """Return an Inspect AI MemoryDataset from all discovered case files."""
    samples = []
    for case in discover_cases(fixtures_dir):
        task_file = case.task_dir / "task.md"
        samples.append(Sample(
            input=task_file.read_text(encoding="utf-8").strip(),
            id=f"{case.fixture_id}/{case.task_id}/{case.case_id}",
            metadata={
                "fixture_dir": str(case.fixture_dir),
                "task_dir": str(case.task_dir),
                "snapshot_path": str(case.fixture_dir / "snapshot.tar.gz"),
                "fixture_name": case.fixture_id,
                "task_name": case.task_id,
                "case_name": case.case_id,
                "case_path": str(case.case_path),
                "workflow": case.workflow,
                "directed_phases": list(case.directed_phases),
                "overall_rubric": case.rubric_body,
            },
        ))
    return MemoryDataset(samples, name="koan-bench")
