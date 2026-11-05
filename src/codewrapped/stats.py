"""Turn commits into a year in review."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import PurePosixPath

from .collect import Commit

# Generated / vendored files would drown out real work in line counts.
IGNORED_FILES = re.compile(
    r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Pipfile\.lock|uv\.lock|Cargo\.lock|"
    r"Gemfile\.lock|composer\.lock|go\.sum|bun\.lockb)$"
    r"|(^|/)(node_modules|vendor|dist|build|\.next|__snapshots__)/"
    r"|\.min\.(js|css)$|\.map$|\.(png|jpe?g|gif|svg|ico|pdf|zip|gz|lock|ipynb)$"
)

LANGUAGES = {
    "py": "Python", "pyi": "Python", "ipynb": "Python", "js": "JavaScript", "mjs": "JavaScript", "cjs": "JavaScript",
    "jsx": "JavaScript", "ts": "TypeScript", "tsx": "TypeScript", "go": "Go", "rs": "Rust", "java": "Java",
    "kt": "Kotlin", "kts": "Kotlin", "swift": "Swift", "c": "C", "h": "C", "cc": "C++", "cpp": "C++", "cxx": "C++",
    "hpp": "C++", "hh": "C++", "cs": "C#", "rb": "Ruby", "php": "PHP", "scala": "Scala", "dart": "Dart",
    "lua": "Lua", "r": "R", "jl": "Julia", "ex": "Elixir", "exs": "Elixir", "erl": "Erlang", "hs": "Haskell",
    "ml": "OCaml", "clj": "Clojure", "zig": "Zig", "nim": "Nim", "sh": "Shell", "bash": "Shell", "zsh": "Shell",
    "fish": "Shell", "ps1": "PowerShell", "sql": "SQL", "html": "HTML", "htm": "HTML", "css": "CSS", "scss": "CSS",
    "sass": "CSS", "less": "CSS", "vue": "Vue", "svelte": "Svelte", "md": "Markdown", "mdx": "Markdown",
    "rst": "reStructuredText", "tex": "LaTeX", "yml": "YAML", "yaml": "YAML", "toml": "TOML", "json": "JSON",
    "tf": "Terraform", "hcl": "Terraform", "sol": "Solidity", "v": "Verilog", "sv": "Verilog", "vhd": "VHDL",
    "m": "Objective-C", "mm": "Objective-C", "pl": "Perl", "dockerfile": "Dockerfile", "proto": "Protobuf",
    "graphql": "GraphQL", "nix": "Nix", "elm": "Elm", "fs": "F#", "cu": "CUDA", "glsl": "GLSL", "wgsl": "WGSL",
}
# Config/markup "languages" count toward lines but never headline someone's year.
SUPPORTING = {"Markdown", "reStructuredText", "YAML", "TOML", "JSON"}

STOPWORDS = set("""a an the and or to of in on for with from by at as is are be it this that into via
use using add added adds update updated updates fix fixed fixes remove removed make made more less new
some small minor wip initial commit merge branch main master refactor cleanup clean bump version readme
docs doc test tests change changes changed improve improved support allow when not no up out get set""".split())

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def language_of(path: str) -> str | None:
    p = PurePosixPath(path)
    if p.name.lower() == "dockerfile":
        return "Dockerfile"
    return LANGUAGES.get(p.suffix.lower().lstrip("."))


@dataclass
class Persona:
    title: str
    line: str


@dataclass
class Wrapped:
    year: int
    name: str
    commits: int = 0
    repos: int = 0
    active_days: int = 0
    added: int = 0
    deleted: int = 0
    files: int = 0
    longest_streak: int = 0
    streak_start: date | None = None
    streak_end: date | None = None
    busiest_day: date | None = None
    busiest_day_commits: int = 0
    busiest_month: str = ""
    peak_hour: int = 0
    peak_weekday: str = ""
    night_share: float = 0.0
    weekend_share: float = 0.0
    heatmap: list[list[int]] = field(default_factory=lambda: [[0] * 24 for _ in range(7)])
    by_month: list[int] = field(default_factory=lambda: [0] * 12)
    languages: list[tuple[str, int]] = field(default_factory=list)  # (language, lines added)
    top_repos: list[tuple[str, int]] = field(default_factory=list)
    top_word: str | None = None
    top_word_count: int = 0
    fix_commits: int = 0
    shortest_message: str | None = None
    biggest_commit: tuple[str, int, str] | None = None  # (subject, lines, repo)
    latest_commit: tuple[str, str, str] | None = None  # (time, subject, repo) of the latest-night commit
    persona: Persona | None = None


def clock12(hour: int, minute: int | None = None) -> str:
    h = (hour % 12) or 12
    return f"{h}{'' if minute is None else f':{minute:02d}'} {'am' if hour < 12 else 'pm'}"


def longest_run(days: list[date]) -> tuple[int, date | None, date | None]:
    if not days:
        return 0, None, None
    best = (1, days[0], days[0])
    start = prev = days[0]
    for d in days[1:]:
        if d - prev == timedelta(days=1):
            if (d - start).days + 1 > best[0]:
                best = ((d - start).days + 1, start, d)
        else:
            start = d
        prev = d
    return best


def compute(commits: list[Commit], year: int, name: str = "") -> Wrapped:
    w = Wrapped(year=year, name=name)
    if not commits:
        return w
    w.commits = len(commits)
    w.repos = len({c.repo for c in commits})

    per_day = Counter(c.when.date() for c in commits)
    days = sorted(per_day)
    w.active_days = len(days)
    w.longest_streak, w.streak_start, w.streak_end = longest_run(days)
    w.busiest_day, w.busiest_day_commits = max(per_day.items(), key=lambda kv: (kv[1], kv[0]))

    for c in commits:
        w.heatmap[c.when.weekday()][c.when.hour] += 1
        w.by_month[c.when.month - 1] += 1
    w.busiest_month = date(year, w.by_month.index(max(w.by_month)) + 1, 1).strftime("%B")
    hours = [sum(w.heatmap[d][h] for d in range(7)) for h in range(24)]
    w.peak_hour = hours.index(max(hours))
    weekdays = [sum(row) for row in w.heatmap]
    w.peak_weekday = WEEKDAYS[weekdays.index(max(weekdays))]
    w.night_share = sum(hours[h] for h in (22, 23, 0, 1, 2, 3, 4)) / w.commits
    w.weekend_share = (weekdays[5] + weekdays[6]) / w.commits

    langs: Counter[str] = Counter()
    files = set()
    biggest = None
    for c in commits:
        size = 0
        for path, a, d in c.files:
            if IGNORED_FILES.search(path):
                continue
            files.add((c.repo, path))
            w.added += a
            w.deleted += d
            size += a + d
            lang = language_of(path)
            if lang:
                langs[lang] += a
        if biggest is None or size > biggest[1]:
            biggest = (c.subject, size, c.repo)
    w.files = len(files)
    w.biggest_commit = biggest if biggest and biggest[1] > 0 else None
    main = [(l, n) for l, n in langs.most_common() if l not in SUPPORTING and n > 0]
    w.languages = (main or [(l, n) for l, n in langs.most_common() if n > 0])[:5]
    w.top_repos = Counter(c.repo for c in commits).most_common(5)

    words: Counter[str] = Counter()
    for c in commits:
        s = c.subject.lower()
        if re.search(r"\b(fix(e[sd])?|bug|hotfix|patch)\b", s):
            w.fix_commits += 1
        for tok in re.findall(r"[a-z][a-z0-9_+#-]{2,}", s):
            if tok not in STOPWORDS:
                words[tok] += 1
    if words:
        w.top_word, w.top_word_count = words.most_common(1)[0]
    subjects = [c.subject.strip() for c in commits if c.subject.strip()]
    if subjects:
        w.shortest_message = min(subjects, key=len)

    def lateness(c: Commit) -> int:  # minutes past 6pm, wrapping past midnight
        m = c.when.hour * 60 + c.when.minute
        return m - 18 * 60 if m >= 18 * 60 else m + 6 * 60 if m < 5 * 60 else -1
    late = max(commits, key=lateness)
    if lateness(late) >= 0:
        w.latest_commit = (clock12(late.when.hour, late.when.minute), late.subject, late.repo)

    w.persona = persona(w)
    return w


def persona(w: Wrapped) -> Persona:
    """Pick the trait that stands out most; each score is how far past its threshold the user is."""
    avg_per_day = w.commits / max(w.active_days, 1)
    rules = [
        (w.night_share / 0.25, "The Night Owl",
         f"{w.night_share:.0%} of your commits landed between 10pm and 5am."),
        (w.weekend_share / 0.30, "The Weekend Warrior",
         f"{w.weekend_share:.0%} of your commits happened on Saturdays and Sundays."),
        (w.longest_streak / 21, "The Marathoner",
         f"You committed {w.longest_streak} days in a row."),
        ((w.deleted / max(w.added, 1)) / 0.8 if w.added > 500 else 0, "The Refactorer",
         f"You deleted {w.deleted:,} lines. Less code, fewer bugs."),
        ((w.fix_commits / w.commits) / 0.35 if w.commits >= 20 else 0, "The Bug Hunter",
         f"{w.fix_commits} of your commits were fixes."),
        (len([l for l, n in w.languages if n > 0.08 * max(w.added, 1)]) / 4, "The Polyglot",
         f"You shipped real code in {len(w.languages)} languages."),
        ((w.busiest_day_commits / avg_per_day) / 6 if w.active_days >= 10 else 0, "The Sprinter",
         f"On your biggest day you made {w.busiest_day_commits} commits."),
        ((sum(w.heatmap[d][h] for d in range(7) for h in range(5, 9)) / w.commits) / 0.2,
         "The Early Bird", "You did your best work before most people's first coffee."),
    ]
    score, title, line = max(rules, key=lambda r: r[0])
    if score < 1:
        return Persona("The Steady Shipper", f"Commits on {w.active_days} days. Consistency is a superpower.")
    return Persona(title, line)
