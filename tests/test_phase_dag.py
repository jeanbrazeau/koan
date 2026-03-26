# Tests for koan/lib/phase_dag.py -- phase transition DAG.

from koan.lib.phase_dag import (
    IMPLEMENTED_PHASES,
    PHASE_DESCRIPTIONS,
    PHASE_TRANSITIONS,
    get_successor_phases,
    is_auto_advance,
    is_stub_phase,
    is_valid_transition,
)

ALL_PHASES = [
    "intake",
    "brief-generation",
    "core-flows",
    "tech-plan",
    "ticket-breakdown",
    "cross-artifact-validation",
    "execution",
    "implementation-validation",
    "completed",
]


# -- PHASE_TRANSITIONS completeness -------------------------------------------

def test_all_phases_have_transition_entries():
    for phase in ALL_PHASES:
        assert phase in PHASE_TRANSITIONS, f"{phase} missing from PHASE_TRANSITIONS"


def test_completed_has_no_successors():
    assert PHASE_TRANSITIONS["completed"] == []


def test_intake_has_two_successors():
    assert len(PHASE_TRANSITIONS["intake"]) == 2


# -- get_successor_phases ------------------------------------------------------

def test_successor_phases_intake():
    assert get_successor_phases("intake") == ["brief-generation", "core-flows"]


def test_successor_phases_brief_generation():
    assert get_successor_phases("brief-generation") == ["core-flows"]


def test_successor_phases_completed():
    assert get_successor_phases("completed") == []


# -- is_auto_advance -----------------------------------------------------------

def test_auto_advance_false_for_intake():
    assert is_auto_advance("intake") is False


def test_auto_advance_true_for_single_successor_phases():
    single_successor = [p for p in ALL_PHASES if len(PHASE_TRANSITIONS[p]) == 1]
    for phase in single_successor:
        assert is_auto_advance(phase) is True, f"{phase} should auto-advance"


def test_auto_advance_false_for_completed():
    assert is_auto_advance("completed") is False


# -- is_stub_phase -------------------------------------------------------------

def test_not_stub_for_implemented_phases():
    for phase in IMPLEMENTED_PHASES:
        assert is_stub_phase(phase) is False, f"{phase} should not be a stub"


def test_not_stub_for_completed():
    assert is_stub_phase("completed") is False


def test_not_stub_for_implementation_validation():
    assert is_stub_phase("implementation-validation") is False


# -- is_valid_transition -------------------------------------------------------

def test_valid_transition_intake_to_brief():
    assert is_valid_transition("intake", "brief-generation") is True


def test_valid_transition_intake_to_core_flows():
    assert is_valid_transition("intake", "core-flows") is True


def test_valid_transition_full_linear_path():
    linear = [
        ("brief-generation", "core-flows"),
        ("core-flows", "tech-plan"),
        ("tech-plan", "ticket-breakdown"),
        ("ticket-breakdown", "cross-artifact-validation"),
        ("cross-artifact-validation", "execution"),
        ("execution", "implementation-validation"),
        ("implementation-validation", "completed"),
    ]
    for from_p, to_p in linear:
        assert is_valid_transition(from_p, to_p) is True, f"{from_p} -> {to_p} should be valid"


def test_invalid_transition_skip():
    assert is_valid_transition("intake", "tech-plan") is False


def test_invalid_transition_backward():
    assert is_valid_transition("core-flows", "intake") is False


def test_invalid_transition_from_completed():
    assert is_valid_transition("completed", "intake") is False


# -- PHASE_DESCRIPTIONS --------------------------------------------------------

def test_all_phases_have_descriptions():
    for phase in ALL_PHASES:
        assert phase in PHASE_DESCRIPTIONS, f"{phase} missing from PHASE_DESCRIPTIONS"
        assert isinstance(PHASE_DESCRIPTIONS[phase], str)
        assert len(PHASE_DESCRIPTIONS[phase]) > 0


# -- IMPLEMENTED_PHASES --------------------------------------------------------

def test_implemented_phases_content():
    expected = {
        "intake",
        "brief-generation",
        "core-flows",
        "tech-plan",
        "ticket-breakdown",
        "cross-artifact-validation",
        "execution",
    }
    assert IMPLEMENTED_PHASES == expected
