// Epic execution status widget. Renders a TUI panel showing:
//   - Story list with status icons
//   - Active subagent: role, step, elapsed time
//   - Recent log tail from the active subagent directory
//   - Autonomous decision counter
//
// The driver creates one instance at the start of runEpicPipeline (before intake)
// and calls update() after each state change. Spans the full epic lifecycle (Phase
// A + B), not just story execution. Pure observation layer — never influences routing.
// Self-renders via pi's setWidget API; a 1-second unref'd timer keeps elapsed time fresh.

import type { ExtensionUIContext } from "@mariozechner/pi-coding-agent";
import type { Theme, ThemeColor } from "@mariozechner/pi-coding-agent";
import { truncateToWidth, visibleWidth } from "@mariozechner/pi-tui";

import type { EpicPhase, StoryStatus } from "../types.js";
import type { LogLine } from "../lib/audit.js";

// -- Types --

export interface ActiveSubagentInfo {
  role: string;
  storyId?: string;
  step: number;
  totalSteps: number;
  stepName: string;
  startedAt: number;
}

export interface EpicWidgetState {
  epicId: string;
  epicPhase: EpicPhase;
  stories: Array<{ storyId: string; status: StoryStatus }>;
  activeSubagent: ActiveSubagentInfo | null;
  logLines: LogLine[];
}

export interface EpicWidgetUpdate {
  epicPhase?: EpicPhase;
  stories?: Array<{ storyId: string; status: StoryStatus }>;
  activeSubagent?: ActiveSubagentInfo | null;
  logLines?: LogLine[];
}

// -- Constants --

const WIDGET_KEY = "koan-epic";
const PAD = 2;
const MAX_LOG_LINES = 5;

// Status icons and colors — no escalated status per §11.3.1.
const STATUS_ICON: Record<StoryStatus, string> = {
  pending: "○",
  selected: "◎",
  planning: "◐",
  executing: "●",
  verifying: "◑",
  done: "✓",
  retry: "↺",
  skipped: "—",
};

const STATUS_COLOR: Record<StoryStatus, ThemeColor> = {
  pending: "muted",
  selected: "accent",
  planning: "accent",
  executing: "accent",
  verifying: "accent",
  done: "success",
  retry: "warning",
  skipped: "dim",
};

// -- Helpers --

function cw(termWidth: number): number {
  return Math.max(40, termWidth - PAD * 2);
}

function line(content: string, termWidth: number, theme: Theme): string {
  const w = cw(termWidth);
  const inner = clamp(content, w);
  return theme.bg("toolPendingBg", " ".repeat(PAD) + inner + " ".repeat(PAD));
}

