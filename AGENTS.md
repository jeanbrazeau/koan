# Koan Architecture Invariant

LLMs write **markdown files only**. LLMs communicate with the driver through **tool calls only**.
The driver maintains `.json` state files internally — no LLM ever reads or writes a `.json` file.

Example: orchestrator calls `koan_complete_story(story_id)` → tool code writes `state.json` + `status.md` →
driver reads `state.json` to route next action. The orchestrator never touches `state.json` directly.
