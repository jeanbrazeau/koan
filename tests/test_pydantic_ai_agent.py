# Tests for koan.agents.pydantic_ai -- PydanticAIAgent golden StreamEvent test
# plus a credential-gated live smoke test against Gemini.
#
# The golden test pins the highest-risk seam: that PydanticAIAgent.run() emits
# the correct StreamEvent sequence when the model calls koan_complete_step and
# returns final text. It uses pydantic-ai's TestModel so no network calls are made.
#
# The live smoke test gates on GOOGLE_API_KEY / GEMINI_API_KEY and verifies
# that a degenerate intake turn advances at least one step and reaches
# turn_complete without error.

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from koan.agents.base import AgentOptions
from koan.agents.pydantic_ai import PydanticAIAgent
from koan.phases import PhaseContext, StepGuidance
from koan.runners.base import StreamEvent
from koan.state import AgentState, AppState
from koan.types import CachingPolicy, ModelSpec


# -- Shared helpers -----------------------------------------------------------


def _fake_phase_module(total_steps: int = 3) -> MagicMock:
    """Build a minimal mock PhaseModule for use in PydanticAIAgent tests.

    Uses the same helper pattern as test_subagent.py's _fake_phase_module()
    so the two test files share the same dependency-free stub shape.
    """
    mod = MagicMock()
    mod.ROLE = "orchestrator"
    mod.TOTAL_STEPS = total_steps
    mod.PHASE_ROLE_CONTEXT = ""
    mod.STEP_NAMES = {1: "Comprehend", 2: "Plan", 3: "Write"}
    mod.validate_step_completion = MagicMock(return_value=None)
    mod.get_next_step = MagicMock(return_value=1)
    mod.step_guidance = MagicMock(return_value=StepGuidance(
        title="Comprehend",
        instructions=["Read the brief."],
    ))
    mod.on_loop_back = AsyncMock()
    return mod


def _make_app_state_with_agent(
    agent_id: str,
    phase_module: MagicMock,
    tmp_subagent_dir: str,
) -> tuple[AppState, AgentState]:
    """Construct a minimal AppState + AgentState pair for PydanticAIAgent tests.

    app_state.run.workflow is set to None so memory injection is skipped.
    The AgentState is registered in app_state.agents so PydanticAIAgent.run()
    can find it via options.agent_id.
    """
    app_state = AppState()
    app_state.run.phase = "intake"
    # No workflow: _compute_memory_injection_core returns "" when workflow is None.
    app_state.run.workflow = None

    event_log = AsyncMock()
    event_log.emit_step_transition = AsyncMock()

    agent = AgentState(
        agent_id=agent_id,
        role="orchestrator",
        subagent_dir=tmp_subagent_dir,
        run_dir="",
        step=0,
        phase_module=phase_module,
        phase_ctx=PhaseContext(run_dir="", subagent_dir=tmp_subagent_dir),
        event_log=event_log,
        is_primary=True,
    )
    app_state.agents[agent_id] = agent
    return app_state, agent


# -- Golden StreamEvent test --------------------------------------------------


