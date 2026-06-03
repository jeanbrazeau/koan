# Attachment delivery tests (M3, updated for the M5 in-process loop).
#
# Scenarios:
#   1. A chat-message attachment surfaces in the loop's resume prompt as a text
#      notice (in-process path; koan_yield removed in M5).
#   2. A binary EmbeddedResource (runner_type "claude") cannot ride the single-
#      string resume prompt -- documents the text-only delivery limitation.
#   3. Per-decision attachments on /api/memory/curation reach koan_memory_propose
#      as File blocks in the correct order (still the MCP-handler path).
#   4. start-run attachments delivered on the first koan_complete_step.

from __future__ import annotations

import asyncio
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from koan.state import AgentState, AppState, UploadState
from koan.phases import PhaseContext
from koan.web.app import create_app
from koan.web.mcp_endpoint import build_mcp_server


# -- Shared helpers ------------------------------------------------------------

def _make_agent(app_state: AppState, tmp_path: Path, runner_type: str = "claude") -> AgentState:
    agent = AgentState(
        agent_id="test-attach-agent",
        role="orchestrator",
        subagent_dir=str(tmp_path),
        run_dir=str(tmp_path),
        step=2,
        is_primary=True,
        runner_type=runner_type,
        event_log=AsyncMock(),
        phase_ctx=PhaseContext(run_dir=str(tmp_path), subagent_dir=str(tmp_path)),
    )
    app_state.agents[agent.agent_id] = agent
    return agent


class FakeContext:
    def __init__(self, agent: AgentState):
        self._agent = agent

    async def get_state(self, key):
        if key == "agent":
            return self._agent
        return None


# -- Scenario 1: in-process resume delivers attachment text to the next turn ---
#
# koan_yield is removed in M5. On the in-process path the loop resumes after a
# terminal-text hand-back: drain_user_messages() + assemble_resume_prompt()
# build the next turn's prompt. Attachments are delivered as TEXT appended to
# that prompt (the loop carries a single string), so the non-claude/in-process
# path surfaces the upload notice; the binary EmbeddedResource produced for
# runner_type "claude" has no .text and is therefore omitted.

@pytest.mark.anyio
async def test_resume_prompt_includes_attachment_text_notice(tmp_path):
    """A buffered message with an attachment yields a resume prompt carrying the
    USER MESSAGE text plus the upload text-notice (non-claude/in-process path).
    """
    from koan.web.uploads import init_upload_state, register_upload, commit_to_run
    from koan.state import drain_user_messages
    from koan.agents.loop import assemble_resume_prompt

    app_state = AppState()
    app_state.run.run_dir = str(tmp_path)
    app_state.run.phase = "intake"
    init_upload_state(app_state.uploads)

    class FakeFile:
        filename = "note.txt"
        content_type = "text/plain"
        file = io.BytesIO(b"hello from note")

    record = await register_upload(app_state.uploads, FakeFile())
    uid = record.id
    commit_to_run(app_state.uploads, [uid], tmp_path)

    import time
    from koan.state import ChatMessage
    app_state.interactions.user_message_buffer.append(ChatMessage(
        content="check this file",
        timestamp_ms=int(time.time() * 1000),
        attachments=[uid],
    ))

    messages = drain_user_messages(app_state)
    prompt = assemble_resume_prompt(messages, app_state, runner_type="pydantic_ai")

    assert "USER MESSAGE" in prompt
    assert "check this file" in prompt
    # Attachment surfaces as a text notice naming the file.
    assert "note.txt" in prompt
    assert "attachment(s) omitted" in prompt


# -- Scenario 2: binary EmbeddedResource is omitted from the single-string prompt

@pytest.mark.anyio
async def test_resume_prompt_omits_binary_attachment_for_claude(tmp_path):
    """For runner_type 'claude', upload_ids_to_blocks returns a binary
    EmbeddedResource with no .text, so it cannot ride the single-string resume
    prompt. The user message text still survives. Documents the in-process
    text-only attachment limitation (full binary delivery would need M5c work).
    """
    from koan.web.uploads import init_upload_state, register_upload, commit_to_run
    from koan.state import drain_user_messages
    from koan.agents.loop import assemble_resume_prompt

    app_state = AppState()
    app_state.run.run_dir = str(tmp_path)
    app_state.run.phase = "intake"
    init_upload_state(app_state.uploads)

    class FakeFile:
        filename = "data.csv"
        content_type = "text/csv"
        file = io.BytesIO(b"a,b,c")

    record = await register_upload(app_state.uploads, FakeFile())
    commit_to_run(app_state.uploads, [record.id], tmp_path)

    import time
    from koan.state import ChatMessage
    app_state.interactions.user_message_buffer.append(ChatMessage(
        content="see attached",
        timestamp_ms=int(time.time() * 1000),
        attachments=[record.id],
    ))

    messages = drain_user_messages(app_state)
    prompt = assemble_resume_prompt(messages, app_state, runner_type="claude")

    assert "USER MESSAGE" in prompt
    assert "see attached" in prompt
    # Binary EmbeddedResource carries no text -> not appended to the prompt.
    assert "data.csv" not in prompt


