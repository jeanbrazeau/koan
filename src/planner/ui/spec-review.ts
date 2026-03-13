// Spec review gate: interactive story approval UI.
// Shown after decomposition so the user can approve, or skip individual stories
// before execution begins. Driver blocks until the user confirms.
//
// Controls:
//   ↑↓         move cursor
//   Space       toggle selected story between "include" and "skip"
//   A           approve all (mark all as include)
//   Enter       confirm and proceed
//   Esc         confirm current selections and proceed

import { promises as fs } from "node:fs";
import * as path from "node:path";

import type { ExtensionUIContext } from "@mariozechner/pi-coding-agent";
import { Key, matchesKey, truncateToWidth, visibleWidth } from "@mariozechner/pi-tui";

export interface SpecReviewResult {
  approved: string[];
  skipped: string[];
}

interface StoryEntry {
  storyId: string;
  title: string;
  include: boolean;
}

async function readStoryTitle(epicDir: string, storyId: string): Promise<string> {
  try {
    const raw = await fs.readFile(path.join(epicDir, "stories", storyId, "story.md"), "utf8");
    // Extract first non-empty, non-heading line after a heading, or first heading text.
    for (const rawLine of raw.split("\n")) {
      const l = rawLine.trim();
      if (!l) continue;
      // Strip leading # characters for headings.
      const text = l.replace(/^#+\s*/, "").trim();
      if (text) return text.slice(0, 80);
    }
    return storyId;
  } catch {
    return storyId;
  }
}

export async function reviewStorySketches(
  epicDir: string,
  storyIds: string[],
  ui: ExtensionUIContext,
): Promise<SpecReviewResult> {
  if (storyIds.length === 0) {
    return { approved: [], skipped: [] };
  }

  // Load story titles asynchronously.
  const titles = await Promise.all(storyIds.map((id) => readStoryTitle(epicDir, id)));
  const entries: StoryEntry[] = storyIds.map((storyId, i) => ({
    storyId,
    title: titles[i] ?? storyId,
    include: true,
  }));

  const result = await ui.custom<{ entries: StoryEntry[] }>((tui, theme, _keybindings, done) => {
    let cursor = 0;
    let cachedLines: string[] | undefined;

    const requestRender = () => {
      cachedLines = undefined;
      tui.requestRender();
    };

    const render = (width: number): string[] => {
      if (cachedLines) return cachedLines;
      const lines: string[] = [];
      const addLine = (l: string) => lines.push(truncateToWidth(l, width));

      addLine(theme.fg("accent", "─".repeat(width)));
      addLine(
        ` ${theme.bold(theme.fg("accent", "Spec Review"))}  ${theme.fg("muted", `${entries.length} stories`)}`,
      );
      addLine(theme.fg("dim", " Review story sketches before execution begins."));
      addLine("");

      for (let i = 0; i < entries.length; i++) {
        const e = entries[i];
        const isCursor = i === cursor;
        const prefix = isCursor ? theme.fg("accent", "→ ") : "  ";
        const checkbox = e.include
          ? theme.fg("success", "[✓]")
          : theme.fg("dim", "[ ]");
        const label = isCursor
          ? theme.bold(theme.fg(e.include ? "text" : "dim", e.storyId))
          : theme.fg(e.include ? "text" : "dim", e.storyId);
        const titleStr = theme.fg("muted", ` — ${e.title}`);
        addLine(`${prefix}${checkbox} ${label}${titleStr}`);
      }

      addLine("");

      const approvedCount = entries.filter((e) => e.include).length;
      const skippedCount = entries.length - approvedCount;
      addLine(
        ` ${theme.fg("success", `${approvedCount} approved`)}  ${theme.fg("dim", `${skippedCount} skipped`)}`,
      );
      addLine("");
      addLine(
        theme.fg("dim", " ↑↓ move • Space toggle • A approve all • Enter confirm • Esc confirm"),
      );
      addLine(theme.fg("accent", "─".repeat(width)));

      cachedLines = lines;
      return lines;
    };

    const handleInput = (data: string) => {
      if (matchesKey(data, Key.up)) {
        cursor = Math.max(0, cursor - 1);
        requestRender();
        return;
      }
      if (matchesKey(data, Key.down)) {
        cursor = Math.min(entries.length - 1, cursor + 1);
        requestRender();
        return;
      }
      if (data === " ") {
        entries[cursor].include = !entries[cursor].include;
        requestRender();
        return;
      }
      if (data === "a" || data === "A") {
        for (const e of entries) e.include = true;
        requestRender();
        return;
      }
      if (matchesKey(data, Key.enter) || matchesKey(data, Key.escape)) {
        done({ entries: entries.map((e) => ({ ...e })) });
        return;
      }
    };

    return {
      render,
      invalidate: () => { cachedLines = undefined; },
      handleInput,
    };
  });

  const approved = result.entries.filter((e) => e.include).map((e) => e.storyId);
  const skipped = result.entries.filter((e) => !e.include).map((e) => e.storyId);
  return { approved, skipped };
}
