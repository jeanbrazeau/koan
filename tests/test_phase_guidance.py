# Static-text assertions verifying that each phase module's step-1 guidance
# includes the "Read brief.md" directive introduced in Milestone 2.
#
# These tests do not boot a runner or mock anything. They instantiate
# step_guidance() with a minimal PhaseContext and assert that key strings
# appear in the joined instruction text. End-to-end behavior (does the LLM
# follow the prompt) is an evals-harness concern.

import pytest

from koan.phases import PhaseContext


# Minimal context that satisfies the PhaseContext constructor.
# run_dir and subagent_dir are the only non-default required fields.
def _ctx() -> PhaseContext:
    return PhaseContext(run_dir="", subagent_dir="")


# ---------------------------------------------------------------------------
# intake
# ---------------------------------------------------------------------------

def test_intake_step3_writes_brief_md():
    from koan.phases import intake
    g = intake.step_guidance(3, _ctx())
    text = "\n".join(g.instructions)
    assert "brief.md" in text
    assert "koan_artifact_write" in text
    assert 'status="Final"' in text
    # All seven section headings must appear
    assert "Initiative" in text
    assert "Scope" in text
    assert "Affected subsystems" in text
    assert "Decisions" in text
    assert "Constraints" in text
    assert "Assumptions" in text
    assert "Open questions" in text


def test_intake_role_context_mentions_brief_md():
    from koan.phases import intake
    assert "brief.md" in intake.PHASE_ROLE_CONTEXT


# ---------------------------------------------------------------------------
# milestone_spec
# ---------------------------------------------------------------------------

def test_milestone_spec_step1_reads_brief_md():
    from koan.phases import milestone_spec
    g = milestone_spec.step_guidance(1, _ctx())
    text = "\n".join(g.instructions)
    assert "brief.md" in text
    assert "Read initiative context" in text


# ---------------------------------------------------------------------------
# milestone_review
# ---------------------------------------------------------------------------

def test_milestone_review_step1_reads_brief_md():
    from koan.phases import milestone_review
    g = milestone_review.step_guidance(1, _ctx())
    text = "\n".join(g.instructions)
    assert "brief.md" in text
    assert "Read initiative context" in text


# ---------------------------------------------------------------------------
# plan_spec
# ---------------------------------------------------------------------------

def test_plan_spec_step1_reads_brief_md():
    from koan.phases import plan_spec
    g = plan_spec.step_guidance(1, _ctx())
    text = "\n".join(g.instructions)
    assert "brief.md" in text
    assert "Read initiative context" in text


# ---------------------------------------------------------------------------
# plan_review
# ---------------------------------------------------------------------------

def test_plan_review_step1_reads_brief_md():
    from koan.phases import plan_review
    g = plan_review.step_guidance(1, _ctx())
    text = "\n".join(g.instructions)
    assert "brief.md" in text
    assert "Read initiative context" in text


# ---------------------------------------------------------------------------
# exec_review
# ---------------------------------------------------------------------------

def test_exec_review_step1_reads_brief_md():
    from koan.phases import exec_review
    g = exec_review.step_guidance(1, _ctx())
    text = "\n".join(g.instructions)
    assert "brief.md" in text
    assert "Read initiative context" in text


# ---------------------------------------------------------------------------
# curation
# ---------------------------------------------------------------------------

def test_curation_step1_reads_brief_md_conditionally():
    from koan.phases import curation
    g = curation.step_guidance(1, _ctx())
    text = "\n".join(g.instructions)
    assert "brief.md" in text
    # The "if present" qualifier distinguishes curation from the unconditional
    # reads in the other five downstream phase modules.
    assert "if present" in text.lower() or "exists" in text.lower()


# ---------------------------------------------------------------------------
# workflow execute guidance
# ---------------------------------------------------------------------------

def test_plan_workflow_execute_guidance_includes_brief_md():
    from koan.lib.workflows import PLAN_WORKFLOW
    guidance = PLAN_WORKFLOW.phases["execute"].guidance
    assert "brief.md" in guidance


def test_milestones_workflow_execute_guidance_includes_brief_md():
    from koan.lib.workflows import MILESTONES_WORKFLOW
    guidance = MILESTONES_WORKFLOW.phases["execute"].guidance
    assert "brief.md" in guidance


# ---------------------------------------------------------------------------
# M3: PhaseBinding.next_phase field
# ---------------------------------------------------------------------------

def test_phasebinding_has_next_phase_field_default_none():
    from koan.lib.workflows import PhaseBinding
    from koan.phases import intake
    b = PhaseBinding(module=intake)
    assert b.next_phase is None


