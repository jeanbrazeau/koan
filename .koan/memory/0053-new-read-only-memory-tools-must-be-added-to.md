---
title: 'Role-curated MCP tool vocabularies in koan/lib/permissions.py: withhold tools
  that do not belong to a role'
type: procedure
created: '2026-04-18T14:36:10Z'
modified: '2026-04-27T08:56:52Z'
related:
- 0066-synthesis-expensive-memory-tools-scoped-to.md
---

This entry documents the role-curated tool-vocabulary pattern in koan's permission fence (`koan/lib/permissions.py`). On 2026-04-21, Leon confirmed the underlying philosophy: each role (orchestrator, scout, executor) gets a deliberately curated set of MCP tools that match its job, and tools that have nothing to do with a role are withheld to reduce the chance of the agent misbehaving by reaching for them. Concretely, an executor agent must not start synthesizing project history or making design decisions while it is supposed to be implementing -- so synthesis-heavy tools like `koan_reflect` stay orchestrator-only even though they are read-only. The fast-path frozensets `_UNIVERSAL_MEMORY_TOOLS` and `_UNIVERSAL_READ_TOOLS` in `koan/lib/permissions.py` are the implementation mechanism for tools that genuinely belong to every role: they branch in `check_permission()` before the orchestrator dispatch and before the role-specific `ROLE_PERMISSIONS` check, so a single allow-statement covers all roles without per-role enumeration. As of 2026-04-21, `_UNIVERSAL_MEMORY_TOOLS` contains `koan_memory_status` and `koan_search`; `_UNIVERSAL_READ_TOOLS` contains `koan_artifact_list` and `koan_artifact_view`. Adding a new tool requires deciding which roles need it: if every role needs it, add it to the appropriate `_UNIVERSAL_*_TOOLS` frozenset and register the MCP handler in `koan/web/mcp_endpoint.py`; otherwise enumerate it in the relevant role's entry in `ROLE_PERMISSIONS`. The duplication-across-roles alternative (universal-by-default for every read tool) was rejected because it would give roles tools they have no business calling.
