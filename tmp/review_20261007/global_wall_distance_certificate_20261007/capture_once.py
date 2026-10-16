"""SOURCE_ONLY one-shot supervisor; no run occurs without a separately reviewed root GO."""
from __future__ import annotations
import hashlib, json, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CASE_PATH, PINS_PATH = HERE / "case.json", HERE / "source_pins.json"
CASE_SHA256 = "1d521dfa7ee65a7c1807b72bb12b5eb1e02a7e7c9dbb58038d875beb22ee2b88"
PINS_SHA256 = "b32b3d02e770188aae4cc88f7bf068ec59fda1069049272fc7c5b9569358bf56"
AUTHORIZATION = "ROOT_20261007_GLOBAL_WALL_DISTANCE_RUN01"
MAX_BYTES = 4 * 1024 * 1024
def digest(path: Path) -> str:
    if not path.is_file():
        raise ValueError("required file missing: " + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()
def encoded(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()
def main() -> int:
    started = time.monotonic()
    if Path.cwd().resolve() != ROOT: raise SystemExit("refusing: run from the pinned workspace root")
    if digest(CASE_PATH) != CASE_SHA256 or digest(PINS_PATH) != PINS_SHA256: raise SystemExit("refusing: capture case or pins changed")
    case = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    pins = json.loads(PINS_PATH.read_text(encoding="utf-8"))
    if case.get("decision") != "SOURCE_ONLY_READY_AWAITING_ROOT_GO" or case.get("authorization") != AUTHORIZATION: raise SystemExit("refusing: source-only case state or authorization mismatch")
    if pins.get("state") != case["decision"] or pins.get("case_sha256") != CASE_SHA256 or pins.get("case_path") != rel(CASE_PATH): raise SystemExit("refusing: capture pins do not bind the case")
    go_path = ROOT / case["go_record"]
    capture = ROOT / case["capture_directory"]
    helper = ROOT / case["invoke_helper"]
    if capture.exists() or not go_path.is_file(): raise SystemExit("refusing: run01 capture exists or separate root GO is absent")
    files = pins.get("files", {})
    required = {"checker_source", "checker_case", "checker_pins", "outer_result", "offset_result", "monostrip_result", "frozen_bspline_driver", "invoke_helper", "independent_review", "independent_decision"}
    if set(files) != required or rel(helper) != case["invoke_helper"]: raise SystemExit("refusing: unexpected pinned file set")
    pre: list[dict[str, Any]] = []
    def check(name: str, path: Path, expected: str | None = None) -> dict[str, Any]:
        value = digest(path)
        if expected is not None and value != expected: raise ValueError("pre-run SHA mismatch: " + name)
        row = {"name": name, "path": rel(path), "sha256": value, "bytes": path.stat().st_size}
        pre.append(row); return row
    check("capture_case", CASE_PATH, CASE_SHA256)
    check("capture_pins", PINS_PATH, PINS_SHA256)
    supervisor_row = check("capture_supervisor", Path(__file__).resolve())
    checked: dict[str, dict[str, Any]] = {}
    for name in sorted(files):
        item = files[name]
        path_text = item["path"]
        if Path(path_text).is_absolute() or ".." in Path(path_text).parts: raise ValueError("unsafe pinned relative path: " + name)
        checked[name] = check(name, ROOT / path_text, item["sha256"])
    helper_row = checked["invoke_helper"]
    raw_go = go_path.read_bytes()
    go_hash = hashlib.sha256(raw_go).hexdigest()
    go = json.loads(raw_go.decode("utf-8"))
    check("root_go_record", go_path, go_hash)
    for key in case["go_required_fields"]:
        if key not in go: raise ValueError("root GO missing field: " + key)
    expected_go = {"decision": "GO", "authorization": AUTHORIZATION, "case_sha256": CASE_SHA256,
        "source_pins_sha256": PINS_SHA256, "invoke_once_sha256": helper_row["sha256"],
        "capture_once_sha256": supervisor_row["sha256"], "root_ready_argument": True, "call_count_authorized": 1}
    if go.get("schema") != case["go_schema"] or any(go.get(k) != v for k, v in expected_go.items()): raise ValueError("separate root GO does not bind this one-shot capture")
    bundle_bytes = sum(row["bytes"] for row in pre)
    raw_limit = case["max_raw_stdout_stderr_bytes"]
    reserve = 2 * raw_limit + 65536
    if bundle_bytes + reserve > case["bounded_files_limit_bytes"] or time.monotonic() - started > 3: raise SystemExit("refusing: preflight exceeds byte/time reserve; no child launched")
    capture.mkdir()
    argv = [sys.executable, "-B", str(helper)]
    began_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    call_started = time.monotonic()
    rc: int | None = None
    timed_out = False
    launch_error: str | None = None
    stdout = stderr = b""
    attempted = True
    timeout = min(case["child_timeout_seconds"], case["whole_call_limit_seconds"] - (call_started - started) - 2)
    try:
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=timeout, check=False)
        rc, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out, stdout, stderr = True, exc.stdout or b"", exc.stderr or b""
    except OSError as exc:
        attempted, launch_error = False, type(exc).__name__
        stderr = str(exc).encode("utf-8", errors="replace")
    child_elapsed = time.monotonic() - call_started
    result_obj: dict[str, Any] | None = None
    parse_error: str | None = None
    try:
        parsed = json.loads(stdout.decode("utf-8"))
        if isinstance(parsed, dict):
            result_obj = parsed
        else:
            parse_error = "stdout JSON was not an object"
    except (UnicodeDecodeError, json.JSONDecodeError):
        parse_error = "no complete JSON object on stdout"
    result_status = result_obj.get("status") if result_obj else None
    result_raw = stdout if result_obj is not None else b""
    (capture / "stdout.bin").write_bytes(stdout)
    (capture / "stderr.bin").write_bytes(stderr)
    (capture / "result.json").write_bytes(result_raw)
    (capture / "authorization.json").write_bytes(raw_go)
    post = [{"name": row["name"], "path": row["path"], "sha256": digest(ROOT / row["path"])} for row in pre]
    unchanged = all(a["sha256"] == b["sha256"] for a, b in zip(pre, post))
    raw_total = len(stdout) + len(stderr)
    status = result_status or ("TIMEOUT" if timed_out else "LAUNCH_ERROR" if launch_error else "NO_RESULT")
    receipt: dict[str, Any] = {
        "schema": "vesselforge.global_wall_distance.run01_receipt.v1",
        "authorization": AUTHORIZATION, "call_count": 1 if attempted else 0,
        "root_ready_argument": True, "process": {"argv": argv, "return_code": rc, "timed_out": timed_out,
        "timeout_seconds": timeout, "launch_error": launch_error, "started_utc": began_utc,
        "child_elapsed_seconds": round(child_elapsed, 6)},
        "result": {"status": status, "return_code": rc, "json_available": result_obj is not None,
        "parse_error": parse_error, "sha256": hashlib.sha256(result_raw).hexdigest()},
        "pre_hashes": pre, "post_hashes": post, "all_preflight_hashes_unchanged": unchanged,
        "root_go_sha256": go_hash, "raw_stdout_bytes": len(stdout), "raw_stderr_bytes": len(stderr),
        "raw_output_limit_bytes": raw_limit, "bounded_input_bundle_bytes": bundle_bytes,
        "capture_tree_bytes": 0, "bounded_total_bytes": 0,
        "whole_call_limit_seconds": case["whole_call_limit_seconds"],
        "whole_supervisor_elapsed_seconds": "0.000000", "external_tool_elapsed_seconds_recorded_by_parent": True,
    }
    fixed = [capture / name for name in ("stdout.bin", "stderr.bin", "result.json", "authorization.json")]
    tree_bytes = total_bytes = 0
    for _ in range(8):
        receipt["capture_tree_bytes"], receipt["bounded_total_bytes"] = tree_bytes, total_bytes
        receipt["whole_supervisor_elapsed_seconds"] = f"{time.monotonic() - started:.6f}"
        receipt_raw = encoded(receipt)
        new_tree = sum(p.stat().st_size for p in fixed) + len(receipt_raw)
        new_total = bundle_bytes + new_tree
        if (new_tree, new_total) == (tree_bytes, total_bytes):
            break
        tree_bytes, total_bytes = new_tree, new_total
    receipt["capture_tree_bytes"], receipt["bounded_total_bytes"] = tree_bytes, total_bytes
    receipt["whole_supervisor_elapsed_seconds"] = f"{time.monotonic() - started:.6f}"
    receipt_raw = encoded(receipt)
    (capture / "receipt.json").write_bytes(receipt_raw)
    actual_tree = sum(p.stat().st_size for p in fixed) + len(receipt_raw)
    actual_total = bundle_bytes + actual_tree
    within_limits = actual_tree == tree_bytes and actual_total == total_bytes and actual_total <= MAX_BYTES and raw_total <= raw_limit and time.monotonic() - started <= case["whole_call_limit_seconds"]
    print(json.dumps({"status": status, "return_code": rc, "timed_out": timed_out,
    "hashes_unchanged": unchanged, "capture_tree_bytes": actual_tree, "bounded_total_bytes": actual_total,
    "within_limits": within_limits, "capture": rel(capture)}, sort_keys=True))
    return 0 if within_limits else 1
if __name__ == "__main__":
    raise SystemExit(main())
