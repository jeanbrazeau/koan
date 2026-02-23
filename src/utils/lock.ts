import { promises as fs } from "node:fs";

// Advisory .lock file for serializing file mutations. Uses O_CREAT|O_EXCL
// for atomic creation (fails if lock already exists). Retry with backoff
// handles transient contention (e.g. parallel QR verifiers).

const RETRY_INTERVAL_MS = 50;
const MAX_WAIT_MS = 5000;

function lockPath(filePath: string): string {
  return `${filePath}.lock`;
}

async function acquire(filePath: string): Promise<void> {
  const lp = lockPath(filePath);
  const deadline = Date.now() + MAX_WAIT_MS;

  while (true) {
    try {
      const fd = await fs.open(lp, "wx");
      await fd.close();
      return;
    } catch (err: unknown) {
      if ((err as NodeJS.ErrnoException).code !== "EEXIST") throw err;
      if (Date.now() >= deadline) {
        throw new Error(`Failed to acquire lock on ${filePath} after ${MAX_WAIT_MS}ms`);
      }
      await new Promise((r) => setTimeout(r, RETRY_INTERVAL_MS));
    }
  }
}

async function release(filePath: string): Promise<void> {
  await fs.rm(lockPath(filePath), { force: true });
}

export async function withFileLock<T>(filePath: string, fn: () => Promise<T>): Promise<T> {
  await acquire(filePath);
  try {
    return await fn();
  } finally {
    await release(filePath);
  }
}
