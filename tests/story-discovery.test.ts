import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { promises as fs } from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

import { discoverStoryIds } from "../src/planner/epic/state.js";

async function mkTempDir(): Promise<string> {
  return fs.mkdtemp(path.join(os.tmpdir(), "koan-test-"));
}

describe("discoverStoryIds", () => {
  it("returns empty array when stories directory does not exist", async () => {
    const epicDir = await mkTempDir();
    try {
      const ids = await discoverStoryIds(epicDir);
      assert.deepEqual(ids, []);
    } finally {
      await fs.rm(epicDir, { recursive: true, force: true });
    }
  });

  it("returns empty array when stories directory is empty", async () => {
    const epicDir = await mkTempDir();
    try {
      await fs.mkdir(path.join(epicDir, "stories"));
      const ids = await discoverStoryIds(epicDir);
      assert.deepEqual(ids, []);
    } finally {
      await fs.rm(epicDir, { recursive: true, force: true });
    }
  });

  it("returns sorted story IDs for each subdirectory", async () => {
    const epicDir = await mkTempDir();
    try {
      const storiesDir = path.join(epicDir, "stories");
      await fs.mkdir(storiesDir);
      // Create story directories out of alphabetical order.
      for (const id of ["add-auth", "migrate-db", "update-api"]) {
        await fs.mkdir(path.join(storiesDir, id));
      }

      const ids = await discoverStoryIds(epicDir);
      assert.deepEqual(ids, ["add-auth", "migrate-db", "update-api"]);
    } finally {
      await fs.rm(epicDir, { recursive: true, force: true });
    }
  });

  it("ignores files in the stories directory", async () => {
    const epicDir = await mkTempDir();
    try {
      const storiesDir = path.join(epicDir, "stories");
      await fs.mkdir(storiesDir);
      await fs.mkdir(path.join(storiesDir, "real-story"));
      // Write a file — should be ignored.
      await fs.writeFile(path.join(storiesDir, "not-a-story.md"), "# ignored\n");

      const ids = await discoverStoryIds(epicDir);
      assert.deepEqual(ids, ["real-story"]);
    } finally {
      await fs.rm(epicDir, { recursive: true, force: true });
    }
  });

  it("returns deterministically sorted IDs regardless of filesystem order", async () => {
    const epicDir = await mkTempDir();
    try {
      const storiesDir = path.join(epicDir, "stories");
      await fs.mkdir(storiesDir);
      // Create in reverse order.
      for (const id of ["zzz-last", "aaa-first", "mmm-middle"]) {
        await fs.mkdir(path.join(storiesDir, id));
      }

      const ids = await discoverStoryIds(epicDir);
      assert.deepEqual(ids, ["aaa-first", "mmm-middle", "zzz-last"]);
    } finally {
      await fs.rm(epicDir, { recursive: true, force: true });
    }
  });
});
