# Shared type literals and constants for the koan orchestrator.
# Python port of src/planner/types.ts -- kept in sync manually.

from typing import Literal

EpicPhase = Literal[
    "intake",
    "brief-generation",
    "core-flows",
    "tech-plan",
    "ticket-breakdown",
    "cross-artifact-validation",
    "execution",
    "implementation-validation",
    "completed",
]

SubagentRole = Literal[
    "intake",
    "scout",
    "decomposer",
    "orchestrator",
    "planner",
    "executor",
    "brief-writer",
    "workflow-orchestrator",
    "ticket-breakdown",
    "cross-artifact-validator",
]

ModelTier = Literal["strong", "standard", "cheap"]

ALL_MODEL_TIERS: tuple[ModelTier, ...] = ("strong", "standard", "cheap")

ROLE_MODEL_TIER: dict[SubagentRole, ModelTier] = {
    "intake": "strong",
    "scout": "cheap",
    "decomposer": "strong",
    "brief-writer": "strong",
    "orchestrator": "strong",
    "planner": "strong",
    "executor": "standard",
    "workflow-orchestrator": "strong",
    "ticket-breakdown": "strong",
    "cross-artifact-validator": "strong",
}
