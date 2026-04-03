# Tests for interaction queue, FIFO activation, stale submission, and cancellation.

from __future__ import annotations

import asyncio
import json
from collections import deque
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest

from koan.state import PendingInteraction


# -- Fixtures -----------------------------------------------------------------

@dataclass
class FakeConfig:
    model_tiers: Any = None
    scout_concurrency: int = 2


@dataclass
class FakeAppState:
    agents: dict = field(default_factory=dict)
    config: FakeConfig = field(default_factory=FakeConfig)
    port: int = 9999
    active_interaction: PendingInteraction | None = None
    interaction_queue: deque[PendingInteraction] = field(default_factory=deque)
    interaction_queue_max: int = 8
    epic_dir: str | None = None
    projection_store: object = field(default_factory=lambda: __import__('koan.projections', fromlist=['ProjectionStore']).ProjectionStore())
    phase_complete_future: asyncio.Future | None = None
    steering_queue: list = field(default_factory=list)
    phase: str = "intake"


def _make_interaction(
    interaction_type: str = "ask",
    agent_id: str = "agent-1",
    future: asyncio.Future | None = None,
    payload: dict | None = None,
) -> PendingInteraction:
    if future is None:
        future = asyncio.get_event_loop().create_future()
    return PendingInteraction(
        type=interaction_type,
        agent_id=agent_id,
        future=future,
        payload=payload or {},
    )


# -- TestQueueCap -------------------------------------------------------------

class TestQueueCap:
    @pytest.mark.anyio
    async def test_9th_request_raises_queue_full(self):
        from fastmcp.exceptions import ToolError

        from koan.state import AgentState
        from koan.web.interactions import enqueue_interaction

        app_state = FakeAppState()
        app_state.active_interaction = _make_interaction(agent_id="other")

        for i in range(8):
            app_state.interaction_queue.append(
                _make_interaction(agent_id=f"q-{i}")
            )

        agent = AgentState(
            agent_id="overflow",
            role="intake",
            subagent_dir="/tmp/test",
        )

        with pytest.raises(ToolError) as exc_info:
                await enqueue_interaction(agent, app_state, "ask", {"questions": []})

        err = json.loads(str(exc_info.value))
        assert err["error"] == "interaction_queue_full"

    @pytest.mark.anyio
    async def test_8th_request_succeeds(self):
        from koan.state import AgentState
        from koan.web.interactions import enqueue_interaction

        app_state = FakeAppState()
        app_state.active_interaction = _make_interaction(agent_id="other")

        for i in range(7):
            app_state.interaction_queue.append(
                _make_interaction(agent_id=f"q-{i}")
            )

        agent = AgentState(
            agent_id="ok",
            role="intake",
            subagent_dir="/tmp/test",
        )

        future = await enqueue_interaction(agent, app_state, "ask", {"questions": []})

        assert not future.done()
        assert len(app_state.interaction_queue) == 8


# -- TestStaleSubmit ----------------------------------------------------------

class TestStaleSubmit:
    @pytest.mark.anyio
    async def test_answer_with_no_active_interaction_returns_409(self):
        from starlette.testclient import TestClient

        from koan.state import AppState
        from koan.web.app import create_app

        app_state = AppState()
        app = create_app(app_state)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/answer", json={"answers": []})
        assert resp.status_code == 409
        assert resp.json()["error"] == "stale_interaction"

    @pytest.mark.anyio
    async def test_answer_wrong_type_returns_409(self):
        from starlette.testclient import TestClient

        from koan.state import AppState
        from koan.web.app import create_app

        app_state = AppState()
        app_state.active_interaction = _make_interaction(interaction_type="artifact-review")
        app = create_app(app_state)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/answer", json={"answers": []})
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_artifact_review_stale_returns_409(self):
        from starlette.testclient import TestClient

        from koan.state import AppState
        from koan.web.app import create_app

        app_state = AppState()
        app = create_app(app_state)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/artifact-review", json={"response": "Accept"})
        assert resp.status_code == 409


