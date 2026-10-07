"""P2-06 (ADR-039): the outreach agent's eval suite runs on every push, replaying the replies its
last live run recorded, so it costs nothing. It passes as recorded, and a planted regression (an
invented price) fails it. Each run is a separate process with its own database."""

import subprocess
import sys

from cornerpin.core.config import REPO_ROOT

from .conftest import Databases


def run_evals(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- our own module, fixed arguments
        [sys.executable, "-m", "evals", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def test_the_suite_passes_on_its_recordings(db: Databases) -> None:
    result = run_evals()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "replaying the recordings" in result.stdout
    assert "This run cost nothing" in result.stdout


def test_a_planted_invented_price_fails_the_suite(db: Databases) -> None:
    result = run_evals("--plant", "invented-price", "--only", "quotes_the_price")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "FAIL  quotes_the_price" in result.stdout
    assert "invented a price ($494,000); the guard held it back" in result.stdout
    assert "didn't state lot 2-6's price ($489,000)" in result.stdout
