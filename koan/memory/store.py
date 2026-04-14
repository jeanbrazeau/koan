# High-level operations over the flat .koan/memory/ directory.

from __future__ import annotations

import re
from pathlib import Path

from .types import MemoryEntry, MemoryType
from .parser import parse_entry
from .writer import write_entry as _write_entry, update_entry as _update_entry

_ENTRY_PATTERN = re.compile(r"^(\d{4})-.*\.md$")


class MemoryStore:
    """File-backed store for koan memory entries in a flat directory."""

    def __init__(self, project_root: str | Path) -> None:
        self._root = Path(project_root)
        self._memory_dir = self._root / ".koan" / "memory"

    # -- Directory management ---------------------------------------------------

    def init(self) -> None:
        """Create the memory directory if it doesn't exist."""
        self._memory_dir.mkdir(parents=True, exist_ok=True)

    # -- Query ------------------------------------------------------------------

    def _iter_entry_paths(self) -> list[Path]:
        """Return all NNNN-*.md paths in the memory directory, sorted by name."""
        if not self._memory_dir.is_dir():
            return []
        return sorted(
            p for p in self._memory_dir.iterdir()
            if p.is_file() and _ENTRY_PATTERN.match(p.name)
        )

    def list_entries(self, type: MemoryType | None = None) -> list[MemoryEntry]:
        """List entries, optionally filtered by type. Sorted by sequence number."""
        entries = [parse_entry(p) for p in self._iter_entry_paths()]
        if type is not None:
            entries = [e for e in entries if e.type == type]
        return entries

    def get_entry(self, number: int) -> MemoryEntry | None:
        """Find and parse a specific entry by global sequence number."""
        if not self._memory_dir.is_dir():
            return None
        prefix = f"{number:04d}-"
        for p in self._memory_dir.iterdir():
            if p.is_file() and p.name.startswith(prefix) and p.name.endswith(".md"):
                return parse_entry(p)
        return None

    def entry_count(self, type: MemoryType | None = None) -> int:
        """Count entries, optionally filtered by type."""
        paths = self._iter_entry_paths()
        if type is None:
            return len(paths)
        return sum(1 for p in paths if parse_entry(p).type == type)

    # -- Mutations --------------------------------------------------------------

    def add_entry(
        self,
        type: MemoryType,
        title: str,
        body: str,
        related: list[str] | None = None,
    ) -> MemoryEntry:
        """Create a new entry, write it to disk, return with file_path set."""
        entry = MemoryEntry(
            title=title,
            type=type,
            body=body,
            related=related or [],
        )
        path = _write_entry(entry, self._memory_dir)
        entry.file_path = path
        return entry

    def update_entry(self, entry: MemoryEntry) -> None:
        """Write an entry back to its existing file_path."""
        _update_entry(entry)

    def forget_entry(self, entry: MemoryEntry) -> None:
        """Delete an entry file from disk. Git preserves history."""
        if entry.file_path is None:
            raise ValueError("entry has no file_path")
        entry.file_path.unlink()

    # -- Summary ----------------------------------------------------------------

    def get_summary(self) -> str | None:
        """Return the content of summary.md if it exists."""
        p = self._memory_dir / "summary.md"
        if p.is_file():
            return p.read_text("utf-8")
        return None

    async def regenerate_summary(self, project_name: str = "") -> None:
        """Regenerate summary.md from all current entries."""
        from .summarize import regenerate_summary

        await regenerate_summary(self, project_name=project_name)
