# Tests for driver route_from_state -- pure routing logic.

import copy

import pytest

from koan.driver import route_from_state


def _story(id: str, status: str) -> dict:
    return {"storyId": id, "status": status}


class TestRouteFromState:
    def test_retry_returns_retry(self):
        stories = [_story("s1", "retry")]
        result = route_from_state(stories)
        assert result == {"action": "retry", "story_id": "s1"}

    def test_selected_returns_execute(self):
        stories = [_story("s1", "selected")]
        result = route_from_state(stories)
        assert result == {"action": "execute", "story_id": "s1"}

    def test_retry_takes_priority_over_selected(self):
        stories = [_story("s1", "selected"), _story("s2", "retry")]
        result = route_from_state(stories)
        assert result["action"] == "retry"
        assert result["story_id"] == "s2"

    def test_all_done_returns_complete(self):
        stories = [_story("s1", "done"), _story("s2", "done")]
        result = route_from_state(stories)
        assert result == {"action": "complete"}

    def test_all_skipped_returns_complete(self):
        stories = [_story("s1", "skipped"), _story("s2", "skipped")]
        result = route_from_state(stories)
        assert result == {"action": "complete"}

    def test_done_and_skipped_mix_returns_complete(self):
        stories = [_story("s1", "done"), _story("s2", "skipped")]
        result = route_from_state(stories)
        assert result == {"action": "complete"}

    def test_pending_only_returns_error(self):
        stories = [_story("s1", "pending"), _story("s2", "pending")]
        result = route_from_state(stories)
        assert result["action"] == "error"
        assert result["error"] is not None

    def test_empty_list_returns_error(self):
        result = route_from_state([])
        assert result["action"] == "error"
        assert result["error"] is not None

    def test_retry_and_done_mix(self):
        stories = [_story("s1", "done"), _story("s2", "retry")]
        result = route_from_state(stories)
        assert result["action"] == "retry"
        assert result["story_id"] == "s2"

    def test_selected_and_done_mix(self):
        stories = [_story("s1", "done"), _story("s2", "selected")]
        result = route_from_state(stories)
        assert result["action"] == "execute"
        assert result["story_id"] == "s2"


class TestRouteFromStatePurity:
    def test_no_mutation_same_result(self):
        stories = [_story("s1", "retry"), _story("s2", "selected")]
        stories_copy = copy.deepcopy(stories)
        r1 = route_from_state(stories)
        r2 = route_from_state(stories)
        assert r1 == r2
        assert stories == stories_copy
