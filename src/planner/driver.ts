// Epic pipeline driver — deterministic coordinator for the full epic lifecycle.
// Reads JSON state and exit codes; applies routing rules. Never parses markdown.
// Per AGENTS.md: driver owns .json state; LLMs own .md files.

import type { ExtensionUIContext } from "@mariozechner/pi-coding-agent";

import {
  loadEpicState,
  saveEpicState,
  loadStoryState,
  saveStoryState,
  loadAllStoryStates,
  ensureSubagentDirectory,
  ensureStoryDirectory,
  discoverStoryIds,
} from "./epic/state.js";
import {
  spawnIntake,
  spawnDecomposer,
  spawnOrchestrator,
  spawnPlanner,
  spawnExecutor,
} from "./subagent.js";
import type { Logger } from "../utils/logger.js";
import type { StoryState } from "./epic/types.js";
import { readRecentLogs, readProjection } from "./lib/audit.js";
import { EpicWidgetController } from "./ui/epic-widget.js";
import { reviewStorySketches } from "./ui/spec-review.js";

// ---------------------------------------------------------------------------
// Routing
// ---------------------------------------------------------------------------

interface RoutingDecision {
  action: "execute" | "retry" | "complete" | "error";
  storyId?: string;
  error?: string;
}

// Simplified routing — no escalation path per §11.3.1 and §11.6.3.
// Retry budget exhaustion is handled inside the retry case (skip + notify).
function routeFromState(stories: StoryState[], log: Logger): RoutingDecision {
  // Priority order:
  // 1. Any story with status 'retry'? → check budget, then re-execute or skip
  // 2. Any story with status 'selected'? → execute it
  // 3. All stories terminal? → complete
  // 4. None of the above → error

  const retry = stories.find((s) => s.status === "retry");
  if (retry) {
    log("Routing: retry", { storyId: retry.storyId });
    return { action: "retry", storyId: retry.storyId };
  }

  const selected = stories.find((s) => s.status === "selected");
  if (selected) {
    log("Routing: execute", { storyId: selected.storyId });
    return { action: "execute", storyId: selected.storyId };
  }

  const terminal = new Set(["done", "skipped"]);
  const allTerminal = stories.every((s) => terminal.has(s.status));
  if (allTerminal && stories.length > 0) {
    log("Routing: complete", { total: stories.length });
    return { action: "complete" };
  }

  return {
    action: "error",
    error: "No actionable story state found (orchestrator may have exited without a routing decision)",
  };
}

// ---------------------------------------------------------------------------
// Active widget polling (§11.6.1)
// ---------------------------------------------------------------------------

// Starts a 2s polling interval that reads the active subagent's projection
// and log tail, then updates the widget. Interval is unref'd so it does not
// prevent process exit.
function startActivePolling(
  activeSubagentDir: string,
  widget: EpicWidgetController,
  startedAt: number,
  role: string,
  storyId?: string,
): () => void {
  const timer = setInterval(async () => {
    try {
      const [projection, logs] = await Promise.all([
        readProjection(activeSubagentDir),
        readRecentLogs(activeSubagentDir),
      ]);
      widget.update({ logLines: logs });
      if (projection) {
        widget.update({
          activeSubagent: {
            role,
            storyId,
            step: projection.step,
            totalSteps: projection.totalSteps,
            stepName: projection.stepName,
            startedAt,
          },
        });
      }
    } catch {
      // Non-fatal — polling is best-effort.
    }
  }, 2000);
  timer.unref();
  return () => clearInterval(timer);
}

// ---------------------------------------------------------------------------
// Phase A helpers
// ---------------------------------------------------------------------------

