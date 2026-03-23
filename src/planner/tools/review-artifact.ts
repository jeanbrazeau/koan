// IPC-based tool: koan_review_artifact.
// Presents a written markdown artifact for human review via file-based IPC,
// pausing subagent execution until the user responds with feedback or accepts.
//
// The review loop is LLM-driven: if the user provides feedback, the LLM revises
// the artifact and invokes this tool again. The tool itself is stateless — it
// reads the artifact, presents it, and returns the user's response verbatim.

import * as path from "node:path";

import { Type, type Static } from "@sinclair/typebox";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import type { RuntimeContext } from "../lib/runtime-context.js";
import { readArtifact } from "../epic/artifacts.js";
import {
  ipcFileExists,
  writeIpcFile,
  createArtifactReviewRequest,
  pollIpcUntilResponse,
  type ArtifactReviewIpcFile,
} from "../lib/ipc.js";

// -- Schema --

const ReviewArtifactSchema = Type.Object({
  path: Type.String({ description: "File path of the artifact to present for review" }),
  description: Type.Optional(Type.String({ description: "Optional context for the reviewer (e.g. 'This is the epic brief')" })),
});

type ReviewArtifactParams = Static<typeof ReviewArtifactSchema>;

// -- Tool description --

const REVIEW_ARTIFACT_DESCRIPTION = `
Present a written artifact (markdown file) for human review.

The user will see the rendered artifact content and can either accept it
or provide feedback. The tool returns ACCEPTED or REVISION REQUESTED with
the user's feedback text. See the review protocol in your system prompt
for how to handle each response.

Parameters:
- path: the file path of the artifact to review
- description: optional context for the reviewer
`.trim();

// -- Execute logic --

type ToolResult = { content: Array<{ type: "text"; text: string }>; details: undefined };

export async function executeReviewArtifact(
  params: ReviewArtifactParams,
  epicDir: string | null,
  subagentDir: string | null,
  signal?: AbortSignal | null,
): Promise<ToolResult> {
  const dir = subagentDir;

  if (!dir) {
    return {
      content: [{ type: "text" as const, text: "Error: koan_review_artifact is only available in subagent context." }],
      details: undefined,
    };
  }

  if (!epicDir) {
    return {
      content: [{ type: "text" as const, text: "Error: Epic directory is not set." }],
      details: undefined,
    };
  }

  if (await ipcFileExists(dir)) {
    return {
      content: [{ type: "text" as const, text: "Error: An IPC request is already pending." }],
      details: undefined,
    };
  }

  let content: string;
  try {
    const relativePath = path.relative(epicDir, params.path);
    content = await readArtifact(epicDir, relativePath);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      content: [{ type: "text" as const, text: `Error: Could not read artifact at "${params.path}": ${msg}` }],
      details: undefined,
    };
  }

  const ipc = createArtifactReviewRequest({
    artifactPath: params.path,
    content,
    description: params.description,
  });
  await writeIpcFile(dir, ipc);

  const { outcome, ipc: answeredIpc } = await pollIpcUntilResponse(dir, ipc, signal);

  switch (outcome) {
    case "answered": {
      const artifactIpc = answeredIpc as ArtifactReviewIpcFile;
      const feedback = artifactIpc.response?.feedback || "(no feedback)";
      const accepted = feedback.trim().toLowerCase() === "accept";

      if (accepted) {
        return {
          content: [{ type: "text" as const, text: "ACCEPTED — The user approved this artifact." }],
          details: undefined,
        };
      }

      return {
        content: [{ type: "text" as const, text:
          "REVISION REQUESTED — The user provided feedback:\n\n" + feedback }],
        details: undefined,
      };
    }
    case "aborted":
      return {
        content: [{ type: "text" as const, text: "The review was aborted." }],
        details: undefined,
      };
    case "file-gone":
    default:
      return {
        content: [{ type: "text" as const, text: "The review was cancelled." }],
        details: undefined,
      };
  }
}

// -- Tool registration --

export function registerReviewArtifactTool(pi: ExtensionAPI, ctx: RuntimeContext): void {
  pi.registerTool({
    name: "koan_review_artifact",
    label: "Review artifact",
    description: REVIEW_ARTIFACT_DESCRIPTION,
    parameters: ReviewArtifactSchema,

    async execute(_toolCallId, params, signal) {
      return executeReviewArtifact(params as ReviewArtifactParams, ctx.epicDir, ctx.subagentDir, signal);
    },
  });
}
