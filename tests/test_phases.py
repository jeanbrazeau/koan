# Tests for phase module get_next_step, validate_step_completion, and purity.

import copy

import pytest

from koan.phases import PhaseContext
from koan.phases import intake
from koan.phases import brief_writer
from koan.phases import core_flows
from koan.phases import tech_plan
from koan.phases import ticket_breakdown
from koan.phases import cross_artifact_validation
from koan.phases import executor
from koan.phases import orchestrator
from koan.phases import workflow_orchestrator
from koan.phases import scout


def _ctx(**kw) -> PhaseContext:
    defaults = {"epic_dir": "/tmp/epic", "subagent_dir": "/tmp/sub"}
    defaults.update(kw)
    return PhaseContext(**defaults)


# -- Intake --------------------------------------------------------------------

class TestIntake:
    # -- Linear progression (steps 1-3) ----------------------------------------

    @pytest.mark.parametrize("step", [1, 2, 3])
    def test_linear_steps(self, step):
        assert intake.get_next_step(step, _ctx()) == step + 1

    # -- Confidence gate (step 4) ----------------------------------------------

    def test_step_4_high_confidence_advances_to_5(self):
        assert intake.get_next_step(4, _ctx(intake_confidence="high")) == 5

    def test_step_4_medium_confidence_loops_to_2(self):
        assert intake.get_next_step(4, _ctx(intake_confidence="medium")) == 2

    def test_step_4_low_confidence_loops_to_2(self):
        assert intake.get_next_step(4, _ctx(intake_confidence="low")) == 2

    def test_step_4_no_confidence_loops_to_2(self):
        assert intake.get_next_step(4, _ctx(intake_confidence=None)) == 2

    def test_validate_step_4_requires_confidence(self):
        result = intake.validate_step_completion(4, _ctx(intake_confidence=None))
        assert result is not None
        assert "koan_set_confidence" in result

    def test_validate_step_4_confidence_set_passes(self):
        assert intake.validate_step_completion(4, _ctx(intake_confidence="medium")) is None

    # -- Review gate (step 5) --------------------------------------------------

    def test_step_5_accepted_completes(self):
        assert intake.get_next_step(5, _ctx(last_review_accepted=True)) is None

    def test_step_5_not_accepted_loops(self):
        assert intake.get_next_step(5, _ctx(last_review_accepted=False)) == 5

    def test_validate_step_5_never_reviewed(self):
        result = intake.validate_step_completion(5, _ctx(last_review_accepted=None))
        assert result is not None
        assert "koan_review_artifact" in result

    def test_validate_step_5_feedback_pending(self):
        result = intake.validate_step_completion(5, _ctx(last_review_accepted=False))
        assert result is not None
        assert "revision" in result.lower() or "feedback" in result.lower()

    def test_validate_step_5_accepted(self):
        assert intake.validate_step_completion(5, _ctx(last_review_accepted=True)) is None

    # -- No gate on other steps ------------------------------------------------

    def test_validate_step_1_no_gate(self):
        assert intake.validate_step_completion(1, _ctx()) is None


# -- Brief Writer --------------------------------------------------------------

class TestBriefWriter:
    def test_step_2_accepted_advances(self):
        assert brief_writer.get_next_step(2, _ctx(last_review_accepted=True)) == 3

    def test_step_2_not_accepted_loops(self):
        assert brief_writer.get_next_step(2, _ctx(last_review_accepted=False)) == 2

    def test_validate_step_2_never_reviewed(self):
        result = brief_writer.validate_step_completion(2, _ctx(last_review_accepted=None))
        assert result is not None
        assert "koan_review_artifact" in result

    def test_validate_step_2_accepted(self):
        assert brief_writer.validate_step_completion(2, _ctx(last_review_accepted=True)) is None

    def test_step_1_to_2(self):
        assert brief_writer.get_next_step(1, _ctx()) == 2

    def test_step_3_completes(self):
        assert brief_writer.get_next_step(3, _ctx()) is None


# -- Workflow Orchestrator -----------------------------------------------------

