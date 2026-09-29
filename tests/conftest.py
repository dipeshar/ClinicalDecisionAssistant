"""Shared synthetic settings; no model calls or external resources."""

from pathlib import Path

import pytest
import yaml

from council.config import load_config
from council.models import Config


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--race-iterations", type=int, default=25,
                     help="Iterations per thread in the combined budget/trace race test")


@pytest.fixture
def config(tmp_path: Path) -> Config:
    data = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    for role in ("specialist", "chair", "red_team"):
        data["models"][role] = {"provider": "fake", "model": "specialist"}
    data["models"]["judge_a"] = {"provider": "fake", "model": "judge-a"}
    data["models"]["judge_b"] = {"provider": "fake", "model": "judge-b"}
    data["privacy"]["approved_providers"] = ["fake"]
    data["paths"]["runs"] = str(tmp_path / "runs")
    path = tmp_path / "test-config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return load_config(path)
