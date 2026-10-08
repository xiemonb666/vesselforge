"""Source-only prepared readback for the already-saved owner-fix NPZ.

This worker never builds or regenerates candidate geometry. Execution requires
the explicit root-review switch and an empty, fixed recovery output directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from focused_checks_recovery_v1 import render_saved_meshes, run_focused_checks


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
REVIEW_ROOT = REPO_ROOT / "vesselforge" / "tmp" / "review_20261005" / "global_two_cap_mesh_candidate"
RECOVERY_ROOT = REVIEW_ROOT / "recovery_readback_ownerfix_v2"
OUTPUT_DIR = RECOVERY_ROOT / "readback_result"
FREEZE_PATH = HERE / "READBACK_RECOVERY_FREEZE_v2.json"

INPUT_PATHS = {
    "baseline_npz": REPO_ROOT / "vesselforge" / "tmp" / "review_20261004" / "surface_ornament_route" / "run02" / "fixture_arrays.npz",
    "local_b_npz": REPO_ROOT / "vesselforge" / "tmp" / "review_20261005" / "ornament_resume" / "local_refinement_run" / "local_b_0p25mm" / "candidate_arrays.npz",
    "local_b_checks": REPO_ROOT / "vesselforge" / "tmp" / "review_20261005" / "ornament_resume" / "local_refinement_run" / "local_b_0p25mm" / "checks.json",
    "refinement_source": REPO_ROOT / "vesselforge" / "experiments" / "surface_ornament_refinement_20261005" / "refinement_prototype.py",
    "case_freeze": REPO_ROOT / "vesselforge" / "experiments" / "surface_ornament_refinement_20261005" / "candidate_cases.json",
}
SAVED_CANDIDATE_NPZ = REVIEW_ROOT / "run02_owner_fix" / "candidate_arrays.npz"
VF_PYTHON = REPO_ROOT / "third_party" / "vesselforge-runtime" / "venv" / "Scripts" / "python.exe"


class ReadbackFailure(RuntimeError):
    """A source, input, or preservation pin failed closed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {name: archive[name].copy() for name in archive.files}


def relative_hashes(paths: dict[str, Path]) -> dict[str, str]:
    return {name: sha256_file(path) for name, path in paths.items()}


def history_paths(freeze: dict[str, Any]) -> dict[str, Path]:
    return {name: REPO_ROOT / relative for name, relative in freeze["history_paths"].items()}


def verify_expected(actual: dict[str, str], expected: dict[str, str], label: str) -> None:
    if actual != expected:
        mismatches = {
            name: {"expected": expected.get(name), "actual": actual.get(name)}
            for name in sorted(set(expected) | set(actual))
            if expected.get(name) != actual.get(name)
        }
        raise ReadbackFailure(f"{label} SHA mismatch: {mismatches}")


def _write_json_new(path: Path, value: dict[str, Any]) -> None:
    rendered = json.dumps(value, indent=2, sort_keys=True, allow_nan=False)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(rendered)
        stream.write("\n")


