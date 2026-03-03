// File-based IPC between subagent and parent session.
// A single ipc.json file per subagent directory holds both the request and
// response. Atomic writes (tmp-rename) prevent partial reads.

import { promises as fs } from "node:fs";
import * as path from "node:path";
import * as crypto from "node:crypto";

// -- Types --

export interface IpcFile {
  request: IpcRequest;
  response: IpcResponse | null; // null while awaiting parent response
}

export interface IpcRequest {
  id: string;          // crypto.randomUUID() — correlates request to response
  type: "ask-question"; // discriminant for routing; extensible to future types
  createdAt: string;   // ISO 8601 timestamp
  payload: AskQuestionPayload;
}

export interface AskQuestionPayload {
  questions: Array<{
    id: string;
    question: string;
    options: Array<{ label: string }>;
    multi?: boolean;
    recommended?: number; // 0-indexed
  }>;
}

export interface IpcResponse {
  id: string;          // must match request.id
  respondedAt: string; // ISO 8601 timestamp
  cancelled: boolean;  // true when user presses Escape
  payload: AskAnswerPayload | null; // null when cancelled
}

export interface AskAnswerPayload {
  answers: Array<{
    id: string;            // matches question id
    selectedOptions: string[];
    customInput?: string;  // populated when user selects "Other"
  }>;
}

// -- File paths --

const IPC_FILE = "ipc.json";
const IPC_TMP_FILE = ".ipc.tmp.json";

// -- I/O helpers --

// Atomic write: .ipc.tmp.json → ipc.json rename.
export async function writeIpcFile(dir: string, data: IpcFile): Promise<void> {
  const tmp = path.join(dir, IPC_TMP_FILE);
  const target = path.join(dir, IPC_FILE);
  await fs.writeFile(tmp, `${JSON.stringify(data, null, 2)}\n`, "utf8");
  await fs.rename(tmp, target);
}

// Returns null on missing file or parse error.
// Treats parse errors as "not ready" to handle partial writes on non-POSIX systems.
export async function readIpcFile(dir: string): Promise<IpcFile | null> {
  try {
    const raw = await fs.readFile(path.join(dir, IPC_FILE), "utf8");
    return JSON.parse(raw) as IpcFile;
  } catch {
    return null;
  }
}

// Fast existence check without parsing.
export async function ipcFileExists(dir: string): Promise<boolean> {
  try {
    await fs.access(path.join(dir, IPC_FILE));
    return true;
  } catch {
    return false;
  }
}

// Removes ipc.json and any lingering .ipc.tmp.json; swallows ENOENT.
export async function deleteIpcFile(dir: string): Promise<void> {
  for (const name of [IPC_FILE, IPC_TMP_FILE]) {
    try {
      await fs.unlink(path.join(dir, name));
    } catch (err: unknown) {
      if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
    }
  }
}

// -- Factory helpers --

export function createAskRequest(payload: AskQuestionPayload): IpcFile {
  return {
    request: {
      id: crypto.randomUUID(),
      type: "ask-question",
      createdAt: new Date().toISOString(),
      payload,
    },
    response: null,
  };
}

export function createAskResponse(requestId: string, payload: AskAnswerPayload): IpcResponse {
  return {
    id: requestId,
    respondedAt: new Date().toISOString(),
    cancelled: false,
    payload,
  };
}

export function createCancelledResponse(requestId: string): IpcResponse {
  return {
    id: requestId,
    respondedAt: new Date().toISOString(),
    cancelled: true,
    payload: null,
  };
}
