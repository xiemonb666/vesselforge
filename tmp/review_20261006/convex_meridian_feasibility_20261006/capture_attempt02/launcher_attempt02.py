"""One-shot corrected launcher; source/import setup only changes from attempt 1."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REVIEW = HERE.parent
ROOT = HERE.parents[4]
SOURCE = ROOT / "vesselforge" / "experiments" / "convex_meridian_feasibility_20261006" / "convex_meridian_feasibility.py"
PINS = REVIEW / "source_pins.json"
FALSE_PINS = REVIEW / "source_pins.pre_authorization.json"
OLD_RECEIPT = REVIEW / "trial_receipt.json"
RESULT = REVIEW / "convex_meridian_feasibility_result.json"
RUN_STARTED = REVIEW / "run_started.json"
DISPATCH = HERE / "dispatch.json"
STDOUT = HERE / "stdout.raw.bin"
STDERR = HERE / "stderr.raw.bin"
RECEIPT = HERE / "receipt.json"
PYTHON = ROOT / "third_party" / "vesselforge-runtime" / "venv" / "Scripts" / "python.exe"
MAX_SECONDS = 60
MAX_BYTES = 8 * 1024 * 1024
OLD_ARTIFACTS = (
    "trial_receipt.json", "trial_dispatch.json", "trial_stdout.bin", "trial_stderr.bin",
    "source_pins.pre_authorization.json",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pin_snapshot() -> dict[str, object]:
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    entries = {"implementation": pins["implementation"],
               "planned_checker": pins["planned_checker"], **pins["inputs"]}
    actual = {key: sha256(ROOT / value["path"]) for key, value in entries.items()}
    expected = {key: value["sha256"] for key, value in entries.items()}
    return {"files": actual, "expected": expected, "all_match": actual == expected,
            "source_pins_sha256": sha256(PINS), "case_authorized": pins.get("case_authorized"),
            "authorization_metadata": pins.get("authorization_metadata")}


def result_summary() -> dict[str, object] | None:
    if not RESULT.exists():
        return None
    size = RESULT.stat().st_size
    digest = sha256(RESULT)
    if size >= MAX_BYTES:
        return {"status": "RESULT_EXCEEDS_8_MIB", "bytes": size, "sha256": digest}
    try:
        payload = json.loads(RESULT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "PARTIAL_OR_INVALID_JSON", "bytes": size, "sha256": digest}
    families = {}
    for name, record in payload.get("families", {}).items():
        audit = record.get("audit", {})
        families[name] = {
            "solver_status": record.get("solver_status"),
            "solver_success": record.get("solver_success"),
            "solver_message": record.get("solver_message"),
            "status": record.get("status"),
            "constraint_rows": record.get("constraint_rows"),
            "audit_status": audit.get("status"),
            "exact_linear_violation_count": audit.get("exact_linear_violation_count"),
            "worst_exact_linear_violations": audit.get("worst_exact_linear_violations"),
            "fixed_reference_direction_speed_floor": audit.get("fixed_reference_direction_speed_floor"),
            "independent_full_span_L1_projection_proof":
                audit.get("independent_full_span_L1_projection_proof")}
    return {"status": payload.get("status"), "families": families, "bytes": size, "sha256": digest}


def main() -> int:
    if RESULT.exists() or RUN_STARTED.exists() or DISPATCH.exists():
        raise RuntimeError("RESULT_RUN_MARKER_OR_ATTEMPT02_DISPATCH_ALREADY_EXISTS")
    if STDOUT.exists() or STDERR.exists() or RECEIPT.exists():
        raise RuntimeError("ATTEMPT02_CAPTURE_ALREADY_EXISTS")
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    old_pins = json.loads(FALSE_PINS.read_text(encoding="utf-8"))
    old_receipt = json.loads(OLD_RECEIPT.read_text(encoding="utf-8"))
    if (pins.get("case_authorized") is not True or
            pins.get("authorization_metadata", {}).get("authorization_source") != "ROOT_ENGINEERING_GO" or
            old_pins.get("case_authorized") is not False or
            sha256(PINS) != old_receipt["source_pins_after_run_sha256"]):
        raise RuntimeError("AUTHORIZATION_OR_ATTEMPT01_PIN_RECEIPT_MISMATCH")
    if sha256(SOURCE) != pins["implementation"]["sha256"]:
        raise RuntimeError("IMPLEMENTATION_HASH_MISMATCH")
    pre_pins = pin_snapshot()
    if not pre_pins["all_match"]:
        raise RuntimeError("PRE_RUN_PIN_MISMATCH")
    old_artifacts_pre = {name: sha256(REVIEW / name) for name in OLD_ARTIFACTS}
    if old_artifacts_pre["trial_stdout.bin"] != old_receipt["stdout_sha256"] or \
            old_artifacts_pre["trial_stderr.bin"] != old_receipt["stderr_sha256"]:
        raise RuntimeError("ATTEMPT01_RAW_CAPTURE_MISMATCH")

    dispatch = {
        "schema": "vesselforge.convex_meridian_feasibility.attempt02_dispatch.v1",
        "launcher_fix": "register dynamic module in sys.modules before exec_module",
        "source_or_input_changes": False, "actual_trial_calls": 1,
        "pre_run_pins": pre_pins, "attempt01_artifact_sha256": old_artifacts_pre}
    with DISPATCH.open("x", encoding="utf-8") as stream:
        json.dump(dispatch, stream, sort_keys=True)

    code = (
        "import importlib.util,json,pathlib,sys; "
        f"p=pathlib.Path({str(SOURCE)!r}); "
        "s=importlib.util.spec_from_file_location('_convex_meridian_trial_attempt02',p); "
        "m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m); "
        "o=m.run_feasibility(root_ready=True); "
        "f={k:{'solver_status':v.get('solver_status'),'solver_success':v.get('solver_success'),"
        "'solver_message':v.get('solver_message'),'status':v.get('status'),"
        "'constraint_rows':v.get('constraint_rows'),"
        "'audit':{n:v.get('audit',{}).get(n) for n in "
        "('status','exact_linear_violation_count','worst_exact_linear_violations',"
        "'fixed_reference_direction_speed_floor','independent_full_span_L1_projection_proof')}} "
        "for k,v in o.get('families',{}).items()}; "
        "print(json.dumps({'status':o.get('status'),'families':f},sort_keys=True,separators=(',',':')))"
    )
    start_unix = time.time()
    start = time.perf_counter()
    timed_out = False
    child_rc: int | None = None
    stdout = b""
    stderr = b""
    try:
        completed = subprocess.run([str(PYTHON), "-c", code], cwd=ROOT,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   timeout=MAX_SECONDS, check=False)
        child_rc = int(completed.returncode)
        stdout, stderr = completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout if isinstance(exc.stdout, bytes) else b""
        stderr = exc.stderr if isinstance(exc.stderr, bytes) else b""
    elapsed = time.perf_counter() - start
    STDOUT.write_bytes(stdout)
    STDERR.write_bytes(stderr)
    post_pins = pin_snapshot()
    old_artifacts_post = {name: sha256(REVIEW / name) for name in OLD_ARTIFACTS}
    result = result_summary()
    supervisor_rc = 124 if timed_out else int(child_rc if child_rc is not None else 1)
    receipt = {
        "schema": "vesselforge.convex_meridian_feasibility.attempt02_receipt.v1",
        "authorization_source": "ROOT_ENGINEERING_GO",
        "human_confirmation": False,
        "single_real_run_feasibility_call": True,
        "lp_attempts_per_family": 1,
        "outer_timeout_seconds": MAX_SECONDS,
        "timed_out": timed_out,
        "child_returncode": child_rc,
        "actual_outer_returncode": supervisor_rc,
        "elapsed_seconds": elapsed,
        "started_unix_seconds": start_unix,
        "pre_run_all_pins": pre_pins,
        "post_run_all_pins": post_pins,
        "pinned_files_unchanged": pre_pins["files"] == post_pins["files"] and
                                  pre_pins["all_match"] and post_pins["all_match"] and
                                  pre_pins["source_pins_sha256"] == post_pins["source_pins_sha256"],
        "attempt01_artifacts_before": old_artifacts_pre,
        "attempt01_artifacts_after": old_artifacts_post,
        "attempt01_artifacts_unchanged": old_artifacts_pre == old_artifacts_post,
        "run_started_marker_exists": RUN_STARTED.exists(),
        "result_exists": RESULT.exists(),
        "result_summary": result,
        "stdout_bytes": len(stdout), "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_bytes": len(stderr), "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "launcher_sha256": sha256(Path(__file__))}
    RECEIPT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"actual_outer_returncode": supervisor_rc,
                      "timed_out": timed_out, "elapsed_seconds": elapsed,
                      "pinned_files_unchanged": receipt["pinned_files_unchanged"],
                      "attempt01_artifacts_unchanged": receipt["attempt01_artifacts_unchanged"],
                      "run_started_marker_exists": receipt["run_started_marker_exists"],
                      "result_summary": result}, sort_keys=True, separators=(",", ":")))
    return supervisor_rc


if __name__ == "__main__":
    sys.exit(main())