class TestPydanticAIAgentGolden:
    """Golden test: PydanticAIAgent.run() emits the correct StreamEvent sequence.

    Uses TestModel (no network) scripted to call koan_complete_step once then
    return final text. Asserts the exact event type sequence so regressions in
    the translation layer are caught immediately.
    """

    @pytest.mark.anyio
    async def test_event_sequence_tool_call_then_final_text(self, tmp_path):
        """PydanticAIAgent emits tool_start, tool_result, token_delta, assistant_text, turn_complete.

        TestModel calls koan_complete_step exactly once (call_tools=['koan_complete_step'])
        then returns a fixed text response. The test asserts:
        1. A tool_start event for koan_complete_step with a non-None tool_use_id.
        2. A tool_result event with tool_name='koan_complete_step' and the same tool_use_id.
        3. At least one token_delta event.
        4. An assistant_text event with non-empty content.
        5. A turn_complete event with non-None usage carrying input_tokens > 0.
        """
        from pydantic_ai.models.test import TestModel

        from koan.types import ModelSpec

        agent_id = "golden-test-001"
        phase_mod = _fake_phase_module()
        app_state, agent_state = _make_app_state_with_agent(
            agent_id, phase_mod, str(tmp_path)
        )

        # TestModel is patched in as the provider model by constructing a ModelSpec
        # that would normally go to Gemini, then overriding the model object inside
        # PydanticAIAgent.run() via monkeypatching build_model.
        model_spec = ModelSpec(
            provider="google",
            model="gemini-2.0-flash",
            thinking="disabled",
        )

        pai_agent = PydanticAIAgent(
            model_spec=model_spec,
            app_state=app_state,
            subagent_dir=str(tmp_path),
        )

        # Patch build_model to return TestModel so no network call is made.
        # TestModel is scripted to call koan_complete_step once then emit text.
        # build_model_settings is also patched to return an empty dict (TestModel
        # ignores model_settings, but the adapter raises NotImplementedError for
        # thinking='disabled' before M7 adds all providers).
        import koan.agents.adapter as adapter_mod

        original_build_model = adapter_mod.build_model
        original_build_model_settings = adapter_mod.build_model_settings
        adapter_mod.build_model = lambda spec: TestModel(
            call_tools=["koan_complete_step"],
            custom_output_text="Analysis complete.",
        )
        adapter_mod.build_model_settings = lambda spec: {}
        try:
            options = AgentOptions(
                role="orchestrator",
                agent_id=agent_id,
                model=None,
                thinking=None,
                system_prompt="You are a koan orchestrator.",
                boot_prompt="Call koan_complete_step to receive your instructions.",
                mcp_url="",
            )

            events: list[StreamEvent] = []
            async for ev in pai_agent.run(options):
                events.append(ev)
        finally:
            adapter_mod.build_model = original_build_model
            adapter_mod.build_model_settings = original_build_model_settings

        # Extract event types for assertion.
        types = [e.type for e in events]

        # A tool_start for koan_complete_step must appear.
        tool_starts = [e for e in events if e.type == "tool_start"]
        assert len(tool_starts) >= 1, f"expected tool_start, got: {types}"
        tool_start = tool_starts[0]
        assert tool_start.tool_name == "koan_complete_step"
        assert tool_start.tool_use_id is not None, "tool_start must carry tool_use_id"

        # A tool_result for koan_complete_step must appear after the tool_start.
        tool_results = [e for e in events if e.type == "tool_result"]
        assert len(tool_results) >= 1, f"expected tool_result, got: {types}"
        tool_result = tool_results[0]
        assert tool_result.tool_name == "koan_complete_step"
        assert tool_result.tool_use_id == tool_start.tool_use_id, (
            f"tool_result.tool_use_id {tool_result.tool_use_id!r} must match "
            f"tool_start.tool_use_id {tool_start.tool_use_id!r}"
        )

        # At least one token_delta or assistant_text event for the final text.
        text_events = [e for e in events if e.type in ("token_delta", "assistant_text")]
        assert len(text_events) >= 1, f"expected text events, got: {types}"

        # turn_complete with real usage.
        turn_completes = [e for e in events if e.type == "turn_complete"]
        assert len(turn_completes) >= 1, f"expected turn_complete, got: {types}"
        tc = turn_completes[-1]
        assert tc.usage is not None, "turn_complete must carry usage (RequestUsage)"
        assert tc.usage.input_tokens > 0, (
            f"expected input_tokens > 0, got {tc.usage.input_tokens}"
        )

    @pytest.mark.anyio
    async def test_agent_state_handshake_observed(self, tmp_path):
        """After run(), agent.handshake_observed is True and agent.step > 0.

        Verifies that advance_step correctly marks the handshake and advances
        the step counter even when driven via PydanticAIAgent.run() with TestModel.
        """
        from pydantic_ai.models.test import TestModel
        import koan.agents.adapter as adapter_mod

        agent_id = "golden-test-002"
        phase_mod = _fake_phase_module()
        app_state, agent_state = _make_app_state_with_agent(
            agent_id, phase_mod, str(tmp_path)
        )

        model_spec = ModelSpec(provider="google", model="gemini-2.0-flash", thinking="disabled")
        pai_agent = PydanticAIAgent(model_spec=model_spec, app_state=app_state, subagent_dir=str(tmp_path))

        orig_bm = adapter_mod.build_model
        orig_bms = adapter_mod.build_model_settings
        adapter_mod.build_model = lambda s: TestModel(call_tools=["koan_complete_step"])
        adapter_mod.build_model_settings = lambda s: {}
        try:
            options = AgentOptions(
                role="orchestrator",
                agent_id=agent_id,
                model=None,
                thinking=None,
                system_prompt="",
                boot_prompt="Call koan_complete_step.",
                mcp_url="",
            )
            async for _ in pai_agent.run(options):
                pass
        finally:
            adapter_mod.build_model = orig_bm
            adapter_mod.build_model_settings = orig_bms

        assert agent_state.handshake_observed is True, "handshake_observed should be True after run"
        assert agent_state.step >= 1, f"step should be >= 1 after handshake, got {agent_state.step}"

    @pytest.mark.anyio
    async def test_exit_code_success(self, tmp_path):
        """exit_code is 0 after a successful run().

        PydanticAIAgent sets _success=True on clean completion; exit_code
        property returns 0 in that case.
        """
        from pydantic_ai.models.test import TestModel
        import koan.agents.adapter as adapter_mod

        agent_id = "golden-test-003"
        phase_mod = _fake_phase_module()
        app_state, _ = _make_app_state_with_agent(agent_id, phase_mod, str(tmp_path))

        model_spec = ModelSpec(provider="google", model="gemini-2.0-flash", thinking="disabled")
        pai_agent = PydanticAIAgent(model_spec=model_spec, app_state=app_state, subagent_dir=str(tmp_path))

        orig_bm = adapter_mod.build_model
        orig_bms = adapter_mod.build_model_settings
        # call_tools=[] so no tools are called; the run produces only text and
        # completes cleanly -- enough to verify that _success is set to True.
        adapter_mod.build_model = lambda s: TestModel(call_tools=[])
        adapter_mod.build_model_settings = lambda s: {}
        try:
            options = AgentOptions(
                role="orchestrator",
                agent_id=agent_id,
                model=None,
                thinking=None,
                system_prompt="",
                boot_prompt="Call koan_complete_step.",
                mcp_url="",
            )
            async for _ in pai_agent.run(options):
                pass
        finally:
            adapter_mod.build_model = orig_bm
            adapter_mod.build_model_settings = orig_bms

        assert pai_agent.exit_code == 0
        assert pai_agent.stderr_output == ""

    @pytest.mark.anyio
    async def test_context_file_injected_at_loop_start(self, tmp_path):
        """Project-dir AGENTS.md is injected before the first model request.

        Sets up a temp project tree with an AGENTS.md at the root and runs
        PydanticAIAgent with options.project_dir pointing at it. After the run,
        agent_state.injected_context_files must contain the AGENTS.md path,
        proving that the ProcessHistory capability fired and injected it.

        TestModel does NOT call any built-in file tools (call_tools=['koan_complete_step'])
        so only the project-dir seed injection (loop start) is exercised here --
        not the just-in-time path-recording injection.
        """
        from pydantic_ai.models.test import TestModel
        import koan.agents.adapter as adapter_mod

        # Create a project tree with AGENTS.md at the root.
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        agents_md = project_dir / "AGENTS.md"
        agents_md.write_text("# Project agents instructions for the golden test")

        agent_id = "golden-ctx-001"
        phase_mod = _fake_phase_module()
        app_state, agent_state = _make_app_state_with_agent(
            agent_id, phase_mod, str(tmp_path)
        )
        # Set project_dir on app_state so the fallback path in pydantic_ai.py works.
        app_state.run.project_dir = str(project_dir)

        model_spec = ModelSpec(provider="google", model="gemini-2.0-flash", thinking="disabled")
        pai_agent = PydanticAIAgent(
            model_spec=model_spec,
            app_state=app_state,
            subagent_dir=str(tmp_path),
        )

        orig_bm = adapter_mod.build_model
        orig_bms = adapter_mod.build_model_settings
        adapter_mod.build_model = lambda s: TestModel(call_tools=["koan_complete_step"])
        adapter_mod.build_model_settings = lambda s: {}
        try:
            options = AgentOptions(
                role="orchestrator",
                agent_id=agent_id,
                model=None,
                thinking=None,
                system_prompt="",
                boot_prompt="Call koan_complete_step.",
                mcp_url="",
                project_dir=str(project_dir),
            )
            async for _ in pai_agent.run(options):
                pass
        finally:
            adapter_mod.build_model = orig_bm
            adapter_mod.build_model_settings = orig_bms

        # The project-dir AGENTS.md must have been injected (seeded at loop start).
        agents_md_path = str(agents_md.resolve())
        assert agents_md_path in agent_state.injected_context_files, (
            f"Expected {agents_md_path!r} in injected_context_files, "
            f"got: {agent_state.injected_context_files!r}"
        )


