"""codewrapped: Spotify Wrapped for your code, from the git history on your machine."""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__, card
from .collect import collect, is_repo
from .show import Story
from .stats import Wrapped, clock12, compute

ACCENT = "#7c6cff"


def human(n: int) -> str:
    return f"{n / 1_000_000:.1f}M" if n >= 1_000_000 else f"{n / 1000:.1f}k" if n >= 10_000 else f"{n:,}"


def story(w: Wrapped, s: Story) -> None:
    s.words("codewrapped", f"Your {w.year} in code", "Reading your git history. Nothing leaves this machine.",
            hold=1.8)
    s.number("commits", w.commits, f"across {w.repos} repo{'s' if w.repos != 1 else ''}, on {w.active_days} days")
    s.number("lines added", w.added, f"and {w.deleted:,} deleted. Net {w.added - w.deleted:+,}.")
    if w.longest_streak > 1:
        s.number("day streak", w.longest_streak,
                 f"{w.streak_start:%b} {w.streak_start.day} to {w.streak_end:%b} {w.streak_end.day}, without a day off")
    if w.languages:
        s.bars("your languages, by lines written", [(l, n) for l, n in w.languages], f"Mostly {w.languages[0][0]}.")
    if len(w.top_repos) > 1:
        s.bars("where your commits went", w.top_repos, f"{w.top_repos[0][0]} got the most love")
    s.words("you code best at", f"{clock12(w.peak_hour)} on {w.peak_weekday}s",
            f"Busiest day: {w.busiest_day:%B} {w.busiest_day.day}, {w.busiest_day_commits} commits"
            + (f". Busiest month: {w.busiest_month}." if w.busiest_month else ""))
    if w.latest_commit:
        t, subject, repo = w.latest_commit
        s.words("your latest-night commit", t, f'"{subject[:70]}" in {repo}')
    if w.top_word:
        s.words("your favorite word in commit messages", w.top_word, f"{w.top_word_count} times"
                + (f". Plus {w.fix_commits} commits that were fixes." if w.fix_commits else ""))
    if w.persona:
        s.words("your developer personality", w.persona.title, w.persona.line, hold=3.0)


def summary(w: Wrapped) -> Panel:
    t = Table.grid(padding=(0, 3))
    t.add_column(style="#a09cbe", justify="right")
    t.add_column(style="bold #f5f3ff")
    t.add_row("commits", f"{w.commits:,}  [#a09cbe]in {w.repos} repos · {w.active_days} active days[/]")
    t.add_row("lines", f"[#3fd17a]+{w.added:,}[/] [#ff5c6c]-{w.deleted:,}[/]  [#a09cbe]{w.files:,} files touched[/]")
    t.add_row("longest streak", f"{w.longest_streak} days" + (
        f"  [#a09cbe]{w.streak_start} → {w.streak_end}[/]" if w.longest_streak > 1 else ""))
    if w.languages:
        t.add_row("languages", "  ".join(f"{l} [#a09cbe]{human(n)}[/]" for l, n in w.languages))
    if w.top_repos:
        t.add_row("top repos", "  ".join(f"{r} [#a09cbe]{n}[/]" for r, n in w.top_repos[:4]))
    t.add_row("rhythm", f"{clock12(w.peak_hour)} · {w.peak_weekday}s · {w.busiest_month}  "
                        f"[#a09cbe]{w.night_share:.0%} at night · {w.weekend_share:.0%} weekends[/]")
    if w.biggest_commit:
        t.add_row("biggest commit", f"{w.biggest_commit[0][:60]}  [#a09cbe]{w.biggest_commit[1]:,} lines · "
                                    f"{w.biggest_commit[2]}[/]")
    if w.shortest_message:
        t.add_row("shortest message", f'"{w.shortest_message}"')
    if w.persona:
        t.add_row("personality", f"[{ACCENT}]{w.persona.title}[/]  [#a09cbe]{w.persona.line}[/]")
    return Panel(t, title=f"[bold {ACCENT}]codewrapped[/] [#a09cbe]{w.year}[/]", title_align="left",
                 border_style=ACCENT, padding=(1, 2))


def make_card(w: Wrapped, path: Path) -> Path:
    stats = [("commits", f"{w.commits:,}"), ("lines added", human(w.added)),
             ("day streak", f"{w.longest_streak}"), ("active days", f"{w.active_days}")]
    # repo names can be private work projects, so the card only shows languages
    return card.render(path, brand="codewrapped", year_label=str(w.year), persona=w.persona.title,
                       tagline=w.persona.line, stats=stats, bars=w.languages, bars_title="languages",
                       footer="uvx codewrapped", accent=(124, 108, 255), top=(18, 16, 44), bottom=(8, 8, 20))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="codewrapped",
                                description="Spotify Wrapped for your code: your year in commits, from every git "
                                            "repo on your machine. Nothing leaves your computer.")
    p.add_argument("paths", nargs="*", type=Path, help="repos or folders to search for repos (default: here)")
    p.add_argument("--year", type=int, default=date.today().year)
    p.add_argument("--author", action="append", help="email or name to count as you (repeatable; default: "
                                                     "your git config)")
    p.add_argument("--everyone", action="store_true", help="include every author (a whole team's wrapped)")
    p.add_argument("--depth", type=int, default=5, help="how deep to look for repos (default 5)")
    p.add_argument("--no-anim", action="store_true")
    p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--card", type=Path, help="share card path (default ./codewrapped-<year>.png)")
    p.add_argument("--no-card", action="store_true")
    p.add_argument("--version", action="version", version=f"codewrapped {__version__}")
    a = p.parse_args(argv)
    console = Console()
    roots = a.paths or [Path.cwd()]
    if not any(is_repo(r) for r in roots) and roots == [Path.cwd()] and Path.cwd() == Path.home():
        console.print("[#a09cbe]Searching your whole home folder for repos. Point me at your code folder to be "
                      "faster: codewrapped ~/code[/]")
    with console.status("[#a09cbe]reading git history…[/]", spinner="dots"):
        commits, repos, ids = collect(roots, a.year, a.author, a.everyone, a.depth)
    if not repos:
        console.print("No git repositories found here. Try: codewrapped ~/code")
        return 1
    if not commits:
        who = ", ".join(sorted(ids)) or "(no git identity configured)"
        console.print(f"Found {len(repos)} repos but no {a.year} commits by {who}.\n"
                      "Add the emails you commit with: codewrapped --author you@work.com --author you@home.com")
        return 1
    name = subprocess.run(["git", "config", "--global", "user.name"], capture_output=True, text=True).stdout.strip()
    w = compute(commits, a.year, name)
    if not a.no_anim and console.is_terminal:
        try:
            story(w, Story(console, ACCENT, a.speed))
        except KeyboardInterrupt:
            pass
    console.print(summary(w))
    if not a.no_card:
        out = a.card or Path(f"codewrapped-{a.year}.png")
        try:
            make_card(w, out)
            console.print(f"\n[bold {ACCENT}]Share card saved:[/] {out}  [#a09cbe](no repo names or code on it, "
                          f"just your numbers and languages)[/]")
        except OSError as e:
            console.print(f"[#a09cbe]Couldn't save the share card: {e}[/]")
    return 0


def run() -> None:
    sys.exit(main())


if __name__ == "__main__":
    run()
