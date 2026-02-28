# Koan Pi Package

## Overview

Koan is an opinionated planning workflow extension for the pi coding agent. It constrains model behavior with deterministic phase orchestration, explicit tool boundaries, and durable file-backed state so planning sessions are repeatable and auditable.

## Architecture

The runtime is split into two modes from the same extension entrypoint:

- **Parent session mode** runs `/koan` commands and orchestrates the workflow.
- **Subagent mode** runs role/phase-specific workflows (architect, QR decomposer, reviewer, fix mode).

The parent controls progression through context capture, plan design, quality review, and iterative fixes. Subagents are isolated processes that communicate through persisted artifacts (`plan.json`, `context.json`, `qr-*.json`) and audit projections.

## Design Decisions

Key design choices that shape implementation:

- **Inversion of control**: TypeScript orchestration code drives agent behavior; models do not self-route workflow steps.
- **Tool-call-driven transitions**: step progression happens via `koan_complete_step` tool calls, not conversational chaining.
- **Default-deny permissions**: each phase explicitly allowlists tools; unknown tool/phase access is blocked.
- **Disk-backed mutations**: planning mutations are immediately persisted with atomic writes instead of deferred finalize steps.
- **Need-to-know prompts**: each subagent only receives the minimum context needed for its task.

## Invariants

The workflow depends on these invariants:

- Planning phases must block direct `edit`/`write` tools.
- Tool failures must throw errors (not return soft error payloads).
- Cross-reference integrity in the plan must validate before progression.
- MUST-severity QR failures remain blocking even as lower-severity checks de-escalate in later fix iterations.

## Boundaries

Current scope focuses on planning and QR orchestration. `/koan execute` is intentionally not implemented yet.
