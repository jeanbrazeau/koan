# Tests for koan.agents.loop -- the in-process multi-turn agent loop.
#
# Two layers:
#   - Pure-helper tests for assemble_resume_prompt / _yolo_yield_response /
#     _directed_yolo_response / drain_and_render_steering (deterministic, no model).
#   - Integration tests that drive PydanticAIAgent.run() (which delegates to
#     run_agent_loop) with pydantic-ai's TestModel, covering the four control-flow
#     paths: non-primary single turn, workflow_done termination, primary
#     park/resume, and yolo synthesis-without-parking.
#
# The primary park/resume path is the one the golden tests in
# test_pydantic_ai_agent.py deliberately avoid (they run non-primary single
# turns); it is pinned here.

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from koan.agents.base import AgentOptions
from koan.agents.pydantic_ai import PydanticAIAgent
from koan.agents.loop import (
    _directed_yolo_response,
    _yolo_yield_response,
    assemble_resume_prompt,
    drain_and_render_steering,
)
from koan.phases import PhaseContext, StepGuidance
from koan.state import AgentState, AppState, ChatMessage
from koan.types import ModelSpec


# -- Pure helpers --------------------------------------------------------------


def test_yolo_yield_response_prefers_recommended_non_done():
    suggestions = [
        {"id": "done", "command": "stop"},
        {"id": "plan-spec", "command": "write the plan", "recommended": True},
    ]
    assert _yolo_yield_response(suggestions) == "write the plan"


def test_yolo_yield_response_falls_back_to_first_non_done_then_proceed():
    assert _yolo_yield_response([{"id": "execute", "command": "go"}]) == "go"
    assert _yolo_yield_response([{"id": "done", "command": "stop"}]) == "proceed"
    assert _yolo_yield_response(None) == "proceed"


def test_directed_yolo_response_steers_to_next_phase():
    directed = ["intake", "plan-spec", "execute", "done"]
    assert "plan-spec" in _directed_yolo_response(directed, "intake")
    # Last real phase -> done tombstone instruction.
    assert 'koan_set_phase("done")' in _directed_yolo_response(directed, "execute")
    # Unknown current phase -> proceed.
    assert _directed_yolo_response(directed, "nope") == "proceed"


def test_assemble_resume_prompt_empty_is_proceed():
    prompt, manifest = assemble_resume_prompt([], AppState(), "pydantic_ai")
    assert prompt == "proceed"
    assert manifest == []


def test_assemble_resume_prompt_wraps_user_message():
    msgs = [ChatMessage(content="do the thing", timestamp_ms=1)]
    prompt, manifest = assemble_resume_prompt(msgs, AppState(), "pydantic_ai")
    assert "USER MESSAGE" in prompt
    assert "do the thing" in prompt
    assert manifest == []  # no attachments


def test_build_phase_suggestions_from_workflow():
    """M7.5: hand-back suggestions are derived from the workflow transitions."""
    from koan.lib.workflows import build_phase_suggestions, get_workflow
    wf = get_workflow("plan")
    sugg = build_phase_suggestions(wf, wf.initial_phase)
    assert sugg, "expected at least the 'done' option"
    assert all({"id", "label", "command"} <= set(s) for s in sugg)
    ids = [s["id"] for s in sugg]
    assert ids[-1] == "done"  # terminal option always last


def test_drain_and_render_steering_emits_event_and_text():
    app_state = AppState()
    agent = AgentState(agent_id="a", role="orchestrator", subagent_dir="", is_primary=True)
    app_state.interactions.steering_queue.append(
        ChatMessage(content="reconsider the auth flow", timestamp_ms=1)
    )
    text = drain_and_render_steering(app_state, agent)
    assert text is not None
    assert "reconsider the auth flow" in text
    # Queue drained.
    assert app_state.interactions.steering_queue == []
    # steering_delivered projection event emitted.
    events = app_state.projection_store.events
    assert any(e.event_type == "steering_delivered" for e in events)
    # Non-primary agents do not drain.
    assert drain_and_render_steering(app_state, None) is None


# -- Integration harness -------------------------------------------------------


def _fake_phase_module(total_steps: int = 3) -> MagicMock:
    mod = MagicMock()
    mod.ROLE = "orchestrator"
    mod.TOTAL_STEPS = total_steps
    mod.PHASE_ROLE_CONTEXT = ""
    mod.STEP_NAMES = {1: "Comprehend", 2: "Plan", 3: "Write"}
    mod.validate_step_completion = MagicMock(return_value=None)
    mod.get_next_step = MagicMock(return_value=1)
    mod.step_guidance = MagicMock(return_value=StepGuidance(
        title="Comprehend", instructions=["Read the brief."],
    ))
    mod.on_loop_back = AsyncMock()
    return mod