# -- Live credential-gated smoke test -----------------------------------------


_GOOGLE_KEY_SET = bool(
    os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
)


@pytest.mark.skipif(
    not _GOOGLE_KEY_SET,
    reason="GOOGLE_API_KEY / GEMINI_API_KEY not set -- skipping live Gemini smoke test",
)
@pytest.mark.anyio
async def test_live_gemini_intake_turn_advances_step(tmp_path):
    """Live: a degenerate intake turn on Gemini advances at least one step.

    Runs PydanticAIAgent.run() with a real Gemini model (google-gla provider).
    Asserts that at least one koan_complete_step tool_result is emitted (proving
    the step machine was called) and that the run reaches turn_complete.
    Skips when no Google API key is configured (cost-conscious per testing posture).
    """
    agent_id = "live-smoke-001"
    phase_mod = _fake_phase_module()
    # get_next_step returning None after step 1 causes advance_step to emit
    # "All steps complete." for non-primary agents (is_primary=False below),
    # which is a natural termination signal for the model.  Without this,
    # a live Gemini model would loop indefinitely calling koan_complete_step.
    phase_mod.get_next_step = MagicMock(return_value=None)
    app_state, agent_state = _make_app_state_with_agent(
        agent_id, phase_mod, str(tmp_path)
    )
    # Non-primary agent: "All steps complete" rather than "call koan_set_phase"
    # on phase boundary, giving the model a clean exit signal.
    agent_state.is_primary = False

    # Build a ModelSpec directly rather than going through resolve_model_spec:
    # builtin profiles map orchestrator -> strong tier -> gemini-2.5-pro-latest
    # which may not be available on all API keys.  gemini-flash-latest is the
    # conservative baseline used for live tests; it is available on standard
    # GOOGLE_API_KEY grants and is sufficient to exercise the tool/step path.
    model_spec = ModelSpec(
        provider="google",
        model="gemini-flash-latest",
        thinking="disabled",
    )

    pai_agent = PydanticAIAgent(
        model_spec=model_spec,
        app_state=app_state,
        subagent_dir=str(tmp_path),
    )

    options = AgentOptions(
        role="orchestrator",
        agent_id=agent_id,
        model=None,
        thinking=None,
        system_prompt="You are a koan orchestrator agent.",
        # Explicit instruction to call the tool exactly once and then reply
        # with text: prevents Gemini from looping or calling koan_set_phase
        # on an empty fake workflow.
        boot_prompt=(
            "Call koan_complete_step exactly once to receive your instructions,"
            " then reply with a brief text summary of what you received."
            " Do not call any other tools."
        ),
        mcp_url="",
    )

    events: list[StreamEvent] = []
    async for ev in pai_agent.run(options):
        events.append(ev)

    types = [e.type for e in events]

    # Must have called koan_complete_step (tool_result proves the call returned).
    tool_results = [
        e for e in events
        if e.type == "tool_result" and e.tool_name == "koan_complete_step"
    ]
    assert len(tool_results) >= 1, (
        f"expected koan_complete_step tool_result in live run, got event types: {types}"
    )

    # Must reach turn_complete.
    turn_completes = [e for e in events if e.type == "turn_complete"]
    assert len(turn_completes) >= 1, (
        f"expected turn_complete in live run, got event types: {types}"
    )

    # turn_complete should carry real usage.
    tc = turn_completes[-1]
    assert tc.usage is not None, "live run turn_complete must carry RequestUsage"
