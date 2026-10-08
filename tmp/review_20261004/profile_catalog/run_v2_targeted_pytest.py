"""Run exactly the v2 profile-catalog tests and retain a complete receipt."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\Users\xiemo\Desktop\ShardForge")
REVIEW = ROOT / "vesselforge" / "tmp" / "review_20261004" / "profile_catalog"
PREFLIGHT = REVIEW / "v2_pytest_prefreeze.json"
PYTHON = ROOT / "third_party" / "vesselforge-runtime" / "venv" / "Scripts" / "python.exe"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    frozen = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    for relative, expected in frozen["locked_source_sha256"].items():
        actual = sha256(ROOT / relative)
        if actual != expected:
            raise RuntimeError(f"preflight source hash mismatch: {relative}")
    if str(PYTHON) != frozen["executable"]:
        raise RuntimeError("preflight Python executable path mismatch")
    argv = list(frozen["argv"])
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    started = datetime.now(timezone.utc).isoformat()
    completed = subprocess.run(
        [str(PYTHON), *argv],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    finished = datetime.now(timezone.utc).isoformat()
    (REVIEW / "v2_pytest_stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (REVIEW / "v2_pytest_stderr.txt").write_text(completed.stderr, encoding="utf-8")
    (REVIEW / "v2_pytest_exit_code.txt").write_text(f"{completed.returncode}\n", encoding="ascii")
    run_record = {
        "cwd": str(ROOT),
        "executable": str(PYTHON),
        "argv": argv,
        "full_argv": [str(PYTHON), *argv],
        "environment": {"PYTHONDONTWRITEBYTECODE": "1"},
        "started_utc": started,
        "finished_utc": finished,
        "exit_code": completed.returncode,
    }
    (REVIEW / "v2_pytest_run.json").write_text(
        json.dumps(run_record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report_files = {
        "vesselforge/src/vesselforge/profile_catalog.py": ROOT / "vesselforge/src/vesselforge/profile_catalog.py",
        "vesselforge/tests/test_profile_catalog.py": ROOT / "vesselforge/tests/test_profile_catalog.py",
        "vesselforge/tmp/review_20261004/profile_catalog/run_v2_targeted_pytest.py": Path(__file__).resolve(),
        "vesselforge/tmp/review_20261004/profile_catalog/freeze_v2_pytest.py": REVIEW / "freeze_v2_pytest.py",
        "vesselforge/tmp/review_20261004/profile_catalog/v2_pytest_prefreeze.json": PREFLIGHT,
        "vesselforge/tmp/review_20261004/profile_catalog/v2_pytest_stdout.txt": REVIEW / "v2_pytest_stdout.txt",
        "vesselforge/tmp/review_20261004/profile_catalog/v2_pytest_stderr.txt": REVIEW / "v2_pytest_stderr.txt",
        "vesselforge/tmp/review_20261004/profile_catalog/v2_pytest_exit_code.txt": REVIEW / "v2_pytest_exit_code.txt",
        "vesselforge/tmp/review_20261004/profile_catalog/v2_pytest_run.json": REVIEW / "v2_pytest_run.json",
        "vesselforge/tmp/review_20261004/profile_catalog/v2_pytest_junit.xml": REVIEW / "v2_pytest_junit.xml",
    }
    after = {
        relative: sha256(path) if path.is_file() else None
        for relative, path in report_files.items()
    }
    after_record = {
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "pytest_exit_code": completed.returncode,
        "files_sha256": after,
    }
    (REVIEW / "v2_pytest_after_sha256.json").write_text(
        json.dumps(after_record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
