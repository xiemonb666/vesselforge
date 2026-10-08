"""Execute the frozen v3 target pytest command once and capture receipts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
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
    preflight_path = RUN / "prefreeze.json"
    frozen = json.loads(preflight_path.read_text(encoding="utf-8"))
    for relative, expected in frozen["locked_source_sha256"].items():
        if sha256(REPO / relative) != expected:
            raise RuntimeError(f"preflight source hash mismatch: {relative}")
    if str(PYTHON) != frozen["executable"] or Path.cwd().resolve() != VESS.resolve():
        raise RuntimeError("preflight execution path mismatch")

    argv = list(frozen["argv"])
    environment = os.environ.copy()
    environment.update(frozen["environment"])
    started = datetime.now(timezone.utc).isoformat()
    completed = subprocess.run(
        [str(PYTHON), *argv],
        cwd=VESS,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    finished = datetime.now(timezone.utc).isoformat()
    (RUN / "stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (RUN / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
    (RUN / "exit_code.txt").write_text(f"{completed.returncode}\n", encoding="ascii")
    run_record = {
        "cwd": str(VESS),
        "executable": str(PYTHON),
        "argv": argv,
        "full_argv": [str(PYTHON), *argv],
        "environment": frozen["environment"],
        "started_utc": started,
        "finished_utc": finished,
        "exit_code": completed.returncode,
    }
    (RUN / "run.json").write_text(json.dumps(run_record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_files = {
        "vesselforge/src/vesselforge/profile_catalog.py": REPO / "vesselforge/src/vesselforge/profile_catalog.py",
        "vesselforge/tests/test_profile_catalog.py": REPO / "vesselforge/tests/test_profile_catalog.py",
        "vesselforge/tmp/review_20261004/profile_catalog/v3.diff": REVIEW / "v3.diff",
        "vesselforge/tmp/review_20261004/profile_catalog/v3_source_test_freeze.json": REVIEW / "v3_source_test_freeze.json",
        "vesselforge/tmp/review_20261004/profile_catalog/v3_run/freeze_v3_pytest.py": RUN / "freeze_v3_pytest.py",
        "vesselforge/tmp/review_20261004/profile_catalog/v3_run/run_v3_pytest.py": Path(__file__).resolve(),
        "vesselforge/tmp/review_20261004/profile_catalog/v3_run/prefreeze.json": preflight_path,
        "vesselforge/tmp/review_20261004/profile_catalog/v3_run/stdout.txt": RUN / "stdout.txt",
        "vesselforge/tmp/review_20261004/profile_catalog/v3_run/stderr.txt": RUN / "stderr.txt",
        "vesselforge/tmp/review_20261004/profile_catalog/v3_run/exit_code.txt": RUN / "exit_code.txt",
        "vesselforge/tmp/review_20261004/profile_catalog/v3_run/run.json": RUN / "run.json",
        "vesselforge/tmp/review_20261004/profile_catalog/v3_run/junit.xml": RUN / "junit.xml",
    }
    after = {relative: sha256(path) if path.is_file() else None for relative, path in report_files.items()}
    after_record = {
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "pytest_exit_code": completed.returncode,
        "files_sha256": after,
    }
    (RUN / "after_sha256.json").write_text(json.dumps(after_record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}, ensure_ascii=False))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
