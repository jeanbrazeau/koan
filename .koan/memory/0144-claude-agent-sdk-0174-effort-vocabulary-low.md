---
title: 'claude-agent-sdk 0.1.74+ effort vocabulary: low / medium / high / xhigh /
  max are five distinct levels; xhigh is Opus-4.7-specific'
type: context
created: '2026-05-08T07:31:08Z'
modified: '2026-05-08T07:31:08Z'
related:
- 0055-opus-47-requires-thinking-display-summarized.md
- 0130-agent-abstraction-in-koanagents-replaces.md
---

This entry records a fact about the claude-agent-sdk Python package's effort field as it relates to koan's Claude Agent SDK integration (`koan/agents/claude.py:ClaudeSDKAgent`, `koan/types.py:ThinkingMode`). On 2026-05-08, during a koan plan workflow that reshaped Claude thinking-mode resolution, the SDK's release notes for 0.1.74 and the source of `claude_agent_sdk.types.ClaudeAgentOptions` in 0.1.76 were inspected. Through 0.1.72 the SDK accepted four effort levels (`low / medium / high / max`); 0.1.74 added `xhigh` as a distinct fifth level. The 0.1.74 release note describes `xhigh` as Opus-4.7-specific, with documented runtime fallback to `high` on other Claude models.

Consequence for koan: koan's `ThinkingMode` literal in `koan/types.py` carries all five levels plus `disabled`. The `xhigh -> max` aliasing that previously existed in `koan/agents/claude.py:_EFFORT_MAP` was deleted on 2026-05-08 because the SDK now treats `xhigh` and `max` as distinct, not aliases. Per-model `thinking_modes` advertised by `ClaudeSDKAgent.list_models` reflect actual SDK support: Opus advertises `xhigh` and `max`; Sonnet and Haiku do not. The koan resolver clamps explicitly via `_best_supported_thinking` rather than relying on the SDK's runtime fallback so the downgrade is deterministic and observable.

Future agents touching the Claude effort surface should consult the SDK's `ClaudeAgentOptions.effort` field in `claude_agent_sdk/types.py` for the current literal definition, and the release notes at https://github.com/anthropics/claude-agent-sdk-python/releases for additions or removals to the effort vocabulary. Treat `xhigh` and `max` as distinct levels with distinct semantics; do not collapse them in koan's ThinkingMode mapping.
