"""Tests for the audit tool, using simulated Git/test commands."""

import ast
from pathlib import Path
import subprocess

import pytest

from tools import mutation_check as audit


def test_t1_plan() -> None:
    source = (audit.ROOT / "src/council/models.py").read_text(encoding="utf-8")
    plan = audit.build_t1(source)
    assert len(plan) == 117
    assert len({row[0] for row in plan}) == 117
    for _, changed, expected, _, _ in plan:
        assert changed != source and expected
        ast.parse(changed)
    assert 'class TurnStatus(StrEnum):\n    OK = "ok"' in plan[6][1]
    assert 'class Round2Status(StrEnum):\n    OK = "INVALID"' in plan[6][1]


def test_spec_requires_one_exact_match() -> None:
    spec = [dict(rule="limit", old="limit = 2", new="limit = 3", test="test_limit")]
    assert audit.build_from_spec("limit = 2", spec)[0][1] == "limit = 3"
    for source in ["limit = 1", "limit = 2\nlimit = 2"]:
        with pytest.raises(ValueError, match="exactly once"):
            audit.build_from_spec(source, spec)


@pytest.mark.parametrize("result", [
    subprocess.CompletedProcess([], 0, " M file.py\n", ""),
    subprocess.CompletedProcess([], 0, "", "warning: inaccessible directory"),
])
def test_dirty_or_unreadable_tree_refused(monkeypatch: pytest.MonkeyPatch, result: subprocess.CompletedProcess[str]) -> None:
    monkeypatch.setattr(audit.subprocess, "run", lambda *args, **kwargs: result)
    with pytest.raises(ValueError, match="clean"):
        audit.require_clean(Path.cwd())


@pytest.mark.parametrize("outcome", ["killed", "survived", "collection_error", "timeout"])
def test_restore_after_every_outcome(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str) -> None:
    target = tmp_path / "example.py"
    target.write_text("original", encoding="utf-8")
    commands: list[list[str]] = []

    def git(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[1] == "restore":
            target.write_text("original", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    def tests(root: Path) -> subprocess.CompletedProcess[str]:
        assert target.read_text() == "broken"
        if outcome == "timeout":
            raise subprocess.TimeoutExpired("pytest", 120)
        # A collection error has no "FAILED " line at all (nothing ran), unlike an
        # ordinary test failure; it must still count as killed, on exit code alone.
        stdout = {"killed": "FAILED tests/test_example.py::test_rule", "survived": "",
                 "collection_error": "ERROR tests/test_example.py - ImportError: boom"}[outcome]
        code = {"killed": 1, "survived": 0, "collection_error": 2}[outcome]
        return subprocess.CompletedProcess([], code, stdout, "")

    monkeypatch.setattr(audit.subprocess, "run", git)
    monkeypatch.setattr(audit, "run_tests", tests)
    mutation = ("rule", "broken", "test_rule", "original", "broken")
    if outcome == "timeout":
        with pytest.raises(subprocess.TimeoutExpired):
            audit.run_mutation(tmp_path, target, mutation)
    else:
        result = audit.run_mutation(tmp_path, target, mutation)
        assert result["killed"] is (outcome != "survived")
    assert target.read_text() == "original"
    assert commands[-2:] == [["git", "restore", "--", "example.py"], ["git", "status", "--porcelain"]]


def test_import_time_crash_is_killed_end_to_end(tmp_path: Path) -> None:
    """A real pytest run: a mutation that crashes a module at import time, before any
    test runs, must be reported killed. This is what the pre-fix tool got wrong: no
    "FAILED " line is ever produced for a collection error, only a nonzero exit code.
    """
    (tmp_path / "tests").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\npythonpath = ["."]\n', encoding="utf-8")
    target = tmp_path / "target.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests" / "conftest.py").write_text("import target\n", encoding="utf-8")
    (tmp_path / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    def git(*args: str) -> None:
        subprocess.run(list(args), cwd=tmp_path, capture_output=True, check=True)

    git("git", "init", "-q")
    git("git", "config", "user.email", "synthetic@example.com")
    git("git", "config", "user.name", "Synthetic")
    git("git", "add", "-A")
    git("git", "commit", "-q", "-m", "synthetic baseline")

    baseline = audit.run_tests(tmp_path)
    assert baseline.returncode == 0

    mutations = audit.build_from_spec(target.read_text(encoding="utf-8"), [
        dict(rule="Import-time crash", old="VALUE = 1",
             new="raise RuntimeError('synthetic import crash')", test="test_ok"),
    ])
    record = audit.run_mutation(tmp_path, target, mutations[0])

    assert record["exit_code"] != 0
    assert not any(line.startswith("FAILED ") for line in record["failed_tests"])
    assert record["killed"] is True
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
    audit.require_clean(tmp_path)
