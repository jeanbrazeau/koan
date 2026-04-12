# Tests for koan.memory.writer

from __future__ import annotations

from pathlib import Path

from koan.memory.types import MemoryEntry
from koan.memory.writer import write_entry, update_entry, write_index, _slugify
from koan.memory.parser import parse_entry
from koan.memory.types import MemoryIndex


def _entry(**overrides) -> MemoryEntry:
    defaults = dict(
        title="PostgreSQL for Auth",
        type="decision",
        date="2026-04-10",
        source="user-stated",
        status="active",
        contextual_introduction="This entry documents the choice of data store.",
        body="On 2026-04-10, user chose PostgreSQL 16.2.",
    )
    defaults.update(overrides)
    return MemoryEntry(**defaults)


class TestSlugify:
    def test_basic(self):
        assert _slugify("PostgreSQL for Auth Service") == "postgresql-for-auth-service"

    def test_special_chars(self):
        assert _slugify("What's up? (test!)") == "whats-up-test"

    def test_truncate(self):
        long_title = "a" * 100
        slug = _slugify(long_title)
        assert len(slug) <= 50

    def test_trailing_hyphen_after_truncation(self):
        # Title that would produce a trailing hyphen at the cut point
        title = "a" * 49 + " b"
        slug = _slugify(title)
        assert not slug.endswith("-")


class TestWriteEntry:
    def test_first_entry(self, tmp_path):
        e = _entry()
        p = write_entry(e, tmp_path)
        assert p.name == "0001-postgresql-for-auth.md"
        assert p.exists()

    def test_second_entry(self, tmp_path):
        write_entry(_entry(), tmp_path)
        p2 = write_entry(_entry(title="Redis for Sessions"), tmp_path)
        assert p2.name == "0002-redis-for-sessions.md"

    def test_no_reuse_after_deletion(self, tmp_path):
        """Deleting the highest-numbered file does not reuse its number
        when a lower-numbered file still exists -- but the scanner only
        sees current files, so max(existing)+1 is the best guarantee
        without external state.  When 0001 exists and 0002 is deleted,
        the next file is 0002 (max(1)+1).  When a *middle* file is
        deleted, the gap is never filled because the scanner uses max,
        not "first available"."""
        write_entry(_entry(), tmp_path)                    # 0001
        write_entry(_entry(title="Second"), tmp_path)      # 0002
        p3 = write_entry(_entry(title="Third"), tmp_path)  # 0003
        assert p3.name == "0003-third.md"
        # Delete the middle file -- gap at 0002 is never filled.
        (tmp_path / "0002-second.md").unlink()
        p4 = write_entry(_entry(title="Fourth"), tmp_path)
        assert p4.name == "0004-fourth.md"

    def test_round_trip(self, tmp_path):
        original = _entry(
            tags=["auth", "db"],
            related=["context/0001-infra.md"],
        )
        p = write_entry(original, tmp_path)
        parsed = parse_entry(p)
        assert parsed.title == original.title
        assert parsed.type == original.type
        assert parsed.date == original.date
        assert parsed.source == original.source
        assert parsed.status == original.status
        assert parsed.tags == original.tags
        assert parsed.related == original.related
        assert parsed.contextual_introduction == original.contextual_introduction
        assert parsed.body == original.body


class TestUpdateEntry:
    def test_preserves_filename(self, tmp_path):
        e = _entry()
        p = write_entry(e, tmp_path)
        e.file_path = p
        e.status = "deprecated"
        update_entry(e)
        reparsed = parse_entry(p)
        assert reparsed.status == "deprecated"
        assert reparsed.file_path == p


class TestWriteIndex:
    def test_writes_index(self, tmp_path):
        idx = MemoryIndex(
            covers=[1, 2, 3],
            token_count=380,
            last_generated="2026-04-15",
            body="Summary of decisions.",
        )
        p = write_index(idx, tmp_path)
        assert p.name == "_index.md"
        assert p.exists()
        text = p.read_text("utf-8")
        assert "covers:" in text
        assert "Summary of decisions." in text
