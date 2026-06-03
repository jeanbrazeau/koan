# In-process built-in tool implementations.
#
# Provides read/write/edit/glob/grep/bash as a PydanticAI FunctionToolset.
# Output formats mirror koan/agents/claude.py's parser spec so the metrics
# parser in spawn_subagent's fan-out works unchanged.
#
# read  -- line-numbered cat -n output: "{number}\t{line}"
#          -> _parse_read_result: {lines_read, bytes_read}
# grep  -- "Found N matches in M files" header + match lines
#          -> _parse_grep_result: {matches, files_matched}
# glob  -- "Found N files" header + one path per line
#          -> _parse_grep_result (fallback): {matches, files_matched}
# write/edit/bash: metrics=None (no parse target in the fold)
#
# Path-scope: write and edit self-validate the resolved path against the
# calling role and run_dir. Planning roles (intake/orchestrator/planner/scout)
# are confined to run_dir; the executor role may write anywhere in the project
# tree. This mirrors koan/lib/permissions.py's path-scope logic but lives
# tool-internally -- a central gate cannot express argument-level constraints.
#
# Context-file injection: path-bearing tools (read/write/edit/glob/grep)
# record their resolved paths into deps.agent.pending_context_files via
# _record_path_for_context_injection. Bash is exempt (no single path arg).
#
# write/edit/glob/grep/bash complete the built-in toolset (M4).
# web_search/web_fetch land in M7 (per-provider native-or-local strategy).

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .koan_tools import ToolDeps


# Planning roles are confined to run_dir for write/edit operations.
# Mirrors PLANNING_ROLES in koan/lib/permissions.py; defined here to avoid
# importing the permissions module (scheduled for M9 deletion).
_PLANNING_ROLES: frozenset[str] = frozenset({
    "intake",
    "orchestrator",
    "planner",
    "scout",
})


# -- Path helpers ------------------------------------------------------------- #


def _resolve_path(file_path: str, deps: Any) -> Path:
    """Resolve file_path to an absolute Path using the agent's run_dir as base.

    Relative paths are anchored to run_dir (when available) so agents that
    receive relative paths from the model still resolve to the correct location.
    """
    p = Path(file_path)
    if p.is_absolute():
        return p
    run_dir = getattr(getattr(deps, "agent", None), "run_dir", None)
    if run_dir:
        return Path(run_dir) / file_path
    return Path.cwd() / file_path


def _enforce_path_scope(deps: Any, resolved_path: Path) -> None:
    """Raise ValueError when a planning role writes outside run_dir.

    Planning roles (intake/orchestrator/planner/scout) may only write inside
    run_dir; the executor role may write anywhere. When run_dir is empty, the
    check is skipped (permissive degradation -- run_dir is set in all real runs).

    Args:
        deps: ToolDeps carrying AgentState (deps.agent.role, deps.agent.run_dir).
        resolved_path: The absolute Path that would be written.
    """
    role = getattr(getattr(deps, "agent", None), "role", "")
    if role not in _PLANNING_ROLES:
        return
    run_dir = getattr(getattr(deps, "agent", None), "run_dir", None)
    if not run_dir:
        return
    resolved = resolved_path.resolve()
    resolved_run = Path(run_dir).resolve()
    try:
        resolved.relative_to(resolved_run)
    except ValueError:
        raise ValueError(
            f"path-scope violation: role={role!r} may only write inside"
            f" run_dir={run_dir!r}, got {str(resolved_path)!r}"
        )


def _record_path_for_context_injection(deps: Any, resolved_path: Path) -> None:
    """Queue any new context files found on the path up to project_root.

    Calls walk_for_context_files and appends the results (deduped) to
    deps.agent.pending_context_files so the history processor injects them
    before the next model request.

    Skips silently when project_root or the agent state is unavailable.

    Args:
        deps: ToolDeps with app_state and agent.
        resolved_path: Absolute Path just accessed by a file tool.
    """
    from .context_files import walk_for_context_files

    agent = getattr(deps, "agent", None)
    if agent is None:
        return
    project_root = getattr(getattr(deps, "app_state", None), "run", None)
    project_root = getattr(project_root, "project_dir", "") if project_root else ""
    if not project_root:
        return

    new_files = walk_for_context_files(
        str(resolved_path),
        project_root,
        agent.injected_context_files,
    )
    pending = set(agent.pending_context_files)
    for f in new_files:
        if f not in pending and f not in agent.injected_context_files:
            agent.pending_context_files.append(f)
            pending.add(f)


