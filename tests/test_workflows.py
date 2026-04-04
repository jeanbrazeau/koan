# Tests for koan/lib/workflows.py -- workflow type system.

import pytest

from koan.lib.workflows import (
    MILESTONES_WORKFLOW,
    PLAN_WORKFLOW,
    WORKFLOWS,
    Workflow,
    get_suggested_phases,
    get_workflow,
    is_valid_transition,
)


# -- get_workflow --------------------------------------------------------------

def test_get_workflow_valid_plan():
    wf = get_workflow("plan")
    assert wf.name == "plan"


def test_get_workflow_valid_milestones():
    wf = get_workflow("milestones")
    assert wf.name == "milestones"


def test_get_workflow_invalid_raises():
    with pytest.raises(ValueError, match="Unknown workflow"):
        get_workflow("nonexistent")


def test_get_workflow_lists_valid_in_error():
    with pytest.raises(ValueError, match="plan"):
        get_workflow("bogus")


# -- get_suggested_phases -----------------------------------------------------

def test_get_suggested_phases_intake():
    phases = get_suggested_phases(PLAN_WORKFLOW, "intake")
    assert "plan-spec" in phases
    assert "execute" in phases


def test_get_suggested_phases_plan_spec():
    phases = get_suggested_phases(PLAN_WORKFLOW, "plan-spec")
    assert "plan-review" in phases
    assert "execute" in phases


def test_get_suggested_phases_plan_review():
    phases = get_suggested_phases(PLAN_WORKFLOW, "plan-review")
    assert "plan-spec" in phases
    assert "execute" in phases


def test_get_suggested_phases_execute():
    phases = get_suggested_phases(PLAN_WORKFLOW, "execute")
    assert "plan-review" in phases


def test_get_suggested_phases_milestones_intake_empty():
    phases = get_suggested_phases(MILESTONES_WORKFLOW, "intake")
    assert phases == []


def test_get_suggested_phases_unknown_phase():
    phases = get_suggested_phases(PLAN_WORKFLOW, "nonexistent")
    assert phases == []


# -- is_valid_transition -------------------------------------------------------

def test_is_valid_transition_available_phase():
    assert is_valid_transition(PLAN_WORKFLOW, "intake", "plan-spec") is True


def test_is_valid_transition_self_blocked():
    assert is_valid_transition(PLAN_WORKFLOW, "intake", "intake") is False


def test_is_valid_transition_unavailable_phase():
    assert is_valid_transition(PLAN_WORKFLOW, "intake", "execution") is False


def test_is_valid_transition_any_to_any_within_workflow():
    """Any phase can transition to any other phase in the workflow (user-directed)."""
    phases = list(PLAN_WORKFLOW.available_phases)
    for from_p in phases:
        for to_p in phases:
            if from_p != to_p:
                assert is_valid_transition(PLAN_WORKFLOW, from_p, to_p) is True, \
                    f"{from_p} -> {to_p} should be valid"


def test_is_valid_transition_milestones_to_plan_spec_denied():
    assert is_valid_transition(MILESTONES_WORKFLOW, "intake", "plan-spec") is False


# -- PLAN_WORKFLOW structure ---------------------------------------------------

def test_plan_workflow_structure():
    wf = PLAN_WORKFLOW
    assert wf.name == "plan"
    assert "intake" in wf.available_phases
    assert "plan-spec" in wf.available_phases
    assert "plan-review" in wf.available_phases
    assert "execute" in wf.available_phases
    assert wf.initial_phase == "intake"


def test_plan_workflow_has_phase_descriptions():
    for phase in PLAN_WORKFLOW.available_phases:
        assert phase in PLAN_WORKFLOW.phase_descriptions
        assert len(PLAN_WORKFLOW.phase_descriptions[phase]) > 0


def test_plan_workflow_has_guidance_for_intake():
    assert "intake" in PLAN_WORKFLOW.phase_guidance
    assert len(PLAN_WORKFLOW.phase_guidance["intake"]) > 0


def test_plan_workflow_has_guidance_for_execute():
    assert "execute" in PLAN_WORKFLOW.phase_guidance
    assert len(PLAN_WORKFLOW.phase_guidance["execute"]) > 0


# -- MILESTONES_WORKFLOW structure ---------------------------------------------

def test_milestones_workflow_structure():
    wf = MILESTONES_WORKFLOW
    assert wf.name == "milestones"
    assert wf.available_phases == ("intake",)
    assert wf.initial_phase == "intake"
    assert wf.suggested_transitions == {"intake": []}


def test_milestones_workflow_has_intake_guidance():
    assert "intake" in MILESTONES_WORKFLOW.phase_guidance
    assert len(MILESTONES_WORKFLOW.phase_guidance["intake"]) > 0


# -- Workflow immutability -----------------------------------------------------

def test_workflow_frozen():
    """Workflow instances cannot have fields reassigned (frozen=True)."""
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        PLAN_WORKFLOW.name = "mutated"


# -- WORKFLOWS registry -------------------------------------------------------

def test_workflows_registry_complete():
    assert "plan" in WORKFLOWS
    assert "milestones" in WORKFLOWS


def test_workflows_registry_values_are_workflow_instances():
    for name, wf in WORKFLOWS.items():
        assert isinstance(wf, Workflow)
        assert wf.name == name
