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
from koan.phases import scout
from koan.phases import plan_spec
from koan.phases import plan_review
from koan.phases import execute as execute_phase


def _ctx(**kw) -> PhaseContext:
    defaults = {"run_dir": "/tmp/run", "subagent_dir": "/tmp/sub"}
    defaults.update(kw)
    return PhaseContext(**defaults)


# -- Intake --------------------------------------------------------------------

class TestIntake:
    # -- Linear progression (steps 1-3) ----------------------------------------

    @pytest.mark.parametrize("step", [1, 2])
    def test_linear_steps(self, step):
        assert intake.get_next_step(step, _ctx()) == step + 1

    def test_step_3_completes(self):
        """Step 3 (Write) completes unconditionally — no review gate."""
        assert intake.get_next_step(3, _ctx()) is None

    # -- No validation gates ---------------------------------------------------

    def test_validate_all_steps_none(self):
        ctx = _ctx()
        for s in range(1, 4):
            assert intake.validate_step_completion(s, ctx) is None

    # -- Step guidance contains workflow context injection ----------------------

    def test_step_1_guidance_with_phase_instructions(self):
        ctx = _ctx(phase_instructions="## Scope\nThis is a plan workflow.")
        g = intake.step_guidance(1, ctx)
        text = "\n".join(g.instructions)
        assert "Workflow Context" in text
        assert "plan workflow" in text

    def test_step_1_guidance_with_workflow_name(self):
        ctx = _ctx(workflow_name="plan")
        g = intake.step_guidance(1, ctx)
        text = "\n".join(g.instructions)
        assert "plan" in text

    def test_step_3_guidance_is_summarize(self):
        ctx = _ctx(run_dir="/tmp/myrun")
        g = intake.step_guidance(3, ctx)
        assert g.title == "Summarize"
        text = "\n".join(g.instructions)
        assert "summary" in text.lower()


# -- Brief Writer --------------------------------------------------------------

class TestBriefWriter:
    def test_step_1_to_2(self):
        assert brief_writer.get_next_step(1, _ctx()) == 2

    def test_step_2_completes(self):
        """Step 2 is terminal — no review gate."""
        assert brief_writer.get_next_step(2, _ctx()) is None

    def test_validate_all_none(self):
        ctx = _ctx()
        for s in (1, 2):
            assert brief_writer.validate_step_completion(s, ctx) is None

    def test_total_steps_is_2(self):
        assert brief_writer.TOTAL_STEPS == 2


# -- Plan Spec -----------------------------------------------------------------

class TestPlanSpec:
    def test_step_1_to_2(self):
        assert plan_spec.get_next_step(1, _ctx()) == 2

    def test_step_2_completes(self):
        assert plan_spec.get_next_step(2, _ctx()) is None

    def test_validate_always_none(self):
        ctx = _ctx()
        for s in (1, 2):
            assert plan_spec.validate_step_completion(s, ctx) is None

    def test_total_steps_is_2(self):
        assert plan_spec.TOTAL_STEPS == 2

    def test_scope_is_plan(self):
        assert plan_spec.SCOPE == "plan"

    def test_step_1_guidance_references_intake_context(self):
        ctx = _ctx(run_dir="/tmp/myrun")
        g = plan_spec.step_guidance(1, ctx)
        text = "\n".join(g.instructions)
        assert "intake" in text.lower()

    def test_step_2_guidance_references_plan_md(self):
        ctx = _ctx(run_dir="/tmp/myrun")
        g = plan_spec.step_guidance(2, ctx)
        text = "\n".join(g.instructions)
        assert "plan.md" in text


# -- Plan Review ---------------------------------------------------------------

