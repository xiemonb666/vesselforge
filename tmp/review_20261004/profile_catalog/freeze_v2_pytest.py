"""Freeze approved v2 test inputs and exact pytest arguments before execution."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\Users\xiemo\Desktop\ShardForge")
REVIEW = ROOT / "vesselforge" / "tmp" / "review_20261004" / "profile_catalog"
PYTHON = ROOT / "third_party" / "vesselforge-runtime" / "venv" / "Scripts" / "python.exe"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    approved = json.loads((REVIEW / "v2_source_test_freeze.json").read_text(encoding="utf-8"))
    module = ROOT / "vesselforge/src/vesselforge/profile_catalog.py"
    tests = ROOT / "vesselforge/tests/test_profile_catalog.py"
    runner = REVIEW / "run_v2_targeted_pytest.py"
    freezer = Path(__file__).resolve()
    if sha256(module) != approved["v2_module_sha256"] or sha256(tests) != approved["v2_test_sha256"]:
        raise RuntimeError("v2 source/test SHA does not match the main-reviewed freeze")
    argv = [
        "-m",
        "pytest",
        "vesselforge/tests/test_profile_catalog.py",
        "-q",
        "-p",
        "no:cacheprovider",
        "--junitxml=vesselforge/tmp/review_20261004/profile_catalog/v2_pytest_junit.xml",
    ]
    sources = (
        "vesselforge/src/vesselforge/profile_catalog.py",
        "vesselforge/tests/test_profile_catalog.py",
        "vesselforge/pyproject.toml",
        "vesselforge/tmp/review_20261004/profile_catalog/v2.diff",
        "vesselforge/tmp/review_20261004/profile_catalog/v2_source_test_freeze.json",
        "vesselforge/tmp/review_20261004/profile_catalog/freeze_v2_pytest.py",
        "vesselforge/tmp/review_20261004/profile_catalog/run_v2_targeted_pytest.py",
        "third_party/vesselforge-runtime/venv/Scripts/python.exe",
    )
    locked = {relative: sha256(ROOT / relative) for relative in sources}
    receipt = {
        "schema": "vesselforge.profile_catalog.v2_pytest_prefreeze/0.1.0",
        "status": "FROZEN_BEFORE_TEST_RUN",
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "authorized_by": "main agent after reviewing v2.diff and approved source/test SHA",
        "cwd": str(ROOT),
        "executable": str(PYTHON),
        "argv": argv,
        "environment": {"PYTHONDONTWRITEBYTECODE": "1"},
        "locked_source_sha256": locked,
        "expected_junit_path": "vesselforge/tmp/review_20261004/profile_catalog/v2_pytest_junit.xml",
        "pytest_limit": "one invocation of test_profile_catalog.py only; no CAD, no solver, no full suite",
    }
    path = REVIEW / "v2_pytest_prefreeze.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "locked_source_sha256": locked, "argv": argv}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