class TestWorkflowOrchestrator:
    def test_step_2_both_gates_met(self):
        ctx = _ctx(proposal_made=True, next_phase_set=True)
        assert workflow_orchestrator.get_next_step(2, ctx) is None

    def test_step_2_proposal_only_loops(self):
        ctx = _ctx(proposal_made=True, next_phase_set=False)
        assert workflow_orchestrator.get_next_step(2, ctx) == 2

    def test_validate_step_2_no_proposal(self):
        result = workflow_orchestrator.validate_step_completion(2, _ctx())
        assert result is not None
        assert "koan_propose_workflow" in result

    def test_validate_step_2_proposal_no_phase(self):
        result = workflow_orchestrator.validate_step_completion(2, _ctx(proposal_made=True))
        assert result is not None
        assert "koan_set_next_phase" in result

    def test_validate_step_2_both_gates_met(self):
        ctx = _ctx(proposal_made=True, next_phase_set=True)
        assert workflow_orchestrator.validate_step_completion(2, ctx) is None

    def test_step_1_to_2(self):
        assert workflow_orchestrator.get_next_step(1, _ctx()) == 2


# -- Orchestrator --------------------------------------------------------------

class TestOrchestrator:
    def test_pre_execution_step_2_completes(self):
        ctx = _ctx(step_sequence="pre-execution")
        assert orchestrator.get_next_step(2, ctx) is None

    def test_post_execution_step_2_advances(self):
        ctx = _ctx(step_sequence="post-execution")
        assert orchestrator.get_next_step(2, ctx) == 3

    def test_post_execution_step_4_completes(self):
        ctx = _ctx(step_sequence="post-execution")
        assert orchestrator.get_next_step(4, ctx) is None

    def test_pre_execution_step_1_advances(self):
        ctx = _ctx(step_sequence="pre-execution")
        assert orchestrator.get_next_step(1, ctx) == 2


# -- Linear modules (all steps linear, no validation gates) --------------------

LINEAR_MODULES = [
    (core_flows, 2),
    (tech_plan, 3),
    (ticket_breakdown, 2),
    (cross_artifact_validation, 2),
    (executor, 2),
    (scout, 3),
]


@pytest.mark.parametrize("mod,total", LINEAR_MODULES, ids=lambda x: x.ROLE if hasattr(x, "ROLE") else str(x))
class TestLinearModules:
    def test_steps_advance(self, mod, total):
        ctx = _ctx()
        for s in range(1, total):
            assert mod.get_next_step(s, ctx) == s + 1

    def test_last_step_completes(self, mod, total):
        assert mod.get_next_step(total, _ctx()) is None

    def test_validate_always_none(self, mod, total):
        ctx = _ctx()
        for s in range(1, total + 1):
            assert mod.validate_step_completion(s, ctx) is None


# -- Purity invariant ----------------------------------------------------------

class TestPurity:
    def test_intake_confidence_gate_purity(self):
        ctx = _ctx(intake_confidence="medium")
        ctx_copy = copy.deepcopy(ctx)
        r1 = intake.get_next_step(4, ctx)
        r2 = intake.get_next_step(4, ctx)
        assert r1 == r2
        assert ctx == ctx_copy

    def test_intake_review_gate_purity(self):
        ctx = _ctx(last_review_accepted=False)
        ctx_copy = copy.deepcopy(ctx)
        r1 = intake.get_next_step(5, ctx)
        r2 = intake.get_next_step(5, ctx)
        assert r1 == r2
        assert ctx == ctx_copy

    def test_brief_writer_purity(self):
        ctx = _ctx(last_review_accepted=True)
        ctx_copy = copy.deepcopy(ctx)
        r1 = brief_writer.get_next_step(2, ctx)
        r2 = brief_writer.get_next_step(2, ctx)
        assert r1 == r2
        assert ctx == ctx_copy

    def test_workflow_orchestrator_purity(self):
        ctx = _ctx(proposal_made=True, next_phase_set=False)
        ctx_copy = copy.deepcopy(ctx)
        r1 = workflow_orchestrator.get_next_step(2, ctx)
        r2 = workflow_orchestrator.get_next_step(2, ctx)
        assert r1 == r2
        assert ctx == ctx_copy