# -- Scenario 3: Per-decision attachments in koan_memory_propose ---------------

@pytest.mark.anyio
async def test_memory_curation_per_decision_attachments(tmp_path):
    """POST /api/memory/curation with per-decision attachments; koan_memory_propose
    emits per-decision File blocks in order after the JSON blob.
    """
    from mcp.types import EmbeddedResource, TextContent
    from koan.web.uploads import init_upload_state, register_upload, commit_to_run
    from koan.projections import ActiveCurationBatch, Proposal
    from koan.web.app import create_app
    from starlette.testclient import TestClient

    app_state = AppState()
    app_state.run.run_dir = str(tmp_path)
    app_state.run.phase = "curation"
    init_upload_state(app_state.uploads)

    agent = _make_agent(app_state, tmp_path, runner_type="claude")
    _, handlers = build_mcp_server(app_state)

    # Upload a file and commit it (simulating api_memory_curation_submit).
    class FakeFile:
        filename = "evidence.md"
        content_type = "text/plain"
        file = io.BytesIO(b"# Evidence")

    record = await register_upload(app_state.uploads, FakeFile())
    commit_to_run(app_state.uploads, [record.id], tmp_path)

    # Build a curation batch with one proposal and push projection events.
    proposal = Proposal(
        id="p1", op="add", seq="", type="context",
        title="Test entry", body="Some body", rationale="test",
    )
    batch = ActiveCurationBatch(
        proposals=[proposal], batch_id="batch-test-1", context_note="",
    )
    from koan.events import build_memory_curation_started
    app_state.projection_store.push_event(
        "memory_curation_started",
        build_memory_curation_started(batch.to_wire()),
        agent_id=agent.agent_id,
    )

    # Schedule koan_memory_propose concurrently; it will block on the future.
    propose_task = asyncio.create_task(
        handlers.koan_memory_propose(FakeContext(agent), proposals=[proposal.model_dump()])
    )

    # Give the task time to reach the await point.
    await asyncio.sleep(0.01)

    # Resolve via direct future manipulation (mirrors what api_memory_curation_submit does).
    future = app_state.interactions.memory_propose_future
    assert future is not None

    decisions = [
        {
            "proposal_id": "p1",
            "decision": "approved",
            "feedback": "",
            "attachments": [record.id],
        }
    ]
    future.set_result(decisions)

    result = await asyncio.wait_for(propose_task, timeout=2.0)

    # Block 0: the JSON blob (json.loads(result[0].text) must work)
    assert isinstance(result[0], TextContent)
    parsed = json.loads(result[0].text)
    # batch_id is generated by the handler; just verify it's a non-empty string
    assert isinstance(parsed.get("batch_id"), str) and parsed["batch_id"]

    # Block 1: the label separator
    assert isinstance(result[1], TextContent)
    assert "Attachments for proposal p1" in result[1].text

    # Block 2: the EmbeddedResource for evidence.md
    assert isinstance(result[2], EmbeddedResource)


# -- Scenario 4: start-run attachment delivered on first koan_complete_step ----

def _make_start_run_agent(app_state: AppState, tmp_path: Path, runner_type: str = "claude") -> AgentState:
    """Build a step-0 primary orchestrator agent with a minimal phase module."""
    from unittest.mock import AsyncMock, MagicMock
    from koan.phases import StepGuidance

    phase_mod = MagicMock()
    phase_mod.ROLE = "intake"
    phase_mod.TOTAL_STEPS = 3
    phase_mod.PHASE_ROLE_CONTEXT = ""
    phase_mod.STEP_NAMES = {1: "Gather"}
    phase_mod.validate_step_completion = MagicMock(return_value=None)
    phase_mod.get_next_step = MagicMock(return_value=2)
    phase_mod.step_guidance = MagicMock(return_value=StepGuidance(
        title="Gather",
        instructions=["Read the task description."],
    ))
    phase_mod.on_loop_back = AsyncMock()

    event_log = AsyncMock()
    event_log.emit_step_transition = AsyncMock()

    agent = AgentState(
        agent_id="test-startrun-agent",
        role="orchestrator",
        subagent_dir=str(tmp_path),
        run_dir=str(tmp_path),
        step=0,
        is_primary=True,
        runner_type=runner_type,
        phase_module=phase_mod,
        phase_ctx=PhaseContext(run_dir=str(tmp_path), subagent_dir=str(tmp_path)),
        event_log=event_log,
    )
    app_state.agents[agent.agent_id] = agent
    return agent


