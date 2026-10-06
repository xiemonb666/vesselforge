"""Single-dispatch supervisor for the explicitly authorized local trial."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
REVIEW = ROOT / "vesselforge" / "tmp" / "review_20261006" / "convex_meridian_feasibility_20261006"
SOURCE = ROOT / "vesselforge" / "experiments" / "convex_meridian_feasibility_20261006" / "convex_meridian_feasibility.py"
PINS = REVIEW / "source_pins.json"
FALSE_PINS = REVIEW / "source_pins.pre_authorization.json"
RESULT = REVIEW / "convex_meridian_feasibility_result.json"
RUN_STARTED = REVIEW / "run_started.json"
DISPATCH = REVIEW / "trial_dispatch.json"
STDOUT = REVIEW / "trial_stdout.bin"
STDERR = REVIEW / "trial_stderr.bin"
RECEIPT = REVIEW / "trial_receipt.json"
PYTHON = ROOT / "third_party" / "vesselforge-runtime" / "venv" / "Scripts" / "python.exe"
MAX_SECONDS = 60
MAX_BYTES = 8 * 1024 * 1024


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pinned_snapshot() -> dict[str, object]:
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    files = {"implementation": pins["implementation"],
             "planned_checker": pins["planned_checker"], **pins["inputs"]}
    actual = {key: sha256(ROOT / entry["path"]) for key, entry in files.items()}
    expected = {key: entry["sha256"] for key, entry in files.items()}
    return {"files": actual, "expected": expected, "all_hashes_match": actual == expected,
            "source_pins_sha256": sha256(PINS),
            "case_authorized": pins.get("case_authorized"),
            "authorization_metadata": pins.get("authorization_metadata")}


def result_summary() -> dict[str, object] | None:
    if not RESULT.exists() or RESULT.stat().st_size >= MAX_BYTES:
        return None
    try:
        payload = json.loads(RESULT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "PARTIAL_OR_INVALID_JSON", "result_bytes": RESULT.stat().st_size,
                "result_sha256": sha256(RESULT)}
    families = {}
    for name, record in payload.get("families", {}).items():
        audit = record.get("audit", {})
        families[name] = {
            "solver_status": record.get("solver_status"),
            "solver_success": record.get("solver_success"),
            "status": record.get("status"),
            "constraint_rows": record.get("constraint_rows"),
            "audit_status": audit.get("status"),
            "exact_linear_violation_count": audit.get("exact_linear_violation_count"),
            "worst_exact_linear_violations": audit.get("worst_exact_linear_violations"),
            "fixed_reference_direction_speed_floor": audit.get("fixed_reference_direction_speed_floor"),
            "independent_full_span_L1_projection_proof": audit.get("independent_full_span_L1_projection_proof")}
    return {"schema": payload.get("schema"), "status": payload.get("status"),
            "families": families, "result_bytes": RESULT.stat().st_size,
            "result_sha256": sha256(RESULT)}


def main() -> int:
    if DISPATCH.exists():
        raise RuntimeError("TRIAL_ALREADY_DISPATCHED")
    if RESULT.exists() or RUN_STARTED.exists():
        raise RuntimeError("RESULT_OR_RUN_STARTED_ALREADY_EXISTS")
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    old_pins = json.loads(FALSE_PINS.read_text(encoding="utf-8"))
    if (pins.get("case_authorized") is not True or
            pins.get("authorization_metadata", {}).get("authorization_source") != "ROOT_ENGINEERING_GO" or
            old_pins.get("case_authorized") is not False):
        raise RuntimeError("AUTHORIZATION_RECORD_MISMATCH")
    if sha256(SOURCE) != pins["implementation"]["sha256"]:
        raise RuntimeError("IMPLEMENTATION_HASH_MISMATCH")
    pre = pinned_snapshot()
    if not pre["all_hashes_match"]:
        raise RuntimeError("PRE_RUN_PIN_MISMATCH")
    dispatch = {"schema": "vesselforge.convex_meridian_feasibility.dispatch.v1",
                "source": "ROOT_ENGINEERING_GO", "human_confirmation": False,
                "single_dispatch": True, "pre_run_pins": pre}
    with DISPATCH.open("x", encoding="utf-8") as stream:
        json.dump(dispatch, stream, sort_keys=True)

    code = (
        "import importlib.util,json,pathlib; "
        f"p=pathlib.Path({str(SOURCE)!r}); "
        "s=importlib.util.spec_from_file_location('_convex_meridian_trial',p); "
        "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
        "o=m.run_feasibility(root_ready=True); "
        "f={k:{'solver_status':v.get('solver_status'),'solver_success':v.get('solver_success'),"
        "'status':v.get('status'),'constraint_rows':v.get('constraint_rows'),"
        "'audit':{n:v.get('audit',{}).get(n) for n in "
        "('status','exact_linear_violation_count','worst_exact_linear_violations',"
        "'fixed_reference_direction_speed_floor','independent_full_span_L1_projection_proof')}} "
        "for k,v in o.get('families',{}).items()}; "
        "print(json.dumps({'status':o.get('status'),'families':f},sort_keys=True,separators=(',',':')))"
    )
    started = time.time()
    elapsed_start = time.perf_counter()
    timed_out = False
    child_rc: int | None
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
        child_rc = None
        stdout = exc.stdout if isinstance(exc.stdout, bytes) else b""
        stderr = exc.stderr if isinstance(exc.stderr, bytes) else b""
    elapsed = time.perf_counter() - elapsed_start
    STDOUT.write_bytes(stdout)
    STDERR.write_bytes(stderr)
    post = pinned_snapshot()
    summary = result_summary()
    receipt = {
        "schema": "vesselforge.convex_meridian_feasibility.trial_receipt.v1",
        "authorization_source": "ROOT_ENGINEERING_GO",
        "human_confirmation": False,
        "single_dispatch_no_retry": True,
        "external_timeout_seconds": MAX_SECONDS,
        "timed_out": timed_out,
        "child_returncode": child_rc,
        "supervisor_returncode": 124 if timed_out else child_rc,
        "elapsed_seconds": elapsed,
        "started_unix_seconds": started,
        "pre_run_all_pins": pre,
        "post_run_all_pins": post,
        "pinned_files_unchanged": pre["files"] == post["files"] and
                                  pre["all_hashes_match"] and post["all_hashes_match"] and
                                  pre["source_pins_sha256"] == post["source_pins_sha256"],
        "source_pins_unchanged_during_trial":
            pre["source_pins_sha256"] == post["source_pins_sha256"],
        "false_source_pins_backup_sha256": sha256(FALSE_PINS),
        "source_pins_after_run_sha256": sha256(PINS),
        "run_started_marker_exists": RUN_STARTED.exists(),
        "result_summary": summary,
        "result_exists": RESULT.exists(),
        "result_bytes": RESULT.stat().st_size if RESULT.exists() else None,
        "result_file_sha256": sha256(RESULT) if RESULT.exists() else None,
        "stdout_bytes": len(stdout), "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_bytes": len(stderr), "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
    }
    RECEIPT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"supervisor_returncode": receipt["supervisor_returncode"],
                      "timed_out": timed_out, "elapsed_seconds": elapsed,
                      "pinned_files_unchanged": receipt["pinned_files_unchanged"],
                      "result_summary": summary}, sort_keys=True, separators=(",", ":")))
    return int(receipt["supervisor_returncode"] or 0)


if __name__ == "__main__":
    sys.exit(main())
