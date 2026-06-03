# koan_yield removal guard (M5b).
#
# koan_yield was removed when the agent loop went in-process: a terminal-text
# turn (no tool calls) is the hand-back signal, so the explicit yield tool is
# gone. These tests assert it does not creep back into the tool registry, the
# permission tables, or the MCP handler surface.

from __future__ import annotations

import dataclasses


def test_koan_yield_absent_from_mcp_tool_registry():
    from koan.runners.base import KOAN_MCP_TOOLS
    assert "koan_yield" not in KOAN_MCP_TOOLS


def test_koan_yield_absent_from_role_permissions():
    from koan.lib.permissions import ROLE_PERMISSIONS
    for role, tools in ROLE_PERMISSIONS.items():
        assert "koan_yield" not in tools, f"koan_yield leaked into {role!r} permissions"


def test_koan_yield_absent_from_mcp_handlers():
    from koan.web.mcp_endpoint import Handlers
    field_names = {f.name for f in dataclasses.fields(Handlers)}
    assert "koan_yield" not in field_names


def test_koan_yield_not_always_allowed_for_orchestrator():
    # The always-allowed base tuple in the orchestrator fence must not include it.
    from koan.lib.permissions import check_permission
    result = check_permission(
        role="orchestrator", tool_name="koan_yield", current_phase="intake",
    )
    assert result["allowed"] is False
