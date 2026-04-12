# Tests for koan.memory.parser

from __future__ import annotations

import pytest
from pathlib import Path

from koan.memory.parser import parse_entry, parse_index, ParseError


WELL_FORMED = """\
---
title: PostgreSQL for Auth Service
type: decision
date: 2026-04-10
source: user-stated
status: active
tags: [auth, postgresql]
supersedes: null
related: [context/0002-infrastructure.md]
---

This entry documents the choice of primary data store.

On 2026-04-10, user decided to migrate the auth service from SQLite
to PostgreSQL 16.2. Rationale: concurrency.
"""

WELL_FORMED_HEADING_BODY = """\
---
title: Migration Steps
type: procedure
date: 2026-04-11
source: post-mortem
status: active
---

This entry covers migration procedures for the data layer.

## Steps

1. Create schema migration file.
2. Run migration.
"""


def _write(tmp_path: Path, content: str, name: str = "entry.md") -> Path:
    p = tmp_path / name
    p.write_text(content, "utf-8")
    return p


class TestParseEntry:
    def test_well_formed(self, tmp_path):
        p = _write(tmp_path, WELL_FORMED)
        e = parse_entry(p)
        assert e.title == "PostgreSQL for Auth Service"
        assert e.type == "decision"
        assert e.date == "2026-04-10"
        assert e.source == "user-stated"
        assert e.status == "active"
        assert e.tags == ["auth", "postgresql"]
        assert e.supersedes is None
        assert e.related == ["context/0002-infrastructure.md"]
        assert "choice of primary data store" in e.contextual_introduction
        assert "PostgreSQL 16.2" in e.body
        assert e.file_path == p

    def test_heading_separates_body(self, tmp_path):
        p = _write(tmp_path, WELL_FORMED_HEADING_BODY)
        e = parse_entry(p)
        assert "migration procedures" in e.contextual_introduction
        assert e.body.startswith("## Steps")

    def test_missing_frontmatter(self, tmp_path):
        p = _write(tmp_path, "Just some text without frontmatter.")
        with pytest.raises(ParseError, match="missing YAML frontmatter"):
            parse_entry(p)

    def test_missing_required_fields(self, tmp_path):
        content = "---\ntitle: Foo\n---\n\nIntro paragraph.\n\nBody text here.\n"
        p = _write(tmp_path, content)
        with pytest.raises(ParseError, match="missing required frontmatter fields"):
            parse_entry(p)

    def test_empty_body(self, tmp_path):
        content = "---\ntitle: Foo\ntype: decision\ndate: 2026-01-01\nsource: user-stated\nstatus: active\n---\n\nOnly an intro.\n"
        p = _write(tmp_path, content)
        with pytest.raises(ParseError, match="missing body"):
            parse_entry(p)

    def test_missing_intro(self, tmp_path):
        content = "---\ntitle: Foo\ntype: decision\ndate: 2026-01-01\nsource: user-stated\nstatus: active\n---\n\n## Heading\n\nBody only.\n"
        p = _write(tmp_path, content)
        with pytest.raises(ParseError, match="missing contextual introduction"):
            parse_entry(p)


class TestParseIndex:
    def test_well_formed(self, tmp_path):
        content = """\
---
type: index
covers: [1, 2, 3]
token_count: 380
last_generated: 2026-04-15
---

Active decisions cover three areas.
"""
        p = _write(tmp_path, content, "_index.md")
        idx = parse_index(p)
        assert idx.covers == [1, 2, 3]
        assert idx.token_count == 380
        assert idx.last_generated == "2026-04-15"
        assert "three areas" in idx.body
        assert idx.file_path == p
