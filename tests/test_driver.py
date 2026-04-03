# Tests for driver -- the persistent orchestrator driver.
# route_from_state has been removed as part of the persistent orchestrator refactor.
# Driver now manages a single long-lived orchestrator process for the entire run.

import pytest

from koan.driver import driver_main, _push_artifact_diff


class TestDriverImports:
    """Smoke test: driver module imports cleanly after refactor."""

    def test_driver_main_importable(self):
        assert callable(driver_main)

    def test_push_artifact_diff_importable(self):
        assert callable(_push_artifact_diff)
