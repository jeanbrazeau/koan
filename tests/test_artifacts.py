# Unit tests for koan/artifacts.py frontmatter helpers.

from __future__ import annotations

import pytest
from pathlib import Path


# -- split_frontmatter ---------------------------------------------------------

def test_split_frontmatter_no_frontmatter():
    from koan.artifacts import split_frontmatter
    text = "# Hello\nsome body\n"
    meta, body = split_frontmatter(text)
    assert meta is None
    assert body == text


def test_split_frontmatter_round_trip():
    from koan.artifacts import split_frontmatter, dump_frontmatter
    original_meta = {"created": "2026-01-01T00:00:00Z", "last_modified": "2026-01-02T00:00:00Z"}
    original_body = "# Hello\n\nsome body\n"
    composed = dump_frontmatter(original_meta) + original_body
    meta, body = split_frontmatter(composed)
    assert meta == original_meta
    assert body == original_body


def test_split_frontmatter_malformed_returns_none():
    from koan.artifacts import split_frontmatter
    # Starts with '---' but no closing delimiter
    text = "---\ncreated: 2026-01-01T00:00:00Z\n# body\n"
    meta, body = split_frontmatter(text)
    assert meta is None
    assert body == text


def test_dump_frontmatter_field_order():
    from koan.artifacts import dump_frontmatter
    meta = {"created": "2026-01-01T00:00:00Z", "last_modified": "2026-01-02T00:00:00Z"}
    result = dump_frontmatter(meta)
    # Must start with opening delimiter and have fields in insertion order
    lines = result.splitlines()
    assert lines[0] == "---"
    assert lines[1].startswith("created:")
    assert lines[2].startswith("last_modified:")
    # Last non-empty line is the closing delimiter
    assert lines[-1] == "---"


# -- write_artifact_atomic -----------------------------------------------------

def test_write_artifact_atomic_sets_defaults(tmp_path):
    from koan.artifacts import write_artifact_atomic, split_frontmatter
    target = tmp_path / "test.md"
    meta = write_artifact_atomic(target, "hello")
    # Status field removed -- only timestamps in the returned meta
    assert "status" not in meta
    assert "created" in meta
    assert "last_modified" in meta
    # Verify on-disk file has frontmatter
    text = target.read_text()
    parsed_meta, body = split_frontmatter(text)
    assert parsed_meta is not None
    assert "status" not in parsed_meta
    assert body == "hello"


def test_write_artifact_atomic_preserves_created(tmp_path):
    from koan.artifacts import write_artifact_atomic, split_frontmatter
    target = tmp_path / "test.md"
    first_meta = write_artifact_atomic(target, "first")
    original_created = first_meta["created"]

    second_meta = write_artifact_atomic(target, "second")
    assert second_meta["created"] == original_created
    # last_modified should be updated (may be same timestamp if fast enough, but key exists)
    assert "last_modified" in second_meta

    _, body = split_frontmatter(target.read_text())
    assert body == "second"


# -- list_artifacts ------------------------------------------------------------

def test_list_artifacts_omits_status(tmp_path):
    from koan.artifacts import list_artifacts, write_artifact_atomic
    # File with frontmatter
    with_fm = tmp_path / "with-fm.md"
    write_artifact_atomic(with_fm, "body")
    # File without frontmatter
    plain = tmp_path / "plain.md"
    plain.write_text("# No frontmatter\n")

    results = list_artifacts(tmp_path)
    by_path = {r["path"]: r for r in results}

    assert "status" not in by_path["plain.md"]
    assert "status" not in by_path["with-fm.md"]
    # Canonical fields are present
    assert "path" in by_path["plain.md"]
    assert "size" in by_path["plain.md"]
    assert "modified_at" in by_path["plain.md"]


# -- Negative-presence guards --------------------------------------------------
# Confirm removed symbols are truly gone; ImportError here means the deletion
# was applied correctly and no stale reference can import them.

def test_status_values_removed():
    """STATUS_VALUES must not be importable from koan.artifacts after removal."""
    with pytest.raises(ImportError):
        from koan.artifacts import STATUS_VALUES  # noqa: F401


def test_read_artifact_status_removed():
    """read_artifact_status must not be importable from koan.artifacts after removal."""
    with pytest.raises(ImportError):
        from koan.artifacts import read_artifact_status  # noqa: F401
