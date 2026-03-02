// Fix-phase step guidance for plan-design targeted repair (dynamic N steps).
//
// totalSteps = 2 + failures.length. Step 1 reads all failures (read-only).
// Steps 2..N+1 each fix one QR item (mutations enabled). Step N+2 reviews
// all fixes (read-only). The step counter IS the item iterator:
// failures[step - 2] gives the current item in the per-item range.
//
// Step 1 explicitly prohibits mutations: without this constraint the LLM
// tends to apply the first fix it identifies without reading all failures,
// producing cascading corrections that address symptoms rather than root causes.

import type { QRItem } from "../../qr/types.js";
import type { StepGuidance } from "../../lib/step.js";
import { buildPlanDesignContextTrigger } from "../../lib/conversation-trigger.js";

// Serializes FAIL items as an XML block injected into the step 1 prompt.
// XML structure mirrors how pi-native tools present structured data.
export function formatFailuresXml(failures: ReadonlyArray<QRItem>): string {
  const items = failures.map((f) => [
    `  <item id="${f.id}" severity="${f.severity}" scope="${f.scope}">`,
    `    <check>${f.check}</check>`,
    f.finding ? `    <finding>${f.finding}</finding>` : `    <finding/>`,
    `  </item>`,
  ].join("\n")).join("\n");

  return [
    "<qr_failures>",
    items,
    "</qr_failures>",
  ].join("\n");
}

// Dynamic step names. Step 1 and the final step have fixed names;
// per-item steps show the QR item ID so the widget displays
// "Step 3/7: Fix D-001" rather than a generic label. The audit log
// uses these names to distinguish per-item transitions.
export function fixStepName(
  step: number,
  totalSteps: number,
  item?: QRItem,
): string {
  if (step === 1) return "Understand QR Failures";
  if (step === totalSteps) return "Review & Finalize";
  return item ? `Fix ${item.id}` : `Fix item ${step - 1}`;
}

// Appends fix workflow instructions to the base architect system prompt.
// The structured STEP LAYOUT section uses indentation to visually separate
// the three phases so the LLM internalizes the one-at-a-time constraint
// from the system prompt rather than discovering it at step 2.
export function buildFixSystemPrompt(
  basePrompt: string,
  failureCount: number,
  totalSteps: number,
): string {
  return [
    basePrompt,
    "",
    "---",
    "",
    `WORKFLOW: ${totalSteps}-STEP PLAN-DESIGN FIX`,
    "",
    `You are fixing ${failureCount} QR failure(s) in an existing plan.`,
    "",
    "STEP LAYOUT:",
    "  Step 1: Read all failures. Understand scope and interactions. READ-ONLY.",
    `  Steps 2-${totalSteps - 1}: Fix ONE failure per step. Each step targets exactly one item.`,
    `  Step ${totalSteps}: Review all fixes against original failures. READ-ONLY.`,
    "",
    "Each step's instructions appear as a tool result after you call koan_complete_step.",
    "Put your work output in the `thoughts` parameter of koan_complete_step.",
    "",
    "CONSTRAINTS:",
    "  - Fix ONLY the identified failures",
    "  - Each per-item step targets exactly ONE failure -- do not fix other items",
    "  - Prefer updating existing entities over adding new ones",
    "  - Do not restructure the plan beyond what failures require",
  ].join("\n");
}

// Three categories of step: understand (step 1), per-item fix
// (2 <= step < totalSteps), and review (step === totalSteps).
// The step counter IS the item iterator -- no separate cursor needed.
export function fixStepGuidance(
  step: number,
  totalSteps: number,
  opts?: { item?: QRItem; allFailuresXml?: string; conversationPath?: string },
): StepGuidance {
  if (step === 1)
    return fixStep1Guidance(totalSteps, opts?.allFailuresXml ?? "", opts?.conversationPath);
  if (step === totalSteps) return fixFinalStepGuidance(totalSteps);
  return fixItemStepGuidance(step, totalSteps, opts?.item);
}

