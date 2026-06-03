# Unit tests for ToolPolicy and compose_toolset.
#
# Verifies that compose_toolset produces the correct per-(role, phase) tool
# set for representative cases, and that it agrees with check_permission for
# a cross-checked sample -- keeping the two in sync until M9 deletes
# check_permission.

from __future__ import annotations

import pytest

from koan.tools.tool_policy import build_tool_policy, compose_toolset
from koan.lib.permissions import (
    _ORCHESTRATOR_STORY_TOOLS,
    _ORCHESTRATOR_SCOUT_PHASES,
    _UNIVERSAL_MEMORY_TOOLS,
    _UNIVERSAL_READ_TOOLS,
    _NON_BASH_READ_TOOLS,
    check_permission,
)

# -- Shared constants for assertions ------------------------------------------

# Tools that must always be present regardless of role or phase.
_ALWAYS_PRESENT = _UNIVERSAL_MEMORY_TOOLS | _UNIVERSAL_READ_TOOLS | _NON_BASH_READ_TOOLS


# -- Fixtures -----------------------------------------------------------------

@pytest.fixture(scope="module")
def policy():
    """Build the ToolPolicy once for the whole module; it is stateless."""
    return build_tool_policy()


# -- Helper -------------------------------------------------------------------

def _compose(policy, role, phase):
    """Thin wrapper so tests read more like assertions than calls."""
    return compose_toolset(policy, role, phase)


# -- Tests: orchestrator in a planning phase ----------------------------------

class TestOrchestratorPlanningPhase:
    """Orchestrator in a planning phase (e.g. plan-spec).

    Scouts are allowed; story tools are NOT; bash is NOT; executor tool is NOT.
    """

    PHASE = "plan-spec"  # a member of _ORCHESTRATOR_SCOUT_PHASES

    def test_universals_present(self, policy):
        """Universal memory and read-only artifact tools must always appear."""
        toolset = _compose(policy, "orchestrator", self.PHASE)
        assert _ALWAYS_PRESENT <= toolset, (
            f"Expected {_ALWAYS_PRESENT!r} to be a subset of {toolset!r}"
        )

    def test_scouts_allowed(self, policy):
        """koan_request_scouts is allowed in planning phases."""
        assert self.PHASE in _ORCHESTRATOR_SCOUT_PHASES, (
            f"{self.PHASE!r} must be in scout phases for this test to be meaningful"
        )
        toolset = _compose(policy, "orchestrator", self.PHASE)
        assert "koan_request_scouts" in toolset

    def test_story_tools_absent(self, policy):
        """Story management tools are not available outside execution."""
        toolset = _compose(policy, "orchestrator", self.PHASE)
        for tool in _ORCHESTRATOR_STORY_TOOLS:
            assert tool not in toolset, f"{tool!r} must not be in {self.PHASE!r} toolset"

    def test_bash_absent(self, policy):
        """Bash is phase-gated for orchestrator; not available in plan-spec."""
        toolset = _compose(policy, "orchestrator", self.PHASE)
        assert "bash" not in toolset

    def test_executor_tool_absent(self, policy):
        """koan_request_executor is not available in planning phases."""
        toolset = _compose(policy, "orchestrator", self.PHASE)
        assert "koan_request_executor" not in toolset

    def test_step_machine_tools_present(self, policy):
        """koan_complete_step and koan_set_phase must always be present."""
        toolset = _compose(policy, "orchestrator", self.PHASE)
        assert "koan_complete_step" in toolset
        assert "koan_set_phase" in toolset

    def test_memory_tools_present(self, policy):
        """Orchestrator-specific memory tools (memorize, forget, reflect) present."""
        toolset = _compose(policy, "orchestrator", self.PHASE)
        for tool in ("koan_memorize", "koan_forget", "koan_reflect"):
            assert tool in toolset, f"{tool!r} must be in orchestrator toolset"


# -- Tests: orchestrator in execution phase -----------------------------------

class TestOrchestratorExecutionPhase:
    """Orchestrator in the legacy 'execution' phase.

    Story tools and bash ARE allowed; scouts are NOT (not in scout_phases).
    """

    PHASE = "execution"

    def test_universals_present(self, policy):
        """Universal memory and read-only artifact tools must always appear."""
        toolset = _compose(policy, "orchestrator", self.PHASE)
        assert _ALWAYS_PRESENT <= toolset

    def test_story_tools_present(self, policy):
        """All four story management tools are available during execution."""
        toolset = _compose(policy, "orchestrator", self.PHASE)
        for tool in _ORCHESTRATOR_STORY_TOOLS:
            assert tool in toolset, f"{tool!r} must be in execution toolset"

    def test_bash_present(self, policy):
        """Bash is allowed for the orchestrator during the execution phase."""
        toolset = _compose(policy, "orchestrator", self.PHASE)
        assert "bash" in toolset

    def test_scouts_absent(self, policy):
        """koan_request_scouts is NOT available in the execution phase."""
        assert self.PHASE not in _ORCHESTRATOR_SCOUT_PHASES, (
            "'execution' must not be in scout phases for this test to be meaningful"
        )
        toolset = _compose(policy, "orchestrator", self.PHASE)
        assert "koan_request_scouts" not in toolset

    def test_executor_tool_present(self, policy):
        """koan_request_executor is available in the execution phase."""
        toolset = _compose(policy, "orchestrator", self.PHASE)
        assert "koan_request_executor" in toolset


# -- Tests: executor role -----------------------------------------------------

