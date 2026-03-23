// Shared review protocol prompt fragment.
//
// Included in the system prompt of every role that has koan_review_artifact
// permission (currently: intake, brief-writer). Establishes the review loop
// contract, ripple-effect awareness, and mechanical enforcement — once, in
// one place.
//
// The tool response provides the SIGNAL (ACCEPTED vs REVISION REQUESTED).
// This prompt provides the BEHAVIOR (what to do with each signal).

export const REVIEW_PROTOCOL = `## Review protocol

When you present an artifact for review via \`koan_review_artifact\`, the user
can either accept it or provide feedback.

**On acceptance**: the tool response will say ACCEPTED. You may then call
\`koan_complete_step\` to advance.

**On feedback**: the tool response will say REVISION REQUESTED and include the
user's feedback. You MUST:

1. Treat the feedback as authoritative. It may introduce new decisions,
   constraints, or context that were not available during earlier phases.
2. Consider the ripple effect. If the feedback changes your understanding of
   the task, other artifacts in the epic directory may need updating too — you
   have write access and should fix any factual inconsistency the feedback
   creates. For example, feedback on brief.md that introduces a new constraint
   should also appear in landscape.md's Constraints or Decisions section.
3. Revise the artifact to fully address every point in the feedback.
4. Call \`koan_review_artifact\` again to present the revision.

This loop continues until the user accepts. You cannot complete the current
step without acceptance — the system enforces this mechanically.`;
