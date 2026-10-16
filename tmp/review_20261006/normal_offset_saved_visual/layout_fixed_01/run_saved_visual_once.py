from __future__ import annotations
import hashlib, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
PINS = HERE / "false_pins.json"
SELF = Path(__file__).resolve()
PYTHON = ROOT / "third_party/vesselforge-runtime/venv/Scripts/python.exe"
START = HERE / "render_started.json"
STDOUT = HERE / "render_stdout.raw.bin"
STDERR = HERE / "render_stderr.raw.bin"
RECEIPT = HERE / "render_receipt.json"
LIMIT, DEADLINE = 2 * 1024 * 1024, 15.0


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wire(record: dict) -> bytes:
    return (json.dumps(record, indent=2, sort_keys=True) + "\n").encode()

def main() -> int:
    began = time.monotonic()
    if sys.argv[1:] != ["--root-go"]: print("SOURCE_ONLY: explicit root GO required"); return 4
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    if pins["render_authorization"]["root_render_only_go_received"] is not True:
        raise PermissionError("ROOT_RENDER_ONLY_GO_REQUIRED")
    files = {k: ROOT / pins["inputs"][k]["path"] for k in ("normal_offset_result","curvature_result","frozen_driver")}
    renderer = ROOT / pins["renderer"]["path"]
    output = ROOT / pins["render_authorization"]["output_path"]
    expected = {k: pins["inputs"][k]["sha256"] for k in files}
    expected.update(renderer=pins["renderer"]["sha256"], runner=pins["runner"]["sha256"])
    paths = {**files, "renderer":renderer, "runner":SELF, "false_pins":PINS}
    expected["false_pins"] = sha(PINS)
    before = {k: {"path":str(p.relative_to(ROOT)),"sha256":sha(p)} for k,p in paths.items()}
    if {k:v["sha256"] for k,v in before.items()} != expected: raise ValueError("RENDER_INPUT_PIN_MISMATCH")
    if output.exists() or any(p.exists() for p in (START,STDOUT,STDERR,RECEIPT)):
        raise FileExistsError("RENDER_OR_CAPTURE_EXISTS_REFUSING_RERUN")
    with START.open("x",encoding="utf-8") as stream: json.dump({"pre_pins":before},stream,indent=2,sort_keys=True)
    command=[str(PYTHON),"-B",str(renderer)]
    rc=None; timed_out=False; error=None; stdout=b""; stderr=b""
    remaining=DEADLINE-(time.monotonic()-began)
    if remaining<=0: rc=124; error="deadline exhausted during preflight"
    else:
        try:
            done=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=remaining,check=False)
            rc,stdout,stderr=done.returncode,done.stdout,done.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out=True; rc=124; error="TimeoutExpired: remaining deadline"
            stdout,stderr=exc.stdout or b"",exc.stderr or b""
        except Exception as exc: rc=127; error=f"{type(exc).__name__}: {exc}"
    child_rc=rc
    with STDOUT.open("xb") as f: f.write(stdout)
    with STDERR.open("xb") as f: f.write(stderr)
    after={k:{"path":str(p.relative_to(ROOT)),"sha256":sha(p)} for k,p in paths.items()}
    changed=before!=after
    image={"exists":output.is_file(),"bytes":output.stat().st_size if output.is_file() else None,
           "sha256":sha(output) if output.is_file() else None}
    elapsed=time.monotonic()-began; late=elapsed>DEADLINE
    if changed: rc=125
    elif late: rc=124
    base=(image["bytes"] or 0)+len(stdout)+len(stderr)+START.stat().st_size
    record={"command":command,"cwd":str(ROOT),"returncode":rc,"child_returncode":child_rc,
            "timed_out":timed_out,"exception":error,"elapsed_seconds":elapsed,
            "deadline_seconds":DEADLINE,"deadline_overrun":late,"pre_pins":before,"post_pins":after,
            "input_pins_unchanged":not changed,
            "output":image,"raw_stdout_bytes":len(stdout),"raw_stderr_bytes":len(stderr),
            "raw_stdout_sha256":sha(STDOUT),"raw_stderr_sha256":sha(STDERR),
            "started_capture_bytes":START.stat().st_size,"base_capture_bytes":base,"max_output_bytes":LIMIT,
            "receipt_bytes":None,"total_capture_bytes":None,"capture_budget_status":"UNKNOWN_FIXED_POINT_NOT_PASS",
            "under_2mib_including_capture_and_receipt":False}
    stable=False; payload=b""
    for attempt in range(1,11):
        size=len(wire(record)); total=base+size; over=total>LIMIT
        record.update(receipt_fixed_point_iterations=attempt,receipt_bytes=size,total_capture_bytes=total,
                      capture_budget_status="EXCEEDED" if over else "WITHIN_LIMIT",
                      under_2mib_including_capture_and_receipt=not over,returncode=126 if over else rc)
        payload=wire(record)
        if len(payload)==size: stable=True; break
    if not stable:
        record.update(returncode=127,receipt_bytes=None,total_capture_bytes=None,
                      capture_budget_status="UNKNOWN_FIXED_POINT_NOT_PASS",
                      under_2mib_including_capture_and_receipt=False)
        payload=wire(record)
    with RECEIPT.open("xb") as f: f.write(payload)
    print(json.dumps({"returncode":record["returncode"],"timed_out":timed_out,"elapsed_seconds":elapsed,"output":image},sort_keys=True))
    return record["returncode"]

if __name__ == "__main__": raise SystemExit(main())
