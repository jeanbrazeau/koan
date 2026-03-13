// Subagent spawn helpers. Each public function delegates to spawnSubagent,
// which handles process lifecycle, stdout/stderr routing to disk, and
// exit-code normalization. When a UI context is provided, an IPC responder
// runs concurrently so subagents can ask questions and request scouts.

import { spawn } from "node:child_process";
import { createWriteStream } from "node:fs";
import * as path from "node:path";

import type { ExtensionUIContext } from "@mariozechner/pi-coding-agent";

import { createLogger, type Logger } from "../utils/logger.js";
import type { SubagentRole, StepSequence } from "./types.js";
import { resolveModelForRole } from "./model-resolver.js";
import { runIpcResponder, type ScoutSpawnContext } from "./lib/ipc-responder.js";
import type { ScoutTask } from "./lib/ipc.js";

// -- Result type --

export interface SubagentResult {
  exitCode: number;
  stderr: string;
  subagentDir: string;
}

// -- Public spawn option types --

export interface SpawnOptions {
  epicDir: string;
  subagentDir: string;
  cwd: string;
  extensionPath: string;
  modelOverride?: string;
  log?: Logger;
  ui?: ExtensionUIContext;
}

export interface SpawnStoryOptions extends SpawnOptions {
  storyId: string;
}

// -- Internal spawn infrastructure --

interface SpawnSubagentOpts {
  epicDir: string;
  subagentDir: string;
  cwd: string;
  extensionPath: string;
  extraFlags?: string[];
  modelOverride?: string;
  ui?: ExtensionUIContext;
  // Scout spawning context for the IPC responder. Provided for all non-scout
  // subagents that may call koan_request_scouts.
  scoutContext?: ScoutSpawnContext;
}

export function buildSpawnArgs(
  role: string,
  prompt: string,
  opts: SpawnSubagentOpts,
): string[] {
  return [
    "-p",
    "-e", opts.extensionPath,
    "--koan-role", role,
    "--koan-epic-dir", opts.epicDir,
    "--koan-subagent-dir", opts.subagentDir,
    ...(opts.extraFlags ?? []),
    ...(opts.modelOverride ? ["--model", opts.modelOverride] : []),
    prompt,
  ];
}

function spawnSubagent(
  role: string,
  prompt: string,
  opts: SpawnSubagentOpts,
  log: Logger,
): Promise<SubagentResult> {
  const args = buildSpawnArgs(role, prompt, opts);
  log(`Spawning ${role} subagent`, { epicDir: opts.epicDir, subagentDir: opts.subagentDir });

  return new Promise((resolve) => {
    const stdoutLog = createWriteStream(path.join(opts.subagentDir, "stdout.log"), { flags: "w" });
    const stderrLog = createWriteStream(path.join(opts.subagentDir, "stderr.log"), { flags: "w" });

    const proc = spawn("pi", args, {
      cwd: opts.cwd,
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    });

    // Start IPC responder concurrently when a UI context is available.
    // The responder polls ipc.json in the subagent directory and routes
    // ask-question requests to the ask UI and scout-request requests to
    // the scout spawning pool.
    let abortIpc: (() => void) | undefined;
    if (opts.ui) {
      const ac = new AbortController();
      abortIpc = () => ac.abort();
      void runIpcResponder(
        opts.subagentDir,
        opts.ui,
        ac.signal,
        opts.scoutContext,
      );
    }

    let stderr = "";

    proc.stdout.on("data", (data: Buffer) => {
      stdoutLog.write(data);
    });

    proc.stderr.on("data", (data: Buffer) => {
      stderr += data.toString();
      stderrLog.write(data);
    });

    proc.on("close", (code) => {
      abortIpc?.();
      stdoutLog.end();
      stderrLog.end();
      const exitCode = code ?? 1;
      log(`${role} subagent exited`, { exitCode });
      resolve({ exitCode, stderr, subagentDir: opts.subagentDir });
    });

    proc.on("error", (error) => {
      abortIpc?.();
      stdoutLog.end();
      stderrLog.end();
      log(`${role} subagent spawn error`, { error: error.message });
      resolve({ exitCode: 1, stderr: error.message, subagentDir: opts.subagentDir });
    });
  });
}

// -- Scout spawner (injected into IPC responder) --
// Defined here to avoid circular imports: ipc-responder.ts uses a callback
// type, not a direct import from this module.

