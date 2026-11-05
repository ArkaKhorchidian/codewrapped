"""Build git repositories with a realistic year of commits, quickly, via `git fast-import`."""
from __future__ import annotations

import random
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

ME = ("Ada Lovelace", "ada@example.com")
OTHER = ("Grace Hopper", "grace@example.com")
REPOS = {
    "api": [".py", ".py", ".py", ".sql", ".md"],
    "dashboard": [".ts", ".tsx", ".tsx", ".css", ".json"],
    "engine": [".rs", ".rs", ".rs", ".toml"],
    "infra": [".tf", ".yml", ".sh"],
}
SUBJECTS = ["fix flaky test", "add pagination to search", "refactor auth middleware", "fix typo",
            "wip", "bump deps", "add dark mode", "fix race in worker pool", "speed up cold start",
            "remove dead code", "add retries", "handle empty state", "fix", "initial schema",
            "rewrite parser", "add metrics", "fix null deref on login", "docs: usage examples"]


def build(root: Path, year: int = 2026, seed: int = 1, per_repo: int = 260, tz_hours: int = -5) -> dict:
    rng = random.Random(seed)
    tz = timezone(timedelta(hours=tz_hours))
    root.mkdir(parents=True, exist_ok=True)
    made = {}
    for name, exts in REPOS.items():
        repo = root / name
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        stream, mark = [], 0
        files: dict[str, int] = {}
        t = datetime(year, 1, 3, 10, 0, tzinfo=tz)
        for i in range(per_repo):
            # mostly daily work with a long streak in spring, a few gaps, lots of late evenings
            if not (datetime(year, 3, 1, tzinfo=tz) <= t <= datetime(year, 4, 20, tzinfo=tz)) and rng.random() < 0.35:
                t += timedelta(days=rng.randint(1, 4))
            t += timedelta(hours=rng.choice([2, 5, 20, 22, 24, 26]), minutes=rng.randint(0, 59))
            if rng.random() < 0.45:
                t = t.replace(hour=rng.choice([21, 22, 23, 0, 1]))
            if t.year > year:
                break
            author = ME if rng.random() < 0.85 else OTHER
            path = f"src/{rng.choice(['core', 'util', 'app', 'lib'])}{rng.randint(1, 6)}{rng.choice(exts)}"
            n = files.get(path, 0) + rng.randint(3, 120)
            if path in files and rng.random() < 0.3:  # refactors shrink files
                n = max(5, files[path] - rng.randint(10, 90))
            files[path] = n
            content = "".join(f"line {k} of {path}\n" for k in range(n))
            mark += 1
            ts = f"{int(t.timestamp())} {t.strftime('%z')}"
            msg = rng.choice(SUBJECTS)
            stream += [f"blob", f"mark :{mark}", f"data {len(content.encode())}", content]
            stream += [f"commit refs/heads/main", f"author {author[0]} <{author[1]}> {ts}",
                       f"committer {author[0]} <{author[1]}> {ts}", f"data {len(msg.encode())}", msg]
            stream += [f"M 100644 :{mark} {path}", ""]
        subprocess.run(["git", "-C", str(repo), "fast-import", "--quiet"], input="\n".join(stream).encode(),
                       check=True)
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"], check=False, capture_output=True)
        made[name] = repo
    return made


if __name__ == "__main__":
    import sys
    build(Path(sys.argv[1]))
    print("fake repos ready")
