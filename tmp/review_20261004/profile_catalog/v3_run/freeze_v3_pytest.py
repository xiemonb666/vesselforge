"""Pin v3 sources and the one approved targeted pytest invocation."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"C:\Users\xiemo\Desktop\ShardForge")
VESS = REPO / "vesselforge"
REVIEW = VESS / "tmp" / "review_20261004" / "profile_catalog"
RUN = REVIEW / "v3_run"
PYTHON = REPO / "third_party" / "vesselforge-runtime" / "venv" / "Scripts" / "python.exe"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    approved = json.loads((REVIEW / "v3_source_test_freeze.json").read_text(encoding="utf-8"))
    if approved["validation"]["pytest_executed"] or not approved["validation"]["waiting_for_main_review"]:
        raise RuntimeError("v3 source freeze is not in the expected pre-test state")
    source = VESS / "src" / "vesselforge" / "profile_catalog.py"
    tests = VESS / "tests" / "test_profile_catalog.py"
    diff = REVIEW / "v3.diff"
    if sha256(source) != approved["v3_module_sha256"]:
        raise RuntimeError("v3 module SHA no longer matches the approved freeze")
    if sha256(tests) != approved["v3_test_sha256"]:
        raise RuntimeError("v3 test SHA no longer matches the approved freeze")
    if sha256(diff) != approved["v3_diff_sha256"]:
        raise RuntimeError("v3 diff SHA no longer matches the approved freeze")

    argv = [
        "-m",
        "pytest",
        "-q",
        "--junitxml=tmp/review_20261004/profile_catalog/v3_run/junit.xml",
        "tests/test_profile_catalog.py",
    ]
    sources = (
        "vesselforge/src/vesselforge/profile_catalog.py",
        "vesselforge/tests/test_profile_catalog.py",
        "vesselforge/tmp/review_20261004/profile_catalog/v3.diff",
        "vesselforge/tmp/review_20261004/profile_catalog/v3_source_test_freeze.json",
        "vesselforge/tmp/review_20261004/profile_catalog/v3_run/freeze_v3_pytest.py",
        "vesselforge/tmp/review_20261004/profile_catalog/v3_run/run_v3_pytest.py",
        "vesselforge/pyproject.toml",
        "third_party/vesselforge-runtime/venv/Scripts/python.exe",
    )
    locked = {relative: sha256(REPO / relative) for relative in sources}
    receipt = {
        "schema": "vesselforge.profile_catalog.v3_pytest_prefreeze/0.1.0",
        "status": "FROZEN_BEFORE_TEST_RUN",
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "approved_by": "main agent",
        "working_directory": str(VESS),
        "executable": str(PYTHON),
        "argv": argv,
        "environment": {
            "PYTHONPATH": "src",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_ADDOPTS": "-p no:cacheprovider",
        },
        "locked_source_sha256": locked,
        "expected_junit_path": "tmp/review_20261004/profile_catalog/v3_run/junit.xml",
        "scope": "tests/test_profile_catalog.py only; no other suite, CAD, or solver",
        "expected_case_count": 17,
    }
    RUN.mkdir(parents=True, exist_ok=True)
    path = RUN / "prefreeze.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "argv": argv, "locked_source_sha256": locked}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
