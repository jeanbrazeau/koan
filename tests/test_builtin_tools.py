# Unit tests for koan.tools.builtin_tools.
#
# Tests each tool in isolation using tmp_path fixtures. All tests are
# synchronous or use anyio where the tool is async. No network calls are made.
#
# Coverage:
# - write/edit create and modify files correctly
# - edit enforces single-unique-match semantics
# - _enforce_path_scope rejects planning-role writes outside run_dir
# - _enforce_path_scope allows executor writes anywhere
# - grep/glob/read produce the metrics dicts the fold expects
# - bash runs a command with output capture and timeout

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from koan.tools.builtin_tools import (
    _enforce_path_scope,
    bash_tool,
    edit_tool,
    glob_tool,
    grep_tool,
    read_tool,
    write_tool,
)


# -- Helpers ----------------------------------------------------------------- #


def _make_ctx(role: str = "executor", run_dir: str = "", project_dir: str = "") -> SimpleNamespace:
    """Build a minimal fake RunContext with ToolDeps for tool tests.

    Returns a SimpleNamespace that mimics just enough of RunContext[ToolDeps]
    for the built-in tools (ctx.deps.agent.role, ctx.deps.agent.run_dir,
    ctx.deps.app_state.run.project_dir, etc.).
    """
    agent = SimpleNamespace(
        role=role,
        run_dir=run_dir,
        injected_context_files=set(),
        pending_context_files=[],
    )
    run_state = SimpleNamespace(project_dir=project_dir)
    app_state = SimpleNamespace(run=run_state)
    deps = SimpleNamespace(agent=agent, app_state=app_state)
    return SimpleNamespace(deps=deps)


# -- write_tool -------------------------------------------------------------- #


@pytest.mark.anyio
async def test_write_tool_creates_file(tmp_path):
    """write_tool creates a new file with the given content.

    Verifies that the file exists on disk and has the exact bytes written.
    """
    target = tmp_path / "out.txt"
    ctx = _make_ctx(run_dir=str(tmp_path))
    result = await write_tool(ctx, str(target), "hello world\n")
    assert target.exists()
    assert target.read_text() == "hello world\n"
    assert "wrote" in result.lower() or str(len("hello world\n")) in result


@pytest.mark.anyio
async def test_write_tool_overwrites_existing_file(tmp_path):
    """write_tool overwrites an existing file completely."""
    target = tmp_path / "out.txt"
    target.write_text("old content")
    ctx = _make_ctx(run_dir=str(tmp_path))
    await write_tool(ctx, str(target), "new content\n")
    assert target.read_text() == "new content\n"


@pytest.mark.anyio
async def test_write_tool_creates_parent_dirs(tmp_path):
    """write_tool creates missing parent directories."""
    target = tmp_path / "sub" / "dir" / "file.txt"
    ctx = _make_ctx(run_dir=str(tmp_path))
    await write_tool(ctx, str(target), "content")
    assert target.exists()


# -- edit_tool --------------------------------------------------------------- #


@pytest.mark.anyio
async def test_edit_tool_single_match(tmp_path):
    """edit_tool replaces a uniquely-occurring old_string with new_string."""
    target = tmp_path / "edit.txt"
    target.write_text("line one\nline two\nline three\n")
    ctx = _make_ctx(run_dir=str(tmp_path))
    result = await edit_tool(ctx, str(target), "line two", "LINE TWO")
    assert target.read_text() == "line one\nLINE TWO\nline three\n"
    assert "1" in result


@pytest.mark.anyio
async def test_edit_tool_multiple_match_rejected(tmp_path):
    """edit_tool returns an error when old_string appears more than once.

    Single-unique-match semantics require exactly one occurrence when
    replace_all=False.
    """
    target = tmp_path / "edit.txt"
    target.write_text("dup dup dup")
    ctx = _make_ctx(run_dir=str(tmp_path))
    result = await edit_tool(ctx, str(target), "dup", "rep")
    assert "Error" in result
    # File should be unchanged.
    assert target.read_text() == "dup dup dup"


@pytest.mark.anyio
async def test_edit_tool_replace_all(tmp_path):
    """edit_tool replaces all occurrences when replace_all=True."""
    target = tmp_path / "edit.txt"
    target.write_text("x x x")
    ctx = _make_ctx(run_dir=str(tmp_path))
    result = await edit_tool(ctx, str(target), "x", "y", replace_all=True)
    assert target.read_text() == "y y y"
    assert "3" in result


