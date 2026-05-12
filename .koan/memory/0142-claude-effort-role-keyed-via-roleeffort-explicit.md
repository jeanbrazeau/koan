---
title: Claude effort role-keyed via ROLE_EFFORT; explicit clamping in resolve_agent_config
  over SDK silent fallback
type: decision
created: '2026-05-08T07:30:46Z'
modified: '2026-05-08T07:30:46Z'
related:
- 0008-three-tier-model-system-strongstandardcheap-over.md
- 0130-agent-abstraction-in-koanagents-replaces.md
---

The Claude thinking/effort resolution path in koan (`koan/agents/registry.py:resolve_agent_config`, `koan/agents/registry.py:_claude_clamp`, `koan/agents/claude.py:list_models`, `koan/types.py:ROLE_EFFORT`) was redesigned on 2026-05-08 to decouple Claude effort from `ProfileTier.thinking` and to clamp explicitly in the koan layer rather than relying on the SDK's runtime fallback. User directed the redesign with the brief: "devise an elegant way to always maximize the thinking visibility. Ideally not hard-coded mappings of model-to-parameters."

The new resolution: a module-level constant `ROLE_EFFORT: dict[SubagentRole, ThinkingMode]` in `koan/types.py` keys effort to the agent's role -- `orchestrator -> max`, `executor -> medium`, `scout -> medium`, with `intake` and `planner` mapped to `max` defensively as legacy roles. The user explicitly noted that a future `reviewer` role should also map to `max`. `resolve_agent_config` branches on `runner_type`: for claude it reads `ROLE_EFFORT[role]` (subscript, not `.get`, so KeyError fires fast for unmapped roles) and clamps via the new private `_claude_clamp` helper; for gemini and codex it returns `profile_tier.thinking` unchanged. `_claude_clamp` lazy-imports `ClaudeSDKAgent`, calls `list_models(installation)` to get per-model `thinking_modes`, and delegates to `_best_supported_thinking`; an INFO log line `(role, model, requested, clamped)` is emitted whenever an actual clamp happens.

Per-model `thinking_modes` in `ClaudeSDKAgent.list_models` were tightened to reflect actual SDK support: Opus advertises `{disabled, low, medium, high, xhigh, max}`; Sonnet and Haiku advertise `{disabled, low, medium, high}`. The same change set the SDK call to always pass `thinking={"type": "adaptive", "display": "summarized"}` for non-disabled effort to maximize thinking-text visibility on Opus 4.7+, whose default `display` is `omitted`.

Alternatives rejected during the run: (a) advertise the full vocabulary uniformly and let the SDK fall back silently from `xhigh`/`max` to `high` on non-Opus models -- rejected during plan-review because the brief required deterministic, observable clamping ("prefer clamping to silent downgrade") and uniform advertising would let the Settings UI offer modes the model would not actually use; (b) profile-tier-keyed effort (the pre-redesign shape) -- rejected because cognitive role and model-strength tier are orthogonal; (c) a per-profile role->effort map -- rejected because role-effort is a project-wide invariant; (d) renaming `xhigh` to `max` (the brief's original wording) -- rejected after user confirmed during plan-spec that the SDK 0.1.74+ vocabulary distinguishes the two levels.
