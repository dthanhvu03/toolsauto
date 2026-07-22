"""Guard: app.services shim must stay gone."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"

IMPORT_RE = re.compile(r"(from|import)\s+app\.services\b")


def test_no_app_services_imports_in_runtime_code():
    offenders = []
    for path in list(APP.rglob("*.py")) + [ROOT / "manage.py"]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if IMPORT_RE.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")
    assert not offenders, "Legacy app.services imports remain:\n" + "\n".join(offenders)


def test_services_package_removed():
    assert not (APP / "services").exists(), (
        "app/services/ must be removed (ADR-007). Import from app.core / app.features / app.platform."
    )