@pytest.mark.anyio
async def test_start_run_attachment_delivered_on_first_complete_step(tmp_path):
    """Upload a file at start-run time, set start_attachments, and assert that
    the first koan_complete_step call returns an EmbeddedResource block for the
    file after the step-1 guidance text. Assert start_attachments is cleared
    after delivery so phase re-entries do not re-emit.
    """
    from mcp.types import EmbeddedResource, TextContent
    from koan.web.uploads import init_upload_state, register_upload, commit_to_run

    app_state = AppState()
    app_state.run.run_dir = str(tmp_path)
    app_state.run.phase = "intake"
    init_upload_state(app_state.uploads)

    agent = _make_start_run_agent(app_state, tmp_path, runner_type="claude")
    _, handlers = build_mcp_server(app_state)

    # Upload a small text file and commit it into the run dir (mirrors what
    # api_start_run does immediately after creating the run directory).
    class FakeFile:
        filename = "brief.txt"
        content_type = "text/plain"
        file = io.BytesIO(b"project brief content")

    record = await register_upload(app_state.uploads, FakeFile())
    uid = record.id
    commit_to_run(app_state.uploads, [uid], tmp_path)

    # Simulate the in-memory state set by api_start_run.
    app_state.run.start_attachments = [uid]

    result = await handlers.koan_complete_step(FakeContext(agent), thoughts="")

    # Block 0: the step-1 guidance TextContent
    assert isinstance(result[0], TextContent)
    assert "Gather" in result[0].text or "Read" in result[0].text

    # Block 1: EmbeddedResource for brief.txt
    assert isinstance(result[1], EmbeddedResource)

    # start_attachments must be cleared so re-entry does not re-emit.
    assert app_state.run.start_attachments == []

    # M3: tool_attachments event should carry the full koan-side manifest.
    events = app_state.projection_store.events
    attach_events = [e for e in events if e.event_type == "tool_attachments"]
    assert len(attach_events) >= 1
    manifest = attach_events[-1].payload.get("attachments", [])
    assert len(manifest) == 1
    assert manifest[0]["upload_id"] == uid
    assert manifest[0]["filename"] == "brief.txt"
    assert manifest[0]["path"] != ""

    # Second call (agent.step is now 1): no File block emitted because
    # start_attachments was cleared and this path is normal within-phase.
    result2 = await handlers.koan_complete_step(FakeContext(agent), thoughts="")
    assert all(isinstance(b, TextContent) for b in result2)


@pytest.mark.anyio
async def test_start_run_attachment_non_claude_gets_text_notice(tmp_path):
    """Same start-run upload flow with runner_type='codex': expect a TextContent
    notice block (not an EmbeddedResource) after the step-1 guidance. The audit
    manifest must still carry the file record.
    """
    from mcp.types import EmbeddedResource, TextContent
    from koan.web.uploads import init_upload_state, register_upload, commit_to_run

    app_state = AppState()
    app_state.run.run_dir = str(tmp_path)
    app_state.run.phase = "intake"
    init_upload_state(app_state.uploads)

    agent = _make_start_run_agent(app_state, tmp_path, runner_type="codex")
    _, handlers = build_mcp_server(app_state)

    class FakeFile:
        filename = "spec.md"
        content_type = "text/plain"
        file = io.BytesIO(b"# Spec")

    record = await register_upload(app_state.uploads, FakeFile())
    uid = record.id
    commit_to_run(app_state.uploads, [uid], tmp_path)

    app_state.run.start_attachments = [uid]

    result = await handlers.koan_complete_step(FakeContext(agent), thoughts="")

    # Block 0: step-1 guidance
    assert isinstance(result[0], TextContent)

    # Block 1: text notice (not an EmbeddedResource)
    assert isinstance(result[1], TextContent)
    assert "attachment(s) omitted" in result[1].text
    assert "spec.md" in result[1].text
    assert not any(isinstance(b, EmbeddedResource) for b in result)

    # M3: tool_attachments event fires with full koan-side fields even for non-Claude.
    events = app_state.projection_store.events
    attach_events = [e for e in events if e.event_type == "tool_attachments"]
    assert len(attach_events) >= 1
    manifest = attach_events[-1].payload.get("attachments", [])
    assert len(manifest) == 1
    assert manifest[0]["upload_id"] == uid
    assert manifest[0]["filename"] == "spec.md"
    assert manifest[0]["path"] != ""
