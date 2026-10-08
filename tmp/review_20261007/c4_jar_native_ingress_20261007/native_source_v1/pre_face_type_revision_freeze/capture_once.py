"""One-shot bounded external capture; execution stays disabled without --root-go."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT = ROOT / "vesselforge/experiments/c4_jar_native_ingress_20261007"
REVIEW = ROOT / "vesselforge/tmp/review_20261007/c4_jar_native_ingress_20261007/native_source_v1"
PINS_PATH = REVIEW / "source_pins.json"
OUTPUT = REVIEW / "run01_root_go"
PYTHON = ROOT / "third_party/vesselforge-runtime/venv/Scripts/python.exe"
DRIVER = EXPERIMENT / "native_c4_ingress.py"
CASE = EXPERIMENT / "native_c4_ingress_case.json"
TIMEOUT_SECONDS = 55
OUTPUT_LIMIT = 20 * 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def encoded_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def all_pinned_files(pins: dict[str, Any]) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for group in ("source_files", "inputs", "preserved_files", "tooling"):
        for name, item in pins.get(group, {}).items():
            paths[f"{group}.{name}"] = ROOT / item["path"]
    paths["pins"] = PINS_PATH
    return paths


def preflight(pins: dict[str, Any]) -> dict[str, str]:
    if pins.get("execution_authorized") is not False:
        raise RuntimeError("source pins must remain execution_authorized=false")
    files = all_pinned_files(pins)
    actual = {}
    for label, path in files.items():
        if not path.is_file():
            raise RuntimeError(f"missing pinned file {label}: {path}")
        actual[label] = sha256_file(path)
    for group in ("source_files", "inputs", "preserved_files", "tooling"):
        for name, item in pins.get(group, {}).items():
            label = f"{group}.{name}"
            if actual[label] != item["sha256"]:
                raise RuntimeError(f"pinned hash mismatch for {label}")
    if sha256_file(CASE) != pins["source_files"]["case"]["sha256"]:
        raise RuntimeError("case pin mismatch")
    if sha256_file(DRIVER) != pins["source_files"]["driver"]["sha256"]:
        raise RuntimeError("driver pin mismatch")
    if sha256_file(Path(__file__)) != pins["source_files"]["runner"]["sha256"]:
        raise RuntimeError("runner pin mismatch")
    return actual


def files_in_output() -> list[Path]:
    return sorted(path for path in OUTPUT.rglob("*") if path.is_file())


def total_output_bytes() -> int:
    return sum(path.stat().st_size for path in files_in_output())


def write_receipt_fixed_point(receipt: dict[str, Any]) -> tuple[bool, int]:
    receipt_path = OUTPUT / "receipt.json"
    receipt["receipt_count_status"] = "PASS_EXACT_BYTES"
    for attempt in range(1, 11):
        receipt["receipt_fixed_point_attempt"] = attempt
        raw = encoded_json(receipt)
        with receipt_path.open("wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        actual_total = total_output_bytes()
        actual_receipt = receipt_path.stat().st_size
        expected_status = "OUTPUT_CAP_EXCEEDED" if actual_total >= OUTPUT_LIMIT else receipt.get("status")
        if receipt.get("status") != expected_status:
            receipt["status"] = expected_status
            continue
        if receipt.get("total_persisted_bytes") == actual_total and receipt.get("receipt_bytes") == actual_receipt:
            return True, actual_total
        receipt["total_persisted_bytes"] = actual_total
        receipt["receipt_bytes"] = actual_receipt
    receipt["receipt_count_status"] = "UNKNOWN_FIXED_POINT_NOT_REACHED"
    receipt["total_persisted_bytes"] = None
    receipt["receipt_bytes"] = None
    with receipt_path.open("wb") as stream:
        stream.write(encoded_json(receipt))
        stream.flush()
        os.fsync(stream.fileno())
    return False, total_output_bytes()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-go", action="store_true", help="explicit future authorization for exactly one attempt")
    args = parser.parse_args()
    if not args.root_go:
        print("execution disabled; require --root-go")
        return 2
    started = time.monotonic()
    pins = json.loads(PINS_PATH.read_text(encoding="utf-8"))
    try:
        pre = preflight(pins)
    except Exception as exc:
        print(json.dumps({"status": "PREFLIGHT_FAIL", "error": f"{type(exc).__name__}: {exc}"}, sort_keys=True))
        return 2
    if OUTPUT.exists():
        print(json.dumps({"status": "OUTPUT_COLLISION_NO_RETRY", "output": str(OUTPUT)}, sort_keys=True))
        return 2
    OUTPUT.mkdir(parents=False, exist_ok=False)
    lock = OUTPUT / "run.lock"
    with lock.open("xb") as stream:
        stream.write((json.dumps({"status": "RUNNING", "argv": sys.argv[:], "started_unix": time.time()}) + "\n").encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    argv = [str(PYTHON), "-B", str(DRIVER), "--root-go", "--output-dir", str(OUTPUT)]
    child_rc: int | None = None
    timed_out = False
    error: str | None = None
    stdout = b""
    stderr = b""
    try:
        completed = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=TIMEOUT_SECONDS, check=False)
        child_rc = int(completed.returncode)
        stdout = completed.stdout or b""
        stderr = completed.stderr or b""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout if isinstance(exc.stdout, bytes) else (exc.stdout or b"").encode("utf-8", "replace")
        stderr = exc.stderr if isinstance(exc.stderr, bytes) else (exc.stderr or b"").encode("utf-8", "replace")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    (OUTPUT / "stdout.raw").write_bytes(stdout)
    (OUTPUT / "stderr.raw").write_bytes(stderr)
    with lock.open("wb") as stream:
        stream.write((json.dumps({"status": "ATTEMPT_RECORDED", "argv": argv, "child_return_code": child_rc, "timed_out": timed_out, "elapsed_seconds": time.monotonic() - started}, sort_keys=True) + "\n").encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    post = {name: sha256_file(path) for name, path in all_pinned_files(pins).items() if path.is_file()}
    changed = pre != post
    status = "INPUT_CHANGED" if changed else "TIMEOUT" if timed_out else "CAPTURE_ERROR" if error else "CHILD_FAILED" if child_rc else "CAPTURED"
    receipt: dict[str, Any] = {
        "schema": "vesselforge.c4_jar_native_ingress.capture_receipt/1.0",
        "status": status,
        "source_freeze_execution_authorized": False,
        "run_authorized_by_explicit_root_go_argument": True,
        "actual_argv": argv,
        "child_return_code": child_rc,
        "timed_out": timed_out,
        "worker_timeout_seconds": TIMEOUT_SECONDS,
        "outer_elapsed_seconds": time.monotonic() - started,
        "error": error,
        "stdout_bytes": len(stdout),
        "stderr_bytes": len(stderr),
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "pre_sha256": pre,
        "post_sha256": post,
        "pre_equals_post": not changed,
        "output_limit_bytes_exclusive": OUTPUT_LIMIT,
        "total_persisted_bytes": None,
        "receipt_bytes": None,
        "receipt_count_status": "PENDING",
    }
    stable, total = write_receipt_fixed_point(receipt)
    status = receipt["status"] if stable else "RECEIPT_COUNT_UNKNOWN"
    receipt_sha = sha256_file(OUTPUT / "receipt.json")
    print(json.dumps({"status": status, "child_return_code": child_rc, "timed_out": timed_out, "elapsed_seconds": time.monotonic() - started, "total_persisted_bytes": total if stable else None, "receipt_sha256": receipt_sha, "output": str(OUTPUT)}, sort_keys=True))
    if status in ("CAPTURED",) and child_rc == 0:
        return 0
    return 124 if timed_out else 1


if __name__ == "__main__":
    raise SystemExit(main())
