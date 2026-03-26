# CodexRunner -- builds codex CLI commands and parses --json JSONL.
# MCP injection via -c flag override (no file I/O needed).

from __future__ import annotations

import json

from .base import StreamEvent


class CodexRunner:
    name = "codex"

    def build_command(self, boot_prompt: str, mcp_url: str, model: str | None) -> list[str]:
        cmd = [
            "codex", "exec", "--json",
            "-c", f"mcp_servers.koan.url={mcp_url}",
            boot_prompt,
        ]
        if model is not None:
            cmd.extend(["--model", model])
        return cmd

    def parse_stream_event(self, line: str) -> list[StreamEvent]:
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return []

        if not isinstance(data, dict):
            return []

        evt_type = data.get("type")

        if evt_type == "turn.started":
            return [StreamEvent(type="thinking", is_thinking=True)]
        if evt_type == "turn.completed":
            return [StreamEvent(type="turn_complete", is_thinking=True, content=data.get("answer"))]
        if evt_type == "turn.failed":
            return [StreamEvent(type="turn_complete", is_thinking=True)]
        return []
