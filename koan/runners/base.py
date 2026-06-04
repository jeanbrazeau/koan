# Runner protocol (CLI-runner contract) -- deleted with the CLI runners in M9.
#
# StreamEvent and KOAN_MCP_TOOLS were relocated to koan/agents/events.py (M9:
# they outlive this module). They are re-exported here so existing importers
# keep working until the rip-out points them at the new home.

from __future__ import annotations

from typing import Protocol

from ..agents.events import KOAN_MCP_TOOLS, StreamEvent  # noqa: F401  (re-export)
from ..types import AgentInstallation, ModelInfo, ThinkingMode


class Runner(Protocol):
    name: str
    supported_thinking_modes: frozenset[ThinkingMode]

    def build_command(
        self,
        boot_prompt: str,
        mcp_url: str,
        installation: AgentInstallation,
        model: str,
        thinking: ThinkingMode,
        system_prompt: str = "",
    ) -> list[str]: ...

    def list_models(self, binary: str) -> list[ModelInfo]: ...

    def parse_stream_event(self, line: str) -> list[StreamEvent]: ...
