"""Find git repositories and read one person's commits for a year. Everything stays local."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

SKIP_DIRS = {
    "node_modules", ".venv", "venv", "env", ".tox", ".cache", "__pycache__", "target", "build", "dist",
    "Library", "Applications", ".Trash", "AppData", ".npm", ".cargo", ".rustup", ".pyenv", ".nvm",
    "vendor", "Pods", "DerivedData", ".gradle", ".m2", "site-packages", ".local", ".git",
}

RS, US = "\x1e", "\x1f"  # record / unit separators keep commit messages unambiguous


@dataclass
class Commit:
    sha: str
    repo: str
    email: str
    name: str
    when: datetime  # author time, in the author's own timezone
    subject: str
    files: list[tuple[str, int, int]] = field(default_factory=list)  # (path, added, deleted)


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    return out.stdout if out.returncode == 0 else ""


def is_repo(path: Path) -> bool:
    return (path / ".git").exists()


def find_repos(roots: Iterable[Path], max_depth: int = 5) -> list[Path]:
    """Walk `roots` for git repositories (not descending into a repo once found)."""
    found: list[Path] = []
    for root in roots:
        root = root.expanduser().resolve()
        if is_repo(root):
            found.append(root)
            continue
        base_depth = len(root.parts)
        for dirpath, dirnames, _ in os.walk(root, onerror=lambda e: None):
            here = Path(dirpath)
            if is_repo(here):
                found.append(here)
                dirnames[:] = []
                continue
            if len(here.parts) - base_depth >= max_depth:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not (d.startswith(".") and d != ".config")]
    seen, unique = set(), []
    for r in found:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return unique


def my_identities(repos: list[Path]) -> set[str]:
    """Emails and names from global git config plus each repo's local config."""
    ids: set[str] = set()
    for key in ("user.email", "user.name"):
        v = subprocess.run(["git", "config", "--global", key], capture_output=True, text=True).stdout.strip()
        if v:
            ids.add(v.lower())
    for r in repos:
        for key in ("user.email", "user.name"):
            v = _git(r, "config", "--local", key).strip()
            if v:
                ids.add(v.lower())
    return ids


def read_commits(repo: Path, year: int, identities: set[str] | None) -> Iterator[Commit]:
    """Non-merge commits from all refs, authored in `year`, by anyone in `identities` (None = everyone)."""
    fmt = f"{RS}%H{US}%ae{US}%an{US}%aI{US}%s"
    log = _git(repo, "log", "--all", "--no-merges", "--numstat", "--no-renames",
               f"--since={year - 1}-12-30", f"--until={year + 1}-01-02", f"--format={fmt}")
    name = repo.name
    for block in log.split(RS)[1:]:
        head, _, rest = block.partition("\n")
        parts = head.split(US)
        if len(parts) < 5:
            continue
        sha, email, author, iso, subject = parts[0], parts[1], parts[2], parts[3], US.join(parts[4:])
        try:
            when = datetime.fromisoformat(iso)
        except ValueError:
            continue
        if when.year != year:  # author-local calendar year
            continue
        if identities is not None and email.lower() not in identities and author.lower() not in identities:
            continue
        files = []
        for line in rest.splitlines():
            cols = line.split("\t")
            if len(cols) == 3:
                a, d, path = cols
                files.append((path, int(a) if a.isdigit() else 0, int(d) if d.isdigit() else 0))
        yield Commit(sha, name, email, author, when, subject, files)


def collect(roots: list[Path], year: int, authors: list[str] | None = None, everyone: bool = False,
            max_depth: int = 5) -> tuple[list[Commit], list[Path], set[str]]:
    repos = find_repos(roots, max_depth=max_depth)
    if everyone:
        ids = None
    else:
        ids = {a.lower() for a in authors} if authors else my_identities(repos)
    commits: dict[str, Commit] = {}
    for r in repos:
        for c in read_commits(r, year, ids):
            commits.setdefault(c.sha, c)  # the same commit can live in several clones/forks
    return sorted(commits.values(), key=lambda c: c.when), repos, ids or set()
