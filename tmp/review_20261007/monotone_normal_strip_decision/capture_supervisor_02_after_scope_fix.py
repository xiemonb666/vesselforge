"""Bounded one-shot capture supervisor; never reruns the verifier."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TIMEOUT_SECONDS = 13.0
MAX_TREE_BYTES = 4 * 1024 * 1024
AUTHORIZATION = "ROOT_20261007_MONOTONE_NORMAL_STRIP_RETRY_AFTER_SCOPE_FIX"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encoded(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    root = Path.cwd().resolve()
    review = Path(__file__).resolve().parent
    pins_path = review / "source_pins.json"
    capture = review / "once_capture_02_after_scope_fix"
    go_path = review / "normal_strip_once_GO_02_after_scope_fix.json"
    call_path = review / "invoke_once_02_after_scope_fix.py"
    supervisor_path = Path(__file__).resolve()
    if capture.exists() or go_path.exists():
        raise SystemExit("refusing: one-shot capture target already exists")
    pins = json.loads(pins_path.read_text(encoding="utf-8"))
    if pins.get("state") != "SOURCE_ONLY_READY_AWAITING_ROOT_GO":
        raise SystemExit("refusing: historical source pins state changed")

    records: list[dict[str, str]] = []
    expected: dict[str, str] = {}
    for group in ("files", "bound_inputs", "superseded_snapshot"):
        for name, item in pins[group].items():
            path = root / item["path"]
            digest = sha(path)
            records.append({"group": group, "name": name, "path": item["path"], "sha256": digest})
            if digest != item["sha256"]:
                raise SystemExit(f"refusing: pre-run pin mismatch {group}.{name}")
            expected[f"{group}.{name}"] = digest
    manifest_rel = str(pins_path.relative_to(root)).replace("\\", "/")
    manifest_sha = sha(pins_path)
    records.append({"group": "manifest", "name": "source_pins", "path": manifest_rel, "sha256": manifest_sha})
    expected["manifest.source_pins"] = manifest_sha
    call_rel = str(call_path.relative_to(root)).replace("\\", "/")
    supervisor_rel = str(supervisor_path.relative_to(root)).replace("\\", "/")
    helper_hashes = {"invoke_once_02_after_scope_fix.py": sha(call_path), "capture_supervisor_02_after_scope_fix.py": sha(supervisor_path)}

    capture.mkdir()
    argv = [sys.executable, "-B", str(call_path)]
    started_utc = utc_now()
    started = time.monotonic()
    rc: int | None = None
    timed_out = False
    launch_error: str | None = None
    raw_stdout = b""
    raw_stderr = b""
    call_attempted = True
    try:
        completed = subprocess.run(argv, cwd=root, capture_output=True, timeout=TIMEOUT_SECONDS, check=False)
        rc, raw_stdout, raw_stderr = completed.returncode, completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        raw_stdout = exc.stdout or b""
        raw_stderr = exc.stderr or b""
    except OSError as exc:
        call_attempted = False
        launch_error = type(exc).__name__
        raw_stderr = str(exc).encode("utf-8", errors="replace")
    elapsed = time.monotonic() - started
    finished_utc = utc_now()

    result_obj: dict[str, Any] | None = None
    result_error: str | None = None
    try:
        value = json.loads(raw_stdout.decode("utf-8"))
        if isinstance(value, dict):
            result_obj = value
        else:
            result_error = "stdout JSON was not an object"
    except (UnicodeDecodeError, json.JSONDecodeError):
        result_error = "no complete JSON result on stdout"
    result_raw = raw_stdout if result_obj is not None else b""

    (capture / "stdout.bin").write_bytes(raw_stdout)
    (capture / "stderr.bin").write_bytes(raw_stderr)
    (capture / "result.json").write_bytes(result_raw)
    post_records: list[dict[str, str]] = []
    for row in records:
        path = root / row["path"]
        post_records.append({"group": row["group"], "name": row["name"], "path": row["path"], "sha256": sha(path)})
    unchanged = all(a["sha256"] == b["sha256"] for a, b in zip(records, post_records))
    pins_after = json.loads(pins_path.read_text(encoding="utf-8"))
    state_unchanged = pins_after.get("state") == pins.get("state") == "SOURCE_ONLY_READY_AWAITING_ROOT_GO"
    process = {"argv": argv, "return_code": rc, "timed_out": timed_out,
               "timeout_seconds": TIMEOUT_SECONDS, "call_attempted": call_attempted,
               "started_utc": started_utc, "finished_utc": finished_utc,
               "elapsed_seconds": round(elapsed, 6), "launch_error": launch_error}
    result_record = {"available": result_obj is not None, "status": result_obj.get("status") if result_obj else None,
                     "sha256": hashlib.sha256(result_raw).hexdigest(), "parse_error": result_error}
    receipt: dict[str, Any] = {
        "schema": "vesselforge.monotone_normal_strip.once_capture_receipt.v1",
        "authorization": AUTHORIZATION,
        "source_pins_state_before": pins.get("state"), "source_pins_state_after": pins_after.get("state"),
        "source_pins_state_unchanged": state_unchanged,
        "process": process, "result": result_record,
        "pre_hashes": records, "post_hashes": post_records,
        "all_source_and_input_hashes_unchanged": unchanged,
        "helper_hashes": helper_hashes,
        "raw_stdout_bytes": len(raw_stdout), "raw_stderr_bytes": len(raw_stderr),
        "output_tree_bytes": 0, "output_tree_limit_bytes": MAX_TREE_BYTES,
    }
    go: dict[str, Any] = {
        "schema": "vesselforge.monotone_normal_strip.root_go_record.v1",
        "authorization": AUTHORIZATION, "verifier_call_count": 1 if call_attempted else 0,
        "root_ready_argument": True, "source_pins_were_modified": False,
        "source_pins_state": pins.get("state"), "return_code": rc, "timed_out": timed_out,
        "result_status": result_record["status"], "receipt_path": str((capture / "receipt.json").relative_to(root)).replace("\\", "/"),
        "receipt_sha256": "", "output_tree_bytes": 0, "output_tree_limit_bytes": MAX_TREE_BYTES,
        "global_minimum_euclidean_wall": "UNKNOWN", "native_brep": "UNKNOWN", "physics": "UNKNOWN", "material": "UNKNOWN",
    }
    fixed_files = [supervisor_path, call_path, capture / "stdout.bin", capture / "stderr.bin", capture / "result.json"]
    tree_bytes = 0
    for _ in range(8):
        receipt["output_tree_bytes"] = tree_bytes
        receipt_raw = encoded(receipt)
        go["output_tree_bytes"] = tree_bytes
        go["receipt_sha256"] = hashlib.sha256(receipt_raw).hexdigest()
        go_raw = encoded(go)
        new_size = sum(p.stat().st_size for p in fixed_files) + len(receipt_raw) + len(go_raw)
        if new_size == tree_bytes:
            break
        tree_bytes = new_size
    else:
        raise SystemExit("output-tree byte count did not stabilize")
    if tree_bytes > MAX_TREE_BYTES:
        raise SystemExit("actual output tree exceeds 4 MiB; no retry permitted")
    receipt["output_tree_bytes"] = tree_bytes
    receipt_raw = encoded(receipt)
    go["output_tree_bytes"] = tree_bytes
    go["receipt_sha256"] = hashlib.sha256(receipt_raw).hexdigest()
    go_raw = encoded(go)
    (capture / "receipt.json").write_bytes(receipt_raw)
    go_path.write_bytes(go_raw)
    actual = sum(p.stat().st_size for p in fixed_files) + len(receipt_raw) + len(go_raw)
    if actual != tree_bytes:
        raise SystemExit(f"final output-tree byte count mismatch: {actual} != {tree_bytes}")
    print(json.dumps({"return_code": rc, "timed_out": timed_out, "result_status": result_record["status"],
                      "elapsed_seconds": round(elapsed, 6), "output_tree_bytes": actual,
                      "hashes_unchanged": unchanged and state_unchanged,
                      "capture": str(capture.relative_to(root)).replace("\\", "/")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
