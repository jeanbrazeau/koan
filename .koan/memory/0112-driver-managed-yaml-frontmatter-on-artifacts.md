---
title: Driver-managed YAML frontmatter on artifacts (status / created / last_modified)
  + Draft / Approved / In-Progress / Final taxonomy + koan_artifact_write tool
type: decision
created: '2026-04-26T09:33:27Z'
modified: '2026-04-26T09:33:27Z'
related:
- 0100-artifact-design-doctrine-distinct-lifetimes.md
- 0101-intake-produces-briefmd-as-a-frozen-handoff.md
---

On 2026-04-25, Leon added driver-managed YAML frontmatter to the koan artifact persistence layer (`koan/artifacts.py`, `koan/web/mcp_endpoint.py`). The change: every artifact written to `~/.koan/runs/<id>/*.md` carries a YAML frontmatter preamble with three fields in fixed insertion order -- `status`, `created`, `last_modified`. Fields are driver-maintained and LLM-invisible: `koan_artifact_view` strips frontmatter via `split_frontmatter()` before returning body to the LLM; `list_artifacts()` exposes `status` per file via `read_artifact_status()` (4 KiB-bounded read). The status taxonomy is `STATUS_VALUES = ("Draft", "Approved", "In-Progress", "Final")` defined in `koan/artifacts.py`; first-write defaults to `In-Progress`; producers set `Final` explicitly for frozen artifacts (intake calls `koan_artifact_write(filename="brief.md", content=BODY, status="Final")`). A new MCP write tool `koan_artifact_write(filename, content, status?)` was added in `koan/web/mcp_endpoint.py` as a non-blocking sibling of the now-retired `koan_artifact_propose`; both shared the `write_artifact_atomic(target, body, status)` helper preserving `created` across rewrites. `koan_artifact_propose` was deleted entirely on 2026-04-26 once all production callers migrated to `koan_artifact_write`. PyYAML usage mirrors `koan/memory/writer.py` and `koan/memory/parser.py`: `yaml.safe_dump(meta, default_flow_style=False, sort_keys=False)` and `yaml.safe_load(text)`. Frontmatter format follows YAML 1.2 frontmatter convention (`---`-delimited block at file head); parseable by any standard markdown reader; malformed frontmatter falls back to `(None, original_text)` with logged warning. `docs/artifacts.md` codifies the lifetime taxonomy (frozen / additive-forward / disposable) and per-artifact lifecycle table.
