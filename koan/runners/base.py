# Runner protocol, StreamEvent, and RunnerDiagnostic.
# Defines the contract that all CLI runner adapters must satisfy.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol


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

    def build_command(self, boot_prompt: str, mcp_url: str, model: str | None) -> list[str]: ...

    def parse_stream_event(self, line: str) -> list[StreamEvent]: ...