# -- TestFIFOActivation -------------------------------------------------------

class TestFIFOActivation:
    @pytest.mark.anyio
    async def test_fifo_order_preserved(self):
        from koan.web.interactions import activate_next_interaction

        app_state = FakeAppState()

        a = _make_interaction(agent_id="A")
        b = _make_interaction(agent_id="B")
        c = _make_interaction(agent_id="C")

        app_state.active_interaction = _make_interaction(agent_id="initial")
        app_state.interaction_queue.extend([a, b, c])

        # Resolve initial -> A becomes active
        activate_next_interaction(app_state)
        assert app_state.active_interaction is a

        # Resolve A -> B becomes active
        activate_next_interaction(app_state)
        assert app_state.active_interaction is b

        # Resolve B -> C becomes active
        activate_next_interaction(app_state)
        assert app_state.active_interaction is c

        # Resolve C -> None
        activate_next_interaction(app_state)
        assert app_state.active_interaction is None


# -- TestCancellationOnExit ---------------------------------------------------

class TestCancellationOnExit:
    @pytest.mark.anyio
    async def test_cancel_active_interaction_on_agent_exit(self):
        from koan.subagent import _cancel_pending_interactions

        app_state = FakeAppState()
        interaction = _make_interaction(agent_id="agent-1")
        app_state.active_interaction = interaction

        _cancel_pending_interactions("agent-1", app_state)

        assert interaction.future.done()
        assert interaction.future.result()["error"] == "agent_exited"
        assert app_state.active_interaction is None

    @pytest.mark.anyio
    async def test_cancel_queued_interactions_on_agent_exit(self):
        from koan.subagent import _cancel_pending_interactions

        app_state = FakeAppState()
        mine_1 = _make_interaction(agent_id="agent-1")
        mine_2 = _make_interaction(agent_id="agent-1")
        other = _make_interaction(agent_id="agent-2")
        app_state.interaction_queue.extend([mine_1, other, mine_2])

        _cancel_pending_interactions("agent-1", app_state)

        assert mine_1.future.done()
        assert mine_1.future.result()["error"] == "agent_exited"
        assert mine_2.future.done()
        assert mine_2.future.result()["error"] == "agent_exited"

        assert not other.future.done()
        assert len(app_state.interaction_queue) == 1
        assert app_state.interaction_queue[0] is other

    @pytest.mark.anyio
    async def test_next_queued_activated_after_cancel(self):
        from koan.subagent import _cancel_pending_interactions

        app_state = FakeAppState()
        active_a = _make_interaction(agent_id="agent-A")
        queued_b = _make_interaction(agent_id="agent-B")

        app_state.active_interaction = active_a
        app_state.interaction_queue.append(queued_b)

        _cancel_pending_interactions("agent-A", app_state)

        assert active_a.future.done()
        assert app_state.active_interaction is queued_b

    @pytest.mark.anyio
    async def test_phase_complete_future_cleared_on_exit(self):
        """_cancel_pending_interactions clears phase_complete_future (QR4)."""
        from koan.subagent import _cancel_pending_interactions

        app_state = FakeAppState()
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        app_state.phase_complete_future = future

        _cancel_pending_interactions("agent-1", app_state)

        assert future.done()
        assert app_state.phase_complete_future is None


# -- TestArtifactReviewResolution ---------------------------------------------

