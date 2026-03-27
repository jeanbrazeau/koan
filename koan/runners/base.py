# Runner protocol, StreamEvent, and RunnerDiagnostic.
# Defines the contract that all CLI runner adapters must satisfy.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from ..types import AgentInstallation, ModelInfo, ThinkingMode


@dataclass(kw_only=True)
class StreamEvent:
    type: Literal["token_delta", "turn_complete", "tool_call", "thinking"]
    content: str | None = None
    is_thinking: bool = False
    tool_name: str | None = None
    tool_args: dict | None = None


@dataclass(kw_only=True)
class RunnerDiagnostic:
    code: str
    runner: str
    stage: str
    message: str
    details: dict | None = None


class RunnerError(RuntimeError):
    def __init__(self, diagnostic: RunnerDiagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


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
    ) -> list[str]: ...

    def list_models(self, binary: str) -> list[ModelInfo]: ...

    def parse_stream_event(self, line: str) -> list[StreamEvent]: ...
