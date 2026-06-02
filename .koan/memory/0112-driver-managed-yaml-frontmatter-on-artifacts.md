---
title: 'Artifact persistence layer: created/last_modified frontmatter + koan_artifact_write
  tool (status taxonomy removed 2026-06-02)'
type: decision
created: '2026-04-26T09:33:27Z'
modified: '2026-06-02T14:08:26Z'
related:
- 0100-artifact-design-doctrine-distinct-lifetimes.md
- 0101-intake-produces-briefmd-as-a-frozen-handoff.md
---

The koan artifact persistence layer (`koan/artifacts.py`, `koan/web/mcp_endpoint.py`) stores phase-produced artifacts as markdown files under `~/.koan/runs/<id>/*.md`, each carrying a driver-managed YAML frontmatter preamble that is LLM-invisible: `koan_artifact_view` strips it via `split_frontmatter()` before returning the body, and the LLM never sees or writes frontmatter. Leon added the frontmatter layer on 2026-04-25 with three fields (`status`, `created`, `last_modified`). On 2026-06-02 Leon removed the `status` field entirely: `STATUS_VALUES = ("Draft", "Approved", "In-Progress", "Final")`, `read_artifact_status()`, and the `status` parameter of `write_artifact_atomic(target, body)` and `koan_artifact_write(filename, content)` are gone; frontmatter now carries only `created` and `last_modified`. Rationale: the status taxonomy was never read by any code path -- `api_artifacts_list` and `build_artifact_diff` key on path/size/mtime only, the projection fold never tracked it, and the orchestrator's conversation context already holds whatever lifecycle state matters. Leon chose status-only removal over making artifacts fully frontmatter-free: `created`/`last_modified` and the `split_frontmatter` / `dump_frontmatter` / `compose_artifact` helpers were kept, because "state" meant the orchestrator-set lifecycle marker, not the passive timestamps. Prompt prose that had used `status="Final"` / `status="In-Progress"` to signal 'frozen at exit' or 'reviewer may rewrite in place' was reworded to plain prose with no status field.