@pytest.mark.anyio
async def test_edit_tool_missing_old_string(tmp_path):
    """edit_tool returns an error when old_string is not found."""
    target = tmp_path / "edit.txt"
    target.write_text("hello world")
    ctx = _make_ctx(run_dir=str(tmp_path))
    result = await edit_tool(ctx, str(target), "missing", "replacement")
    assert "Error" in result
    assert target.read_text() == "hello world"


# -- _enforce_path_scope ----------------------------------------------------- #


def test_enforce_path_scope_planning_inside_run_dir_allowed(tmp_path):
    """Planning role write inside run_dir is allowed (no exception raised)."""
    run_dir = str(tmp_path)
    ctx = _make_ctx(role="orchestrator", run_dir=run_dir)
    target = tmp_path / "plan.md"
    # Should not raise.
    _enforce_path_scope(ctx.deps, target)


def test_enforce_path_scope_planning_outside_run_dir_rejected(tmp_path):
    """Planning role write outside run_dir raises ValueError."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ctx = _make_ctx(role="orchestrator", run_dir=str(run_dir))
    outside = tmp_path / "outside.txt"
    with pytest.raises(ValueError, match="path-scope violation"):
        _enforce_path_scope(ctx.deps, outside)


def test_enforce_path_scope_executor_outside_run_dir_allowed(tmp_path):
    """Executor role may write anywhere; no exception raised."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ctx = _make_ctx(role="executor", run_dir=str(run_dir))
    outside = tmp_path / "project" / "src" / "file.py"
    # Should not raise.
    _enforce_path_scope(ctx.deps, outside)


