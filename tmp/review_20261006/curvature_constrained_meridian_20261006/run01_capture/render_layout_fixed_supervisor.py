from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path.cwd().resolve()
CAP = ROOT / "vesselforge" / "tmp" / "review_20261006" / "curvature_constrained_meridian_20261006" / "run01_capture"
OUT = CAP / "render_only_saved_layout_fixed_01"
RENDERER = CAP / "render_saved_candidates_layout_fixed.py"
FILES = {
    "result": CAP.parent / "curvature_constrained_meridian_result.json",
    "driver": ROOT / "vesselforge" / "experiments" / "semantic_base_neck_bspline_20261006" / "semantic_base_neck_driver.py",
    "implementation": ROOT / "vesselforge" / "experiments" / "curvature_constrained_meridian_20261006" / "curvature_constrained_meridian.py",
    "original_renderer": CAP / "render_saved_candidates.py", "layout_renderer": RENDERER}
EXPECTED = {
    "result": "839c461cdf0dcae93f362ee7d80d0446cf52b6b1e1f04ed18842e17527673185",
    "driver": "038974cbbe3965f7f03f1ad0199d0aba00b56294840e411ca9a21fbde42466a3",
    "implementation": "96875bb6592a6fd57ceef4dc326c35faeb3f96de16607faa816c7d3fed1e08ce",
    "original_renderer": "32f7e4f30a20e8c0f815393ef00ff660618193ab501dce4c034fe35e250de3a0",
    "layout_renderer": "171eb4dd6149fbc86196cc31589ca7553e3330e7866ca46e039f75bb22eaacdd"}
PYTHON = ROOT / "third_party" / "vesselforge-runtime" / "venv" / "Scripts" / "python.exe"
START = CAP / "render_layout_fixed_started.json"
STDOUT = CAP / "render_layout_fixed_stdout.bin"
STDERR = CAP / "render_layout_fixed_stderr.bin"
RECEIPT = CAP / "render_layout_fixed_receipt.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pin() -> dict:
    return {name: {"path": str(path.relative_to(ROOT)), "sha256": sha(path), "bytes": path.stat().st_size}
            for name, path in FILES.items()}


def main() -> int:
    if OUT.exists() or any(path.exists() for path in (START, STDOUT, STDERR, RECEIPT)):
        raise FileExistsError("LAYOUT_RENDER_OUTPUT_OR_CAPTURE_EXISTS_REFUSING_RERUN")
    before = pin()
    if {name: item["sha256"] for name, item in before.items()} != EXPECTED:
        raise ValueError("LAYOUT_RENDER_INPUT_PIN_MISMATCH")
    with START.open("xb") as stream:
        stream.write(json.dumps({"pre_pins": before, "one_shot": True}, indent=2, sort_keys=True).encode())
    command = [str(PYTHON), "-B", str(RENDERER)]
    started = time.monotonic(); rc = None; timed_out = False; error = None; stdout = b""; stderr = b""
    try:
        done = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=20, check=False)
        rc, stdout, stderr = done.returncode, done.stdout, done.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out, error = True, "TimeoutExpired: 20 seconds"
        stdout, stderr = exc.stdout or b"", exc.stderr or b""
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.monotonic() - started
    STDOUT.write_bytes(stdout); STDERR.write_bytes(stderr)
    after = pin()
    images = [p for p in OUT.rglob("*") if p.is_file()] if OUT.exists() else []
    outputs = {str(p.relative_to(ROOT)): {"bytes": p.stat().st_size, "sha256": sha(p)} for p in images}
    out_bytes = sum(p.stat().st_size for p in images)
    record = {"command": command, "cwd": str(ROOT), "timeout_seconds": 20, "returncode": rc,
              "timed_out": timed_out, "exception": error, "elapsed_seconds": elapsed,
              "pre_pins": before, "post_pins": after, "outputs": outputs,
              "renderer_output_bytes": out_bytes, "renderer_outputs_under_2mib": out_bytes < 2*1024*1024,
              "raw_stdout_bytes": len(stdout), "raw_stderr_bytes": len(stderr)}
    RECEIPT.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"returncode": rc, "timed_out": timed_out, "elapsed_seconds": elapsed,
                      "exception": error, "outputs": outputs, "renderer_output_bytes": out_bytes}, sort_keys=True))
    return 0 if rc == 0 and not timed_out and error is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
