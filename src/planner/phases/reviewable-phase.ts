// ReviewablePhase: abstract layer between BasePhase and phases that gate a step
// on user review of an artifact via koan_review_artifact.
//
// Owns the review-tracking state (lastReviewAccepted) and the two event
// listeners that maintain it. Subclasses declare which step is gated and
// which artifact name appears in error messages.

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

import type { Logger } from "../../utils/logger.js";
import type { RuntimeContext } from "../lib/runtime-context.js";
import { EventLog } from "../lib/audit.js";
import { BasePhase } from "./base-phase.js";

export abstract class ReviewablePhase extends BasePhase {
  // Subclasses declare which step requires a passing review and the artifact
  // name used in validation error messages.
  protected abstract readonly reviewGatedStep: number;
  protected abstract readonly reviewedArtifactName: string;

  // Tracks whether the last koan_review_artifact call was accepted by the user.
  // null = never reviewed; true = last review accepted; false = last review had feedback.
  private lastReviewAccepted: boolean | null = null;

  constructor(
    pi: ExtensionAPI,
    ctx: RuntimeContext,
    log?: Logger,
    eventLog?: EventLog,
  ) {
    super(pi, ctx, log, eventLog);

    // When koan_review_artifact is called, mark as pending (not yet accepted).
    pi.on("tool_call", (event) => {
      if (event.toolName === "koan_review_artifact") {
        this.lastReviewAccepted = false;
      }
      return undefined;
    });

    // When koan_review_artifact returns, check the response for ACCEPTED.
    pi.on("tool_result", (event) => {
      if (event.toolName === "koan_review_artifact" && !event.isError) {
        const text = event.content?.[0];
        if (text && "text" in text && typeof text.text === "string") {
          this.lastReviewAccepted = text.text.startsWith("ACCEPTED");
        }
      }
    });
  }

  // Hook for subclasses that need to reset the review gate on step entry
  // (e.g. IntakePhase resets when entering step 5 so only step-5 reviews count).
  protected resetReviewGate(): void {
    this.lastReviewAccepted = null;
  }

  protected async validateStepCompletion(step: number): Promise<string | null> {
    if (step !== this.reviewGatedStep) {
      return super.validateStepCompletion(step);
    }

    if (this.lastReviewAccepted === null) {
      return `You must call koan_review_artifact on ${this.reviewedArtifactName} before completing this step. ` +
        `Write ${this.reviewedArtifactName}, then invoke koan_review_artifact to present it for review.`;
    }
    if (!this.lastReviewAccepted) {
      return `The user provided feedback on your artifact — you must address it. ` +
        `Revise ${this.reviewedArtifactName} based on the feedback, then call koan_review_artifact again. ` +
        `You cannot complete this step until the user accepts.`;
    }

    return super.validateStepCompletion(step);
  }
}
