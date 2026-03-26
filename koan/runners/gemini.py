# GeminiRunner -- builds gemini CLI commands and parses stream-json JSONL.
# MCP injection via additive merge into .gemini/settings.json.

from __future__ import annotations

import json
from pathlib import Path

from .base import RunnerDiagnostic, RunnerError, StreamEvent


class GeminiRunner:
    name = "gemini"

    def __init__(self, *, subagent_dir: str) -> None:
        self.subagent_dir = subagent_dir

    def build_command(self, boot_prompt: str, mcp_url: str, model: str | None) -> list[str]:
        gemini_dir = Path(self.subagent_dir) / ".gemini"
        settings_path = gemini_dir / "settings.json"

        existing = self._load_existing(settings_path)
        self._merge_mcp(existing, mcp_url, settings_path)
        self._write_settings(existing, settings_path, gemini_dir)

        cmd = ["gemini", "--output-format", "stream-json", "-p", boot_prompt]
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

        if evt_type == "message":
            return [StreamEvent(type="token_delta", content=data.get("content", ""))]
        if evt_type == "tool_use":
            return [StreamEvent(
                type="tool_call",
                tool_name=data.get("name"),
                tool_args=data.get("input"),
            )]
        if evt_type == "result":
            return [StreamEvent(type="turn_complete")]
        return []

    # -- Private helpers -------------------------------------------------------

    def _load_existing(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text("utf-8"))
        except json.JSONDecodeError as e:
            raise RunnerError(RunnerDiagnostic(
                code="mcp_inject_failed",
                runner="gemini",
                stage="build_command",
                message=f"Existing .gemini/settings.json is not valid JSON: {e}",
            )) from e
        if not isinstance(raw, dict):
            raise RunnerError(RunnerDiagnostic(
                code="mcp_inject_failed",
                runner="gemini",
                stage="build_command",
                message=f"Expected top-level object in {path}, got {type(raw).__name__}",
                details={"actual_type": type(raw).__name__},
            ))
        return raw

    def _merge_mcp(self, existing: dict, mcp_url: str, path: Path) -> None:
        servers = existing.get("mcpServers", {})
        if not isinstance(servers, dict):
            raise RunnerError(RunnerDiagnostic(
                code="mcp_inject_failed",
                runner="gemini",
                stage="build_command",
                message=f"mcpServers in {path} is not an object, got {type(servers).__name__}",
                details={"actual_type": type(servers).__name__},
            ))
        if "koan" in servers:
            koan_entry = servers["koan"]
            if not isinstance(koan_entry, dict):
                raise RunnerError(RunnerDiagnostic(
                    code="mcp_inject_failed",
                    runner="gemini",
                    stage="build_command",
                    message=f"mcpServers.koan in {path} is not an object, got {type(koan_entry).__name__}",
                    details={"actual_type": type(koan_entry).__name__},
                ))
            current_url = koan_entry.get("httpUrl")
            if current_url != mcp_url:
                raise RunnerError(RunnerDiagnostic(
                    code="mcp_inject_failed",
                    runner="gemini",
                    stage="build_command",
                    message=f"Conflicting koan MCP entry in {path}: existing url={current_url}",
                    details={"existing_url": current_url, "requested_url": mcp_url},
                ))
        existing.setdefault("mcpServers", {})["koan"] = {"httpUrl": mcp_url}

    def _write_settings(self, data: dict, path: Path, gemini_dir: Path) -> None:
        try:
            gemini_dir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, indent=2) + "\n", "utf-8")
            tmp.rename(path)
        except OSError as e:
            raise RunnerError(RunnerDiagnostic(
                code="mcp_inject_failed",
                runner="gemini",
                stage="build_command",
                message=f"Failed to write .gemini/settings.json: {e}",
            )) from e
