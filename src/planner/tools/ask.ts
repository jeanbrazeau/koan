// koan_ask_question tool: subagent-side of the file-based IPC ask flow.
// Writes ipc.json, polls until parent writes a response, then returns
// formatted answers to the LLM. The entire poll loop is wrapped in a
// try/finally that deletes ipc.json, guaranteeing cleanup on all exit paths.

import { Type, type Static } from "@sinclair/typebox";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import type { SubagentRef } from "../lib/dispatch.js";
import {
  ipcFileExists,
  writeIpcFile,
  readIpcFile,
  deleteIpcFile,
  createAskRequest,
  type AskAnswerPayload,
} from "../lib/ipc.js";

// -- Tool schema (mirrors pi-ask-tool-extension exactly) --

const OptionItemSchema = Type.Object({
  label: Type.String({ description: "Display label" }),
});

const QuestionItemSchema = Type.Object({
  id: Type.String({ description: "Question id (e.g. auth, cache, priority)" }),
  question: Type.String({ description: "Question text" }),
  options: Type.Array(OptionItemSchema, {
    description: "Available options. Do not include 'Other'.",
    minItems: 1,
  }),
  multi: Type.Optional(Type.Boolean({ description: "Allow multi-select" })),
  recommended: Type.Optional(
    Type.Number({ description: "0-indexed recommended option. '(Recommended)' is shown automatically." }),
  ),
});

const AskParamsSchema = Type.Object({
  questions: Type.Array(QuestionItemSchema, { description: "Questions to ask", minItems: 1 }),
});

type AskParams = Static<typeof AskParamsSchema>;

// -- Result formatting --

interface QuestionResult {
  id: string;
  question: string;
  options: string[];
  multi: boolean;
  selectedOptions: string[];
  customInput?: string;
}

function formatSelectionForSummary(result: QuestionResult): string {
  const hasSelectedOptions = result.selectedOptions.length > 0;
  const hasCustomInput = Boolean(result.customInput);

  if (!hasSelectedOptions && !hasCustomInput) return "(cancelled)";

  if (hasSelectedOptions && hasCustomInput) {
    const selectedPart = result.multi
      ? `[${result.selectedOptions.join(", ")}]`
      : result.selectedOptions[0];
    return `${selectedPart} + Other: "${result.customInput}"`;
  }

  if (hasCustomInput) return `"${result.customInput}"`;
  if (result.multi) return `[${result.selectedOptions.join(", ")}]`;
  return result.selectedOptions[0] ?? "(no selection)";
}

function formatQuestionContext(result: QuestionResult, index: number): string {
  const lines: string[] = [
    `Question ${index + 1} (${result.id})`,
    `Prompt: ${result.question}`,
    "Options:",
    ...result.options.map((o, i) => `  ${i + 1}. ${o}`),
    "Response:",
  ];

  const hasSelectedOptions = result.selectedOptions.length > 0;
  const hasCustomInput = Boolean(result.customInput);

  if (!hasSelectedOptions && !hasCustomInput) {
    lines.push("  Selected: (cancelled)");
    return lines.join("\n");
  }

  if (hasSelectedOptions) {
    const text = result.multi
      ? `[${result.selectedOptions.join(", ")}]`
      : result.selectedOptions[0];
    lines.push(`  Selected: ${text}`);
  }

  if (hasCustomInput) {
    if (!hasSelectedOptions) lines.push("  Selected: Other (type your own)");
    lines.push(`  Custom input: ${result.customInput}`);
  }

  return lines.join("\n");
}

function buildSessionContent(results: QuestionResult[]): string {
  const summaryLines = results.map((r) => `${r.id}: ${formatSelectionForSummary(r)}`).join("\n");
  const contextBlocks = results.map((r, i) => formatQuestionContext(r, i)).join("\n\n");
  return `User answers:\n${summaryLines}\n\nAnswer context:\n${contextBlocks}`;
}

function buildQuestionResults(
  params: AskParams,
  answers: AskAnswerPayload["answers"],
): QuestionResult[] {
  return params.questions.map((q) => {
    const answer = answers.find((a) => a.id === q.id) ?? { id: q.id, selectedOptions: [] };
    return {
      id: q.id,
      question: q.question,
      options: q.options.map((o) => o.label),
      multi: q.multi ?? false,
      selectedOptions: answer.selectedOptions,
      customInput: answer.customInput,
    };
  });
}

// -- Tool registration --

const ASK_TOOL_DESCRIPTION = `
Ask the user for clarification when a choice materially affects the outcome.

- Use when multiple valid approaches have different trade-offs.
- Prefer 2-5 concise options.
- Use multi=true when multiple answers are valid.
- Use recommended=<index> (0-indexed) to mark the default option.
- You can ask multiple related questions in one call using questions[].
- Do NOT include an 'Other' option; UI adds it automatically.
`.trim();

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function registerAskTools(pi: ExtensionAPI, subagentRef: SubagentRef): void {
  pi.registerTool({
    name: "koan_ask_question",
    label: "Ask question",
    description: ASK_TOOL_DESCRIPTION,
    parameters: AskParamsSchema,

    async execute(_toolCallId, params, signal) {
      const askParams = params as AskParams;
      const dir = subagentRef.dir;

      if (!dir) {
        return {
          content: [{ type: "text" as const, text: "Error: koan_ask_question is only available in subagent context." }],
          details: undefined,
        };
      }

      if (await ipcFileExists(dir)) {
        return {
          content: [{ type: "text" as const, text: "Error: A question request is already pending." }],
          details: undefined,
        };
      }

      const ipc = createAskRequest(askParams);
      await writeIpcFile(dir, ipc);

      let aborted = false;
      const onAbort = () => { aborted = true; };
      if (signal) {
        signal.addEventListener("abort", onAbort, { once: true });
      }

      type PollResult = "answered" | "cancelled" | "aborted" | "file-gone";
      let pollResult: PollResult = "file-gone";
      let answeredPayload: AskAnswerPayload | null = null;

      try {
        while (!aborted) {
          await sleep(500);
          if (signal?.aborted) {
            aborted = true;
            break;
          }

          const current = await readIpcFile(dir);
          if (current === null) {
            pollResult = "file-gone";
            break;
          }

          if (current.response !== null && current.response.id === ipc.request.id) {
            if (current.response.cancelled) {
              pollResult = "cancelled";
            } else {
              pollResult = "answered";
              answeredPayload = current.response.payload;
            }
            break;
          }
        }

        if (aborted) {
          pollResult = "aborted";
        }
      } finally {
        await deleteIpcFile(dir);
      }

      switch (pollResult) {
        case "answered": {
          const results = buildQuestionResults(askParams, answeredPayload?.answers ?? []);
          return {
            content: [{ type: "text" as const, text: buildSessionContent(results) }],
            details: undefined,
          };
        }
        case "cancelled":
          return {
            content: [{ type: "text" as const, text: "The user declined to answer. Proceed with your best judgment." }],
            details: undefined,
          };
        case "aborted":
          return {
            content: [{ type: "text" as const, text: "The question was aborted." }],
            details: undefined,
          };
        case "file-gone":
          return {
            content: [{ type: "text" as const, text: "The question was cancelled." }],
            details: undefined,
          };
      }
    },
  });
}