function clamp(text: string, width: number): string {
  const truncated = truncateToWidth(text, width, "", false);
  const vw = visibleWidth(truncated);
  return vw >= width ? truncated : truncated + " ".repeat(width - vw);
}

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`;
  return `${m}m ${String(sec).padStart(2, "0")}s`;
}

// -- Render --

function renderHeader(state: EpicWidgetState, theme: Theme, width: number): string {
  const elapsed = state.activeSubagent
    ? theme.fg("dim", formatElapsed(Date.now() - state.activeSubagent.startedAt))
    : "";
  const title = theme.bold(theme.fg("accent", `Epic · ${state.epicId}`));
  const phaseBadge = theme.fg("muted", ` · ${state.epicPhase}`);
  const left = `${title}${phaseBadge}`;
  const gap = Math.max(1, width - visibleWidth(left) - visibleWidth(elapsed));
  return clamp(`${left}${" ".repeat(gap)}${elapsed}`, width);
}

function renderStoryList(state: EpicWidgetState, theme: Theme, width: number): string[] {
  if (state.stories.length === 0) {
    return [clamp(theme.fg("muted", "  No stories yet"), width)];
  }
  return state.stories.map(({ storyId, status }) => {
    const icon = STATUS_ICON[status] ?? "?";
    const color = STATUS_COLOR[status] ?? "muted";
    const iconStr = theme.fg(color, icon);
    const label = status === "executing" || status === "planning" || status === "verifying"
      ? theme.bold(theme.fg(color, storyId))
      : theme.fg(color, storyId);
    const statusLabel = theme.fg("dim", ` (${status})`);
    return clamp(`  ${iconStr} ${label}${statusLabel}`, width);
  });
}

function renderActiveSubagent(state: EpicWidgetState, theme: Theme, width: number): string[] {
  const sa = state.activeSubagent;
  if (!sa) {
    return [clamp(theme.fg("muted", "  idle"), width)];
  }
  const roleLabel = sa.storyId ? `${sa.role} · ${sa.storyId}` : sa.role;
  const stepLabel = sa.totalSteps > 0
    ? `step ${sa.step}/${sa.totalSteps}${sa.stepName ? ` · ${sa.stepName}` : ""}`
    : "starting";
  const elapsedStr = formatElapsed(Date.now() - sa.startedAt);
  return [
    clamp(`  ${theme.bold(theme.fg("accent", roleLabel))}  ${theme.fg("muted", stepLabel)}`, width),
    clamp(`  ${theme.fg("dim", elapsedStr)}`, width),
  ];
}

function renderLogTail(state: EpicWidgetState, theme: Theme, width: number): string[] {
  const entries = state.logLines.slice(-MAX_LOG_LINES);
  if (entries.length === 0) {
    return [clamp(theme.fg("dim", "  (no log entries)"), width)];
  }
  return entries.map((entry) => {
    const toolStr = theme.bold(theme.fg("accent", entry.tool));
    const summary = entry.summary.trim();
    const sep = summary ? " " : "";
    return clamp(`  ${toolStr}${sep}${theme.fg("muted", summary)}`, width);
  });
}

function renderDivider(label: string, theme: Theme, width: number): string {
  const tag = ` ${label} `;
  const tagLen = visibleWidth(tag);
  const dashCount = Math.max(0, width - tagLen);
  const left = Math.floor(dashCount / 2);
  const right = dashCount - left;
  return clamp(
    `${theme.fg("dim", "─".repeat(left))}${theme.bold(theme.fg("muted", tag))}${theme.fg("dim", "─".repeat(right))}`,
    width,
  );
}

function render(state: EpicWidgetState, theme: Theme, termWidth: number): string[] {
  const w = cw(termWidth);
  const L = (content: string) => line(content, termWidth, theme);
  const lines: string[] = [];

  lines.push(L(""));
  lines.push(L(renderHeader(state, theme, w)));
  lines.push(L(renderDivider("stories", theme, w)));
  for (const l of renderStoryList(state, theme, w)) lines.push(L(l));
  lines.push(L(renderDivider("active", theme, w)));
  for (const l of renderActiveSubagent(state, theme, w)) lines.push(L(l));
  lines.push(L(renderDivider("log", theme, w)));
  for (const l of renderLogTail(state, theme, w)) lines.push(L(l));
  lines.push(L(""));

  return lines;
}

// -- EpicWidgetController --

export class EpicWidgetController {
  private state: EpicWidgetState;
  private lastHash = "";
  private timer: ReturnType<typeof setInterval>;
  private ui: ExtensionUIContext;

  constructor(ui: ExtensionUIContext, epicId: string) {
    this.ui = ui;
    this.state = {
      epicId,
      epicPhase: "intake",
      stories: [],
      activeSubagent: null,
      logLines: [],
    };
    this.timer = setInterval(() => this.doRender(), 1000);
    this.timer.unref();
    this.doRender();
  }

  update(patch: EpicWidgetUpdate): void {
    if (patch.epicPhase !== undefined) this.state.epicPhase = patch.epicPhase;
    if (patch.stories !== undefined) this.state.stories = patch.stories;
    if (patch.activeSubagent !== undefined) this.state.activeSubagent = patch.activeSubagent;
    if (patch.logLines !== undefined) this.state.logLines = patch.logLines;
    this.doRender();
  }

  destroy(): void {
    clearInterval(this.timer);
    this.ui.setWidget(WIDGET_KEY, undefined);
  }

  private doRender(): void {
    const snapshot = {
      ...this.state,
      stories: this.state.stories.map((s) => ({ ...s })),
      logLines: this.state.logLines.map((l) => ({ ...l })),
      activeSubagent: this.state.activeSubagent ? { ...this.state.activeSubagent } : null,
    };
    const { theme } = this.ui;

    const hashLines = render(snapshot, theme, 0);
    const hash = hashLines.join("\n");
    if (hash === this.lastHash) return;
    this.lastHash = hash;

    this.ui.setWidget(WIDGET_KEY, (_tui, th) => ({
      render: (width: number) => render(snapshot, th, width),
      invalidate: () => {},
    }));
  }
}
