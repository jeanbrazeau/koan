# Eval Fixtures

Each subdirectory is one benchmark fixture. Structure:

    <fixture-name>/
        task.md          -- task description (UTF-8 plain text)
        snapshot.tar.gz  -- git archive of the target project at a specific commit
        memory/          -- copy of .koan/memory/ at that point

`snapshot.tar.gz` and `memory/` are gitignored -- they are large and must be
captured manually by Leon. Only `task.md` is committed.

To capture a new fixture from the koan project itself:

    mkdir -p evals/fixtures/<name>/memory
    git archive HEAD --format=tar.gz -o evals/fixtures/<name>/snapshot.tar.gz
    cp .koan/memory/*.md evals/fixtures/<name>/memory/
    echo "Your task description" > evals/fixtures/<name>/task.md