def _make(agent_id: str, tmp_dir: str, is_primary: bool) -> tuple[AppState, AgentState]:
    app_state = AppState()
    app_state.run.phase = "intake"
    app_state.run.workflow = None
    event_log = AsyncMock()
    event_log.emit_step_transition = AsyncMock()
    agent = AgentState(
        agent_id=agent_id,
        role="orchestrator",
        subagent_dir=tmp_dir,
        run_dir="",
        step=0,
        phase_module=_fake_phase_module(),
        phase_ctx=PhaseContext(run_dir="", subagent_dir=tmp_dir),
        event_log=event_log,
        is_primary=is_primary,
        runner_type="pydantic_ai",
    )
    app_state.agents[agent_id] = agent
    return app_state, agent


@contextmanager
def _test_model(call_tools):
    """Patch the adapter so the agent runs against TestModel (no network)."""
    from pydantic_ai.models.test import TestModel
    import koan.agents.adapter as adapter_mod
    orig_bm, orig_bms = adapter_mod.build_model, adapter_mod.build_model_settings
    adapter_mod.build_model = lambda spec: TestModel(
        call_tools=call_tools, custom_output_text="done for now",
    )
    adapter_mod.build_model_settings = lambda spec: {}
    try:
        yield
    finally:
        adapter_mod.build_model = orig_bm
        adapter_mod.build_model_settings = orig_bms


def _agent(app_state: AppState, tmp_path) -> PydanticAIAgent:
    spec = ModelSpec(provider="google", model="gemini-2.0-flash", thinking="disabled")
    return PydanticAIAgent(model_spec=spec, app_state=app_state, subagent_dir=str(tmp_path))


def _options(agent_id: str) -> AgentOptions:
    return AgentOptions(
        role="orchestrator", agent_id=agent_id, model=None, thinking=None,
        system_prompt="", boot_prompt="Begin.", mcp_url="",
    )


# -- Integration: control-flow paths -------------------------------------------


@pytest.mark.anyio
async def test_non_primary_runs_single_turn_no_park(tmp_path):
    """A non-primary agent runs exactly one turn and returns without parking."""
    app_state, _ = _make("loop-np", str(tmp_path), is_primary=False)
    with _test_model(call_tools=[]):
        events = [ev async for ev in _agent(app_state, tmp_path).run(_options("loop-np"))]
    assert len([e for e in events if e.type == "turn_complete"]) == 1
    assert app_state.interactions.yield_future is None  # never parked


@pytest.mark.anyio
async def test_workflow_done_terminates_primary_without_parking(tmp_path):
    """workflow_done set before the run -> a primary agent runs one turn and
    returns at the post-turn termination check, never reaching the hand-back."""
    app_state, _ = _make("loop-done", str(tmp_path), is_primary=True)
    app_state.run.workflow_done = True
    with _test_model(call_tools=[]):
        events = [ev async for ev in _agent(app_state, tmp_path).run(_options("loop-done"))]
    assert len([e for e in events if e.type == "turn_complete"]) == 1
    assert app_state.interactions.yield_future is None


@pytest.mark.anyio
async def test_primary_parks_then_resumes_then_terminates(tmp_path):
    """A primary agent parks on yield_future at the terminal-text hand-back,
    resumes with the buffered user message on resolution, and terminates once
    workflow_done is set. Asserts >= 2 turns and that history accumulated."""
    app_state, agent_state = _make("loop-pr", str(tmp_path), is_primary=True)
    events = []

    async def consume(run_iter):
        async for ev in run_iter:
            events.append(ev)

    with _test_model(call_tools=[]):
        run_iter = _agent(app_state, tmp_path).run(_options("loop-pr"))
        task = asyncio.create_task(consume(run_iter))

        # Wait for the loop to park (turn 1 hand-back).
        for _ in range(500):
            if app_state.interactions.yield_future is not None:
                break
            await asyncio.sleep(0.005)
        assert app_state.interactions.yield_future is not None, "loop did not park"

        # Buffer a reply and arrange termination after the resumed turn.
        app_state.interactions.user_message_buffer.append(
            ChatMessage(content="keep going", timestamp_ms=1)
        )
        app_state.run.workflow_done = True
        app_state.interactions.yield_future.set_result(None)

        await asyncio.wait_for(task, timeout=10)

    assert len([e for e in events if e.type == "turn_complete"]) >= 2
    assert agent_state.message_history, "message_history should accumulate across turns"
    # A yield_started event marks the hand-back.
    assert any(e.event_type == "yield_started" for e in app_state.projection_store.events)


@pytest.mark.anyio
async def test_yolo_primary_synthesizes_without_parking(tmp_path, monkeypatch):
    """Under yolo, a primary agent never parks -- it synthesizes the next prompt.
    The yolo helper is patched to set workflow_done so the loop terminates after
    the second turn instead of synthesizing forever."""
    app_state, _ = _make("loop-yolo", str(tmp_path), is_primary=True)
    app_state.server.yolo = True

    def _fake_yolo(suggestions):
        # Terminate after the next turn's End-node check.
        app_state.run.workflow_done = True
        return "proceed"

    monkeypatch.setattr("koan.agents.loop._yolo_yield_response", _fake_yolo)

    with _test_model(call_tools=[]):
        events = [ev async for ev in _agent(app_state, tmp_path).run(_options("loop-yolo"))]

    assert app_state.interactions.yield_future is None, "yolo must not park"
    assert len([e for e in events if e.type == "turn_complete"]) >= 2
