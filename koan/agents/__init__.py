# Public API for koan.agents -- the Agent abstraction (Protocol) and the
# PydanticAI in-process implementation.
#
# M4: ClaudeSDKAgent and CommandLineAgent removed -- the CLI/SDK agent path is
# deleted. The only implementation is PydanticAIAgent (koan/agents/pydantic_ai.py).

from .base import Agent, AgentDiagnostic, AgentError, AgentOptions
from .registry import AgentRegistry, compute_balanced_profile, compute_builtin_profiles

__all__ = [
    "Agent",
    "AgentDiagnostic",
    "AgentError",
    "AgentOptions",
    "AgentRegistry",
    "compute_balanced_profile",
    "compute_builtin_profiles",
]
