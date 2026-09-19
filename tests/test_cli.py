"""Exercise the skeleton without provider calls or an installed project."""

from pathlib import Path
import subprocess
import sys

import pytest

from council.cli import main


def test_no_arguments_shows_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "usage: python -m council" in output
    assert "decision support only" in output
    assert "requires human clinical sign-off" in output
    assert "Synthetic data only" in output


def test_module_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "council", "--help"],
        cwd=Path(__file__).resolve().parents[1] / "src",
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage: python -m council" in result.stdout
    assert "requires human clinical sign-off" in result.stdout
    assert result.stderr == ""


def test_unknown_option_is_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--unknown"])
    assert error.value.code == 2
    assert "unrecognized arguments: --unknown" in capsys.readouterr().err
