import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { promises as fs } from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

import { ProgressReporter, readSubagentState } from "../src/utils/progress.js";

async function createTempDir(prefix: string): Promise<string> {
  const base = await fs.mkdtemp(path.join(os.tmpdir(), prefix));
  return base;
}

describe("ProgressReporter", () => {
  it("persists progress updates and completion state", async () => {
    const tempRoot = await createTempDir("koan-progress-");
    const reporterDir = path.join(tempRoot, "reporter");
    await fs.mkdir(reporterDir, { recursive: true });

    const reporter = new ProgressReporter(reporterDir, "planner", "analysis");

    await reporter.update("gathering context");
    await reporter.update("synthesizing plan");
    await reporter.complete("completed");

    const state = await readSubagentState(reporterDir);
    assert.ok(state, "state file should be readable");
    assert.equal(state.role, "planner");
    assert.equal(state.phase, "analysis");
    assert.equal(state.status, "completed");
    assert.equal(state.current, "completed");
    assert.equal(state.trail.length, 3);
    assert.deepEqual(
      state.trail.map((entry) => entry.msg),
      ["gathering context", "synthesizing plan", "completed"],
      "trail should capture chronological updates"
    );

    await fs.rm(tempRoot, { recursive: true, force: true });
  });
});
