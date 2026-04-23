---
title: Eval benchmark fixtures are git snapshots of koan at specific commits
type: decision
created: '2026-04-17T12:06:26Z'
modified: '2026-04-22T09:23:43Z'
---

The koan eval benchmark fixture format was established on 2026-04-17 and revised on 2026-04-22 during the Inspect-to-DeepEval migration. Leon decided on 2026-04-17 that the reference benchmark corpus would be the koan project itself, captured at specific git commits. In the initial 2026-04-17 design, each fixture directory under `evals/fixtures/<name>/` stored the project state as `snapshot.tar.gz` (a `git archive HEAD --format=tar.gz` of the target project, tracked via git-lfs); the solver untarred it into a temp dir per run. Alongside the snapshot, each fixture carried `task.md` (the task description) and a `memory/` copy of `.koan/memory/` at that commit.

On 2026-04-22, Leon replaced the tarball scheme with a git submodule at `evals/fixtures/<name>/repo/` pinned to a specific SHA. For `koan-1`, the submodule is self-referential -- it points at the koan repo itself pinned to `fc3511684a626fbc33e2806bd089847dd7eea167`, the exact commit the original tarball was archived from (verified by tree comparison). The submodule scheme eliminates the `git lfs install && git lfs pull` hydration step (which had surfaced as "not a gzip file" errors when skipped) and makes snapshot bumps a normal `git -C evals/fixtures/<name>/repo checkout <new-sha> && git add evals/fixtures/<name>/repo && git commit`. Leon's 2026-04-17 rationale (koan as its own reference corpus captures real-world complexity; re-capture is simple) carries forward; the re-capture command changed from `git archive` to a submodule SHA bump. The 2026-04-17 rejected alternatives (synthetic fictional codebase; live session capture) remain rejected for the original reasons.