# -- cat -n format helper ----------------------------------------------------- #


def _cat_n_format(content: str, offset: int) -> str:
    """Format file content as cat -n output: line-numbered with tab separator.

    Produces the exact format that koan/agents/claude.py:_parse_read_result
    expects to derive {lines_read, bytes_read} metrics. Line numbers are
    1-based and include the offset so callers requesting a slice see correct
    absolute line numbers in the output.
    """
    lines = content.splitlines(keepends=True)
    parts = []
    for i, line in enumerate(lines, start=offset + 1):
        # Strip trailing newline for the numbered format; the line body is then
        # appended without a trailing newline because the join adds "\n" later.
        parts.append(f"{i}\t{line.rstrip(chr(10))}")
    return "\n".join(parts)


# -- Tool implementations ----------------------------------------------------- #


async def read_tool(
    ctx: Any,
    file_path: str,
    offset: int = 0,
    limit: int = 2000,
) -> str:
    """Read a file and return its contents in line-numbered cat -n format.

    Honoring offset and limit mirrors the built-in Read tool the Claude SDK
    provided. The output format ({line_number}\\t{line_content}) is what
    _parse_read_result in koan/agents/claude.py expects for computing
    {lines_read, bytes_read} metrics.

    Path resolution is relative to run_dir when available. After reading,
    the resolved path is recorded for just-in-time context-file injection.

    Args:
        ctx: PydanticAI RunContext with ToolDeps as deps.
        file_path: Absolute or relative path to read.
        offset: 0-based line offset to start reading from (default 0).
        limit: Maximum number of lines to return (default 2000).
    """
    deps = getattr(ctx, "deps", None)
    resolved = _resolve_path(file_path, deps)

    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"Error reading {file_path}: {e}"

    lines = content.splitlines(keepends=True)
    slice_ = lines[offset: offset + limit]
    sliced_content = "".join(slice_)

    # Record for context-file injection after a successful read.
    if deps is not None:
        _record_path_for_context_injection(deps, resolved)

    return _cat_n_format(sliced_content, offset)


async def write_tool(ctx: Any, file_path: str, content: str) -> str:
    """Create or overwrite a file with the given content.

    Enforces path-scope: planning roles (intake/orchestrator/planner/scout)
    may only write inside run_dir; executors may write the full project tree.
    After writing, the resolved path is recorded for context-file injection.

    Args:
        ctx: PydanticAI RunContext with ToolDeps as deps.
        file_path: Absolute or relative path to create/overwrite.
        content: Full content to write to the file.
    """
    deps = getattr(ctx, "deps", None)
    resolved = _resolve_path(file_path, deps)

    if deps is not None:
        _enforce_path_scope(deps, resolved)

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
    except OSError as e:
        return f"Error writing {file_path}: {e}"

    if deps is not None:
        _record_path_for_context_injection(deps, resolved)

    return f"Wrote {len(content)} bytes to {file_path}"