function makeScoutSpawnContext(
  opts: SpawnOptions,
  log: Logger,
): ScoutSpawnContext {
  return {
    epicDir: opts.epicDir,
    async spawnScout(task: ScoutTask, scoutSubagentDir: string, outputFile: string): Promise<number> {
      const scoutModel = await resolveModelForRole("scout");
      const prompt = `${task.prompt}\n\nWrite your findings to: ${outputFile}\nYour investigator role: ${task.role}`;
      const result = await spawnSubagent(
        "scout",
        prompt,
        {
          epicDir: opts.epicDir,
          subagentDir: scoutSubagentDir,
          cwd: opts.cwd,
          extensionPath: opts.extensionPath,
          modelOverride: scoutModel,
          // Scouts do not get an IPC responder — they are narrow investigators.
        },
        log,
      );
      return result.exitCode;
    },
  };
}

// -- Public spawn functions --

// Intake: reads conversation, extracts context, requests scouts, asks user questions.
export async function spawnIntake(opts: SpawnOptions): Promise<SubagentResult> {
  const role: SubagentRole = "intake";
  const log = opts.log ?? createLogger("Subagent");
  const modelOverride = opts.modelOverride ?? await resolveModelForRole(role);
  const scoutContext = makeScoutSpawnContext(opts, log);
  return spawnSubagent(
    role,
    "Begin the intake phase.",
    { ...opts, modelOverride, scoutContext },
    log,
  );
}

// Scout: answers one narrow codebase question and writes findings to outputFile.
// Note: scouts are spawned by the IPC responder (via makeScoutSpawnContext) when
// a subagent calls koan_request_scouts. This function is also callable directly
// from the driver if needed.
export async function spawnScout(
  opts: SpawnOptions & { question: string; role?: string; outputFile: string },
): Promise<SubagentResult> {
  const subagentRole: SubagentRole = "scout";
  const log = opts.log ?? createLogger("Subagent");
  const modelOverride = opts.modelOverride ?? await resolveModelForRole(subagentRole);
  const prompt = [
    opts.question,
    opts.role ? `Your investigator role: ${opts.role}` : "",
    `Write your findings to: ${opts.outputFile}`,
  ].filter(Boolean).join("\n");
  return spawnSubagent(subagentRole, prompt, { ...opts, modelOverride }, log);
}

// Decomposer: splits the epic into stories.
export async function spawnDecomposer(opts: SpawnOptions): Promise<SubagentResult> {
  const role: SubagentRole = "decomposer";
  const log = opts.log ?? createLogger("Subagent");
  const modelOverride = opts.modelOverride ?? await resolveModelForRole(role);
  const scoutContext = makeScoutSpawnContext(opts, log);
  return spawnSubagent(
    role,
    "Begin the decomposition phase.",
    { ...opts, modelOverride, scoutContext },
    log,
  );
}

// Orchestrator: pre-execution or post-execution decision making.
export async function spawnOrchestrator(
  opts: SpawnOptions & { stepSequence: StepSequence; storyId?: string },
): Promise<SubagentResult> {
  const role: SubagentRole = "orchestrator";
  const log = opts.log ?? createLogger("Subagent");
  const modelOverride = opts.modelOverride ?? await resolveModelForRole(role);
  const extraFlags: string[] = ["--koan-step-sequence", opts.stepSequence];
  if (opts.storyId) {
    extraFlags.push("--koan-story-id", opts.storyId);
  }
  const prompt = `Begin the ${opts.stepSequence} orchestrator phase.`;
  return spawnSubagent(
    role,
    prompt,
    { ...opts, extraFlags, modelOverride },
    log,
  );
}

// Planner: produces a detailed plan for a story.
export async function spawnPlanner(opts: SpawnStoryOptions): Promise<SubagentResult> {
  const role: SubagentRole = "planner";
  const log = opts.log ?? createLogger("Subagent");
  const modelOverride = opts.modelOverride ?? await resolveModelForRole(role);
  const extraFlags: string[] = ["--koan-story-id", opts.storyId];
  const scoutContext = makeScoutSpawnContext(opts, log);
  const prompt = `Begin the planning phase for story ${opts.storyId}.`;
  return spawnSubagent(
    role,
    prompt,
    { ...opts, extraFlags, modelOverride, scoutContext },
    log,
  );
}

// Executor: implements a story plan.
export async function spawnExecutor(
  opts: SpawnStoryOptions & { retryContext?: string },
): Promise<SubagentResult> {
  const role: SubagentRole = "executor";
  const log = opts.log ?? createLogger("Subagent");
  const modelOverride = opts.modelOverride ?? await resolveModelForRole(role);
  const extraFlags: string[] = ["--koan-story-id", opts.storyId];
  if (opts.retryContext) {
    extraFlags.push("--koan-retry-context", opts.retryContext);
  }
  const basePrompt = `Implement the plan for story ${opts.storyId}.`;
  const prompt = opts.retryContext
    ? `${basePrompt}\n\nPrevious attempt failed: ${opts.retryContext}`
    : basePrompt;
  return spawnSubagent(
    role,
    prompt,
    { ...opts, extraFlags, modelOverride },
    log,
  );
}
