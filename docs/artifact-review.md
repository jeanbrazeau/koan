# Artifact Review

IPC-based protocol for presenting a written artifact to the user and collecting
feedback. Used by the brief-writer phase; reusable for any future markdown
artifact that requires a review-revise loop before pipeline advancement.

> Parent doc: [architecture.md](./architecture.md)
>
> General IPC patterns: [ipc.md](./ipc.md)

---

## Overview

The artifact review protocol pauses subagent execution while the user reads a
rendered markdown artifact and either accepts it or provides revision feedback.
The review loop is LLM-driven: the subagent writes the artifact, calls
`koan_review_artifact`, revises on feedback, and calls the tool again. The
protocol is stateless — each invocation is a fresh IPC request.

---

## Message Type

Third discriminated union member of `IpcFile`, alongside `ask` and
`scout-request`:

```typescript
interface ArtifactReviewPayload {
  artifactPath: string;  // file path of the artifact (for display label)
  content: string;       // raw markdown content (read from file by the tool)
  description?: string;  // optional context for the reviewer
}

interface ArtifactReviewResponse {
  id: string;
  respondedAt: string;
  feedback: string;      // "Accept" or free-form text
}

interface ArtifactReviewIpcFile {
  type: "artifact-review";
  id: string;            // UUID, for response correlation
  createdAt: string;
  payload: ArtifactReviewPayload;
  response: ArtifactReviewResponse | null;  // null = pending
}
```

---

## Tool Interface

**Name:** `koan_review_artifact`

**Parameters:**
- `path` (string) — file path of the artifact to review
- `description` (string, optional) — context for the reviewer

**Execution flow:**

1. Reads the file at `path` to obtain raw markdown content
2. Creates `ArtifactReviewIpcFile` with content embedded
3. Writes `ipc.json` (atomic tmp-rename)
4. Polls at 500ms intervals until response appears or signal aborts
5. Deletes `ipc.json` in the `finally` block (cleanup even on abort)
6. Returns feedback string to the LLM

**Return values:**

```
User feedback:
Accept

--- or ---

User feedback:
The goals section needs a latency metric. Constraint #3 is too broad.
```

**LLM behavior on response:**
- `"Accept"` → call `koan_complete_step`
- Any other text → revise the artifact, call `koan_review_artifact` again

---

## "Accept" Is Verbatim Text

When the user clicks "Accept" in the web UI, the feedback string sent to the
subagent is literally `"Accept"`. When the user provides feedback, it is their
typed text. Both cases travel the same code path in the tool and the IPC
responder.

The tool interface is uniform: the LLM reads the feedback string and applies
judgment. There are no special fields, no boolean flags, no branching protocol.

**Why:** A dedicated `accepted: boolean` field would create two response shapes
and require the protocol and tool handler to branch. Uniform text keeps the
tool stateless and lets the LLM decide how to proceed rather than executing a
mechanical branch.

---

## Web UI Component

`ArtifactReview.jsx` is mounted when `pendingInput.type === "artifact-review"`.

**Layout:**
```
┌─────────────────────────────────────────┐
│  Review: <artifactPath>                 │
│  ─────────────────────────              │
│  ┌─────────────────────────────────┐    │
│  │  [rendered markdown content]    │    │
│  └─────────────────────────────────┘    │
│  ┌─────────────────────────────────┐    │
│  │ Feedback (optional)             │    │
│  └─────────────────────────────────┘    │
│  [Send Feedback]          [Accept ✓]    │
└─────────────────────────────────────────┘
```

**Behavior:**
- Receives raw markdown from `pendingInput.payload.content`
- Renders client-side via `marked.parse(content)` → `dangerouslySetInnerHTML`
- "Accept" → `POST /api/artifact-review` with `{ token, requestId, feedback: "Accept" }`
- "Send Feedback" → `POST /api/artifact-review` with `{ token, requestId, feedback: textareaValue }` (button disabled when textarea is empty)
- Unmounts when the server clears `pendingInput` after writing the response
- Remounts with updated content when the LLM revises and re-invokes the tool

**Markdown safety:** `marked` does not sanitize by default. Content is
LLM-generated from a local file — not user-provided — so this is acceptable
here. If the pattern is reused for user-provided content, add DOMPurify.

---

## HTTP Endpoint

**`POST /api/artifact-review`**

Validates `token` (403 if mismatch), `requestId`, and `feedback` (must be a
non-null string). Resolves the pending `Promise` in `pendingInputs`. Returns
`{ ok: true }` on success, `{ ok: false, error: "..." }` on validation failure
or missing `requestId`.

---

## SSE Events

| Event | Direction | Payload |
|-------|-----------|---------|
| `artifact-review` | server → browser | `{ requestId, artifactPath, content, description }` |
| `artifact-review-cancelled` | server → browser | `{ requestId }` |

**SSE replay:** `replayState()` replays the `artifact-review` event if a
review is pending when a browser reconnects. Without this, a reconnect during
an active review loses the pending form and stalls the pipeline indefinitely.

---

## Review Loop

```
brief-writer LLM calls koan_review_artifact({ path: "…/brief.md" })
  → tool reads brief.md content
  → tool writes ArtifactReviewIpcFile { type: "artifact-review", response: null }
  → tool enters 500ms poll loop (LLM turn blocked)

ipc-responder detects { type: "artifact-review", response: null }
  → calls webServer.requestArtifactReview(payload, signal)
    → creates Promise in pendingInputs map
    → pushes SSE "artifact-review" event → browser mounts ArtifactReview
    → user reads rendered markdown, submits feedback or clicks Accept
    → POST /api/artifact-review → resolves Promise
  → writes ArtifactReviewResponse { feedback } to ipc.json (atomic)

tool poll detects response !== null
  → breaks loop, deletes ipc.json
  → returns "User feedback:\n{feedback}" to LLM

if feedback === "Accept":
  LLM calls koan_complete_step → phase advances
else:
  LLM revises artifact, calls koan_review_artifact again
  (loop repeats with fresh IPC request)
```

---

## Reusability

The artifact review mechanism is not epic-brief-specific. Any planning phase
that produces a markdown artifact can use the same pattern:

1. Write the artifact to the epic directory
2. Call `koan_review_artifact` with the path
3. Process the feedback string: revise and re-invoke, or accept and advance

Future phases that could use this pattern: core flows document, technical plan,
architecture decision record. Adding a new phase requires only: assigning the
`koan_review_artifact` permission to the new role (in `permissions.ts`) and
implementing the review loop in the phase's step 2 guidance. The web UI
component, HTTP endpoint, and SSE plumbing are shared.
