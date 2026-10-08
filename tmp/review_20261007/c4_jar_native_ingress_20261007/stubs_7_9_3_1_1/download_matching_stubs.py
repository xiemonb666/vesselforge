import hashlib
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(r"C:\Users\xiemo\Desktop\ShardForge")
OUT = ROOT / r"vesselforge\tmp\review_20261007\c4_jar_native_ingress_20261007\stubs_7_9_3_1_1"
PINS_PATH = OUT / "download_pins.json"
SELF = OUT / "download_matching_stubs.py"
PYTHON = ROOT / r"third_party\vesselforge-runtime\venv\Scripts\python.exe"
WHEEL_NAME = "cadquery_ocp_stubs-7.9.3.1.1-py3-none-win_amd64.whl"
WHEEL_SHA256 = "5ecba090df1ada12c558ff4a1b49c61d5155edc8cb3411067a785e3b43f4b359"
WHEEL_URL = "https://files.pythonhosted.org/packages/6c/de/2a93a7cd47226bdd802674e8a040235ef1a1a4433bbf4d220e21253fe31e/cadquery_ocp_stubs-7.9.3.1.1-py3-none-win_amd64.whl"
TIMEOUT_S = 25.0
LOG_CAP = 204800


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def pin_snapshot(pins):
    groups = {}
    for key in ("files", "programs"):
        rows = []
        for row in pins[key]:
            path = ROOT / Path(row["path"])
            exists = path.is_file()
            rows.append({
                "path": row["path"],
                "exists": exists,
                "bytes": path.stat().st_size if exists else None,
                "sha256": sha256(path) if exists else None,
                "expected_sha256": row["sha256"],
            })
        groups[key] = rows
    groups["pins_file_sha256"] = sha256(PINS_PATH)
    return groups


def pins_match(snap):
    return all(r["exists"] and r["sha256"] == r["expected_sha256"]
               for group in ("files", "programs") for r in snap[group])


def as_bytes(value):
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8", errors="replace")


def persist_total():
    return sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())


def write_receipt(path, obj):
    path.write_bytes((json.dumps(obj, ensure_ascii=True, indent=2) + "\n").encode("utf-8"))


pins = json.loads(PINS_PATH.read_text(encoding="utf-8"))
start = time.monotonic()
pre = pin_snapshot(pins)
argv = [
    str(PYTHON), "-B", "-m", "pip", "download",
    "--no-deps", "--no-index", "--only-binary=:all:", "--no-cache-dir", "--quiet",
    "--dest", str(OUT), WHEEL_URL,
]
status = "PREPIN_MISMATCH"
returncode = None
stdout = b""
stderr = b""
exception_type = None
if pins_match(pre):
    status = "RUNNING_DOWNLOAD_ONLY"
    try:
        done = subprocess.run(argv, capture_output=True, timeout=TIMEOUT_S)
        stdout, stderr, returncode = as_bytes(done.stdout), as_bytes(done.stderr), done.returncode
        status = "DOWNLOADED_RC0" if returncode == 0 else "PIP_DOWNLOAD_RC_NONZERO"
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = as_bytes(exc.stdout), as_bytes(exc.stderr)
        status, exception_type = "PIP_DOWNLOAD_TIMEOUT", "subprocess.TimeoutExpired"
    except Exception as exc:
        stderr = (type(exc).__name__ + ": " + str(exc)).encode("utf-8", errors="replace")
        status, exception_type = "PIP_DOWNLOAD_LAUNCH_ERROR", type(exc).__name__
else:
    stderr = b"pre-download pins did not match; pip was not started\n"

elapsed = time.monotonic() - start
(OUT / "pip_download.stdout.bin").write_bytes(stdout)
(OUT / "pip_download.stderr.bin").write_bytes(stderr)
post = pin_snapshot(pins)
metadata_stable = pre == post
if status == "DOWNLOADED_RC0" and not metadata_stable:
    status = "RUNTIME_METADATA_CHANGED"
wheel_path = OUT / WHEEL_NAME
wheel_exists = wheel_path.is_file()
wheel_bytes = wheel_path.stat().st_size if wheel_exists else None
wheel_hash = sha256(wheel_path) if wheel_exists else None
if status == "DOWNLOADED_RC0" and wheel_hash != WHEEL_SHA256:
    status = "WHEEL_HASH_MISMATCH"
logs_bytes = len(stdout) + len(stderr)
if logs_bytes > LOG_CAP and status == "DOWNLOADED_RC0":
    status = "LOG_LIMIT_EXCEEDED"

receipt = {
    "schema": "vesselforge.ocp_stubs_download_receipt/0.1",
    "status": status,
    "argv": argv,
    "timeout_seconds": TIMEOUT_S,
    "elapsed_seconds": elapsed,
    "returncode": returncode,
    "exception_type": exception_type,
    "download_only": True,
    "installation_performed": False,
    "OCP_imported": False,
    "CAD_or_geometry_run": False,
    "stdout_bytes": len(stdout),
    "stderr_bytes": len(stderr),
    "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
    "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
    "logs_total_bytes": logs_bytes,
    "logs_cap_bytes": LOG_CAP,
    "logs_within_cap": logs_bytes <= LOG_CAP,
    "source_pins_pre": pre,
    "source_pins_post": post,
    "runtime_metadata_unchanged": metadata_stable,
    "wheel": {
        "filename": WHEEL_NAME,
        "exists": wheel_exists,
        "bytes": wheel_bytes,
        "actual_sha256": wheel_hash,
        "expected_sha256": WHEEL_SHA256,
        "hash_matches": wheel_hash == WHEEL_SHA256,
    },
    "receipt_count_status": "PENDING_FIXED_POINT",
    "receipt_bytes": None,
    "total_persisted_bytes": None,
    "fixed_point_iterations": 0,
}
receipt_path = OUT / "download_receipt.json"
stable = False
for i in range(1, 11):
    receipt["fixed_point_iterations"] = i
    write_receipt(receipt_path, receipt)
    current_receipt = receipt_path.stat().st_size
    total = persist_total()
    if (receipt["receipt_bytes"] == current_receipt and
            receipt["total_persisted_bytes"] == total and
            receipt["receipt_count_status"] == "EXACT_FIXED_POINT"):
        stable = True
        break
    receipt["receipt_bytes"] = current_receipt
    receipt["total_persisted_bytes"] = total
    receipt["receipt_count_status"] = "EXACT_FIXED_POINT"
if not stable:
    receipt["receipt_count_status"] = "UNKNOWN_FIXED_POINT_FAILED"
    receipt["receipt_bytes"] = None
    receipt["total_persisted_bytes"] = None
    receipt["fixed_point_iterations"] = 10
    write_receipt(receipt_path, receipt)
print(json.dumps({
    "status": receipt["status"],
    "returncode": receipt["returncode"],
    "elapsed_seconds": receipt["elapsed_seconds"],
    "wheel_bytes": receipt["wheel"]["bytes"],
    "wheel_hash_matches": receipt["wheel"]["hash_matches"],
    "runtime_metadata_unchanged": receipt["runtime_metadata_unchanged"],
    "logs_total_bytes": receipt["logs_total_bytes"],
    "total_persisted_bytes": receipt["total_persisted_bytes"],
}, separators=(",", ":")))