def _artifact_manifest(directory: Path) -> list[dict[str, Any]]:
    items = []
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            items.append({
                "path": path.relative_to(directory).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root-approved-readback", action="store_true")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    if not args.root_approved_readback:
        print("SOURCE_ONLY_AWAITING_ROOT_REVIEW; no input arrays loaded.")
        return 0

    requested_output = Path(args.output_dir).resolve()
    if requested_output != OUTPUT_DIR.resolve():
        raise ReadbackFailure(f"refusing output outside the fixed recovery directory: {requested_output}")
    if requested_output.exists():
        raise ReadbackFailure(f"refusing to reuse existing recovery output: {requested_output}")
    if not RECOVERY_ROOT.is_dir():
        raise ReadbackFailure("outer recovery directory must be created by the approved parent runner")

    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    source_before: dict[str, str] = {}
    input_before: dict[str, str] = {}
    history_before: dict[str, str] = {}
    candidate_sha_before: str | None = None
    output_dir_created = False
    numerical_status = "NOT_STARTED"
    numerical_report_path: Path | None = None
    render_status: dict[str, Any] = {"status": "NOT_ATTEMPTED"}
    checks: dict[str, Any] | None = None
    load_ready = False
    baseline: dict[str, np.ndarray] | None = None
    local_b: dict[str, np.ndarray] | None = None
    cases: dict[str, Any] | None = None
    local_b_checks: dict[str, Any] | None = None
    saved_candidate: dict[str, np.ndarray] | None = None
    exception_text: str | None = None
    exception_type: str | None = None

    try:
        freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
        if freeze.get("freeze_id") != "ownerfix_saved_npz_readback_recovery_v2":
            raise ReadbackFailure("unexpected readback recovery freeze identifier")
        source_paths = {name: REPO_ROOT / relative for name, relative in freeze["source_paths"].items()}
        source_before = relative_hashes(source_paths)
        verify_expected(source_before, freeze["source_sha256"], "source")
        input_before = relative_hashes(INPUT_PATHS)
        verify_expected(input_before, freeze["input_sha256"], "pinned input")
        candidate_sha_before = sha256_file(SAVED_CANDIDATE_NPZ)
        if candidate_sha_before != freeze["saved_candidate_npz_sha256"]:
            raise ReadbackFailure("saved run02 candidate NPZ SHA differs from recovery freeze")
        if sha256_file(VF_PYTHON) != freeze["vf_python_sha256"]:
            raise ReadbackFailure("VesselForge Python executable differs from recovery freeze")
        frozen_history_paths = history_paths(freeze)
        history_before = relative_hashes(frozen_history_paths)
        verify_expected(history_before, freeze["history_sha256"], "preserved history")

        requested_output.mkdir(parents=False, exist_ok=False)
        output_dir_created = True
        baseline = load_npz(INPUT_PATHS["baseline_npz"])
        local_b = load_npz(INPUT_PATHS["local_b_npz"])
        saved_candidate = load_npz(SAVED_CANDIDATE_NPZ)
        local_b_checks = json.loads(INPUT_PATHS["local_b_checks"].read_text(encoding="utf-8"))
        cases = json.loads(INPUT_PATHS["case_freeze"].read_text(encoding="utf-8"))
        load_ready = True

        expected_provenance = {
            "baseline_fixture_arrays_sha256": freeze["input_sha256"]["baseline_npz"],
            "refinement_source_sha256": freeze["input_sha256"]["refinement_source"],
            "case_freeze_sha256": freeze["input_sha256"]["case_freeze"],
        }
        for field_name, expected in expected_provenance.items():
            actual = str(np.asarray(local_b[field_name]).item())
            if actual != expected:
                raise ReadbackFailure(f"local-B embedded provenance mismatch at {field_name}")
        if len(local_b["vertices_rest_xyz_mm"]) <= len(baseline["vertices_rest_xyz_mm"]):
            raise ReadbackFailure("pinned local-B does not contain the frozen baseline prefix")
        if int(np.asarray(local_b["original_vertex_count"]).item()) != len(baseline["vertices_rest_xyz_mm"]):
            raise ReadbackFailure("pinned local-B original vertex count differs from baseline")
        if int(np.asarray(local_b["original_face_count"]).item()) != len(baseline["faces"]):
            raise ReadbackFailure("pinned local-B original face count differs from baseline")
        if str(cases.get("freeze_id")) != "surface_ornament_refinement_20261005_source_review_v1":
            raise ReadbackFailure("unexpected pinned case freeze identifier")

        # This is the only numerical readback call. It consumes the saved NPZ;
        # candidate_owner_fix is imported only by the checker for its toy owner test.
        checks = run_focused_checks(baseline, local_b, saved_candidate, cases, local_b_checks)
        numerical_status = "NUMERICAL_CHECK_PASS" if checks["focused_checks_pass"] else "NUMERICAL_CHECK_FAIL"
        completion_label = (
            "RECOVERED_CANDIDATE_READBACK_FROM_FAILED_RUN"
            if checks["focused_checks_pass"] else "DISCREPANCY"
        )
        primary_report = {
            "readback_id": "ownerfix_saved_npz_readback_recovery_v2",
            "completion_label": completion_label,
            "numerical_status": numerical_status,
            "original_run02_status": "UNKNOWN_OR_FAIL",
            "original_run02_failure": "TypeError while serializing returned focused checks",
            "generation_invoked": False,
            "saved_candidate_npz_sha256": candidate_sha_before,
            "input_sha256": input_before,
            "source_sha256": source_before,
            "checks": checks,
        }
        primary_path = requested_output / "readback_checks.json"
        _write_json_new(primary_path, primary_report)
        numerical_report_path = primary_path
    except Exception as exc:
        numerical_status = (
            "NUMERICAL_REPORT_SERIALIZATION_FAIL" if checks is not None
            else "NUMERICAL_READBACK_EXCEPTION"
        )
        exception_type = type(exc).__name__
        exception_text = str(exc)
        if output_dir_created and numerical_report_path is None:
            primary_report = {
                "readback_id": "ownerfix_saved_npz_readback_recovery_v2",
                "completion_label": "DISCREPANCY",
                "numerical_status": numerical_status,
                "original_run02_status": "UNKNOWN_OR_FAIL",
                "generation_invoked": False,
                "error_type": exception_type,
                "error": exception_text,
                "traceback": traceback.format_exc(),
                "source_sha256_before": source_before,
                "input_sha256_before": input_before,
                "saved_candidate_npz_sha256_before": candidate_sha_before,
            }
            numerical_report_path = requested_output / "readback_checks.json"
            _write_json_new(numerical_report_path, primary_report)

    if output_dir_created:
        render_started = time.perf_counter()
        if load_ready and saved_candidate is not None and cases is not None:
            try:
                # Rendering is intentionally after readback_checks.json and is
                # reported separately from numerical status.
                render_saved_meshes(saved_candidate, requested_output, cases)
                image_names = (
                    "global_equal_aspect_actual_mesh.png",
                    "two_caps_equal_aspect_actual_mesh.png",
                )
                images = []
                for name in image_names:
                    path = requested_output / name
                    if not path.is_file():
                        raise ReadbackFailure(f"renderer did not produce {name}")
                    images.append({"path": name, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
                render_status = {
                    "status": "RENDER_PASS",
                    "render_elapsed_seconds": time.perf_counter() - render_started,
                    "actual_saved_candidate_mesh": True,
                    "images": images,
                }
            except Exception as exc:
                render_status = {
                    "status": "RENDER_FAIL",
                    "render_elapsed_seconds": time.perf_counter() - render_started,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
        else:
            render_status = {
                "status": "RENDER_NOT_ATTEMPTED_INPUT_OR_PIN_FAILURE",
                "render_elapsed_seconds": 0.0,
            }
        _write_json_new(requested_output / "render_status.json", render_status)

        source_after: dict[str, str] = {}
        input_after: dict[str, str] = {}
        history_after: dict[str, str] = {}
        candidate_sha_after: str | None = None
        try:
            freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
            source_paths = {name: REPO_ROOT / relative for name, relative in freeze["source_paths"].items()}
            source_after = relative_hashes(source_paths)
            input_after = relative_hashes(INPUT_PATHS)
            history_after = relative_hashes(history_paths(freeze))
            candidate_sha_after = sha256_file(SAVED_CANDIDATE_NPZ)
        except Exception as exc:
            if exception_type is None:
                exception_type, exception_text = type(exc).__name__, str(exc)

        pins_unchanged = (
            source_after == source_before == freeze.get("source_sha256", {})
            and input_after == input_before == freeze.get("input_sha256", {})
            and history_after == history_before == freeze.get("history_sha256", {})
            and candidate_sha_after == candidate_sha_before == freeze.get("saved_candidate_npz_sha256")
        )
        receipt_status = "READBACK_COMPLETED" if pins_unchanged else "DISCREPANCY_PIN_DRIFT"
        if exception_type is not None and numerical_status == "NOT_STARTED":
            receipt_status = "DISCREPANCY_READBACK_EXCEPTION"
        receipt = {
            "readback_id": "ownerfix_saved_npz_readback_recovery_v2",
            "status": receipt_status,
            "completion_label": (
                "RECOVERED_CANDIDATE_READBACK_FROM_FAILED_RUN"
                if (numerical_report_path is not None and numerical_status == "NUMERICAL_CHECK_PASS"
                    and checks is not None and bool(checks.get("focused_checks_pass")))
                else "DISCREPANCY"
            ),
            "actual_argv": sys.argv,
            "generation_invoked": False,
            "cad_or_solver_invoked": False,
            "started_at_utc": started_at,
            "elapsed_seconds": time.perf_counter() - started,
            "source_freeze_sha256": sha256_file(FREEZE_PATH),
            "source_sha256_before": source_before,
            "source_sha256_after": source_after,
            "pinned_input_sha256_before": input_before,
            "pinned_input_sha256_after": input_after,
            "saved_candidate_npz_sha256_before": candidate_sha_before,
            "saved_candidate_npz_sha256_after": candidate_sha_after,
            "history_sha256_before": history_before,
            "history_sha256_after": history_after,
            "pins_unchanged": pins_unchanged,
            "numerical_status": numerical_status,
            "numerical_report": "readback_checks.json" if numerical_report_path is not None else None,
            "render_status": render_status,
            "error_type": exception_type,
            "error": exception_text,
            "artifacts_before_receipt": _artifact_manifest(requested_output),
        }
        _write_json_new(requested_output / "readback_receipt.json", receipt)

    if not output_dir_created:
        return 2
    if not (source_after == source_before == freeze.get("source_sha256", {})
            and input_after == input_before == freeze.get("input_sha256", {})
            and history_after == history_before == freeze.get("history_sha256", {})
            and candidate_sha_after == candidate_sha_before == freeze.get("saved_candidate_npz_sha256")):
        return 2
    if numerical_status != "NUMERICAL_CHECK_PASS" or render_status.get("status") != "RENDER_PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
