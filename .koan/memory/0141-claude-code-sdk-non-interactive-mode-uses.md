---
title: Claude Code SDK / non-interactive mode uses TodoWrite; TaskCreate/TaskUpdate/TaskList/TaskGet/TaskStop/TaskOutput
  are interactive-only
type: context
created: '2026-05-05T06:23:34Z'
modified: '2026-05-05T06:23:34Z'
related:
- 0130-agent-abstraction-in-koanagents-replaces.md
---

This entry records a fact about the Claude Code built-in tool catalog as it relates to koan's Claude Agent SDK integration (`koan/agents/claude.py:ClaudeSDKAgent`, `koan/subagent.py:CLAUDE_TOOL_WHITELISTS`). On 2026-05-05, while curating the per-role Claude tool whitelists, the canonical Claude Code tools-reference at https://code.claude.com/docs/en/tools-reference was consulted. The reference documents two task-tracking surfaces: `TodoWrite` ("Manages the session task checklist. Available in non-interactive mode and the Agent SDK; interactive sessions use TaskCreate, TaskGet, TaskList, and TaskUpdate instead.") and the interactive `Task*` family (`TaskCreate`, `TaskGet`, `TaskList`, `TaskUpdate`, `TaskStop`, `TaskOutput`). Koan runs Claude through the Agent SDK in non-interactive mode (`claude_agent_sdk.ClaudeSDKClient` driven by `ClaudeSDKAgent`), so `TodoWrite` is the only meaningful task-tracking tool in koan's setup; the `Task*` family is unavailable regardless of whether it is listed in the `tools` whitelist.

Consequence for koan: prior to 2026-05-05 the executor's whitelist string in `CLAUDE_TOOL_WHITELISTS` carried `TaskCreate,TaskUpdate,TaskList,TaskGet,TaskStop,TaskOutput` as dead entries -- they were exposed to the model but never callable, surviving from a pre-SDK-migration era. The 2026-05-05 curation removed them. User chose not to add `TodoWrite` either; the koan loop already structures executor work via story-level plans and the SDK-internal todo list duplicates that bookkeeping. A second class confusion to be aware of: Claude's subagent-spawn tool is named `Agent`, not `Task` -- the `Task*` names refer to the task-list family, not to subagent spawning. Future agents touching the Claude built-in tool surface should consult the canonical tools-reference URL above rather than relying on tool-name intuition.