async function runIntake(
  epicDir: string,
  cwd: string,
  extensionPath: string,
  log: Logger,
  ui: ExtensionUIContext | null,
  widget: EpicWidgetController | null,
): Promise<boolean> {
  const subagentDir = await ensureSubagentDirectory(epicDir, "intake");
  const startedAt = Date.now();
  let stopPolling: (() => void) | undefined;
  if (widget) {
    widget.update({ activeSubagent: { role: "intake", step: 0, totalSteps: 3, stepName: "", startedAt } });
    stopPolling = startActivePolling(subagentDir, widget, startedAt, "intake");
  }
  const result = await spawnIntake({ epicDir, subagentDir, cwd, extensionPath, log, ui: ui ?? undefined });
  stopPolling?.();
  if (widget) {
    const logs = await readRecentLogs(subagentDir);
    widget.update({ logLines: logs, activeSubagent: null });
  }
  if (result.exitCode !== 0) {
    log("Intake failed", { exitCode: result.exitCode });
    return false;
  }
  return true;
}

async function runDecomposer(
  epicDir: string,
  cwd: string,
  extensionPath: string,
  log: Logger,
  ui: ExtensionUIContext | null,
  widget: EpicWidgetController | null,
): Promise<boolean> {
  const subagentDir = await ensureSubagentDirectory(epicDir, "decomposer");
  const startedAt = Date.now();
  let stopPolling: (() => void) | undefined;
  if (widget) {
    widget.update({ activeSubagent: { role: "decomposer", step: 0, totalSteps: 2, stepName: "", startedAt } });
    stopPolling = startActivePolling(subagentDir, widget, startedAt, "decomposer");
  }
  const result = await spawnDecomposer({ epicDir, subagentDir, cwd, extensionPath, log, ui: ui ?? undefined });
  stopPolling?.();
  if (widget) {
    const logs = await readRecentLogs(subagentDir);
    widget.update({ logLines: logs, activeSubagent: null });
  }
  if (result.exitCode !== 0) {
    log("Decomposer failed", { exitCode: result.exitCode });
    return false;
  }
  return true;
}

// ---------------------------------------------------------------------------
// Phase B helpers
// ---------------------------------------------------------------------------

