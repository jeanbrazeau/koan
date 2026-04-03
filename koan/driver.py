# Driver -- coordinates the persistent orchestrator for an epic run.
# Simplified: spawns one long-lived orchestrator process for the entire run.

from __future__ import annotations

from typing import TYPE_CHECKING

from .artifacts import list_artifacts
from .epic_state import ensure_subagent_directory
from .events import build_artifact_diff
from .logger import get_logger
from .subagent import spawn_subagent

if TYPE_CHECKING:
    from .state import AppState

log = get_logger("driver")


# -- Artifact diff helper ------------------------------------------------------

def _push_artifact_diff(app_state: AppState) -> None:
    """Scan epic artifacts and emit per-file diff events against current projection."""
    if not app_state.epic_dir:
        return
    try:
        new_artifacts = list_artifacts(app_state.epic_dir)
    except Exception:
        return
    run = app_state.projection_store.projection.run
    if run is None:
        old = {}
    else:
        # build_artifact_diff expects dict[str, dict] with 'modified_at' and 'size' keys
        old = {path: {"path": info.path, "size": info.size, "modified_at": info.modified_at}
               for path, info in run.artifacts.items()}
    for event_type, payload in build_artifact_diff(old, new_artifacts):
        app_state.projection_store.push_event(event_type, payload)


# -- Main driver loop ---------------------------------------------------------

async def driver_main(app_state: AppState) -> None:
    """Wait for start event, then spawn the persistent orchestrator for the entire run."""
    log.info("Driver waiting for start event...")
    await app_state.start_event.wait()

    epic_dir = app_state.epic_dir
    if epic_dir is None:
        log.error("epic_dir is None after start event -- aborting")
        return

    app_state.phase = "intake"
    app_state.projection_store.push_event("phase_started", {"phase": "intake"})
    subagent_dir = await ensure_subagent_directory(epic_dir, "orchestrator")

    task = {
        "role": "orchestrator",
        "epic_dir": epic_dir,
        "subagent_dir": subagent_dir,
        "project_dir": app_state.project_dir,
        "task_description": app_state.task_description,
    }

    result = await spawn_subagent(task, app_state)

    # Orchestrator exited — workflow is over
    app_state.projection_store.push_event("workflow_completed", {
        "success": result.exit_code == 0,
        "phase": app_state.phase,
        "summary": f"Workflow ended in phase '{app_state.phase}'",
    })
