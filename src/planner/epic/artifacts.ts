// Epic artifact I/O -- list, read, and write markdown artifacts within an epic directory.
// All writes use atomic tmp+rename to prevent partial reads during concurrent access.
// Artifacts are .md files in the epic root and under stories/ (excluding subagents/).

import { promises as fs } from "node:fs";
import * as path from "node:path";

// -- Types --

export interface ArtifactEntry {
  path: string;
  size: number;
  modifiedAt: string;
}

// -- List --

export async function listArtifacts(epicDir: string): Promise<ArtifactEntry[]> {
  const results: ArtifactEntry[] = [];

  // Pass 1: epic root .md files
  const rootEntries = await fs.readdir(epicDir, { withFileTypes: true });
  for (const e of rootEntries) {
    if (!e.isFile() || !e.name.endsWith(".md")) continue;
    const abs = path.join(epicDir, e.name);
    const stat = await fs.stat(abs);
    results.push({
      path: e.name,
      size: stat.size,
      modifiedAt: stat.mtime.toISOString(),
    });
  }

  // Pass 2: stories/ recursive scan
  const storiesDir = path.join(epicDir, "stories");
  try {
    const entries = await fs.readdir(storiesDir, { withFileTypes: true, recursive: true });
    for (const e of entries) {
      if (!e.isFile() || !e.name.endsWith(".md")) continue;
      const parent = (e as any).parentPath ?? (e as any).path ?? storiesDir;
      const abs = path.join(parent, e.name);
      const rel = path.relative(epicDir, abs);
      if (rel.split(path.sep).includes("subagents")) continue;
      const stat = await fs.stat(abs);
      results.push({
        path: rel,
        size: stat.size,
        modifiedAt: stat.mtime.toISOString(),
      });
    }
  } catch (err: unknown) {
    if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
  }

  results.sort((a, b) => a.path.localeCompare(b.path));
  return results;
}

// -- Read --

export async function readArtifact(epicDir: string, relativePath: string): Promise<string> {
  const abs = path.resolve(epicDir, relativePath);
  const root = path.resolve(epicDir);
  const rel = path.relative(root, abs);
  if (rel !== "" && (rel.startsWith("..") || path.isAbsolute(rel))) {
    throw new Error(`Path "${relativePath}" escapes the epic directory.`);
  }
  return fs.readFile(abs, "utf8");
}

// -- Write --

export async function writeArtifact(epicDir: string, relativePath: string, content: string): Promise<void> {
  const abs = path.resolve(epicDir, relativePath);
  const tmp = `${abs}.tmp`;
  await fs.writeFile(tmp, content, "utf8");
  await fs.rename(tmp, abs);
}