class TestArtifactReviewResolution:
    @pytest.mark.anyio
    async def test_accept_resolves_future_with_accepted_true(self):
        from starlette.testclient import TestClient

        from koan.state import AppState
        from koan.web.app import create_app

        app_state = AppState()
        interaction = _make_interaction(interaction_type="artifact-review")
        app_state.active_interaction = interaction

        app = create_app(app_state)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/artifact-review",
            json={"accepted": True, "token": interaction.token},
        )

        assert resp.status_code == 200
        result = interaction.future.result()
        assert result["accepted"] is True
        assert result["response"] == ""

    @pytest.mark.anyio
    async def test_feedback_resolves_future_with_accepted_false(self):
        from starlette.testclient import TestClient

        from koan.state import AppState
        from koan.web.app import create_app

        app_state = AppState()
        interaction = _make_interaction(interaction_type="artifact-review")
        app_state.active_interaction = interaction

        app = create_app(app_state)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/artifact-review",
            json={"response": "Please add more detail", "token": interaction.token},
        )

        assert resp.status_code == 200
        result = interaction.future.result()
        assert result["accepted"] is False
        assert result["response"] == "Please add more detail"

    @pytest.mark.anyio
    async def test_accept_mcp_handler_returns_accepted_string(self):
        from koan.phases import PhaseContext
        from koan.state import AgentState
        from koan.web.mcp_endpoint import _agent_ctx, koan_review_artifact

        import koan.web.mcp_endpoint as mcp_mod

        app_state = FakeAppState()
        old_app_state = mcp_mod._app_state
        mcp_mod._app_state = app_state

        phase_ctx = PhaseContext(epic_dir="/tmp", subagent_dir="/tmp/test")
        agent = AgentState(
            agent_id="test-review",
            role="intake",
            subagent_dir="/tmp/test",
            phase_ctx=phase_ctx,
        )

        # Pre-create and resolve the interaction future
        interaction = _make_interaction(interaction_type="artifact-review", agent_id="test-review")
        interaction.future.set_result({"response": "", "accepted": True})
        app_state.active_interaction = interaction

        token = _agent_ctx.set(agent)
        try:
            with patch("koan.web.mcp_endpoint._check_or_raise"), \
                 patch("koan.web.mcp_endpoint.enqueue_interaction", return_value=interaction.future), \
                 patch("aiofiles.open", side_effect=FileNotFoundError):
                # We need to provide a real file for the artifact read;
                # patch aiofiles to return content
                import aiofiles
                from unittest.mock import AsyncMock, MagicMock

                mock_file = AsyncMock()
                mock_file.__aenter__ = AsyncMock(return_value=mock_file)
                mock_file.__aexit__ = AsyncMock(return_value=False)
                mock_file.read = AsyncMock(return_value="artifact content")

                with patch("aiofiles.open", return_value=mock_file):
                    result = await koan_review_artifact(path="/tmp/test.md", description="test")
        finally:
            _agent_ctx.reset(token)
            mcp_mod._app_state = old_app_state

        assert result == "ACCEPTED"

    @pytest.mark.anyio
    async def test_feedback_mcp_handler_returns_revision_requested(self):
        from koan.phases import PhaseContext
        from koan.state import AgentState
        from koan.web.mcp_endpoint import _agent_ctx, koan_review_artifact

        import koan.web.mcp_endpoint as mcp_mod

        app_state = FakeAppState()
        old_app_state = mcp_mod._app_state
        mcp_mod._app_state = app_state

        phase_ctx = PhaseContext(epic_dir="/tmp", subagent_dir="/tmp/test")
        agent = AgentState(
            agent_id="test-review",
            role="intake",
            subagent_dir="/tmp/test",
            phase_ctx=phase_ctx,
        )

        interaction = _make_interaction(interaction_type="artifact-review", agent_id="test-review")
        interaction.future.set_result({"response": "needs work", "accepted": False})
        app_state.active_interaction = interaction

        token = _agent_ctx.set(agent)
        try:
            from unittest.mock import AsyncMock

            mock_file = AsyncMock()
            mock_file.__aenter__ = AsyncMock(return_value=mock_file)
            mock_file.__aexit__ = AsyncMock(return_value=False)
            mock_file.read = AsyncMock(return_value="artifact content")

            with patch("koan.web.mcp_endpoint._check_or_raise"), \
                 patch("koan.web.mcp_endpoint.enqueue_interaction", return_value=interaction.future), \
                 patch("aiofiles.open", return_value=mock_file):
                result = await koan_review_artifact(path="/tmp/test.md", description="test")
        finally:
            _agent_ctx.reset(token)
            mcp_mod._app_state = old_app_state

        assert result.startswith("REVISION REQUESTED:")