async def edit_tool(
    ctx: Any,
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> str:
    """Edit a file by replacing an exact string match.

    Single-unique-match semantics by default: raises an error when old_string
    has zero occurrences or more than one occurrence (unless replace_all=True).
    Enforces path-scope for planning roles.
    After editing, the resolved path is recorded for context-file injection.

    Args:
        ctx: PydanticAI RunContext with ToolDeps as deps.
        file_path: Absolute or relative path to edit.
        old_string: The exact string to replace (must appear exactly once when
                    replace_all=False).
        new_string: The replacement string (may be different content or empty).
        replace_all: When True, replace every occurrence; skip uniqueness check.
    """
    deps = getattr(ctx, "deps", None)
    resolved = _resolve_path(file_path, deps)

    if deps is not None:
        _enforce_path_scope(deps, resolved)

    try:
        existing = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"Error reading {file_path}: {e}"

    count = existing.count(old_string)
    if count == 0:
        return f"Error: old_string not found in {file_path}"
    if not replace_all and count > 1:
        return (
            f"Error: old_string appears {count} times in {file_path}; "
            f"use replace_all=True to replace all occurrences, or provide "
            f"more context to make the match unique"
        )

    updated = existing.replace(old_string, new_string) if replace_all else existing.replace(old_string, new_string, 1)

    try:
        resolved.write_text(updated, encoding="utf-8")
    except OSError as e:
        return f"Error writing {file_path}: {e}"

    replaced_count = count if replace_all else 1
    if deps is not None:
        _record_path_for_context_injection(deps, resolved)

    return f"Replaced {replaced_count} occurrence(s) of old_string in {file_path}"


async def glob_tool(ctx: Any, pattern: str, path: str | None = None) -> str:
    """Find files matching a glob pattern.

    Returns a "Found N files" header followed by one matching path per line.
    The header format lets _parse_grep_result in koan/agents/claude.py derive
    {matches, files_matched} metrics -- glob matches are file-per-match since
    each path IS the match. After listing, the search root is recorded for
    context-file injection.

    Args:
        ctx: PydanticAI RunContext with ToolDeps as deps.
        pattern: Glob pattern to match, e.g. "**/*.py".
        path: Optional directory to search in (defaults to run_dir or cwd).
    """
    deps = getattr(ctx, "deps", None)
    if path is not None:
        search_root = _resolve_path(path, deps)
    else:
        run_dir = getattr(getattr(deps, "agent", None), "run_dir", None) if deps else None
        search_root = Path(run_dir) if run_dir else Path.cwd()

    try:
        matches = sorted(str(p) for p in search_root.glob(pattern))
    except Exception as e:
        return f"Error running glob {pattern!r} in {search_root}: {e}"

    n = len(matches)
    # Format: "Found N files" header that _parse_grep_result recognises.
    # Each file is its own match, so files_matched == matches.
    header = f"Found {n} files"
    if n == 0:
        result = header
    else:
        result = header + "\n" + "\n".join(matches)

    if deps is not None:
        _record_path_for_context_injection(deps, search_root)

    return result


async def grep_tool(
    ctx: Any,
    pattern: str,
    path: str | None = None,
    glob: str | None = None,
) -> str:
    """Search file contents for a regex pattern.

    Emits a "Found N matches in M files" header followed by matching lines in
    "file:line_number:content" format. The header is what _parse_grep_result in
    koan/agents/claude.py expects to derive {matches, files_matched} metrics.

    Args:
        ctx: PydanticAI RunContext with ToolDeps as deps.
        pattern: Regular-expression pattern to search for.
        path: Directory or file to search in (defaults to run_dir or cwd).
        glob: Optional glob pattern to filter which files are searched.
    """
    deps = getattr(ctx, "deps", None)
    if path is not None:
        search_root = _resolve_path(path, deps)
    else:
        run_dir = getattr(getattr(deps, "agent", None), "run_dir", None) if deps else None
        search_root = Path(run_dir) if run_dir else Path.cwd()

    # Collect candidate files.
    if search_root.is_file():
        candidates = [search_root]
    else:
        file_glob = glob if glob else "**/*"
        try:
            candidates = [
                p for p in search_root.glob(file_glob)
                if p.is_file()
            ]
        except Exception as e:
            return f"Error finding files for grep in {search_root}: {e}"

    # Search each file.
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        return f"Error: invalid pattern {pattern!r}: {e}"

    match_lines: list[str] = []
    files_with_matches: set[str] = set()

    for candidate in sorted(candidates):
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if compiled.search(line):
                match_lines.append(f"{candidate}:{lineno}:{line}")
                files_with_matches.add(str(candidate))

    n_matches = len(match_lines)
    n_files = len(files_with_matches)
    header = f"Found {n_matches} matches in {n_files} files"

    if n_matches == 0:
        result = header
    else:
        result = header + "\n" + "\n".join(match_lines)

    if deps is not None:
        _record_path_for_context_injection(deps, search_root)

    return result


async def bash_tool(
    ctx: Any,
    command: str,
    timeout: int | None = None,
) -> str:
    """Execute a shell command and return stdout + stderr combined.

    No sandbox is applied -- keep the current permission posture. Bash is
    exempt from context-file injection (no single canonical path argument).

    Args:
        ctx: PydanticAI RunContext with ToolDeps as deps.
        command: Shell command to execute.
        timeout: Optional timeout in seconds (default None = no limit).
    """
    deps = getattr(ctx, "deps", None)
    run_dir = getattr(getattr(deps, "agent", None), "run_dir", None) if deps else None
    cwd = run_dir or None

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        combined = result.stdout
        if result.stderr:
            combined = combined + result.stderr if combined else result.stderr
        if result.returncode != 0:
            combined = f"Exit code: {result.returncode}\n{combined}"
        return combined if combined else ""
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s: {command}"
    except Exception as e:
        return f"Error running command: {e}"


# -- Toolset builder ---------------------------------------------------------- #


def build_builtin_toolset() -> Any:
    """Build the built-in FunctionToolset with all M4 tools registered.

    Registers read, write, edit, glob, grep, bash. web_search and web_fetch
    are deferred to M7 (per-provider native-or-local strategy).

    Each tool is wrapped in a thin inner function without a RunContext type
    annotation: 'from __future__ import annotations' makes annotations
    into strings, which pydantic_ai's schema generation cannot resolve for
    RunContext[...]. Omitting the annotation lets pydantic_ai detect the
    context parameter via takes_ctx=True.

    Returns a FunctionToolset[ToolDeps] with all built-in tools registered
    under their canonical lowercase names so KOAN_MCP_TOOLS and the
    spawn_subagent fan-out recognise them.
    """
    from pydantic_ai.toolsets.function import FunctionToolset

    ts: FunctionToolset[Any] = FunctionToolset()

    # -- read ------------------------------------------------------------------
    async def _read(ctx, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        """Read a file and return contents with line numbers for precise editing."""
        return await read_tool(ctx, file_path, offset, limit)

    ts.add_function(
        _read,
        takes_ctx=True,
        name="read",
        description=(
            "Read a file from the local filesystem. Returns line-numbered content "
            "in cat -n format ({line_number}\\t{content}). "
            "Use offset and limit to read large files in pages."
        ),
    )

    # -- write -----------------------------------------------------------------
    async def _write(ctx, file_path: str, content: str) -> str:
        """Create or overwrite a file with the given content."""
        return await write_tool(ctx, file_path, content)

    ts.add_function(
        _write,
        takes_ctx=True,
        name="write",
        description=(
            "Create or overwrite a file with the given content. "
            "Planning roles (orchestrator/scout/planner/intake) are confined to run_dir; "
            "the executor role may write anywhere in the project tree."
        ),
    )

    # -- edit ------------------------------------------------------------------
    async def _edit(
        ctx,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> str:
        """Edit a file by replacing an exact string match (single-unique-match by default)."""
        return await edit_tool(ctx, file_path, old_string, new_string, replace_all)

    ts.add_function(
        _edit,
        takes_ctx=True,
        name="edit",
        description=(
            "Edit a file by replacing old_string with new_string. "
            "By default enforces single-unique-match semantics: old_string must appear "
            "exactly once. Use replace_all=True to replace every occurrence."
        ),
    )

    # -- glob ------------------------------------------------------------------
    async def _glob(ctx, pattern: str, path: str | None = None) -> str:
        """Find files matching a glob pattern in a directory."""
        return await glob_tool(ctx, pattern, path)

    ts.add_function(
        _glob,
        takes_ctx=True,
        name="glob",
        description=(
            "Find files matching a glob pattern (e.g. '**/*.py'). "
            "Returns a summary header and the list of matching paths."
        ),
    )

    # -- grep ------------------------------------------------------------------
    async def _grep(
        ctx,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> str:
        """Search file contents for a regular-expression pattern."""
        return await grep_tool(ctx, pattern, path, glob)

    ts.add_function(
        _grep,
        takes_ctx=True,
        name="grep",
        description=(
            "Search file contents for a regular-expression pattern. "
            "Returns a 'Found N matches in M files' summary plus matching lines. "
            "Use the glob parameter to filter which files are searched."
        ),
    )

    # -- bash ------------------------------------------------------------------
    async def _bash(ctx, command: str, timeout: int | None = None) -> str:
        """Execute a shell command and return stdout + stderr combined."""
        return await bash_tool(ctx, command, timeout)

    ts.add_function(
        _bash,
        takes_ctx=True,
        name="bash",
        description=(
            "Execute a shell command and return combined stdout + stderr. "
            "No sandbox is applied. Optionally specify a timeout in seconds."
        ),
    )

    return ts
