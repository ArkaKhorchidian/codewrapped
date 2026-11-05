import subprocess
from datetime import date, datetime, timedelta, timezone

from PIL import Image

from codewrapped.cli import main
from codewrapped.collect import Commit, collect, find_repos
from codewrapped.stats import compute, language_of, longest_run, persona
from fake_repos import build


def test_find_repos_skips_noise(tmp_path):
    build(tmp_path / "code", per_repo=5)
    (tmp_path / "code/node_modules/dep/.git").mkdir(parents=True)  # must be skipped
    (tmp_path / "code/api/nested/.git").mkdir(parents=True)  # inside a repo: not descended into
    names = sorted(r.name for r in find_repos([tmp_path]))
    assert names == ["api", "dashboard", "engine", "infra"]


def test_collect_filters_author_and_year_and_dedupes(tmp_path):
    build(tmp_path / "code", per_repo=60, seed=4)
    # a clone of the same repo must not double-count commits
    subprocess.run(["git", "clone", "-q", str(tmp_path / "code/api"), str(tmp_path / "code/api-copy")], check=True)
    mine, repos, _ = collect([tmp_path], 2026, ["ada@example.com"])
    everyone, _, _ = collect([tmp_path], 2026, everyone=True)
    assert len(repos) == 5
    assert mine and all(c.email == "ada@example.com" and c.when.year == 2026 for c in mine)
    assert len(everyone) > len(mine)
    assert len({c.sha for c in mine}) == len(mine)
    assert collect([tmp_path], 2015, ["ada@example.com"])[0] == []


def test_matching_by_name_too(tmp_path):
    build(tmp_path / "code", per_repo=20, seed=2)
    by_name, _, _ = collect([tmp_path], 2026, ["ada lovelace"])
    by_email, _, _ = collect([tmp_path], 2026, ["ada@example.com"])
    assert {c.sha for c in by_name} == {c.sha for c in by_email}


def c(day, hour=12, files=(("a.py", 10, 2),), subject="work", repo="r"):
    tz = timezone(timedelta(hours=-5))
    return Commit(f"{day}{hour}{subject}", repo, "me@x", "Me", datetime(2026, 1, day, hour, 0, tzinfo=tz), subject,
                  list(files))


def test_streaks_and_counts():
    assert longest_run([date(2026, 1, d) for d in (1, 2, 3, 5, 6)]) == (3, date(2026, 1, 1), date(2026, 1, 3))
    commits = [c(1), c(2), c(3), c(3, 23, subject="fix login bug"), c(5, 2, files=(("package-lock.json", 900, 0),
                                                                                   ("ui.tsx", 40, 5)))]
    w = compute(commits, 2026)
    assert (w.commits, w.active_days, w.longest_streak) == (5, 4, 3)
    assert w.added == 4 * 10 - 10 + 40 + 10 and w.deleted == 4 * 2 + 5  # lockfile ignored
    assert dict(w.languages) == {"Python": 40, "TypeScript": 40}
    assert w.fix_commits == 1 and w.latest_commit[0] == "2:00 am"
    assert w.busiest_day == date(2026, 1, 3)


def test_language_detection():
    assert language_of("src/main.rs") == "Rust" and language_of("Dockerfile") == "Dockerfile"
    assert language_of("x.unknownext") is None


def test_persona_night_owl():
    commits = [c(d, 23) for d in range(1, 15)] + [c(d, 10) for d in range(15, 20)]
    w = compute(commits, 2026)
    assert w.persona.title == "The Night Owl"


def test_cli_end_to_end(tmp_path, capsys):
    build(tmp_path / "code", per_repo=80, seed=6)
    card = tmp_path / "card.png"
    code = main([str(tmp_path / "code"), "--author", "ada@example.com", "--year", "2026", "--no-anim",
                 "--card", str(card)])
    out = capsys.readouterr().out
    assert code == 0 and "codewrapped" in out and "commits" in out
    assert Image.open(card).size == (1200, 675)


def test_cli_no_commits_is_helpful(tmp_path, capsys):
    build(tmp_path / "code", per_repo=5)
    assert main([str(tmp_path / "code"), "--author", "nobody@x", "--no-anim", "--no-card"]) == 1
    assert "--author" in capsys.readouterr().out
