from __future__ import annotations
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path.cwd().resolve()
CAP = ROOT / "vesselforge" / "tmp" / "review_20261006" / "curvature_constrained_meridian_20261006" / "run01_capture"
OUT = CAP / "render_only_saved_01"
RENDERER = CAP / "render_saved_candidates.py"
RESULT = CAP.parent / "curvature_constrained_meridian_result.json"
DRIVER = ROOT / "vesselforge" / "experiments" / "semantic_base_neck_bspline_20261006" / "semantic_base_neck_driver.py"
SOURCE = ROOT / "vesselforge" / "experiments" / "curvature_constrained_meridian_20261006" / "curvature_constrained_meridian.py"
PYTHON = ROOT / "third_party" / "vesselforge-runtime" / "venv" / "Scripts" / "python.exe"
FILES = {"result": RESULT, "driver": DRIVER, "implementation": SOURCE, "renderer": RENDERER}
EXPECTED = {"result": "839c461cdf0dcae93f362ee7d80d0446cf52b6b1e1f04ed18842e17527673185",
            "driver": "038974cbbe3965f7f03f1ad0199d0aba00b56294840e411ca9a21fbde42466a3",
            "implementation": "96875bb6592a6fd57ceef4dc326c35faeb3f96de16607faa816c7d3fed1e08ce",
            "renderer": "32f7e4f30a20e8c0f815393ef00ff660618193ab501dce4c034fe35e250de3a0"}
START = CAP / "render_only_started.json"
STDOUT = CAP / "render_only_stdout.bin"
STDERR = CAP / "render_only_stderr.bin"
RECEIPT = CAP / "render_only_receipt.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pins() -> dict:
    return {key: {"path": str(path.relative_to(ROOT)), "sha256": sha(path), "bytes": path.stat().st_size}
            for key, path in FILES.items()}


def main() -> int:
    if OUT.exists() or any(p.exists() for p in (START, STDOUT, STDERR, RECEIPT)):
        raise FileExistsError("RENDER_ONLY_OUTPUT_OR_CAPTURE_ALREADY_EXISTS_REFUSING_RERUN")
    before = pins()
    if {key: row["sha256"] for key, row in before.items()} != EXPECTED:
        raise ValueError("RENDER_ONLY_INPUT_PIN_MISMATCH")
    runtime = {"python": str(PYTHON), "python_sha256": sha(PYTHON), "version": sys.version,
               "matplotlib_distribution_version": importlib.metadata.version("matplotlib")}
    with START.open("xb") as stream:
        stream.write(json.dumps({"started_utc_not_recorded": True, "pre_pins": before,
                                 "runtime": runtime}, sort_keys=True, indent=2).encode())
    started = time.monotonic()
    command = [str(PYTHON), "-B", str(RENDERER)]
    timed_out, exception, rc = False, None, None
    stdout, stderr = b"", b""
    try:
        done = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=20, check=False)
        stdout, stderr, rc = done.stdout, done.stderr, done.returncode
    except subprocess.TimeoutExpired as error:
        timed_out = True
        stdout, stderr = error.stdout or b"", error.stderr or b""
        exception = "TimeoutExpired: subprocess.run timeout=20 seconds"
    except Exception as error:
        exception = f"{type(error).__name__}: {error}"
    elapsed = time.monotonic() - started
    STDOUT.write_bytes(stdout); STDERR.write_bytes(stderr)
    after = pins()
    outputs = {}
    for path in (OUT / "saved_meridian_geometry_preview.png", OUT / "render_manifest.json"):
        outputs[path.name] = ({"exists": True, "bytes": path.stat().st_size, "sha256": sha(path)}
                              if path.is_file() else {"exists": False})
    record = {"invocation": "saved render-only renderer; no geometry/optimization call",
              "command": command, "cwd": str(ROOT), "timeout_seconds": 20, "timed_out": timed_out,
              "returncode": rc, "exception": exception, "elapsed_seconds": elapsed,
              "pre_pins": before, "post_pins": after, "runtime": runtime, "outputs": outputs,
              "raw_stdout_bytes": len(stdout), "raw_stderr_bytes": len(stderr),
              "total_capture_artifact_bytes": None, "under_2mib": None}
    RECEIPT.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tracked = [START, STDOUT, STDERR, RECEIPT, *[p for p in OUT.rglob("*") if p.is_file()]]
    record["total_capture_artifact_bytes"] = sum(p.stat().st_size for p in tracked if p.exists())
    record["under_2mib"] = record["total_capture_artifact_bytes"] < 2 * 1024 * 1024
    RECEIPT.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"returncode": rc, "timed_out": timed_out, "elapsed_seconds": elapsed,
                      "exception": exception, "outputs": outputs,
                      "total_capture_artifact_bytes": record["total_capture_artifact_bytes"],
                      "under_2mib": record["under_2mib"]}, sort_keys=True))
    return 0 if rc == 0 and not timed_out and exception is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
