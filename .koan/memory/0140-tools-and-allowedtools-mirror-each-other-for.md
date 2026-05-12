---
title: tools and allowed_tools mirror each other for Claude built-in tools; narrow
  allowedTools causes the orchestrator to over-prefer the explicit allow
type: decision
created: '2026-05-05T06:23:29Z'
modified: '2026-05-05T06:23:29Z'
related:
- 0056-permission-mode-acceptedits-auto-approves-a-fixed-bash.md
- 0130-agent-abstraction-in-koanagents-replaces.md
---

This entry documents the per-role Claude built-in tool curation in koan (`koan/subagent.py:CLAUDE_TOOL_WHITELISTS`, `koan/subagent.py:_build_claude_tool_lists`, `koan/agents/claude.py` consumer at `ClaudeAgentOptions(tools=..., allowed_tools=...)`). On 2026-05-05, user directed the design that the same per-role list of canonical Claude built-in tool names is used for both `AgentOptions.available_tools` (passed as the SDK's `tools` field, controlling the visible vocabulary) and `AgentOptions.allowed_tools` (passed as `allowed_tools`, controlling auto-approval); the MCP-namespace pattern `mcp__koan__*` is appended to `allowed_tools` only because it is not a built-in tool name. User's stated rationale: koan has no `can_use_tool` callback, so distinguishing "visible" from "auto-allowed" has no operational meaning, and maintaining different sets is mere overhead.

The motivating observation came from a live run on 2026-05-05: the orchestrator (Claude Sonnet) was using `Bash cat` / `Bash rg` for file inspection rather than calling `Read` / `Glob` / `Grep` directly. Investigation traced this to the prior post-SDK-migration setup where `available_tools` carried the full role whitelist (Read, Write, Edit, Bash, Glob, Grep, WebFetch, WebSearch for orchestrator) but `allowed_tools` was hardcoded to `["mcp__koan__*", "Bash"]`. Even though `Read` / `Glob` / `Grep` are documented as "Permission Required: No" in the Claude Code tools reference and need no auto-approval, the model treated the narrow `allowedTools` set as an authoritative signal of which tools were sanctioned, gravitating to the explicit allow (`Bash`) and avoiding the rest. Mirroring the lists collapses the ambiguity.

Alternatives rejected: (a) keep the disjoint sets and only fix the per-role `tools` whitelist -- rejected because it would not address the Bash-dominance bias; (b) switch to the SDK's `claude_code` preset for `tools` -- rejected because the curation discipline (each role only sees what it needs) is more important than vocabulary completeness; (c) introduce a `can_use_tool` callback and gate per-invocation -- rejected because koan has no per-invocation policy that needs enforcement at this layer; the koan MCP permission fence in `koan/lib/permissions.py` is the separate authority for koan-tool gating per phase. Companion decisions made in the same run: `Agent` (Claude's subagent-spawn tool) is denied for all roles because koan owns subagent spawning via `koan_request_scouts` / `koan_request_executor`; `permission_mode="acceptEdits"` is preserved unchanged because it continues to auto-approve the safe Bash subset (`mkdir`, `touch`, `rm`, `rmdir`, `mv`, `cp`, `sed`) inside `--add-dir` scope.
