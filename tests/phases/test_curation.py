# Tests for the curation phase module.

from __future__ import annotations

from koan.phases import PhaseContext, curation


def _ctx(**kw) -> PhaseContext:
    defaults = {"run_dir": "/tmp/run", "subagent_dir": "/tmp/sub"}
    defaults.update(kw)
    return PhaseContext(**defaults)


class TestModuleShape:
    def test_total_steps_is_2(self):
        assert curation.TOTAL_STEPS == 2

    def test_role_is_orchestrator(self):
        assert curation.ROLE == "orchestrator"

    def test_scope_is_general(self):
        assert curation.SCOPE == "general"

    def test_step_names(self):
        assert curation.STEP_NAMES == {1: "Inventory", 2: "Memorize"}

    def test_system_prompt_is_nonempty(self):
        assert isinstance(curation.SYSTEM_PROMPT, str)
        assert len(curation.SYSTEM_PROMPT) > 100

    def test_system_prompt_writing_discipline(self):
        # The writing-discipline pillars must be present.
        sp = curation.SYSTEM_PROMPT.lower()
        for term in ("temporally", "attribut", "stand alone", "concretely"):
            assert term in sp, f"missing {term!r} in SYSTEM_PROMPT"

    def test_system_prompt_enumerates_memory_tools(self):
        # Tools must be visible at the role layer.
        sp = curation.SYSTEM_PROMPT
        assert "koan_memorize" in sp
        assert "koan_forget" in sp
        assert "koan_memory_status" in sp

    def test_system_prompt_declares_classification_schema(self):
        sp = curation.SYSTEM_PROMPT
        for label in ("ADD", "UPDATE", "NOOP", "DEPRECATE"):
            assert label in sp, f"schema label {label!r} missing from SYSTEM_PROMPT"

    def test_system_prompt_declares_structural_invariant(self):
        # Propose-then-write must be stated, not buried.
        sp = curation.SYSTEM_PROMPT.lower()
        assert "propose" in sp and "approve" in sp

    def test_system_prompt_declares_read_write_asymmetry(self):
        # Reads of .koan/memory/*.md are allowed; writes are not.
        sp = curation.SYSTEM_PROMPT
        # Reads explicitly allowed and explained:
        assert "Reading individual entries" in sp
        assert ".koan/memory/" in sp
        # Writes explicitly forbidden:
        assert "Do NOT write or delete files under `.koan/`" in sp

    def test_system_prompt_acknowledges_coding_agent_memory(self):
        # CLAUDE.md / AGENTS.md / .cursor/ etc. are a separate, read-only system.
        sp = curation.SYSTEM_PROMPT
        assert "coding agent" in sp.lower()
        assert "CLAUDE.md" in sp
        assert "READ-ONLY" in sp


class TestLifecycle:
    def test_get_next_step_linear(self):
        ctx = _ctx()
        assert curation.get_next_step(1, ctx) == 2

    def test_get_next_step_terminal(self):
        assert curation.get_next_step(2, _ctx()) is None

    def test_validate_all_none(self):
        ctx = _ctx()
        for s in (1, 2):
            assert curation.validate_step_completion(s, ctx) is None


class TestStepHeaders:
    """Every step must render workflow_shape, goal, and tools_this_step blocks
    with a YOU-ARE-HERE marker pointing at the current step."""

    def test_step_1_renders_workflow_shape(self):
        g = curation.step_guidance(1, _ctx())
        text = "\n".join(g.instructions)
        assert "<workflow_shape>" in text
        assert "</workflow_shape>" in text
        # Position marker on step 1.
        # Format: `... step 1 -- Inventory ...   (<-- YOU ARE HERE)` on the step-1 line.
        for line in text.splitlines():
            if "step 1 -- Inventory" in line:
                assert "YOU ARE HERE" in line, f"step-1 line missing marker: {line!r}"
                break
        else:
            raise AssertionError("step-1 line not found in workflow_shape block")
        for line in text.splitlines():
            if "step 2 -- Memorize" in line:
                assert "YOU ARE HERE" not in line, f"step-2 line wrongly marked: {line!r}"

    def test_step_2_renders_workflow_shape(self):
        g = curation.step_guidance(2, _ctx())
        text = "\n".join(g.instructions)
        assert "<workflow_shape>" in text
        for line in text.splitlines():
            if "step 2 -- Memorize" in line:
                assert "YOU ARE HERE" in line, f"step-2 line missing marker: {line!r}"
                break
        else:
            raise AssertionError("step-2 line not found in workflow_shape block")

    def test_both_steps_render_goal_block(self):
        for step in (1, 2):
            text = "\n".join(curation.step_guidance(step, _ctx()).instructions)
            assert "<goal>" in text and "</goal>" in text
            assert "koan_memorize" in text  # the goal names the central tool

    def test_step_1_tools_block_calls_memory_status_first(self):
        text = "\n".join(curation.step_guidance(1, _ctx()).instructions)
        assert "<tools_this_step>" in text
        assert "koan_memory_status" in text
        # FIRST is the load-bearing word.
        assert "FIRST" in text

    def test_step_2_tools_block_lists_write_tools(self):
        text = "\n".join(curation.step_guidance(2, _ctx()).instructions)
        assert "<tools_this_step>" in text
        assert "koan_yield" in text
        assert "koan_memorize" in text
        assert "koan_forget" in text


