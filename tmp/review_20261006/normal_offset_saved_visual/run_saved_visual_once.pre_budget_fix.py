from __future__ import annotations
import hashlib, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
PINS = HERE / "false_pins.json"
SELF = Path(__file__).resolve()
PYTHON = ROOT / "third_party/vesselforge-runtime/venv/Scripts/python.exe"
START = HERE / "render_started.json"
STDOUT = HERE / "render_stdout.raw.bin"
STDERR = HERE / "render_stderr.raw.bin"
RECEIPT = HERE / "render_receipt.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
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
    with START.open("x",encoding="utf-8") as stream:
        json.dump({"pre_pins":before},stream,indent=2,sort_keys=True)
    command=[str(PYTHON),"-B",str(renderer)]; began=time.monotonic()
    rc=None; timed_out=False; error=None; stdout=b""; stderr=b""
    try:
        done=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=15,check=False)
        rc,stdout,stderr=done.returncode,done.stdout,done.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out=True; error="TimeoutExpired: 15 seconds"
        stdout,stderr=exc.stdout or b"",exc.stderr or b""
    except Exception as exc: error=f"{type(exc).__name__}: {exc}"
    elapsed=time.monotonic()-began
    with STDOUT.open("xb") as f: f.write(stdout)
    with STDERR.open("xb") as f: f.write(stderr)
    after={k:{"path":str(p.relative_to(ROOT)),"sha256":sha(p)} for k,p in paths.items()}
    image={"exists":output.is_file(),"bytes":output.stat().st_size if output.is_file() else None,
           "sha256":sha(output) if output.is_file() else None}
    record={"command":command,"cwd":str(ROOT),"returncode":rc,"timed_out":timed_out,"exception":error,
            "elapsed_seconds":elapsed,"timeout_seconds":15,"pre_pins":before,"post_pins":after,
            "output":image,"raw_stdout_bytes":len(stdout),"raw_stderr_bytes":len(stderr),
            "raw_stdout_sha256":sha(STDOUT),"raw_stderr_sha256":sha(STDERR),"max_output_bytes":2097152}
    encoded=json.dumps(record,indent=2,sort_keys=True)+"\n"
    if image["bytes"] is not None and image["bytes"]+len(stdout)+len(stderr)+len(encoded.encode())>2097152:
        record["under_2mib_including_capture_and_receipt"]=False
    else: record["under_2mib_including_capture_and_receipt"]=True
    with RECEIPT.open("xb") as f: f.write((json.dumps(record,indent=2,sort_keys=True)+"\n").encode())
    print(json.dumps({"returncode":rc,"timed_out":timed_out,"elapsed_seconds":elapsed,"output":image},sort_keys=True))
    return rc if rc is not None else (124 if timed_out else 127)


if __name__ == "__main__": raise SystemExit(main())
