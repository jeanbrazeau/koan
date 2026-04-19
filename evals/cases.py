# evals/cases.py
# Case file parsing and discovery.
#
# A case file is a markdown file with YAML frontmatter that declares a
# workflow and a directed phase sequence. The body below the closing ---
# is the cross-cutting rubric used by the workflow_overall scorer.
#
# Case files live at fixtures/<f>/tasks/<t>/cases/<slug>.md and are
# discovered at module import time by tasks.py.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Case:
    fixture_id: str           # e.g. "koan-1"
    task_id: str              # e.g. "yolo-flag"
    case_id: str              # e.g. "full" (filename stem)
    fixture_dir: Path
    task_dir: Path
    case_path: Path           # the .md file itself
    workflow: str             # from frontmatter, e.g. "plan"
    directed_phases: list[str]  # from frontmatter, must end with "done"
    rubric_body: str          # body below the closing ---, used as overall rubric


def parse_case_file(case_path: Path) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_str).

    Reads case_path, splits on lines that equal exactly '---', and
    parses the frontmatter block with yaml.safe_load. Raises
    ValueError with a path-prefixed message if the file does not
    start with '---', has no closing '---', or yields non-dict YAML.
    """
    text = case_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    # Strip trailing newline from the separator check so "---\n" == "---".
    def _is_sep(line: str) -> bool:
        return line.rstrip("\n\r") == "---"

    if not lines or not _is_sep(lines[0]):
        raise ValueError(f"{case_path}: must start with '---'")

    # Find the closing separator starting from line index 1.
    close_idx = None
    for i in range(1, len(lines)):
        if _is_sep(lines[i]):
            close_idx = i
            break

    if close_idx is None:
        raise ValueError(f"{case_path}: no closing '---' found")

    fm_text = "".join(lines[1:close_idx])
    body_text = "".join(lines[close_idx + 1:]).lstrip("\n")

    fm = yaml.safe_load(fm_text)
    if not isinstance(fm, dict):
        raise ValueError(
            f"{case_path}: YAML frontmatter must be a mapping, got {type(fm).__name__}"
        )

    return fm, body_text


def load_case(
    fixture_dir: Path,
    task_dir: Path,
    case_path: Path,
) -> Case:
    """Parse case_path and validate required frontmatter fields.

    Required keys: 'workflow' (str) and 'directed_phases' (list of str,
    last element 'done'). Raises ValueError on missing/invalid fields,
    with the case_path included in the error message for debugging.
    """
    fm, body = parse_case_file(case_path)

    workflow = fm.get("workflow")
    if not isinstance(workflow, str) or not workflow:
        raise ValueError(f"{case_path}: 'workflow' must be a non-empty string")

    directed_phases = fm.get("directed_phases")
    if not isinstance(directed_phases, list) or not directed_phases:
        raise ValueError(f"{case_path}: 'directed_phases' must be a non-empty list")
    if not all(isinstance(p, str) for p in directed_phases):
        raise ValueError(f"{case_path}: 'directed_phases' entries must all be strings")
    if directed_phases[-1] != "done":
        raise ValueError(
            f"{case_path}: 'directed_phases' must end with 'done',"
            f" got '{directed_phases[-1]}'"
        )

    return Case(
        fixture_id=fixture_dir.name,
        task_id=task_dir.name,
        case_id=case_path.stem,
        fixture_dir=fixture_dir,
        task_dir=task_dir,
        case_path=case_path,
        workflow=workflow,
        directed_phases=directed_phases,
        rubric_body=body,
    )


def discover_cases(fixtures_dir: Path) -> list[Case]:
    """Walk fixtures/<f>/tasks/<t>/cases/*.md and return all Cases.

    Skips directories without a tasks subdir, tasks without a task.md,
    and tasks without a cases subdir. Returns cases sorted by
    (fixture_id, task_id, case_id) for deterministic ordering.
    """
    cases = []
    for fixture_dir in sorted(fixtures_dir.iterdir()):
        if not fixture_dir.is_dir():
            continue
        tasks_dir = fixture_dir / "tasks"
        if not tasks_dir.is_dir():
            continue
        for task_dir in sorted(tasks_dir.iterdir()):
            if not task_dir.is_dir():
                continue
            task_file = task_dir / "task.md"
            if not task_file.exists():
                continue
            cases_dir = task_dir / "cases"
            if not cases_dir.is_dir():
                continue
            for case_path in sorted(cases_dir.glob("*.md")):
                cases.append(load_case(fixture_dir, task_dir, case_path))

    return sorted(cases, key=lambda c: (c.fixture_id, c.task_id, c.case_id))
