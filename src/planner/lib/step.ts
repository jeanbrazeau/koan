// Step prompt assembly for koan phase workflows.
//
// formatStep() wraps step guidance with a header and a mandatory invoke-after
// directive. The directive at the END of every step is as important as the
// boot prompt at the beginning: primacy (first message) establishes the
// koan_complete_step habit; recency (last thing in each step) reinforces it.
// Together they make the calling pattern robust across model capability levels.
//
// The `thoughts` parameter on koan_complete_step captures the model's work output
// (analysis, review, findings) as a tool parameter rather than text output. This
// ensures models that can't mix text + tool_call in one response still advance
// the workflow.

export interface StepGuidance {
  title: string;
  instructions: string[];
  // Override the default "WHEN DONE: Call koan_complete_step..." directive.
  // Use for terminal steps that must call a domain tool (e.g. koan_select_story)
  // before koan_complete_step, or for steps where the completion signal differs.
  invokeAfter?: string;
}

// Appended to every step that doesn't override invokeAfter.
// Positioned last for recency — LLMs weight end-of-context instructions heavily.
const DEFAULT_INVOKE = [
  "WHEN DONE: Call koan_complete_step with your findings in the `thoughts` parameter.",
  "Do NOT call this tool until the work described in this step is finished.",
].join("\n");

export function formatStep(g: StepGuidance): string {
  const header = `${g.title}\n${"=".repeat(g.title.length)}\n\n`;
  const body = g.instructions.join("\n");
  const invoke = g.invokeAfter ?? DEFAULT_INVOKE;
  return `${header}${body}\n\n${invoke}`;
}