// Step 1 prompt reframes analysis as "note interactions" rather than
// "plan your fixes mentally" to avoid priming the LLM for batch application.
// The one-at-a-time delivery is stated explicitly so the LLM expects
// per-item steps rather than a single batch-fix step.
function fixStep1Guidance(
  totalSteps: number,
  failuresXml: string,
  conversationPath?: string,
): StepGuidance {
  const itemCount = totalSteps - 2;
  return {
    title: `Step 1/${totalSteps}: Understand QR Failures`,
    instructions: [
      "QR FAILURES TO FIX:",
      "",
      failuresXml,
      "",
      ...buildPlanDesignContextTrigger(conversationPath ?? "<planDir>/conversation.jsonl"),
      "",
      `There are ${itemCount} failure(s). You will fix them one at a time`,
      `in steps 2 through ${totalSteps - 1}. Each step presents a single item.`,
      "",
      "For each failing item:",
      "  - Identify the scope (which milestone, decision, or intent)",
      "  - Understand what the check requires",
      "  - Read the finding to understand why it failed",
      "",
      "Use getter tools to inspect scoped entities:",
      "  - koan_get_plan: overview, structure, decisions",
      "  - koan_get_milestone: milestone details and intents",
      "  - koan_get_decision: decision rationale",
      "  - koan_get_intent: intent definition",
      "",
      "Note interactions between failures:",
      "  - Do any failures share the same entity scope?",
      "  - Could fixing one affect another's context?",
      "",
      "This is a READ-ONLY step. Do not apply any changes.",
    ],
  };
}

// Per-item fix step. Shows only the single item being fixed so the LLM
// focuses on one failure rather than attempting batch fixes that produce
// cascading corrections. Mutations are enabled by the step gate in
// fix-phase.ts for this range.
//
// Positional context ("FIX ITEM N OF M") grounds the LLM in the sequence,
// matching the reference impl's "item {idx} of {total}" pattern. The
// explicit anti-batch gate ("Do not fix other failures") is the prompt-level
// complement to the code-level step gate that blocks mutations outside the
// per-item range.
function fixItemStepGuidance(
  step: number,
  totalSteps: number,
  item?: QRItem,
): StepGuidance {
  // Defensive fallbacks: handleStepComplete guarantees item is present for
  // per-item steps (failures[next-2] is in-bounds), but the function signature
  // accepts optional to keep it callable from tests or future call sites.
  const itemXml = item ? formatFailuresXml([item]) : "<qr_failures/>";
  const itemLabel = item?.id ?? `item ${step - 1}`;
  const itemIdx = step - 1;
  const itemCount = totalSteps - 2;

  return {
    title: `Step ${step}/${totalSteps}: Fix ${itemLabel}`,
    instructions: [
      `FIX ITEM ${itemIdx} OF ${itemCount}:`,
      "",
      itemXml,
      "",
      "Apply a targeted fix for this failure using your analysis from step 1.",
      "",
      "Available mutation tools:",
      "  - koan_set_overview / koan_set_constraints / koan_set_invisible_knowledge",
      "  - koan_set_milestone_* / koan_set_intent / koan_set_decision",
      "  - koan_add_milestone / koan_add_intent / koan_add_decision (if needed)",
      "",
      "RULES:",
      "  - Fix ONLY this failure. Do not fix other failures in this step.",
      "  - Prefer updating existing entities over adding new ones",
      "  - Do not restructure the plan beyond what this failure requires",
    ],
  };
}

// Final review step. Accepts only totalSteps because the call site guard
// (step === totalSteps) guarantees identity. A two-parameter form would
// create a hidden contract ("pass equal values") with no type enforcement.
//
// "All per-item fixes are complete" explicitly closes the mutation phase
// and establishes the read-only review frame. "This step is READ-ONLY"
// is the prompt-level complement to the step gate blocking mutations.
function fixFinalStepGuidance(totalSteps: number): StepGuidance {
  return {
    title: `Step ${totalSteps}/${totalSteps}: Review & Finalize`,
    instructions: [
      "All per-item fixes are complete. This step is READ-ONLY.",
      "",
      "Call koan_get_plan to read the current plan state.",
      "",
      "Verify each fix:",
      "  - Does the fix address the specific check that failed?",
      "  - Are previously passing items unaffected?",
      "  - Is the plan internally consistent?",
      "",
      "Summarize in the `thoughts` parameter of koan_complete_step:",
      "  - Which failures were fixed and how",
      "  - Any remaining concerns or regression risks",
    ],
    // The review step requires reading the plan before completing --
    // the review is meaningless without it. The custom invokeAfter
    // enforces this sequencing explicitly.
    invokeAfter: [
      "WHEN DONE: First call koan_get_plan to confirm the final plan state.",
      "Then call koan_complete_step with your review summary in the `thoughts` parameter.",
      "Do NOT call koan_complete_step before calling koan_get_plan.",
    ].join("\n"),
  };
}
