# Tests for koan.memory.writer

from __future__ import annotations

import time

from koan.memory.parser import parse_entry
from koan.memory.types import MemoryEntry
from koan.memory.writer import _slugify, update_entry, write_entry


def _entry(**overrides) -> MemoryEntry:
    defaults = dict(
        title="PostgreSQL for Auth",
        type="decision",
        body=(
            "This entry documents the choice of data store.\n\n"
            "On 2026-04-10, user chose PostgreSQL 16.2 over SQLite."
        ),
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
        title = "a" * 49 + " b"
        slug = _slugify(title)
        assert not slug.endswith("-")


class TestWriteEntry:
    def test_first_entry(self, tmp_path):
        e = _entry()
        p = write_entry(e, tmp_path)
        assert p.name == "0001-postgresql-for-auth.md"
        assert p.exists()

    def test_auto_timestamps(self, tmp_path):
        e = _entry()
        write_entry(e, tmp_path)
        assert e.created != ""
        assert e.modified != ""
        assert e.created == e.modified  # same instant on creation

    def test_preserves_existing_created(self, tmp_path):
        e = _entry(created="2026-01-01T00:00:00Z")
        write_entry(e, tmp_path)
        assert e.created == "2026-01-01T00:00:00Z"
        # modified is always set on write
        assert e.modified != ""
        assert e.modified != e.created

    def test_second_entry(self, tmp_path):
        write_entry(_entry(), tmp_path)
        p2 = write_entry(_entry(title="Redis for Sessions"), tmp_path)
        assert p2.name == "0002-redis-for-sessions.md"

    def test_no_reuse_of_middle_gap(self, tmp_path):
        write_entry(_entry(), tmp_path)                    # 0001
        write_entry(_entry(title="Second"), tmp_path)      # 0002
        p3 = write_entry(_entry(title="Third"), tmp_path)  # 0003
        assert p3.name == "0003-third.md"
        (tmp_path / "0002-second.md").unlink()
        p4 = write_entry(_entry(title="Fourth"), tmp_path)
        assert p4.name == "0004-fourth.md"

    def test_round_trip(self, tmp_path):
        original = _entry(related=["0001-infra.md"])
        p = write_entry(original, tmp_path)
        parsed = parse_entry(p)
        assert parsed.title == original.title
        assert parsed.type == original.type
        assert parsed.body == original.body.strip()
        assert parsed.related == original.related
        assert parsed.created == original.created
        assert parsed.modified == original.modified


class TestUpdateEntry:
    def test_preserves_filename_and_created(self, tmp_path):
        e = _entry()
        p = write_entry(e, tmp_path)
        e.file_path = p
        original_created = e.created
        # Sleep long enough to guarantee a different second-precision timestamp
        time.sleep(1.1)
        e.body = "Updated body."
        update_entry(e)
        reparsed = parse_entry(p)
        assert reparsed.body == "Updated body."
        assert reparsed.created == original_created
        assert reparsed.modified != original_created