async function runStoryExecution(
  epicDir: string,
  cwd: string,
  extensionPath: string,
  storyId: string,
  log: Logger,
  ui: ExtensionUIContext | null,
  widget: EpicWidgetController | null,
): Promise<void> {
  // 1. Set status to 'planning'.
  const story = await loadStoryState(epicDir, storyId);
  await saveStoryState(epicDir, storyId, {
    ...story,
    status: "planning",
    updatedAt: new Date().toISOString(),
  });

  // 2. Spawn planner.
  const plannerDir = await ensureSubagentDirectory(epicDir, `planner-${storyId}`);
  const plannerStarted = Date.now();
  let stopPolling: (() => void) | undefined;
  if (widget) {
    widget.update({
      activeSubagent: { role: "planner", storyId, step: 0, totalSteps: 3, stepName: "", startedAt: plannerStarted },
    });
    stopPolling = startActivePolling(plannerDir, widget, plannerStarted, "planner", storyId);
  }

  const planResult = await spawnPlanner({ epicDir, subagentDir: plannerDir, cwd, extensionPath, storyId, log, ui: ui ?? undefined });
  stopPolling?.();

  if (widget) {
    const logs = await readRecentLogs(plannerDir);
    widget.update({ logLines: logs });
  }

  if (planResult.exitCode !== 0) {
    log("Planner failed — skipping executor, proceeding to post-execution orchestrator", {
      storyId, exitCode: planResult.exitCode,
    });

    const s2 = await loadStoryState(epicDir, storyId);
    await saveStoryState(epicDir, storyId, {
      ...s2,
      status: "verifying",
      updatedAt: new Date().toISOString(),
    });

    const postDir = await ensureSubagentDirectory(epicDir, `orchestrator-post-${storyId}`);
    const orchStarted = Date.now();
    if (widget) {
      widget.update({ activeSubagent: { role: "orchestrator", storyId, step: 0, totalSteps: 4, stepName: "", startedAt: orchStarted } });
      stopPolling = startActivePolling(postDir, widget, orchStarted, "orchestrator", storyId);
    }

    await spawnOrchestrator({ epicDir, subagentDir: postDir, cwd, extensionPath, stepSequence: "post-execution", storyId, log, ui: ui ?? undefined });
    stopPolling?.();

    if (widget) {
      const logs = await readRecentLogs(postDir);
      widget.update({ logLines: logs });
    }
    return;
  }

  // 3. Set status to 'executing'.
  const s3 = await loadStoryState(epicDir, storyId);
  await saveStoryState(epicDir, storyId, {
    ...s3,
    status: "executing",
    updatedAt: new Date().toISOString(),
  });

  // 4. Spawn executor.
  const execDir = await ensureSubagentDirectory(epicDir, `executor-${storyId}`);
  const execStarted = Date.now();
  if (widget) {
    widget.update({ activeSubagent: { role: "executor", storyId, step: 0, totalSteps: 2, stepName: "", startedAt: execStarted } });
    stopPolling = startActivePolling(execDir, widget, execStarted, "executor", storyId);
  }

  const execResult = await spawnExecutor({ epicDir, subagentDir: execDir, cwd, extensionPath, storyId, log, ui: ui ?? undefined });
  stopPolling?.();

  if (widget) {
    const logs = await readRecentLogs(execDir);
    widget.update({ logLines: logs });
  }

  if (execResult.exitCode !== 0) {
    log("Executor failed", { storyId, exitCode: execResult.exitCode });
  }

  // 5. Set status to 'verifying'.
  const s4 = await loadStoryState(epicDir, storyId);
  await saveStoryState(epicDir, storyId, {
    ...s4,
    status: "verifying",
    updatedAt: new Date().toISOString(),
  });

  // 6. Spawn orchestrator (post-execution) — writes verdict to story state.
  const postDir = await ensureSubagentDirectory(epicDir, `orchestrator-post-${storyId}`);
  const orchStarted = Date.now();
  if (widget) {
    widget.update({ activeSubagent: { role: "orchestrator", storyId, step: 0, totalSteps: 4, stepName: "", startedAt: orchStarted } });
    stopPolling = startActivePolling(postDir, widget, orchStarted, "orchestrator", storyId);
  }

  await spawnOrchestrator({ epicDir, subagentDir: postDir, cwd, extensionPath, stepSequence: "post-execution", storyId, log, ui: ui ?? undefined });
  stopPolling?.();

  if (widget) {
    const logs = await readRecentLogs(postDir);
    widget.update({ logLines: logs });
  }
}

// retryCount is the 1-based retry attempt number (1 for first retry, 2 for
// second, etc.). It is included in directory names so each retry gets its own
// isolated stdout.log and events.jsonl, preventing directory collision when
// DEFAULT_MAX_RETRIES > 1.
async function runStoryReexecution(
  epicDir: string,
  cwd: string,
  extensionPath: string,
  storyId: string,
  retryCount: number,
  failureContext: string | undefined,
  log: Logger,
  ui: ExtensionUIContext | null,
  widget: EpicWidgetController | null,
): Promise<void> {
  const execDir = await ensureSubagentDirectory(epicDir, `executor-${storyId}-retry-${retryCount}`);
  const execStarted = Date.now();
  let stopPolling: (() => void) | undefined;
  if (widget) {
    widget.update({ activeSubagent: { role: "executor", storyId, step: 0, totalSteps: 2, stepName: "retry", startedAt: execStarted } });
    stopPolling = startActivePolling(execDir, widget, execStarted, "executor", storyId);
  }

  await spawnExecutor({ epicDir, subagentDir: execDir, cwd, extensionPath, storyId, retryContext: failureContext, log, ui: ui ?? undefined });
  stopPolling?.();

  if (widget) {
    const logs = await readRecentLogs(execDir);
    widget.update({ logLines: logs });
  }

  const story = await loadStoryState(epicDir, storyId);
  await saveStoryState(epicDir, storyId, {
    ...story,
    status: "verifying",
    updatedAt: new Date().toISOString(),
  });

  const postDir = await ensureSubagentDirectory(epicDir, `orchestrator-post-${storyId}-retry-${retryCount}`);
  const orchStarted = Date.now();
  if (widget) {
    widget.update({ activeSubagent: { role: "orchestrator", storyId, step: 0, totalSteps: 4, stepName: "", startedAt: orchStarted } });
    stopPolling = startActivePolling(postDir, widget, orchStarted, "orchestrator", storyId);
  }

  await spawnOrchestrator({ epicDir, subagentDir: postDir, cwd, extensionPath, stepSequence: "post-execution", storyId, log, ui: ui ?? undefined });
  stopPolling?.();

  if (widget) {
    const logs = await readRecentLogs(postDir);
    widget.update({ logLines: logs });
  }
}