class TestPlanReview:
    def test_step_1_to_2(self):
        assert plan_review.get_next_step(1, _ctx()) == 2

    def test_step_2_completes(self):
        assert plan_review.get_next_step(2, _ctx()) is None

    def test_validate_always_none(self):
        ctx = _ctx()
        for s in (1, 2):
            assert plan_review.validate_step_completion(s, ctx) is None

    def test_total_steps_is_2(self):
        assert plan_review.TOTAL_STEPS == 2

    def test_scope_is_plan(self):
        assert plan_review.SCOPE == "plan"

    def test_step_1_guidance_references_intake_and_plan(self):
        ctx = _ctx(run_dir="/tmp/myrun")
        g = plan_review.step_guidance(1, ctx)
        text = "\n".join(g.instructions)
        assert "intake" in text.lower()
        assert "plan.md" in text


# -- Execute Phase -------------------------------------------------------------

class TestExecutePhase:
    def test_step_1_to_2(self):
        assert execute_phase.get_next_step(1, _ctx()) == 2

    def test_step_2_completes(self):
        assert execute_phase.get_next_step(2, _ctx()) is None

    def test_validate_always_none(self):
        ctx = _ctx()
        for s in (1, 2):
            assert execute_phase.validate_step_completion(s, ctx) is None

    def test_total_steps_is_2(self):
        assert execute_phase.TOTAL_STEPS == 2

    def test_scope_is_general(self):
        assert execute_phase.SCOPE == "general"

    def test_step_1_guidance_with_phase_instructions(self):
        ctx = _ctx(phase_instructions="## What to hand off\nCall koan_request_executor.")
        g = execute_phase.step_guidance(1, ctx)
        text = "\n".join(g.instructions)
        assert "koan_request_executor" in text


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


# -- Executor (rewritten: 3-step) ----------------------------------------------

class TestExecutor:
    def test_step_1_to_2(self):
        assert executor.get_next_step(1, _ctx()) == 2

    def test_step_2_to_3(self):
        assert executor.get_next_step(2, _ctx()) == 3

    def test_step_3_completes(self):
        assert executor.get_next_step(3, _ctx()) is None

    def test_validate_always_none(self):
        ctx = _ctx()
        for s in (1, 2, 3):
            assert executor.validate_step_completion(s, ctx) is None

    def test_total_steps_is_3(self):
        assert executor.TOTAL_STEPS == 3

    def test_scope_is_general(self):
        assert executor.SCOPE == "general"

    def test_step_1_guidance_with_artifacts(self):
        ctx = _ctx(run_dir="/tmp/myrun", executor_artifacts=["plan.md"])
        g = executor.step_guidance(1, ctx)
        text = "\n".join(g.instructions)
        assert "/tmp/myrun/plan.md" in text

    def test_step_1_guidance_with_phase_instructions(self):
        ctx = _ctx(phase_instructions="Key constraint: don't touch auth module.")
        g = executor.step_guidance(1, ctx)
        text = "\n".join(g.instructions)
        assert "Key constraint" in text

    def test_step_1_guidance_with_retry_context(self):
        ctx = _ctx(retry_context="Previous run failed at step 3 due to import error.")
        g = executor.step_guidance(1, ctx)
        text = "\n".join(g.instructions)
        assert "import error" in text


# -- Linear modules (all steps linear, no validation gates) --------------------

LINEAR_MODULES = [
    (core_flows, 2),
    (tech_plan, 3),
    (ticket_breakdown, 2),
    (cross_artifact_validation, 2),
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
    def test_intake_step_3_pure(self):
        """Intake step 3 always returns None (no review gate)."""
        ctx = _ctx()
        ctx_copy = copy.deepcopy(ctx)
        r1 = intake.get_next_step(3, ctx)
        r2 = intake.get_next_step(3, ctx)
        assert r1 == r2 == None
        assert ctx == ctx_copy

    def test_brief_writer_step_2_pure(self):
        """Brief writer step 2 always returns None (no review gate)."""
        ctx = _ctx()
        ctx_copy = copy.deepcopy(ctx)
        r1 = brief_writer.get_next_step(2, ctx)
        r2 = brief_writer.get_next_step(2, ctx)
        assert r1 == r2 == None
        assert ctx == ctx_copy