def test_phasebinding_next_phase_can_be_set():
    from koan.lib.workflows import PhaseBinding
    from koan.phases import intake
    b = PhaseBinding(module=intake, next_phase="plan-spec")
    assert b.next_phase == "plan-spec"


def test_plan_workflow_next_phase_defaults():
    from koan.lib.workflows import PLAN_WORKFLOW
    expected = {
        "intake":       "plan-spec",
        "plan-spec":    "plan-review",
        "plan-review":  None,
        "execute":      "exec-review",
        "exec-review":  None,
        "curation":     None,
    }
    for phase_name, expected_next in expected.items():
        binding = PLAN_WORKFLOW.phases[phase_name]
        assert binding.next_phase == expected_next, (
            f"PLAN_WORKFLOW[{phase_name!r}].next_phase: "
            f"expected {expected_next!r}, got {binding.next_phase!r}"
        )


def test_milestones_workflow_next_phase_defaults():
    from koan.lib.workflows import MILESTONES_WORKFLOW
    expected = {
        "intake":           "milestone-spec",
        "milestone-spec":   "plan-spec",
        "milestone-review": None,
        "plan-spec":        "plan-review",
        "plan-review":      None,
        "execute":          "exec-review",
        "exec-review":      None,
        "curation":         None,
    }
    for phase_name, expected_next in expected.items():
        binding = MILESTONES_WORKFLOW.phases[phase_name]
        assert binding.next_phase == expected_next, (
            f"MILESTONES_WORKFLOW[{phase_name!r}].next_phase: "
            f"expected {expected_next!r}, got {binding.next_phase!r}"
        )


# ---------------------------------------------------------------------------
# M3: PhaseContext.next_phase and suggested_phases fields
# ---------------------------------------------------------------------------

def test_phase_context_has_next_phase_and_suggested_phases_defaults():
    ctx = _ctx()
    assert ctx.next_phase is None
    assert ctx.suggested_phases == []


# ---------------------------------------------------------------------------
# M3: terminal_invoke helper
# ---------------------------------------------------------------------------

def test_terminal_invoke_with_next_phase_calls_set_phase():
    from koan.phases.format_step import terminal_invoke
    text = terminal_invoke("plan-spec", [])
    assert 'koan_set_phase("plan-spec")' in text


def test_terminal_invoke_with_none_calls_yield():
    from koan.phases.format_step import terminal_invoke
    text = terminal_invoke(None, ["plan-spec", "execute"])
    assert "koan_yield" in text
    assert "plan-spec" in text
    assert "execute" in text


def test_terminal_invoke_yield_with_no_suggestions_no_hint_clause():
    from koan.phases.format_step import terminal_invoke
    text = terminal_invoke(None, [])
    assert "koan_yield" in text
    # Without suggestions, no "(e.g. ...)" clause should appear
    assert "(e.g." not in text
    # "done" option should still be mentioned
    assert "done" in text


def test_format_phase_complete_removed():
    import importlib
    import koan.phases.format_step as mod
    # format_phase_complete must not exist on the module after M3
    assert not hasattr(mod, "format_phase_complete"), (
        "format_phase_complete was not removed from koan.phases.format_step"
    )


# ---------------------------------------------------------------------------
# M3: per-phase last-step invoke_after uses terminal_invoke
# ---------------------------------------------------------------------------

def _ctx_with_next(next_phase, suggested_phases=None):
    """Build a PhaseContext with next_phase and suggested_phases populated."""
    ctx = PhaseContext(
        run_dir="",
        subagent_dir="",
        next_phase=next_phase,
        suggested_phases=suggested_phases or [],
    )
    return ctx


def test_intake_last_step_invoke_after_is_terminal_invoke():
    from koan.phases import intake
    from koan.phases.format_step import terminal_invoke
    ctx = _ctx_with_next("plan-spec", ["plan-spec"])
    g = intake.step_guidance(intake.TOTAL_STEPS, ctx)
    assert g.invoke_after == terminal_invoke("plan-spec", ["plan-spec"])


def test_milestone_spec_last_step_invoke_after_is_terminal_invoke():
    from koan.phases import milestone_spec
    from koan.phases.format_step import terminal_invoke
    ctx = _ctx_with_next("plan-spec", ["milestone-review", "plan-spec"])
    g = milestone_spec.step_guidance(milestone_spec.TOTAL_STEPS, ctx)
    assert g.invoke_after == terminal_invoke("plan-spec", ["milestone-review", "plan-spec"])


