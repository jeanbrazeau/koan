---
title: Behavioral constraints require both a prompt instruction and a mechanical gate
type: decision
created: '2026-04-16T09:00:52Z'
modified: '2026-04-16T09:00:52Z'
related:
- 0009-permission-fence-impractical-across-llm-backends.md
---

The koan orchestration system uses `koan/web/mcp_endpoint.py` and `koan/lib/permissions.py` to enforce behavioral constraints for subagent roles. On 2026-04-16, the architecture documentation in `docs/architecture.md` established that behavioral constraints require both a prompt instruction and a mechanical gate. The maintainer recorded the rationale: prompt instructions alone were found insufficient because LLMs can ignore them without error; mechanical gates alone were found insufficient because they produce cryptic "blocked" tool errors with no context for the model to self-correct and retry. The document identified three enforcement mechanisms: (1) the permission fence (`check_permission` in `koan/lib/permissions.py`), which blocks disallowed tool calls and returns a rejection message; (2) `validate_step_completion()`, which blocks `koan_complete_step` advancement until required pre-calls have been made; and (3) tool descriptions, which provide soft guidance only and cannot be enforced. The maintainer established the rule that any constraint mattering for correctness requires both a prompt instruction (so the LLM understands the requirement) and a mechanical gate (so non-compliance is caught and corrected rather than silently propagated).
