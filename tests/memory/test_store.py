# Tests for koan.memory.store

from __future__ import annotations

from koan.memory.store import MemoryStore


class TestInit:
    def test_creates_directories(self, tmp_path):
        store = MemoryStore(tmp_path)
        store.init()
        mem = tmp_path / ".koan" / "memory"
        assert (mem / "decisions").is_dir()
        assert (mem / "context").is_dir()
        assert (mem / "lessons").is_dir()
        assert (mem / "procedures").is_dir()
        assert (mem / "milestones").is_dir()
        assert (tmp_path / ".koan" / "user").is_dir()

    def test_idempotent(self, tmp_path):
        store = MemoryStore(tmp_path)
        store.init()
        store.init()
        assert (tmp_path / ".koan" / "memory" / "decisions").is_dir()


class TestAddAndList:
    def test_add_and_list_round_trip(self, tmp_path):
        store = MemoryStore(tmp_path)
        store.init()
        e = store.add_entry(
            type="decision",
            title="Use PostgreSQL",
            date="2026-04-10",
            source="user-stated",
            contextual_introduction="Documents the DB choice.",
            body="Chose PostgreSQL 16.2 over SQLite.",
        )
        assert e.file_path is not None
        assert e.file_path.exists()

        entries = store.list_entries(type="decision")
        assert len(entries) == 1
        assert entries[0].title == "Use PostgreSQL"

    def test_list_all_types(self, tmp_path):
        store = MemoryStore(tmp_path)
        store.init()
        store.add_entry("decision", "D1", "2026-01-01", "user-stated", "Intro.", "Body.")
        store.add_entry("lesson", "L1", "2026-01-02", "post-mortem", "Intro.", "Body.")
        store.add_entry("context", "C1", "2026-01-03", "user-stated", "Intro.", "Body.")
        assert len(store.list_entries()) == 3

    def test_list_with_type_filter(self, tmp_path):
        store = MemoryStore(tmp_path)
        store.init()
        store.add_entry("decision", "D1", "2026-01-01", "user-stated", "Intro.", "Body.")
        store.add_entry("lesson", "L1", "2026-01-02", "post-mortem", "Intro.", "Body.")
        assert len(store.list_entries(type="decision")) == 1
        assert len(store.list_entries(type="lesson")) == 1
        assert len(store.list_entries(type="milestone")) == 0


class TestGetEntry:
    def test_by_type_and_number(self, tmp_path):
        store = MemoryStore(tmp_path)
        store.init()
        store.add_entry("decision", "First", "2026-01-01", "user-stated", "Intro.", "Body.")
        store.add_entry("decision", "Second", "2026-01-02", "user-stated", "Intro.", "Body.")
        e = store.get_entry("decision", 2)
        assert e is not None
        assert e.title == "Second"

    def test_missing(self, tmp_path):
        store = MemoryStore(tmp_path)
        store.init()
        assert store.get_entry("decision", 99) is None


class TestEntryCount:
    def test_count_all(self, tmp_path):
        store = MemoryStore(tmp_path)
        store.init()
        store.add_entry("decision", "D1", "2026-01-01", "user-stated", "Intro.", "Body.")
        store.add_entry("lesson", "L1", "2026-01-02", "post-mortem", "Intro.", "Body.")
        assert store.entry_count() == 2

    def test_count_by_type(self, tmp_path):
        store = MemoryStore(tmp_path)
        store.init()
        store.add_entry("decision", "D1", "2026-01-01", "user-stated", "Intro.", "Body.")
        store.add_entry("decision", "D2", "2026-01-02", "user-stated", "Intro.", "Body.")
        store.add_entry("lesson", "L1", "2026-01-03", "post-mortem", "Intro.", "Body.")
        assert store.entry_count(type="decision") == 2
        assert store.entry_count(type="lesson") == 1


class TestDeprecateEntry:
    def test_changes_status(self, tmp_path):
        store = MemoryStore(tmp_path)
        store.init()
        e = store.add_entry("decision", "D1", "2026-01-01", "user-stated", "Intro.", "Body.")
        assert e.status == "active"
        store.deprecate_entry(e)
        assert e.status == "deprecated"
        # Re-read from disk to verify persistence
        reparsed = store.get_entry("decision", 1)
        assert reparsed is not None
        assert reparsed.status == "deprecated"


class TestSummaryAndIndex:
    def test_no_summary(self, tmp_path):
        store = MemoryStore(tmp_path)
        store.init()
        assert store.get_summary() is None

    def test_summary_exists(self, tmp_path):
        store = MemoryStore(tmp_path)
        store.init()
        summary_path = tmp_path / ".koan" / "memory" / "summary.md"
        summary_path.write_text("# Project Summary\n\nOverview here.\n", "utf-8")
        assert store.get_summary() is not None
        assert "Overview here" in store.get_summary()

    def test_no_index(self, tmp_path):
        store = MemoryStore(tmp_path)
        store.init()
        assert store.get_index("decision") is None

    def test_index_exists(self, tmp_path):
        from koan.memory.writer import write_index
        from koan.memory.types import MemoryIndex

        store = MemoryStore(tmp_path)
        store.init()
        idx = MemoryIndex(covers=[1, 2], token_count=200, last_generated="2026-04-15", body="Summary.")
        write_index(idx, tmp_path / ".koan" / "memory" / "decisions")
        result = store.get_index("decision")
        assert result is not None
        assert result.covers == [1, 2]