def test_milestone_review_last_step_invoke_after_is_terminal_invoke():
    from koan.phases import milestone_review
    from koan.phases.format_step import terminal_invoke
    ctx = _ctx_with_next(None, ["milestone-spec", "plan-spec"])
    g = milestone_review.step_guidance(milestone_review.TOTAL_STEPS, ctx)
    assert g.invoke_after == terminal_invoke(None, ["milestone-spec", "plan-spec"])


def test_plan_spec_last_step_invoke_after_is_terminal_invoke():
    from koan.phases import plan_spec
    from koan.phases.format_step import terminal_invoke
    ctx = _ctx_with_next("plan-review", ["plan-review", "execute"])
    g = plan_spec.step_guidance(plan_spec.TOTAL_STEPS, ctx)
    assert g.invoke_after == terminal_invoke("plan-review", ["plan-review", "execute"])


def test_plan_review_last_step_invoke_after_is_terminal_invoke():
    from koan.phases import plan_review
    from koan.phases.format_step import terminal_invoke
    ctx = _ctx_with_next(None, ["plan-spec", "execute"])
    g = plan_review.step_guidance(plan_review.TOTAL_STEPS, ctx)
    assert g.invoke_after == terminal_invoke(None, ["plan-spec", "execute"])


def test_execute_last_step_invoke_after_is_terminal_invoke():
    from koan.phases import execute
    from koan.phases.format_step import terminal_invoke
    ctx = _ctx_with_next("exec-review", ["exec-review", "curation"])
    g = execute.step_guidance(execute.TOTAL_STEPS, ctx)
    assert g.invoke_after == terminal_invoke("exec-review", ["exec-review", "curation"])


def test_exec_review_last_step_invoke_after_is_terminal_invoke():
    from koan.phases import exec_review
    from koan.phases.format_step import terminal_invoke
    ctx = _ctx_with_next(None, ["curation", "plan-spec"])
    g = exec_review.step_guidance(exec_review.TOTAL_STEPS, ctx)
    assert g.invoke_after == terminal_invoke(None, ["curation", "plan-spec"])


def test_curation_last_step_invoke_after_is_terminal_invoke():
    from koan.phases import curation
    from koan.phases.format_step import terminal_invoke
    ctx = _ctx_with_next(None, [])
    g = curation.step_guidance(curation.TOTAL_STEPS, ctx)
    assert g.invoke_after == terminal_invoke(None, [])


# ---------------------------------------------------------------------------
# M4: rewrite-or-loopback in review phases
# ---------------------------------------------------------------------------

def test_plan_review_step2_has_rewrite_or_loopback():
    from koan.phases import plan_review
    g = plan_review.step_guidance(2, _ctx())
    text = "\n".join(g.instructions)
    assert "Rewrite-or-loop-back classification" in text
    assert "koan_artifact_write" in text
    assert "loop-back to plan-spec" in text or "plan-spec" in text
    assert "new-files-needed" in text


def test_milestone_review_step2_has_rewrite_or_loopback():
    from koan.phases import milestone_review
    g = milestone_review.step_guidance(2, _ctx())
    text = "\n".join(g.instructions)
    assert "Rewrite-or-loop-back classification" in text
    assert "koan_artifact_write" in text
    assert "milestone-spec" in text
    assert "new-files-needed" in text


def test_exec_review_step2_has_rewrite_or_loopback():
    from koan.phases import exec_review
    g = exec_review.step_guidance(2, _ctx())
    text = "\n".join(g.instructions)
    assert "Rewrite-or-loop-back of the plan artifact" in text
    assert "koan_artifact_write" in text
    assert "new-files-needed" in text


def test_exec_review_step2_has_milestones_update_block():
    from koan.phases import exec_review
    g = exec_review.step_guidance(2, _ctx())
    text = "\n".join(g.instructions)
    assert "milestones.md UPDATE" in text
    assert "Integration points created" in text
    assert "Patterns established" in text
    assert "Constraints discovered" in text
    assert "Deviations from plan" in text


def test_exec_review_step1_reads_milestones_md():
    from koan.phases import exec_review
    g = exec_review.step_guidance(1, _ctx())
    text = "\n".join(g.instructions)
    assert "milestones.md" in text
    assert "Read milestone state" in text


def test_milestone_spec_step1_redecompose_mode_replaces_update():
    from koan.phases import milestone_spec
    g = milestone_spec.step_guidance(1, _ctx())
    text = "\n".join(g.instructions)
    # RE-DECOMPOSE must appear
    assert "RE-DECOMPOSE" in text
    # UPDATE mode directives must be gone -- exec-review owns these transitions
    assert "mark the completed milestone" not in text.lower()
    assert "add an Outcome section" not in text.lower() or "do NOT add Outcome" in text


