// Barrel re-export: preserves import paths for callers outside lib/.
// Real implementations live in the four sub-modules:
//   audit-events.ts  -- event type definitions (no I/O)
//   audit-fold.ts    -- pure fold/correlate/summarize (no I/O)
//   event-log.ts     -- EventLog class, extractors, readProjection
//   audit-log-formatter.ts -- LogLine formatters for the web UI
//
// Internal lib/ imports should target the specific sub-module directly.

export * from "./audit-events.js";
export * from "./audit-fold.js";
export * from "./event-log.js";
export * from "./audit-log-formatter.js";
