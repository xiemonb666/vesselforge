import hashlib
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(r"C:\Users\xiemo\Desktop\ShardForge")
OUT = ROOT / r"vesselforge\tmp\review_20261007\c4_jar_native_ingress_20261007\API_INSPECTION\once_02"
PINS_PATH = OUT / "source_pins.json"
INSPECTOR = OUT / "inspect_ocp_docs.py"
SELF = OUT / "capture_once_02.py"
PYTHON = ROOT / r"third_party\vesselforge-runtime\venv\Scripts\python.exe"
CAP = 204800
CHILD_TIMEOUT_S = 5.0
start = time.monotonic()


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def pin_snapshot(pins):
    rows = []
    for row in pins["files"]:
        path = ROOT / Path(row["path"])
        exists = path.is_file()
        rows.append({
            "path": row["path"],
            "exists": exists,
            "bytes": path.stat().st_size if exists else None,
            "sha256": sha256(path) if exists else None,
            "expected_sha256": row["sha256"],
        })
    programs = []
    for row in pins["programs"]:
        path = ROOT / Path(row["path"])
        exists = path.is_file()
        programs.append({
            "path": row["path"],
            "exists": exists,
            "bytes": path.stat().st_size if exists else None,
            "sha256": sha256(path) if exists else None,
            "expected_sha256": row["sha256"],
        })
    return {
        "files": rows,
        "programs": programs,
        "source_pins_sha256": sha256(PINS_PATH),
    }


def all_match(snapshot):
    return all(x["exists"] and x["sha256"] == x["expected_sha256"]
               for group in ("files", "programs") for x in snapshot[group])


def as_bytes(value):
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8", errors="replace")


def write_json(path, data):
    payload = (json.dumps(data, ensure_ascii=True, indent=2) + "\n").encode("utf-8")
    path.write_bytes(payload)
    return len(payload)


def persisted_bytes():
    return sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())


pins = json.loads(PINS_PATH.read_text(encoding="utf-8"))
pre = pin_snapshot(pins)
argv = [str(PYTHON), "-B", str(INSPECTOR)]
status = "PREPIN_MISMATCH"
child_rc = None
stdout = b""
stderr = b""
exception = None
if all_match(pre):
    status = "RUNNING"
    try:
        completed = subprocess.run(argv, capture_output=True, timeout=CHILD_TIMEOUT_S)
        stdout = as_bytes(completed.stdout)
        stderr = as_bytes(completed.stderr)
        child_rc = completed.returncode
        status = "COMPLETED_RC0" if child_rc == 0 else "CHILD_RC_NONZERO"
    except subprocess.TimeoutExpired as exc:
        stdout = as_bytes(exc.stdout)
        stderr = as_bytes(exc.stderr)
        status = "TIMEOUT_5S"
        exception = "subprocess.TimeoutExpired"
    except Exception as exc:
        stderr = (type(exc).__name__ + ": " + str(exc)).encode("utf-8", errors="replace")
        status = "LAUNCH_OR_CAPTURE_ERROR"
        exception = type(exc).__name__
else:
    stderr = b"pre-run pins did not match; child was not started\n"

elapsed = time.monotonic() - start
(OUT / "stdout.bin").write_bytes(stdout)
(OUT / "stderr.bin").write_bytes(stderr)
post = pin_snapshot(pins)
if status in ("COMPLETED_RC0", "CHILD_RC_NONZERO", "TIMEOUT_5S") and pre != post:
    status = "INPUT_CHANGED"

receipt = {
    "schema": "vesselforge.ocp_doc_only_capture_receipt/0.1",
    "status": status,
    "attempt_count": 1 if status not in ("PREPIN_MISMATCH",) else 0,
    "argv": argv,
    "child_timeout_seconds": CHILD_TIMEOUT_S,
    "outer_elapsed_seconds": elapsed,
    "child_returncode": child_rc,
    "exception_type": exception,
    "geometry_constructed": False,
    "cad_or_step_run": False,
    "solver_run": False,
    "retry_performed": False,
    "stdout_bytes": len(stdout),
    "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
    "stderr_bytes": len(stderr),
    "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
    "source_pins_pre": pre,
    "source_pins_post": post,
    "source_pins_unchanged": pre == post,
    "source_pins_file_sha256": post["source_pins_sha256"],
    "output_budget_bytes": CAP,
    "receipt_count_status": "PENDING_FIXED_POINT",
    "receipt_byte_count": None,
    "total_persisted_bytes": None,
    "within_output_budget": None,
    "fixed_point_iterations": 0,
}

receipt_path = OUT / "receipt.json"
stable = False
for i in range(1, 11):
    receipt["fixed_point_iterations"] = i
    write_json(receipt_path, receipt)
    actual_receipt_bytes = receipt_path.stat().st_size
    actual_total_bytes = persisted_bytes()
    if (receipt["receipt_byte_count"] == actual_receipt_bytes and
            receipt["total_persisted_bytes"] == actual_total_bytes and
            receipt["within_output_budget"] == (actual_total_bytes <= CAP) and
            receipt["receipt_count_status"] == "EXACT_FIXED_POINT"):
        stable = True
        break
    receipt["receipt_byte_count"] = actual_receipt_bytes
    receipt["total_persisted_bytes"] = actual_total_bytes
    receipt["within_output_budget"] = actual_total_bytes <= CAP
    receipt["receipt_count_status"] = "EXACT_FIXED_POINT"

if not stable:
    receipt["receipt_count_status"] = "UNKNOWN_FIXED_POINT_FAILED"
    receipt["receipt_byte_count"] = None
    receipt["total_persisted_bytes"] = None
    receipt["within_output_budget"] = None
    receipt["fixed_point_iterations"] = 10
    write_json(receipt_path, receipt)

print(json.dumps({
    "status": receipt["status"],
    "child_returncode": receipt["child_returncode"],
    "elapsed_seconds": receipt["outer_elapsed_seconds"],
    "stdout_bytes": receipt["stdout_bytes"],
    "stderr_bytes": receipt["stderr_bytes"],
    "source_pins_unchanged": receipt["source_pins_unchanged"],
    "receipt_count_status": receipt["receipt_count_status"],
    "total_persisted_bytes": receipt["total_persisted_bytes"],
    "within_output_budget": receipt["within_output_budget"],
}, separators=(",", ":")))