def test_milestone_spec_phase_binding_guidance_redecompose_framing():
    from koan.lib.workflows import MILESTONES_WORKFLOW
    guidance = MILESTONES_WORKFLOW.phases["milestone-spec"].guidance
    assert "RE-DECOMPOSE" in guidance
    # Old UPDATE-mode framing must be gone
    assert "UPDATE mode" not in guidance
    assert "mark the completed\nmilestone [done]" not in guidance


def test_exec_review_milestones_guidance_specifies_update():
    from koan.lib.workflows import _EXEC_REVIEW_MILESTONES_GUIDANCE
    assert "milestones.md UPDATE" in _EXEC_REVIEW_MILESTONES_GUIDANCE
    assert "Integration points" in _EXEC_REVIEW_MILESTONES_GUIDANCE
    assert "four-subsection Outcome" in _EXEC_REVIEW_MILESTONES_GUIDANCE


def test_exec_review_plan_guidance_no_milestones_update():
    from koan.lib.workflows import _EXEC_REVIEW_PLAN_GUIDANCE
    # Plan workflow has no milestones.md; UPDATE block must not appear there
    assert "milestones.md UPDATE" not in _EXEC_REVIEW_PLAN_GUIDANCE


def test_milestones_workflow_exec_review_transitions_order():
    from koan.lib.workflows import MILESTONES_WORKFLOW
    assert MILESTONES_WORKFLOW.transitions["exec-review"] == [
        "plan-spec", "curation", "milestone-spec"
    ]


def test_phase_trust_doc_describes_rewrite_or_loopback():
    import pathlib
    doc = pathlib.Path(__file__).parent.parent / "docs" / "phase-trust.md"
    text = doc.read_text()
    assert "rewrite-or-loop-back" in text.lower() or "rewrite-or-loopback" in text.lower()
    assert "role-level" in text.lower()
    assert "prompt discipline" in text.lower()
    # Old advisory-only framing must be gone
    assert "advisory only" not in text.lower()
    assert "reports findings, does not modify" not in text.lower()


# ---------------------------------------------------------------------------
# M5: inline-review backend removal + comments-as-steering channel
# ---------------------------------------------------------------------------

def test_steering_message_block_renders_artifact_path():
    """steering_message_block prefixes [artifact: {path}] when artifact_path is set."""
    from koan.phases.format_step import steering_message_block
    from koan.state import ChatMessage

    msg = ChatMessage(content="Add error handling", timestamp_ms=0, artifact_path="brief.md")
    block = steering_message_block(msg)
    assert "[artifact: brief.md]" in block.text
    assert "Add error handling" in block.text


def test_steering_message_block_no_artifact_path():
    """steering_message_block omits [artifact:] prefix when artifact_path is None."""
    from koan.phases.format_step import steering_message_block
    from koan.state import ChatMessage

    msg = ChatMessage(content="general comment", timestamp_ms=0, artifact_path=None)
    block = steering_message_block(msg)
    assert "[artifact:" not in block.text
    assert "general comment" in block.text


def test_koan_artifact_propose_removed_from_permissions():
    """koan_artifact_propose must not appear in orchestrator ROLE_PERMISSIONS."""
    from koan.lib.permissions import ROLE_PERMISSIONS
    assert "koan_artifact_propose" not in ROLE_PERMISSIONS["orchestrator"]


def test_koan_artifact_propose_not_importable_as_handler():
    """koan_artifact_propose must not be importable as a handler from mcp_endpoint."""
    from koan.web.mcp_endpoint import Handlers
    assert not hasattr(Handlers, "koan_artifact_propose"), (
        "koan_artifact_propose field was not removed from Handlers dataclass"
    )


def test_phase_summaries_field_removed():
    """Run.phase_summaries must not exist after M5."""
    from koan.projections import Run
    assert "phase_summaries" not in Run.model_fields, (
        "Run.phase_summaries field was not removed"
    )


def test_active_artifact_review_field_removed():
    """Run.active_artifact_review must not exist after M5."""
    from koan.projections import Run
    assert "active_artifact_review" not in Run.model_fields, (
        "Run.active_artifact_review field was not removed"
    )


def test_intake_step3_no_chat_synthesis():
    """Intake step 3 must not instruct the orchestrator to compose a prose synthesis."""
    from koan.phases import intake
    g = intake.step_guidance(3, _ctx())
    text = "\n".join(g.instructions)
    assert "Compose the prose synthesis in chat" not in text
    assert "phase summary" not in text
    assert "RAG anchor" not in text
    # The artifact write is still there
    assert "koan_artifact_write" in text
    assert "brief.md" in text
