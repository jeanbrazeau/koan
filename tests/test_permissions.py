# Unit tests for koan.lib.permissions -- exhaustive permission matrix coverage.

import pytest

from koan.lib.permissions import (
    PLANNING_ROLES,
    READ_TOOLS,
    ROLE_PERMISSIONS,
    STEP_1_BLOCKED_TOOLS,
    WRITE_TOOLS,
    check_permission,
)


ALL_ROLES = list(ROLE_PERMISSIONS.keys())

# Union of every tool name the permission system knows about.
ALL_KOAN_TOOLS: frozenset[str] = frozenset().union(
    *(perms for perms in ROLE_PERMISSIONS.values()),
    READ_TOOLS,
)


# -- Read tools always pass ----------------------------------------------------

class TestReadToolsAlwaysAllowed:
    def test_known_roles(self):
        for role in ALL_ROLES:
            for tool in READ_TOOLS:
                r = check_permission(role, tool)
                assert r["allowed"], f"{tool} should be allowed for {role}"

    def test_unknown_role(self):
        for tool in READ_TOOLS:
            r = check_permission("nonexistent-role", tool)
            assert r["allowed"], f"{tool} should be allowed even for unknown role"


# -- Unknown role blocks non-read tools ----------------------------------------

class TestUnknownRoleBlocked:
    def test_non_read_tool_denied(self):
        r = check_permission("nonexistent-role", "koan_complete_step")
        assert not r["allowed"]
        assert "Unknown role" in r["reason"]

    def test_write_denied(self):
        r = check_permission("nonexistent-role", "edit")
        assert not r["allowed"]


# -- Step 1 blocking ----------------------------------------------------------

class TestStep1Blocking:
    def setup_method(self):
        self.blocked = list(STEP_1_BLOCKED_TOOLS)

    def test_intake_step_1_allows(self):
        """Intake no longer blocks tools at step 1 (gather step uses all tools)."""
        for tool in self.blocked:
            r = check_permission("intake", tool, current_step=1)
            assert r["allowed"], f"intake step 1 should allow {tool}"

    def test_brief_writer_step_1_blocks(self):
        for tool in self.blocked:
            r = check_permission("brief-writer", tool, current_step=1)
            assert not r["allowed"], f"brief-writer step 1 should block {tool}"

    def test_brief_writer_step_2_allows(self):
        # Only check tools that brief-writer actually has in its role set.
        bw_allowed = ROLE_PERMISSIONS["brief-writer"]
        for tool in self.blocked:
            if tool not in bw_allowed:
                continue
            r = check_permission("brief-writer", tool, current_step=2)
            assert r["allowed"], f"brief-writer step 2 should allow {tool}"


# -- Exhaustive role x tool matrix ---------------------------------------------

def _build_matrix():
    """Generate (role, tool, expected_allowed) for every role x tool pair.

    Expected result: allowed iff the tool is in READ_TOOLS or in that role's
    ROLE_PERMISSIONS entry.  Step is set to 2 to avoid step-1 blocking.
    """
    cases = []
    for role in ALL_ROLES:
        allowed_set = ROLE_PERMISSIONS[role] | READ_TOOLS
        for tool in sorted(ALL_KOAN_TOOLS):
            expected = tool in allowed_set
            cases.append((role, tool, expected))
    return cases


_MATRIX = _build_matrix()
_MATRIX_IDS = [f"{role}-{tool}-{'allow' if exp else 'deny'}" for role, tool, exp in _MATRIX]


class TestExhaustiveRoleToolMatrix:
    """Mechanically verify every role x tool combination against ROLE_PERMISSIONS."""

    @pytest.mark.parametrize("role,tool,expected", _MATRIX, ids=_MATRIX_IDS)
    def test_role_tool(self, role, tool, expected):
        r = check_permission(role, tool, current_step=2)
        assert r["allowed"] == expected, (
            f"role={role} tool={tool}: expected allowed={expected}, got {r}"
        )


# -- Exhaustive step-1 matrix -------------------------------------------------

def _build_step1_matrix():
    """For brief-writer at step 1, verify blocked tools are denied
    and all other allowed tools still pass.  Intake no longer has a
    step-1 gate so its step-1 expectations match normal permissions."""
    cases = []
    for role in ("intake", "brief-writer"):
        allowed_set = ROLE_PERMISSIONS[role] | READ_TOOLS
        for tool in sorted(ALL_KOAN_TOOLS):
            # Only brief-writer blocks tools at step 1; intake does not.
            if role == "brief-writer" and tool in STEP_1_BLOCKED_TOOLS:
                expected = False
            elif tool in allowed_set:
                expected = True
            else:
                expected = False
            cases.append((role, tool, expected))
    return cases


_STEP1_MATRIX = _build_step1_matrix()
_STEP1_IDS = [f"{role}-step1-{tool}-{'allow' if exp else 'deny'}" for role, tool, exp in _STEP1_MATRIX]


class TestExhaustiveStep1Matrix:
    """Verify step-1 blocking interacts correctly with every tool for affected roles."""

    @pytest.mark.parametrize("role,tool,expected", _STEP1_MATRIX, ids=_STEP1_IDS)
    def test_step1(self, role, tool, expected):
        r = check_permission(role, tool, current_step=1)
        assert r["allowed"] == expected, (
            f"role={role} step=1 tool={tool}: expected allowed={expected}, got {r}"
        )


# -- Path scoping --------------------------------------------------------------

class TestPathScoping:
    def setup_method(self):
        self.epic = "/tmp/epic"

    def test_write_inside_epic_allowed(self):
        r = check_permission(
            "intake", "write",
            epic_dir=self.epic,
            tool_args={"path": "/tmp/epic/foo.md"},
            current_step=2,
        )
        assert r["allowed"]

    def test_write_outside_epic_denied(self):
        r = check_permission(
            "intake", "write",
            epic_dir=self.epic,
            tool_args={"path": "/home/user/evil.sh"},
            current_step=2,
        )
        assert not r["allowed"]
        assert "outside epic directory" in r["reason"]

    def test_edit_outside_epic_denied(self):
        r = check_permission(
            "planner", "edit",
            epic_dir=self.epic,
            tool_args={"path": "/etc/passwd"},
            current_step=2,
        )
        assert not r["allowed"]

    def test_write_at_epic_root_allowed(self):
        r = check_permission(
            "intake", "write",
            epic_dir=self.epic,
            tool_args={"path": "/tmp/epic"},
            current_step=2,
        )
        assert r["allowed"]


# -- Executor unrestricted write -----------------------------------------------

class TestExecutorUnrestricted:
    def test_write_outside_epic_allowed(self):
        r = check_permission(
            "executor", "write",
            epic_dir="/tmp/epic",
            tool_args={"path": "/home/user/code.py"},
            current_step=2,
        )
        assert r["allowed"]


# -- No epic_dir / no path arg ------------------------------------------------

class TestNoEpicDirNoPathArg:
    def test_no_epic_dir_allows_write(self):
        r = check_permission("intake", "write", current_step=2)
        assert r["allowed"]

    def test_no_path_arg_allows_write(self):
        r = check_permission(
            "intake", "write",
            epic_dir="/tmp/epic",
            tool_args={"content": "hello"},
            current_step=2,
        )
        assert r["allowed"]

    def test_no_tool_args_allows_write(self):
        r = check_permission(
            "intake", "write",
            epic_dir="/tmp/epic",
            current_step=2,
        )
        assert r["allowed"]
