---
title: Eval fixture snapshots are self-referential git submodules pinned to a SHA,
  not tarballs
type: decision
created: '2026-04-22T09:17:00Z'
modified: '2026-04-22T09:17:00Z'
---

This entry documents the fixture-snapshot storage format under `evals/fixtures/<name>/repo/` for the koan eval harness. On 2026-04-22, Leon replaced the previous `evals/fixtures/<name>/snapshot.tar.gz` scheme (tarballs tracked via git-lfs) with a git submodule at `evals/fixtures/<name>/repo/` pinned to a specific commit of the target project. For the `koan-1` fixture the submodule points at the koan repo itself -- a self-referential submodule -- pinned to SHA `fc3511684a626fbc33e2806bd089847dd7eea167`, the "epoch" commit the original tarball was captured from, verified by tree comparison against the tarball-adding commit `12fe420c6402c5134247ed253a7404a7268fbeaa`.

Leon's stated rationale: git-lfs required `git lfs install && git lfs pull` to hydrate, a recurring developer-setup papercut that surfaced as "not a gzip file" when skipped; tarballs are opaque -- not diffable, not blame-able, hard to bump to a new snapshot commit -- and reproducing a snapshot required remembering to re-run `git archive HEAD --format=tar.gz` at the right commit. With submodules the pinned SHA is the reproducibility guarantee; bumping a snapshot becomes `git -C evals/fixtures/<name>/repo checkout <sha> && git add evals/fixtures/<name>/repo && git commit`. Self-referential submodules are unusual but supported; `git clone --recurse-submodules` terminates because the submodule SHA is fixed and does not recurse into its own submodule entry.

Leon decided that the runner (`evals/runner.py`) copies the submodule tree into a `tempfile.TemporaryDirectory()` per run via `shutil.copytree(snapshot_path, project_tmp, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))`. Copying keeps cases independent and mutation-safe (plan-spec writes `plan.md`, execute modifies files). Option B -- running koan in-place against the submodule working tree and resetting via `git clean -fdx && git checkout -- .` afterward -- was rejected by Leon for cleanup fragility. Leon stated that if the self-referential approach turns out to have edge cases that cannot be cleanly resolved (nested CI checkouts, submodule URL resolution differences local vs. CI), future agents must surface the issue rather than silently falling back to a different approach.