class TestStep1Inventory:
    def test_title_is_inventory(self):
        g = curation.step_guidance(1, _ctx())
        assert g.title == "Inventory"

    def test_renders_directive_block(self):
        ctx = _ctx(phase_instructions="## Source: postmortem\n\nWork from transcript.")
        g = curation.step_guidance(1, ctx)
        text = "\n".join(g.instructions)
        assert "<directive>" in text
        assert "</directive>" in text
        assert "postmortem" in text
        assert "transcript" in text

    def test_renders_task_block_when_present(self):
        ctx = _ctx(task_description="audit my memory entries for staleness")
        g = curation.step_guidance(1, ctx)
        text = "\n".join(g.instructions)
        assert "<task>" in text
        assert "</task>" in text
        assert "audit my memory entries for staleness" in text

    def test_renders_task_block_placeholder_when_absent(self):
        g = curation.step_guidance(1, _ctx())
        text = "\n".join(g.instructions)
        assert "<task>" in text
        assert "no user task" in text.lower()

    def test_default_directive_when_missing(self):
        g = curation.step_guidance(1, _ctx())
        text = "\n".join(g.instructions)
        assert "No directive provided" in text

    def test_calls_out_memory_status(self):
        g = curation.step_guidance(1, _ctx())
        text = "\n".join(g.instructions)
        assert "koan_memory_status" in text

    def test_acknowledges_coding_agent_memory_as_read_only(self):
        text = "\n".join(curation.step_guidance(1, _ctx()).instructions)
        assert "CLAUDE.md" in text or "coding agent" in text.lower()

    def test_produces_candidate_list_contract(self):
        text = "\n".join(curation.step_guidance(1, _ctx()).instructions)
        assert "candidate list" in text.lower()


class TestStep2Memorize:
    def test_title_is_memorize(self):
        g = curation.step_guidance(2, _ctx())
        assert g.title == "Memorize"

    def test_contains_loop_vocabulary(self):
        text = "\n".join(curation.step_guidance(2, _ctx()).instructions).lower()
        assert "draft" in text
        assert "yield" in text
        assert "apply" in text
        assert "batch" in text

    def test_contains_classification_labels(self):
        text = "\n".join(curation.step_guidance(2, _ctx()).instructions)
        for label in ("ADD", "UPDATE", "NOOP", "DEPRECATE"):
            assert label in text

    def test_references_memory_tools(self):
        text = "\n".join(curation.step_guidance(2, _ctx()).instructions)
        assert "koan_memorize" in text
        assert "koan_forget" in text
        assert "koan_yield" in text

    def test_does_not_redefine_writing_discipline(self):
        # Writing discipline lives in the system prompt; step 2 should not
        # duplicate it. Sentinel: "1-3 sentences" is system-prompt-only.
        text = "\n".join(curation.step_guidance(2, _ctx()).instructions)
        assert "1-3 sentences" not in text

    def test_includes_anticipatory_check(self):
        # The anticipatory check is the central new defense against the
        # "phase ended with zero writes" failure.
        text = "\n".join(curation.step_guidance(2, _ctx()).instructions)
        assert "Anticipatory check" in text
        assert "did you call" in text.lower() or "did you call `koan_memorize`" in text.lower() or "Did you call" in text

    def test_wrap_up_calls_memory_status(self):
        # Wrap-up (folded in from former step 3) calls koan_memory_status
        # for summary regeneration.
        text = "\n".join(curation.step_guidance(2, _ctx()).instructions)
        assert "Wrap-up" in text
        # koan_memory_status appears multiple times; just ensure it's there.
        assert "koan_memory_status" in text

    def test_reports_counts_in_schema_terms(self):
        text = "\n".join(curation.step_guidance(2, _ctx()).instructions).lower()
        assert "added" in text
        assert "updated" in text
        assert "deprecated" in text
        assert "noop" in text
