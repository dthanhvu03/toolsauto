"""P0-4: FACEBOOK_PLAYWRIGHT_HEADLESS defaults to headed (false)."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PY = ROOT / "app" / "config.py"
_GETENV = re.compile(
    r"os\.getenv\(\s*['\"]FACEBOOK_PLAYWRIGHT_HEADLESS['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)"
)

_SUBPROCESS = r"""
import os, sys
mode = sys.argv[1]
os.environ.pop("FACEBOOK_PLAYWRIGHT_HEADLESS", None)
if mode != "unset":
    os.environ["FACEBOOK_PLAYWRIGHT_HEADLESS"] = mode
import dotenv
dotenv.load_dotenv = lambda *a, **k: False
from app.config import FACEBOOK_PLAYWRIGHT_HEADLESS
print("1" if FACEBOOK_PLAYWRIGHT_HEADLESS else "0", end="")
"""


def _source_default() -> str:
    text = CONFIG_PY.read_text(encoding="utf-8")
    match = _GETENV.search(text)
    assert match, "FACEBOOK_PLAYWRIGHT_HEADLESS getenv default not found"
    return match.group(1)


def _headless_in_clean_process(mode: str) -> bool:
    env = os.environ.copy()
    env.pop("FACEBOOK_PLAYWRIGHT_HEADLESS", None)
    # Dummy auth so config.py does not sys.exit when dotenv is stubbed.
    env.setdefault("ADMIN_USERNAME", "test")
    env.setdefault("ADMIN_PASSWORD", "test")
    env.setdefault("SECRET_KEY", "test-secret-key")
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS, mode],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip() == "1"


def test_config_source_default_is_false():
    assert _source_default() == "false"


def test_default_false_when_env_unset():
    assert _headless_in_clean_process("unset") is False


def test_env_true_still_headless():
    assert _headless_in_clean_process("true") is True
    assert _headless_in_clean_process("TRUE") is True


def test_env_false_headed():
    assert _headless_in_clean_process("false") is False
