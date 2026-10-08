from __future__ import annotations
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path.cwd().resolve()
REVIEW = ROOT / "vesselforge" / "tmp" / "review_20261006" / "curvature_constrained_meridian_20261006"
CAPTURE = REVIEW / "run01_capture"
SOURCE = ROOT / "vesselforge" / "experiments" / "curvature_constrained_meridian_20261006" / "curvature_constrained_meridian.py"
DRIVER = ROOT / "vesselforge" / "experiments" / "semantic_base_neck_bspline_20261006" / "semantic_base_neck_driver.py"
CASE = DRIVER.with_name("fixed_cases.json")
SEED = ROOT / "vesselforge" / "tmp" / "review_20261006" / "semantic_base_neck_bspline_20261006" / "minimum_jerk_candidate" / "semantic_minimum_jerk_result.json"
DESIGN = SOURCE.with_name("design_cases.json")
PINS = REVIEW / "source_pins.json"
MARKER = REVIEW / "run_started.json"
RESULT = REVIEW / "curvature_constrained_meridian_result.json"
WORKER = ROOT / "third_party" / "vesselforge-runtime" / "venv" / "Scripts" / "python.exe"
INPUTS = {"implementation": SOURCE, "driver": DRIVER, "fixed_cases": CASE,
          "actual_seed": SEED, "design_cases": DESIGN, "source_pins": PINS}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_pin() -> dict:
    dist = importlib.metadata.distribution("scipy")
    metadata_dir = Path(dist._path)
    meta_files = {}
    for name in ("METADATA", "RECORD"):
        p = metadata_dir / name
        meta_files[name] = sha(p) if p.is_file() else None
    return {"python_executable": str(Path(sys.executable).resolve()),
            "python_executable_sha256": sha(Path(sys.executable).resolve()),
            "python_version": sys.version, "scipy_distribution_version": dist.version,
            "scipy_metadata_files": meta_files}


def pin_inputs() -> dict:
    return {name: {"path": str(path.relative_to(ROOT)), "sha256": sha(path), "bytes": path.stat().st_size}
            for name, path in INPUTS.items()}


def total_review_bytes() -> int:
    return sum(p.stat().st_size for p in REVIEW.rglob("*") if p.is_file())


def main() -> int:
    if not ROOT.is_dir() or not CAPTURE.is_dir():
        raise RuntimeError("EXPECTED_WORKSPACE_OR_CAPTURE_DIRECTORY_MISSING")
    if MARKER.exists() or RESULT.exists():
        raise RuntimeError("ONE_SHOT_MARKER_OR_RESULT_EXISTS_REFUSING_LAUNCH")
    if any((CAPTURE / name).exists() for name in ("stdout.bin", "stderr.bin", "receipt.json")):
        raise RuntimeError("CAPTURE_ARTIFACT_EXISTS_REFUSING_LAUNCH")
    before = {"inputs": pin_inputs(), "runtime": runtime_pin()}
    child_code = (
        "import json, runpy; "
        f"ns=runpy.run_path({str(SOURCE)!r}); "
        "out=ns['run_constrained_design'](root_ready=True, design_cases=None); "
        "print(json.dumps({'status': out.get('status'), 'elapsed_seconds': out.get('elapsed_seconds'), "
        "'families': {k: {'optimizer_status': v.get('optimizer_status'), "
        "'promotion_status': v.get('promotion_status'), 'reason': v.get('reason')} "
        "for k,v in out.get('families', {}).items()}}, default=str, sort_keys=True))"
    )
    command = [str(WORKER), "-B", "-c", child_code]
    started = time.monotonic()
    timed_out = False
    returncode = None
    stdout = b""
    stderr = b""
    exception = None
    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=60, check=False)
        stdout, stderr, returncode = completed.stdout, completed.stderr, completed.returncode
    except subprocess.TimeoutExpired as error:
        timed_out = True
        stdout = error.stdout or b""
        stderr = error.stderr or b""
        exception = "TimeoutExpired: subprocess.run timeout=60 seconds"
    except Exception as error:
        exception = f"{type(error).__name__}: {error}"
    elapsed = time.monotonic() - started
    (CAPTURE / "stdout.bin").write_bytes(stdout)
    (CAPTURE / "stderr.bin").write_bytes(stderr)
    after = {"inputs": pin_inputs(), "runtime": runtime_pin()}
    outputs = {}
    for name, path in (("marker", MARKER), ("result", RESULT)):
        outputs[name] = ({"path": str(path.relative_to(ROOT)), "exists": True,
                          "bytes": path.stat().st_size, "sha256": sha(path)} if path.is_file()
                         else {"path": str(path.relative_to(ROOT)), "exists": False})
    receipt = {"schema": "vesselforge.curvature_constrained_meridian.run_capture.v1",
               "invocation": "run_constrained_design(root_ready=True, design_cases=None)",
               "worker_command": command, "cwd": str(ROOT), "timeout_seconds": 60,
               "timed_out": timed_out, "returncode": returncode, "elapsed_seconds": elapsed,
               "exception": exception, "pre_pins": before, "post_pins": after,
               "raw_stdout_bytes": len(stdout), "raw_stderr_bytes": len(stderr),
               "outputs": outputs, "total_review_bytes_including_receipt": None,
               "total_review_bytes_under_8mib": None}
    receipt_path = CAPTURE / "receipt.json"
    encoded = json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8")
    receipt["total_review_bytes_including_receipt"] = total_review_bytes() + len(encoded)
    receipt["total_review_bytes_under_8mib"] = receipt["total_review_bytes_including_receipt"] < 8 * 1024 * 1024
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"returncode": returncode, "timed_out": timed_out, "elapsed_seconds": elapsed,
                      "exception": exception, "result_exists": outputs["result"]["exists"],
                      "result_bytes": outputs["result"].get("bytes"),
                      "total_review_bytes": total_review_bytes()}, sort_keys=True))
    return 0 if not exception and returncode == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
