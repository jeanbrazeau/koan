export const PLAN_DESIGN_CONTEXT_TRIGGER_ID = "plan-design-context-trigger";
export const PLAN_DOCS_CONTEXT_TRIGGER_ID = "plan-docs-context-trigger";

function exampleCommands(conversationPath: string, keywordRegex: string): string[] {
  return [
    "Example commands (starting points; adapt as needed):",
    `  CONV=\"${conversationPath}\"`,
    "  rg -n '\"role\":\"user\"|\"toolCall\"|koan_plan|phase|decision|constraint|tradeoff' \"$CONV\"",
    "  jq -cr 'select(.type==\"message\" and (.message.role==\"user\" or .message.role==\"assistant\")) | {ts:.timestamp, role:.message.role, text:([.message.content[]? | select(.type==\"text\") | .text] | join(\"\\n\"))} | select(.text != \"\")' \"$CONV\"",
    `  jq -cr --arg re \"${keywordRegex}\" 'select(.type==\"message\") | {role:.message.role, texts:[.message.content[]? | select(.type==\"text\") | .text]} | .texts[]? as $t | select($t|test($re;\"i\")) | {role, text:$t}' \"$CONV\"`,
    "  jq -r 'select(.type==\"message\" and .message.role==\"assistant\") | .message.content[]? | select(.type==\"toolCall\" and .name==\"read\") | .arguments.path' \"$CONV\" | sort -u",
  ];
}

export function buildPlanDesignContextTrigger(conversationPath: string): string[] {
  return [
    "Use conversation context from the exact JSONL file path below.",
    `Conversation file (absolute path): ${conversationPath}`,
    "",
    "This phase requires conversation grounding by default.",
    "Before finalizing this step, open conversation.jsonl and extract:",
    "  - task intent and acceptance shape",
    "  - user constraints and preferences",
    "  - prior rejected options and decision rationale",
    "",
    "Read selectively (do not scan blindly end-to-end):",
    "  - prioritize type='message' with role='user'/'assistant'",
    "  - use type='compaction' entries for summarized earlier context",
    "",
    ...exampleCommands(
      conversationPath,
      "phase|planner|koan_plan|constraint|decision|tradeoff|acceptance",
    ),
    "",
    "conversation.jsonl is read-only.",
  ];
}

export function buildPlanDocsContextTrigger(conversationPath: string): string[] {
  return [
    "Use conversation context from the exact JSONL file path below when needed.",
    `Conversation file (absolute path): ${conversationPath}`,
    "",
    "Consult conversation.jsonl when plan artifacts do not fully explain:",
    "  - why a decision was made",
    "  - which tradeoff was accepted",
    "  - what implicit project knowledge should be documented",
    "  - how user preferences should affect docs emphasis",
    "",
    "Start from plan artifacts first; use conversation.jsonl to fill rationale gaps.",
    "Read selectively (message + compaction entries), not exhaustively.",
    "",
    ...exampleCommands(
      conversationPath,
      "decision|tradeoff|why|constraint|docs|readme|diagram|comment|rationale",
    ),
    "",
    "conversation.jsonl is read-only.",
  ];
}
