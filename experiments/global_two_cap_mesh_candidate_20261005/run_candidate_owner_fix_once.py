"""Bounded parent runner for the quarantined two-cap candidate.

This file does not run on import. A reviewed invocation performs exactly one
candidate subprocess in the fixed run02_owner_fix directory; it never retries.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
REVIEW_ROOT = REPO_ROOT / "vesselforge" / "tmp" / "review_20261005" / "global_two_cap_mesh_candidate"
RUN_DIR = REVIEW_ROOT / "run02_owner_fix"
LOCK_PATH = REVIEW_ROOT / ".run02_owner_fix.parent_runner.lock"
FREEZE_PATH = HERE / "SOURCE_FREEZE_owner_fix.json"
CONTRACT_PATH = HERE / "candidate_contract_owner_fix.json"
SOURCE_PATHS = {
    "candidate_owner_fix.py": HERE / "candidate_owner_fix.py",
    "focused_checks_owner_fix.py": HERE / "focused_checks_owner_fix.py",
    "candidate_contract_owner_fix.json": CONTRACT_PATH,
    "SOURCE_REVIEW_owner_fix.md": HERE / "SOURCE_REVIEW_owner_fix.md",
    "run_candidate_owner_fix_once.py": Path(__file__).resolve(),
    "SOURCE_FREEZE_owner_fix.json": FREEZE_PATH,
    "owner_lookup_toy_check.py": HERE / "owner_lookup_toy_check.py",
    "run01_failure_snapshot_before_owner_fix.json": REVIEW_ROOT / "run01_failure_snapshot_before_owner_fix.json",
    "owner_fix_two_parent_toy_check.json": REVIEW_ROOT / "owner_fix_two_parent_toy_check.json",
    "prewrite_budget_audit.py": REVIEW_ROOT / "prewrite_budget_audit.py",
    "prewrite_budget_audit.json": REVIEW_ROOT / "prewrite_budget_audit.json",
}
INPUT_PATHS = {
    "baseline_fixture_npz": REPO_ROOT / "vesselforge" / "tmp" / "review_20261004" / "surface_ornament_route" / "run02" / "fixture_arrays.npz",
    "local_b_candidate_npz": REPO_ROOT / "vesselforge" / "tmp" / "review_20261005" / "ornament_resume" / "local_refinement_run" / "local_b_0p25mm" / "candidate_arrays.npz",
    "local_b_checks": REPO_ROOT / "vesselforge" / "tmp" / "review_20261005" / "ornament_resume" / "local_refinement_run" / "local_b_0p25mm" / "checks.json",
    "ornament_refinement_source": REPO_ROOT / "vesselforge" / "experiments" / "surface_ornament_refinement_20261005" / "refinement_prototype.py",
    "ornament_case_freeze": REPO_ROOT / "vesselforge" / "experiments" / "surface_ornament_refinement_20261005" / "candidate_cases.json",
}
MAX_TOTAL_SECONDS = 120.0
CLEANUP_RESERVE_SECONDS = 12.0
MAX_RETAINED_OUTPUT_BYTES = 20 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _snapshot() -> dict[str, dict[str, str]]:
    return {
        "sources": {name: _sha256(path) for name, path in SOURCE_PATHS.items()},
        "pinned_inputs": {name: _sha256(path) for name, path in INPUT_PATHS.items()},
    }


def _expected_hashes() -> tuple[dict[str, str], dict[str, str]]:
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    source_expected = dict(freeze["source_sha256"])
    source_expected["prewrite_budget_audit.py"] = freeze["prewrite_audit"]["script_sha256"]
    source_expected["prewrite_budget_audit.json"] = freeze["prewrite_audit"]["result_sha256"]
    input_expected = {
        "baseline_fixture_npz": contract["pinned_inputs"]["baseline_fixture_npz_sha256"],
        "local_b_candidate_npz": contract["pinned_inputs"]["local_b_candidate_npz_sha256"],
        "local_b_checks": contract["pinned_inputs"]["local_b_checks_sha256"],
        "ornament_refinement_source": contract["pinned_inputs"]["ornament_refinement_source_sha256"],
        "ornament_case_freeze": contract["pinned_inputs"]["ornament_case_freeze_sha256"],
    }
    return source_expected, input_expected


def _pin_mismatches(snapshot: dict[str, dict[str, str]]) -> list[str]:
    expected_sources, expected_inputs = _expected_hashes()
    mismatches: list[str] = []
    for name, expected in expected_sources.items():
        actual = snapshot["sources"].get(name)
        if actual != expected:
            mismatches.append(f"source:{name}:expected={expected}:actual={actual}")
    for name, expected in expected_inputs.items():
        actual = snapshot["pinned_inputs"].get(name)
        if actual != expected:
            mismatches.append(f"input:{name}:expected={expected}:actual={actual}")
    return mismatches


def _kill_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=4.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            pass


def _write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)


def _ensure_run_dir() -> None:
    resolved_root = REVIEW_ROOT.resolve()
    resolved_run = RUN_DIR.resolve()
    if resolved_run.parent != resolved_root:
        raise RuntimeError("fixed run directory escaped the authorized review directory")
    if not resolved_run.exists():
        resolved_run.mkdir(parents=False, exist_ok=False)


def main() -> int:
    started = time.monotonic()
    deadline = started + MAX_TOTAL_SECONDS
    if sys.argv[1:] != ["--root-approved-run"]:
        print("source-only: invoke with --root-approved-run only after explicit root approval", file=sys.stderr)
        return 64
    receipt: dict[str, Any] = {
        "runner_id": "global_two_cap_mesh_candidate_owner_fix_parent_runner_v1",
        "status": "RUNNER_STARTING",
        "started_at_utc": _utc_now(),
        "runner_argv": list(sys.argv),
        "candidate_argv": [sys.executable, str(HERE / "candidate_owner_fix.py"), "--run"],
        "cwd": str(REPO_ROOT),
        "fixed_run_directory": str(RUN_DIR),
        "hard_total_wall_clock_seconds": MAX_TOTAL_SECONDS,
        "cleanup_reserve_seconds": CLEANUP_RESERVE_SECONDS,
        "combined_child_output_retention_cap_bytes": MAX_RETAINED_OUTPUT_BYTES,
        "stderr_merged_into_stdout": True,
        "automatic_retry": False,
        "required_approval_switch": "--root-approved-run",
        "approval_switch_present": True,
        "candidate_generation_was_invoked": False,
        "candidate_return_code": None,
        "timed_out": False,
    }
    lock_fd: int | None = None
    lock_owned = False
    process: subprocess.Popen[bytes] | None = None
    reader: threading.Thread | None = None
    retained = bytearray()
    observed_output_bytes = 0
    output_truncated = False
    output_lock = threading.Lock()
    snapshot_before: dict[str, dict[str, str]] | None = None
    snapshot_after: dict[str, dict[str, str]] | None = None
    child_launch_error: str | None = None
    timeout_reason: str | None = None

    try:
        REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
        if RUN_DIR.exists():
            print(f"refusing existing run directory: {RUN_DIR}", file=sys.stderr)
            return 73
        try:
            lock_fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            lock_owned = True
            os.write(lock_fd, f"pid={os.getpid()}\n".encode("ascii"))
            os.close(lock_fd)
            lock_fd = None
        except FileExistsError:
            print(f"refusing existing runner lock: {LOCK_PATH}", file=sys.stderr)
            return 73

        snapshot_before = _snapshot()
        receipt["source_sha256_before"] = snapshot_before["sources"]
        receipt["pinned_input_sha256_before"] = snapshot_before["pinned_inputs"]
        mismatches = _pin_mismatches(snapshot_before)
        if mismatches:
            receipt["status"] = "PREFLIGHT_PIN_MISMATCH"
            receipt["pin_mismatches"] = mismatches
        elif time.monotonic() >= deadline - CLEANUP_RESERVE_SECONDS:
            receipt["status"] = "RUNNER_DEADLINE_BEFORE_CHILD"
        else:
            if deadline - time.monotonic() <= CLEANUP_RESERVE_SECONDS:
                receipt["status"] = "RUNNER_DEADLINE_BEFORE_CHILD"
            else:
                creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
                process = subprocess.Popen(
                    receipt["candidate_argv"],
                    cwd=str(REPO_ROOT),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=0,
                    creationflags=creationflags,
                    start_new_session=(os.name != "nt"),
                )
                receipt["candidate_generation_was_invoked"] = True
                receipt["child_pid"] = process.pid
                receipt["candidate_started_at_utc"] = _utc_now()
                child_started = time.monotonic()
                child_timeout = min(
                    deadline - child_started - CLEANUP_RESERVE_SECONDS,
                    MAX_TOTAL_SECONDS - CLEANUP_RESERVE_SECONDS,
                )
                if child_timeout <= 0:
                    receipt["timed_out"] = True
                    timeout_reason = "runner deadline reserve exhausted during child launch"
                    _kill_process_tree(process)

                def drain_output() -> None:
                    nonlocal observed_output_bytes, output_truncated
                    assert process is not None and process.stdout is not None
                    while True:
                        chunk = process.stdout.read(READ_CHUNK_BYTES)
                        if not chunk:
                            break
                        with output_lock:
                            observed_output_bytes += len(chunk)
                            remaining_capacity = MAX_RETAINED_OUTPUT_BYTES - len(retained)
                            if remaining_capacity > 0:
                                retained.extend(chunk[:remaining_capacity])
                            if len(chunk) > max(0, remaining_capacity):
                                output_truncated = True

                reader = threading.Thread(target=drain_output, name="candidate-output-drain", daemon=True)
                reader.start()
                if child_timeout > 0:
                    try:
                        process.wait(timeout=child_timeout)
                    except subprocess.TimeoutExpired:
                        receipt["timed_out"] = True
                        timeout_reason = "candidate subprocess exceeded runner deadline reserve"
                        _kill_process_tree(process)
                child_return_code = process.poll()
                if child_return_code is None:
                    _kill_process_tree(process)
                    child_return_code = process.poll()
                receipt["candidate_return_code"] = child_return_code
                receipt["candidate_elapsed_seconds"] = time.monotonic() - child_started
                receipt["candidate_finished_at_utc"] = _utc_now()
                join_budget = max(0.0, deadline - time.monotonic() - 5.0)
                reader.join(timeout=join_budget)
                if reader.is_alive():
                    _kill_process_tree(process)
                    reader.join(timeout=max(0.0, deadline - time.monotonic() - 3.0))
                if reader.is_alive():
                    timeout_reason = timeout_reason or "output pipe did not close within reserved cleanup time"
                with output_lock:
                    receipt["combined_child_output_observed_bytes"] = observed_output_bytes
                    receipt["combined_child_output_retained_bytes"] = len(retained)
                    receipt["combined_child_output_truncated"] = output_truncated
                if receipt["timed_out"]:
                    receipt["status"] = "CHILD_TIMEOUT_TERMINATED"
                elif reader.is_alive():
                    receipt["status"] = "CHILD_OUTPUT_DRAIN_TIMEOUT"
                else:
                    receipt["status"] = "CHILD_EXITED"
                    if child_return_code != 0:
                        receipt["status"] = "CHILD_NONZERO_EXIT"
                if timeout_reason:
                    receipt["timeout_or_cleanup_detail"] = timeout_reason
        if process is None and receipt["status"] in {"PREFLIGHT_PIN_MISMATCH", "RUNNER_DEADLINE_BEFORE_CHILD"}:
            receipt["combined_child_output_observed_bytes"] = 0
            receipt["combined_child_output_retained_bytes"] = 0
            receipt["combined_child_output_truncated"] = False
        snapshot_after = _snapshot()
        receipt["source_sha256_after"] = snapshot_after["sources"]
        receipt["pinned_input_sha256_after"] = snapshot_after["pinned_inputs"]
        receipt["source_and_input_hashes_unchanged"] = snapshot_before == snapshot_after if snapshot_before else None
        receipt["finished_at_utc"] = _utc_now()
        receipt["elapsed_seconds_before_receipt_write"] = time.monotonic() - started
        if process is not None and snapshot_before != snapshot_after:
            receipt["status"] = "SOURCE_OR_INPUT_CHANGED_DURING_RUN"
        elif process is not None and receipt["status"] == "CHILD_EXITED" and receipt["candidate_return_code"] == 0:
            receipt["status"] = "CHILD_EXITED_ZERO; quality outcome is in candidate checks/manifest"
        _ensure_run_dir()
        output_bytes = bytes(retained)
        _write_new(RUN_DIR / "parent_runner_combined_output.bin", output_bytes)
        receipt["combined_output_path"] = str(RUN_DIR / "parent_runner_combined_output.bin")
        receipt_bytes = (json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        _write_new(RUN_DIR / "parent_runner_receipt.json", receipt_bytes)
        return 0 if process is not None and receipt["candidate_return_code"] == 0 and not receipt["timed_out"] else 1
    except BaseException as exc:
        child_launch_error = f"{type(exc).__name__}: {exc}"
        if process is not None and process.poll() is None:
            _kill_process_tree(process)
        receipt["status"] = "PARENT_RUNNER_EXCEPTION"
        receipt["parent_runner_error"] = child_launch_error
        if process is not None:
            receipt["candidate_return_code"] = process.poll()
        try:
            if snapshot_before is not None and snapshot_after is None:
                snapshot_after = _snapshot()
                receipt["source_sha256_after"] = snapshot_after["sources"]
                receipt["pinned_input_sha256_after"] = snapshot_after["pinned_inputs"]
                receipt["source_and_input_hashes_unchanged"] = snapshot_before == snapshot_after
            receipt["finished_at_utc"] = _utc_now()
            receipt["elapsed_seconds_before_receipt_write"] = time.monotonic() - started
            _ensure_run_dir()
            if not (RUN_DIR / "parent_runner_combined_output.bin").exists():
                _write_new(RUN_DIR / "parent_runner_combined_output.bin", bytes(retained))
            if not (RUN_DIR / "parent_runner_receipt.json").exists():
                receipt_bytes = (json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
                _write_new(RUN_DIR / "parent_runner_receipt.json", receipt_bytes)
        except BaseException as record_error:
            print(f"could not record parent-runner receipt: {type(record_error).__name__}: {record_error}", file=sys.stderr)
        return 1
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        if lock_owned:
            try:
                LOCK_PATH.unlink(missing_ok=True)
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
