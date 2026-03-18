// Scout phase prompts — 4-step investigation workflow:
//   Step 1: Orient    (identify entry points, plan investigation)
//   Step 2: Investigate (deep read, trace dependencies, gather evidence)
//   Step 3: Verify & Analyze (re-read cited files, organize findings)
//   Step 4: Report    (write findings.md with verified facts)
//
// The system prompt establishes the investigator identity but contains no task
// details — a scout doesn't know its question until koan_complete_step returns
// step 1 guidance. This is intentional: including the question in the system
// prompt or spawn prompt would front-load instructions before the tool-call
// pattern is established, causing weaker models to answer inline and exit.
//
// The verification step (3) is the key addition over the original single-step
// design. Cheap models hallucinate file paths and API names. Re-reading every
// file before reporting catches confabulation before it reaches the intake-LLM.

import type { StepGuidance } from "../../lib/step.js";

export const SCOUT_STEP_NAMES: Record<number, string> = {
  1: "Orient",
  2: "Investigate",
  3: "Verify & Analyze",
  4: "Report",
};

export function scoutSystemPrompt(): string {
  return `You are a codebase investigator. You are assigned one narrow, specific question about a codebase. Your job is to methodically explore the relevant code, verify your findings, and write a grounded report.

## Your role

You find facts. You do NOT interpret, recommend, or opine.

## Strict rules

- MUST answer only the assigned question. Do not expand scope.
- MUST write only factual observations: what the code does, what files exist, what patterns are present.
- MUST NOT produce recommendations or suggestions of any kind.
- MUST NOT express opinions about code quality.
- MUST NOT produce implementation plans or design ideas.
- MUST include file paths and line numbers when referencing code.
- MUST include relevant code excerpts (verbatim) to support each finding.
- SHOULD be thorough within the question scope: follow references, check related files.
- SHOULD note explicitly when something is NOT present (e.g., "No tests found for this module").

## Output file

You write a single markdown file with your findings. The file location and format are provided in your final step.

## Tools available

- All read tools (read, bash, grep, glob, find, ls) — for reading the codebase.
- \`write\` / \`edit\` — for writing the output file only.
- \`koan_complete_step\` — to signal completion.`;
}

export function scoutStepGuidance(
  step: number,
  question: string,
  outputFile: string,
  investigatorRole: string,
): StepGuidance {
  switch (step) {
    case 1:
      return {
        title: SCOUT_STEP_NAMES[1],
        instructions: [
          "Understand the question and identify where to look in the codebase.",
          "",
          "## Your Assignment",
          "",
          ...(question ? [`**Question:** ${question}`] : []),
          ...(investigatorRole ? [`**Your investigator role:** ${investigatorRole}`] : []),
          "",
          "## Actions",
          "",
          "1. Parse the question: what exactly are you being asked to find?",
          "2. Identify search terms, file patterns, and likely directory locations.",
          "3. Use grep, glob, find, or ls to locate 3–8 candidate entry-point files.",
          "4. Do NOT read file contents yet — just identify targets.",
          "",
          "Report your entry points and investigation plan in the `thoughts` parameter.",
        ],
      };

    case 2:
      return {
        title: SCOUT_STEP_NAMES[2],
        instructions: [
          "Read the entry-point files and trace through the code to answer the question.",
          "",
          "## Actions",
          "",
          "1. Read each entry-point file identified in the previous step.",
          "2. Follow imports, cross-references, and call chains to related files.",
          "3. For each relevant finding, note the file path, line numbers, and a verbatim code excerpt.",
          "4. Be thorough: do not stop at the first partial answer. Check related files.",
          "5. If a file turns out to be irrelevant, move on — do not force-fit it.",
          "",
          "Report your findings and the files you read in the `thoughts` parameter.",
        ],
      };

    case 3:
      return {
        title: SCOUT_STEP_NAMES[3],
        instructions: [
          "Verify every claim you plan to report and organize your findings.",
          "",
          "## Verification",
          "",
          "1. Re-read every file you plan to cite in your report.",
          "2. Confirm that file paths are correct and the code excerpts match the actual content.",
          "3. If you find a discrepancy, correct it. If a file does not exist, remove the reference.",
          "",
          "## Analysis",
          "",
          "4. Organize your verified findings into a clear answer to the original question.",
          "5. Identify any gaps — things you could not determine or areas you could not access.",
          "6. Note anything that is explicitly NOT present (missing tests, missing config, etc.).",
          "",
          "Report your verified findings and any gaps in the `thoughts` parameter.",
        ],
      };

    case 4:
      return {
        title: SCOUT_STEP_NAMES[4],
        instructions: [
          "Write your findings to the output file.",
          "",
          `**Output file:** ${outputFile}`,
          "",
          "Write a markdown file with these exact sections:",
          "",
          "## Question",
          "Restate the assigned question verbatim.",
          "",
          "## Findings",
          "Factual observations that answer the question. Use sub-sections if the answer has multiple parts.",
          "Cite file paths and line numbers for every claim. Include code snippets where relevant.",
          "Every finding must be backed by a file you actually read — no inferred claims.",
          "",
          "## Files Examined",
          "List every file you read during this investigation.",
          "",
          "## Gaps",
          "Note anything you could not determine. If no gaps, write: (none)",
        ],
      };

    default:
      return {
        title: `Step ${step}`,
        instructions: [`Execute step ${step}.`],
      };
  }
}
