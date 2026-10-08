from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    freeze_dir = Path(__file__).resolve().parent
    artifact_dir = freeze_dir.parent
    repo = freeze_dir.parents[4]
    package_dir = repo / "vesselforge"
    source = package_dir / "src/vesselforge/ornament_fields.py"
    test = package_dir / "tests/test_ornament_fields.py"
    freeze = json.loads((freeze_dir / "freeze.json").read_text(encoding="utf-8"))
    expected_source = freeze["files"]["vesselforge/src/vesselforge/ornament_fields.py"]["v2_sha256"]
    expected_test = freeze["files"]["vesselforge/tests/test_ornament_fields.py"]["v2_sha256"]
    before = {"source_sha256": sha256(source), "test_sha256": sha256(test)}
    if before["source_sha256"] != expected_source or before["test_sha256"] != expected_test:
        raise SystemExit("Live source/test do not match the reviewed v2 freeze; pytest not run.")

    stdout_path = artifact_dir / "pytest_v2.stdout.txt"
    stderr_path = artifact_dir / "pytest_v2.stderr.txt"
    junit_path = artifact_dir / "pytest_v2.junit.xml"
    receipt_path = artifact_dir / "pytest_v2_receipt.json"
    argv = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/test_ornament_fields.py",
        f"--junitxml={junit_path}",
    ]
    result = subprocess.run(
        argv,
        cwd=package_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")
    after = {"source_sha256": sha256(source), "test_sha256": sha256(test)}
    receipt = {
        "task": "Reviewed VesselForge ornament_fields v2 targeted pytest",
        "executable": sys.executable,
        "argv": argv,
        "cwd": str(package_dir),
        "source_test_sha256_before": before,
        "source_test_sha256_after": after,
        "stdout_file": str(stdout_path),
        "stdout": result.stdout,
        "stderr_file": str(stderr_path),
        "stderr": result.stderr,
        "junit_xml": str(junit_path) if junit_path.exists() else None,
        "junit_xml_sha256": sha256(junit_path) if junit_path.exists() else None,
        "exit_code": result.returncode,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
