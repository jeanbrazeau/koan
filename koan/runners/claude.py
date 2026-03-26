# ClaudeRunner -- builds claude CLI commands and parses stream-json JSONL.
# MCP injection via --mcp-config file written to the subagent directory.

from __future__ import annotations

import json
from pathlib import Path

from .base import RunnerDiagnostic, RunnerError, StreamEvent


class ClaudeRunner:
    name = "claude"

    def __init__(self, *, subagent_dir: str) -> None:
        self.subagent_dir = subagent_dir

    def build_command(self, boot_prompt: str, mcp_url: str, model: str | None) -> list[str]:
        config_dir = Path(self.subagent_dir)
        config_path = config_dir / "mcp-config.json"
        config_data = {"mcpServers": {"koan": {"type": "http", "url": mcp_url}}}

        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            tmp = config_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(config_data, indent=2) + "\n", "utf-8")
            tmp.rename(config_path)
        except OSError as e:
            raise RunnerError(RunnerDiagnostic(
                code="mcp_inject_failed",
                runner="claude",
                stage="build_command",
                message=f"Failed to write MCP config: {e}",
            )) from e

        cmd = [
            "claude", "-p", boot_prompt,
            "--output-format", "stream-json",
            "--mcp-config", str(config_path),
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

        if evt_type == "assistant":
            return self._parse_assistant(data)
        if evt_type == "result":
            evt = self._parse_result(data)
            return [evt] if evt is not None else []
        return []

    # -- Private helpers -------------------------------------------------------

    def _parse_assistant(self, data: dict) -> list[StreamEvent]:
        blocks = data.get("content")
        if not isinstance(blocks, list) or len(blocks) == 0:
            return []

        events: list[StreamEvent] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text":
                events.append(StreamEvent(type="token_delta", content=block.get("text", "")))
            elif block_type == "tool_use":
                events.append(StreamEvent(
                    type="tool_call",
                    tool_name=block.get("name"),
                    tool_args=block.get("input"),
                ))
            elif block_type == "thinking":
                events.append(StreamEvent(type="thinking", is_thinking=True))
        return events

    def _parse_result(self, data: dict) -> StreamEvent | None:
        subtype = data.get("subtype")
        if subtype == "success":
            return StreamEvent(type="turn_complete", content=data.get("result"))
        return StreamEvent(type="turn_complete")
