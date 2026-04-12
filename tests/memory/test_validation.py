# Tests for koan.memory.validation

from __future__ import annotations

from koan.memory.types import MemoryEntry
from koan.memory.validation import validate_entry


def _valid_entry(**overrides) -> MemoryEntry:
    defaults = dict(
        title="PostgreSQL for Auth",
        type="decision",
        date="2026-04-10",
        source="user-stated",
        status="active",
        contextual_introduction="Documents the data store choice.",
        body="Chose PostgreSQL 16.2 over SQLite.",
    )
    defaults.update(overrides)
    return MemoryEntry(**defaults)


class TestValidEntry:
    def test_passes(self):
        assert validate_entry(_valid_entry()) == []


class TestMissingRequired:
    def test_missing_title(self):
        errors = validate_entry(_valid_entry(title=""))
        assert any("title" in e for e in errors)

    def test_missing_type(self):
        errors = validate_entry(_valid_entry(type=""))
        assert any("type" in e for e in errors)

    def test_missing_date(self):
        errors = validate_entry(_valid_entry(date=""))
        assert any("date" in e for e in errors)

    def test_missing_source(self):
        errors = validate_entry(_valid_entry(source=""))
        assert any("source" in e for e in errors)

    def test_missing_status(self):
        errors = validate_entry(_valid_entry(status=""))
        assert any("status" in e for e in errors)


class TestInvalidValues:
    def test_invalid_type(self):
        errors = validate_entry(_valid_entry(type="opinion"))
        assert any("invalid type" in e for e in errors)

    def test_invalid_source(self):
        errors = validate_entry(_valid_entry(source="guessed"))
        assert any("invalid source" in e for e in errors)

    def test_invalid_status(self):
        errors = validate_entry(_valid_entry(status="pending"))
        assert any("invalid status" in e for e in errors)

    def test_invalid_date_format(self):
        errors = validate_entry(_valid_entry(date="April 10"))
        assert any("ISO 8601" in e for e in errors)


class TestMissingContent:
    def test_missing_intro(self):
        errors = validate_entry(_valid_entry(contextual_introduction=""))
        assert any("contextual_introduction" in e for e in errors)

    def test_missing_body(self):
        errors = validate_entry(_valid_entry(body=""))
        assert any("body" in e for e in errors)