async function refreshWidgetStories(epicDir: string, widget: EpicWidgetController): Promise<void> {
  try {
    const stories = await loadAllStoryStates(epicDir);
    widget.update({ stories: stories.map((s) => ({ storyId: s.storyId, status: s.status })) });
  } catch {
    // Non-fatal — widget update is best-effort.
  }
}

async function runStoryLoop(
  epicDir: string,
  cwd: string,
  extensionPath: string,
  log: Logger,
  ui: ExtensionUIContext | null,
  widget: EpicWidgetController | null,
): Promise<{ success: boolean; summary: string }> {
  {

    // 2. Spawn orchestrator (pre-execution) — selects first story.
    const preDir = await ensureSubagentDirectory(epicDir, "orchestrator-pre");
    const preStarted = Date.now();
    let stopPolling: (() => void) | undefined;
    if (widget) {
      widget.update({ activeSubagent: { role: "orchestrator", step: 0, totalSteps: 2, stepName: "pre-execution", startedAt: preStarted } });
      stopPolling = startActivePolling(preDir, widget, preStarted, "orchestrator");
    }

    const preResult = await spawnOrchestrator({ epicDir, subagentDir: preDir, cwd, extensionPath, stepSequence: "pre-execution", log, ui: ui ?? undefined });
    stopPolling?.();

    if (preResult.exitCode !== 0) {
      return { success: false, summary: "Pre-execution orchestrator failed" };
    }

    if (widget) await refreshWidgetStories(epicDir, widget);

    // 3. Story execution loop — route until terminal state.
    while (true) {
      const stories = await loadAllStoryStates(epicDir);
      if (widget) {
        widget.update({ stories: stories.map((s) => ({ storyId: s.storyId, status: s.status })) });
      }

      const routing = routeFromState(stories, log);

      switch (routing.action) {
        case "execute": {
          const storyId = routing.storyId as string;
          await runStoryExecution(epicDir, cwd, extensionPath, storyId, log, ui, widget);
          if (widget) await refreshWidgetStories(epicDir, widget);
          break;
        }

        case "retry": {
          const storyId = routing.storyId as string;
          const story = stories.find((s) => s.storyId === storyId) as StoryState;

          // Retry budget exhaustion: skip + notify per §11.6.3.
          if (story.retryCount >= story.maxRetries) {
            log("Retry budget exhausted, skipping story", { storyId, retryCount: story.retryCount });
            await saveStoryState(epicDir, storyId, {
              ...story,
              status: "skipped",
              skipReason: `Retry budget exhausted after ${story.retryCount} attempt(s). Last failure: ${story.failureSummary ?? "(none recorded)"}`,
              updatedAt: new Date().toISOString(),
            });
            ui?.notify(`Story ${storyId} skipped after ${story.retryCount} failed attempt(s).`, "warning");
            if (widget) await refreshWidgetStories(epicDir, widget);
            // Continue loop — other stories may still be runnable.
            continue;
          }

          await saveStoryState(epicDir, storyId, {
            ...story,
            status: "executing",
            retryCount: story.retryCount + 1,
            updatedAt: new Date().toISOString(),
          });
          await runStoryReexecution(epicDir, cwd, extensionPath, storyId, story.retryCount + 1, story.failureSummary, log, ui, widget);
          if (widget) await refreshWidgetStories(epicDir, widget);
          break;
        }

        case "complete": {
          const done = stories.filter((s) => s.status === "done").length;
          const skipped = stories.filter((s) => s.status === "skipped").length;
          if (widget) widget.update({ activeSubagent: null });
          return { success: true, summary: `Epic complete: ${done} done, ${skipped} skipped` };
        }

        case "error":
          return { success: false, summary: routing.error as string };
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function runEpicPipeline(
  epicDir: string,
  cwd: string,
  extensionPath: string,
  log: Logger,
  ui: ExtensionUIContext | null,
): Promise<{ success: boolean; summary: string }> {
  // Widget created at pipeline start — spans the full epic lifecycle (Phase A + B).
  // Widget is an observation layer: receives one-way update() calls, never
  // influences routing decisions.
  const epicState = await loadEpicState(epicDir);
  const widget = ui ? new EpicWidgetController(ui, epicState.epicId) : null;

  try {
    // Phase A: Epic Creation.
    ui?.notify("Starting intake...", "info");
    await saveEpicState(epicDir, { ...epicState, phase: "intake" });
    if (widget) widget.update({ epicPhase: "intake" });

    const intakeOk = await runIntake(epicDir, cwd, extensionPath, log, ui, widget);
    if (!intakeOk) return { success: false, summary: "Intake phase failed" };

    const afterIntake = await loadEpicState(epicDir);
    await saveEpicState(epicDir, { ...afterIntake, phase: "decomposition" });
    if (widget) widget.update({ epicPhase: "decomposition" });

    const decompOk = await runDecomposer(epicDir, cwd, extensionPath, log, ui, widget);
    if (!decompOk) return { success: false, summary: "Decomposition phase failed" };

    // Discover stories by scanning the filesystem — per AGENTS.md invariant,
    // LLMs write markdown files only. The decomposer wrote stories/{id}/story.md
    // files; the driver scans to discover IDs and populates epic-state.json.
    const storyIds = await discoverStoryIds(epicDir);
    log("Discovered story IDs", { count: storyIds.length, ids: storyIds });

    for (const storyId of storyIds) {
      await ensureStoryDirectory(epicDir, storyId);
    }

    const afterDecomp = await loadEpicState(epicDir);
    await saveEpicState(epicDir, { ...afterDecomp, stories: storyIds, phase: "review" });
    if (widget) {
      widget.update({ epicPhase: "review" });
      const initialStories = await loadAllStoryStates(epicDir);
      widget.update({ stories: initialStories.map((s) => ({ storyId: s.storyId, status: s.status })) });
    }

    // Spec review gate — present story sketches for human approval if UI is available.
    if (ui && storyIds.length > 0) {
      ui.notify("Decomposition complete. Review story sketches...", "info");
      const reviewResult = await reviewStorySketches(epicDir, storyIds, ui);
      log("Spec review complete", { approved: reviewResult.approved.length, skipped: reviewResult.skipped.length });

      for (const skippedId of reviewResult.skipped) {
        const skippedStory = await loadStoryState(epicDir, skippedId);
        await saveStoryState(epicDir, skippedId, {
          ...skippedStory,
          status: "skipped",
          skipReason: "Removed during spec review",
          updatedAt: new Date().toISOString(),
        });
      }

      const reviewedState = await loadEpicState(epicDir);
      await saveEpicState(epicDir, { ...reviewedState, stories: storyIds });
    } else {
      log("Spec review gate: auto-approving (no UI or no stories)");
    }

    // Phase B: Execution.
    const beforeExec = await loadEpicState(epicDir);
    await saveEpicState(epicDir, { ...beforeExec, phase: "executing" });
    if (widget) widget.update({ epicPhase: "executing" });

    const result = await runStoryLoop(epicDir, cwd, extensionPath, log, ui, widget);

    if (result.success) {
      const afterExec = await loadEpicState(epicDir);
      await saveEpicState(epicDir, { ...afterExec, phase: "completed" });
      if (widget) widget.update({ epicPhase: "completed" });
    }

    return result;
  } finally {
    widget?.destroy();
  }
}