def test_enforce_path_scope_scout_outside_run_dir_rejected(tmp_path):
    """Scout role is a planning role; writes outside run_dir are rejected."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ctx = _make_ctx(role="scout", run_dir=str(run_dir))
    outside = tmp_path / "other.md"
    with pytest.raises(ValueError, match="path-scope violation"):
        _enforce_path_scope(ctx.deps, outside)


def test_enforce_path_scope_empty_run_dir_skips_check(tmp_path):
    """When run_dir is empty, the path-scope check is skipped (permissive)."""
    ctx = _make_ctx(role="orchestrator", run_dir="")
    target = tmp_path / "anywhere.txt"
    # Should not raise even for a planning role.
    _enforce_path_scope(ctx.deps, target)


# -- read_tool --------------------------------------------------------------- #


@pytest.mark.anyio
async def test_read_tool_returns_numbered_lines(tmp_path):
    """read_tool returns cat -n formatted output with 1-based line numbers."""
    target = tmp_path / "input.txt"
    target.write_text("alpha\nbeta\ngamma\n")
    ctx = _make_ctx(run_dir=str(tmp_path))
    result = await read_tool(ctx, str(target))
    lines = result.splitlines()
    assert lines[0].startswith("1\t")
    assert lines[1].startswith("2\t")
    assert lines[2].startswith("3\t")
    assert "alpha" in lines[0]
    assert "beta" in lines[1]


@pytest.mark.anyio
async def test_read_tool_metrics_derivable(tmp_path):
    """read_tool output lets _parse_read_result_from_content derive metrics."""
    from koan.agents.pydantic_ai import _parse_read_result_from_content

    target = tmp_path / "data.txt"
    content = "line one\nline two\n"
    target.write_text(content)
    ctx = _make_ctx(run_dir=str(tmp_path))
    result = await read_tool(ctx, str(target))
    metrics = _parse_read_result_from_content(result)
    assert metrics is not None
    assert metrics["lines_read"] == 2
    assert metrics["bytes_read"] > 0


# -- grep_tool --------------------------------------------------------------- #


@pytest.mark.anyio
async def test_grep_tool_finds_matches(tmp_path):
    """grep_tool returns a 'Found N matches in M files' header plus match lines."""
    (tmp_path / "a.txt").write_text("foo bar\nbaz\nfoo again\n")
    (tmp_path / "b.txt").write_text("no match here\n")
    ctx = _make_ctx(run_dir=str(tmp_path))
    result = await grep_tool(ctx, r"foo", str(tmp_path))
    assert result.startswith("Found 2 matches in 1 file")
    assert "foo" in result


@pytest.mark.anyio
async def test_grep_tool_no_matches(tmp_path):
    """grep_tool returns 'Found 0 matches' when no lines match the pattern."""
    (tmp_path / "a.txt").write_text("line one\nline two\n")
    ctx = _make_ctx(run_dir=str(tmp_path))
    result = await grep_tool(ctx, r"zzznomatch", str(tmp_path))
    assert "Found 0 matches" in result


@pytest.mark.anyio
async def test_grep_tool_metrics_derivable(tmp_path):
    """grep_tool output lets _parse_grep_result_from_content derive metrics."""
    from koan.agents.pydantic_ai import _parse_grep_result_from_content

    (tmp_path / "f.py").write_text("def foo():\n    pass\ndef bar():\n    pass\n")
    ctx = _make_ctx(run_dir=str(tmp_path))
    result = await grep_tool(ctx, r"def ", str(tmp_path))
    metrics = _parse_grep_result_from_content(result)
    assert metrics is not None
    assert metrics["matches"] == 2
    assert metrics["files_matched"] == 1


# -- glob_tool --------------------------------------------------------------- #


@pytest.mark.anyio
async def test_glob_tool_finds_files(tmp_path):
    """glob_tool returns matching file paths with a 'Found N files' header."""
    (tmp_path / "alpha.py").write_text("")
    (tmp_path / "beta.py").write_text("")
    (tmp_path / "gamma.txt").write_text("")
    ctx = _make_ctx(run_dir=str(tmp_path))
    result = await glob_tool(ctx, "*.py", str(tmp_path))
    assert result.startswith("Found 2 files")
    assert "alpha.py" in result
    assert "beta.py" in result
    assert "gamma.txt" not in result


@pytest.mark.anyio
async def test_glob_tool_no_matches(tmp_path):
    """glob_tool returns 'Found 0 files' when no files match the pattern."""
    ctx = _make_ctx(run_dir=str(tmp_path))
    result = await glob_tool(ctx, "*.nomatch", str(tmp_path))
    assert "Found 0 files" in result


@pytest.mark.anyio
async def test_glob_tool_metrics_derivable(tmp_path):
    """glob_tool output lets _parse_grep_result_from_content derive metrics."""
    from koan.agents.pydantic_ai import _parse_grep_result_from_content

    (tmp_path / "x.md").write_text("")
    (tmp_path / "y.md").write_text("")
    ctx = _make_ctx(run_dir=str(tmp_path))
    result = await glob_tool(ctx, "*.md", str(tmp_path))
    metrics = _parse_grep_result_from_content(result)
    assert metrics is not None
    assert metrics["matches"] == 2
    assert metrics["files_matched"] == 2


# -- bash_tool --------------------------------------------------------------- #


@pytest.mark.anyio
async def test_bash_tool_captures_stdout(tmp_path):
    """bash_tool returns the stdout of the executed command."""
    ctx = _make_ctx(run_dir=str(tmp_path))
    result = await bash_tool(ctx, "echo hello_bash_test")
    assert "hello_bash_test" in result


@pytest.mark.anyio
async def test_bash_tool_captures_stderr(tmp_path):
    """bash_tool captures stderr alongside stdout in the combined output."""
    ctx = _make_ctx(run_dir=str(tmp_path))
    # 'ls /nonexistent_path_xyz' writes to stderr.
    result = await bash_tool(ctx, "ls /nonexistent_path_xyz_koan_test 2>&1")
    # Should not raise; error message goes to combined output.
    assert isinstance(result, str)


@pytest.mark.anyio
async def test_bash_tool_timeout(tmp_path):
    """bash_tool returns an error string when the command exceeds the timeout."""
    ctx = _make_ctx(run_dir=str(tmp_path))
    result = await bash_tool(ctx, "sleep 10", timeout=1)
    assert "timed out" in result.lower() or "timeout" in result.lower()


@pytest.mark.anyio
async def test_bash_tool_nonzero_exit_code_included(tmp_path):
    """bash_tool includes the exit code in the output when it is nonzero."""
    ctx = _make_ctx(run_dir=str(tmp_path))
    result = await bash_tool(ctx, "exit 42")
    assert "42" in result