class TestExecutorRole:
    """Executor role.

    Has bash unconditionally; has koan_complete_step; no orchestrator tools.
    """

    PHASE = "execute"

    def test_universals_present(self, policy):
        """Universal memory and read-only artifact tools always present."""
        toolset = _compose(policy, "executor", self.PHASE)
        assert _ALWAYS_PRESENT <= toolset

    def test_bash_present(self, policy):
        """Non-orchestrator roles always have bash regardless of phase."""
        toolset = _compose(policy, "executor", self.PHASE)
        assert "bash" in toolset

    def test_koan_complete_step_present(self, policy):
        """Executors need koan_complete_step to advance through their steps."""
        toolset = _compose(policy, "executor", self.PHASE)
        assert "koan_complete_step" in toolset

    def test_no_orchestrator_story_tools(self, policy):
        """Story management tools are orchestrator-only."""
        toolset = _compose(policy, "executor", self.PHASE)
        for tool in _ORCHESTRATOR_STORY_TOOLS:
            assert tool not in toolset

    def test_no_orchestrator_set_phase(self, policy):
        """koan_set_phase is orchestrator-only."""
        toolset = _compose(policy, "executor", self.PHASE)
        assert "koan_set_phase" not in toolset

    def test_write_edit_present(self, policy):
        """Executors have write and edit (unrestricted file access)."""
        toolset = _compose(policy, "executor", self.PHASE)
        assert "write" in toolset
        assert "edit" in toolset


# -- Tests: scout role --------------------------------------------------------

class TestScoutRole:
    """Scout role.

    Minimal tool set: koan_complete_step plus read tools and universals.
    """

    PHASE = "plan-spec"

    def test_universals_present(self, policy):
        """Universal memory and read-only artifact tools always present."""
        toolset = _compose(policy, "scout", self.PHASE)
        assert _ALWAYS_PRESENT <= toolset

    def test_koan_complete_step_present(self, policy):
        """Scouts need koan_complete_step."""
        toolset = _compose(policy, "scout", self.PHASE)
        assert "koan_complete_step" in toolset

    def test_bash_present(self, policy):
        """Non-orchestrator roles always have bash."""
        toolset = _compose(policy, "scout", self.PHASE)
        assert "bash" in toolset

    def test_no_write_edit(self, policy):
        """Scouts must not have write or edit (read-only role)."""
        toolset = _compose(policy, "scout", self.PHASE)
        assert "write" not in toolset
        assert "edit" not in toolset

    def test_no_orchestrator_tools(self, policy):
        """Scouts do not have orchestrator-specific tools."""
        toolset = _compose(policy, "scout", self.PHASE)
        assert "koan_set_phase" not in toolset
        assert "koan_reflect" not in toolset


# -- Cross-check: compose_toolset vs check_permission -------------------------

# Sample triples (role, phase, tool) whose allow/deny must agree between
# compose_toolset and check_permission. This keeps the two in sync until M9.
# check_permission uses (role, tool_name, current_phase) keyword arguments.
_CROSS_CHECK_SAMPLES: list[tuple[str, str, str, bool]] = [
    # (role, phase, tool, expected_allowed)
    # Orchestrator universals -- always allowed in any phase.
    ("orchestrator", "plan-spec",   "koan_memory_status",   True),
    ("orchestrator", "plan-spec",   "koan_search",          True),
    ("orchestrator", "plan-spec",   "koan_artifact_list",   True),
    ("orchestrator", "plan-spec",   "koan_artifact_view",   True),
    # Orchestrator phase-conditional tools.
    ("orchestrator", "plan-spec",   "koan_request_scouts",  True),
    ("orchestrator", "execution",   "koan_request_scouts",  False),
    ("orchestrator", "execution",   "koan_select_story",    True),
    ("orchestrator", "plan-spec",   "koan_select_story",    False),
    ("orchestrator", "execution",   "bash",                 True),
    ("orchestrator", "plan-spec",   "bash",                 False),
    # Executor.
    ("executor",     "execute",     "koan_complete_step",   True),
    ("executor",     "execute",     "bash",                 True),
    ("executor",     "execute",     "koan_set_phase",       False),
    # Scout.
    ("scout",        "plan-spec",   "koan_complete_step",   True),
    ("scout",        "plan-spec",   "koan_set_phase",       False),
    ("scout",        "plan-spec",   "koan_reflect",         False),
    # Non-bash read tools: always allowed for all roles.
    ("scout",        "plan-spec",   "read",                 True),
    ("orchestrator", "execution",   "glob",                 True),
]


class TestCrossCheckWithCheckPermission:
    """compose_toolset and check_permission must agree on allow/deny for every sample.

    This asserts that the two gate implementations stay in sync. If they
    diverge, either compose_toolset has a bug or the permissions table
    changed without updating the policy.
    """

    @pytest.mark.parametrize("role,phase,tool,expected", _CROSS_CHECK_SAMPLES)
    def test_agree(self, policy, role, phase, tool, expected):
        """Both gates must return the same decision for (role, phase, tool)."""
        toolset = compose_toolset(policy, role, phase)
        compose_says = tool in toolset
        perm_says = check_permission(
            role=role, tool_name=tool, current_phase=phase
        )["allowed"]

        assert compose_says == expected, (
            f"compose_toolset({role!r}, {phase!r}) -> {tool!r} in set = {compose_says}, "
            f"expected {expected}"
        )
        assert perm_says == expected, (
            f"check_permission(role={role!r}, tool={tool!r}, phase={phase!r}) = {perm_says}, "
            f"expected {expected}"
        )
        # Belt-and-suspenders: both implementations agree with each other.
        assert compose_says == perm_says, (
            f"compose_toolset and check_permission disagree on "
            f"(role={role!r}, phase={phase!r}, tool={tool!r}): "
            f"compose={compose_says}, check_permission={perm_says}"
        )
