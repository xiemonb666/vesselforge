"""Read back and render the preserved run02 candidate without remeshing it.

This adapter is deliberately separate from candidate.py. It never calls
candidate.main, builds a mesh, writes the source NPZ, or touches the original
run02 receipt. Its only generated files belong in the new completion_review
directory after explicit root approval to execute this source.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
REVIEW_ROOT = REPO_ROOT / "vesselforge" / "tmp" / "review_20261005" / "global_mesh_quality_candidate"
RUN02_DIR = REVIEW_ROOT / "run02_v2bugfix"
OUTPUT_DIR = REVIEW_ROOT / "completion_review"
SOURCE_FREEZE_PATH = HERE / "SOURCE_FREEZE.json"
PRE_READBACK_SNAPSHOT = RUN02_DIR / "pre_readback_source_snapshot"
PRE_READBACK_SNAPSHOT_MANIFEST = PRE_READBACK_SNAPSHOT / "snapshot_manifest.json"
LOCAL_B_DIR = REVIEW_ROOT.parent / "ornament_resume" / "local_refinement_run" / "local_b_0p25mm"

BASELINE_PATH = (
    REPO_ROOT / "vesselforge" / "tmp" / "review_20261004" / "surface_ornament_route"
    / "run02" / "fixture_arrays.npz"
)
LOCAL_B_NPZ = LOCAL_B_DIR / "candidate_arrays.npz"
LOCAL_B_CHECKS = LOCAL_B_DIR / "checks.json"
OLD_REFINEMENT_SOURCE = HERE.parent / "surface_ornament_refinement_20261005" / "refinement_prototype.py"
OLD_CASES = HERE.parent / "surface_ornament_refinement_20261005" / "candidate_cases.json"
SAVED_CANDIDATE_NPZ = RUN02_DIR / "candidate_arrays.npz"
ORIGINAL_RUN02_RECEIPT = RUN02_DIR / "run_receipt.json"

EXPECTED = {
    "baseline_sha256": "b44bb78176e690d8bc92ab2fc10f0803e142a0311acee8ff3944d4e324b9b974",
    "local_b_sha256": "8a2539dff0a05444951ecae6bd66ba2d849c753764dc635a4bacdf8382c6cfdf",
    "local_b_checks_sha256": "4e4c08b96bd6e7dd47a3285377979fc93fc3865a0bc1fcdd48d79397c23e14e8",
    "refinement_source_sha256": "5e946c205fb233e9354dfdde10d562597484ee38193e7930f93ce999f5840f74",
    "case_freeze_sha256": "ab89a0832366d0391b9539248cfbfab62e7ea770f3cf9b1499ee6b39b0b533c1",
    "saved_candidate_sha256": "11f3ddad24e8d8a1aa2d46d6e8be9b28049c87ad6226e47cf84eaff9eae167d9",
    "run02_receipt_sha256": "5b8588696346fcb396c2c8eee36365ffccc30bf93c3e4bf36be5195713153184",
    "run02_source_freeze_sha256": "47dbd74954126eecb648b3ee693cf1877150404f4db3aef06d9c338c194867e3",
    "candidate_source_sha256": "9fa7ed881d30444dba545d3b1f6b3fd12e08faf8bd77cfdd0f124d002499cd5e",
    "focused_checks_sha256": "17302c5e331d18fd0cb3696f3e3d96f7f6872a8f02b19073f2386617ff35a9e6",
    "pre_readback_checker_sha256": "35ca4504cb161bd5780c0d9f6e7df53eea72b51e7fd0a8486dcea62d92bc5c65",
    "pre_readback_snapshot_manifest_sha256": "b29535c353d75d929502b7d4ba683dd7feed8ae046a1e94f0e23060f3a9ebac8",
}

IMMUTABLE_INPUTS = (
    ("baseline", BASELINE_PATH, EXPECTED["baseline_sha256"]),
    ("local_b_candidate", LOCAL_B_NPZ, EXPECTED["local_b_sha256"]),
    ("local_b_checks", LOCAL_B_CHECKS, EXPECTED["local_b_checks_sha256"]),
    ("refinement_source", OLD_REFINEMENT_SOURCE, EXPECTED["refinement_source_sha256"]),
    ("case_freeze", OLD_CASES, EXPECTED["case_freeze_sha256"]),
    ("saved_run02_candidate", SAVED_CANDIDATE_NPZ, EXPECTED["saved_candidate_sha256"]),
)
MAX_WALL_CLOCK_SECONDS = 120.0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_pin(name: str, path: Path, expected: str) -> dict[str, Any]:
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"pinned SHA mismatch for {name}: {actual}")
    return {"name": name, "path": str(path), "sha256": actual, "bytes": path.stat().st_size}


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {name: archive[name].copy() for name in archive.files}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def main() -> int:
    started_at = datetime.now(timezone.utc).isoformat()
    started_clock = time.perf_counter()
    output_dir_created = False
    receipt: dict[str, Any] = {
        "completion_label": "READBACK_PENDING",
        "status": "RUNNING",
        "run_id": "run02_v2bugfix",
        "saved_candidate_sha256": EXPECTED["saved_candidate_sha256"],
        "original_run02_receipt_sha256": EXPECTED["run02_receipt_sha256"],
        "candidate_generation_invoked": False,
        "candidate_main_invoked": False,
        "cad_or_solver_invoked": False,
        "automatic_retry": False,
        "started_at_utc": started_at,
        "execution_cap_seconds": MAX_WALL_CLOCK_SECONDS,
    }
    try:
        resolved_root = REVIEW_ROOT.resolve()
        output_dir = OUTPUT_DIR.resolve()
        if resolved_root not in output_dir.parents:
            raise RuntimeError("completion output path escaped the authorized review directory")
        if OUTPUT_DIR.exists():
            raise RuntimeError(f"completion_review already exists; refusing reuse: {OUTPUT_DIR}")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
        output_dir_created = True
        write_json(OUTPUT_DIR / "readback_receipt.json", receipt)

        checker_path = HERE / "focused_checks.py"
        candidate_source = HERE / "candidate.py"
        freeze_pin = file_pin("v2bugfix_source_freeze", SOURCE_FREEZE_PATH, EXPECTED["run02_source_freeze_sha256"])
        candidate_source_pin = file_pin("frozen_candidate_source", candidate_source, EXPECTED["candidate_source_sha256"])
        checker_pin = file_pin("narrowly_fixed_focused_checks", checker_path, EXPECTED["focused_checks_sha256"])
        snapshot_checker = PRE_READBACK_SNAPSHOT / "focused_checks.py"
        snapshot_freeze = PRE_READBACK_SNAPSHOT / "SOURCE_FREEZE.json"
        snapshot_checker_pin = file_pin("pre_readback_checker_snapshot", snapshot_checker, EXPECTED["pre_readback_checker_sha256"])
        snapshot_freeze_pin = file_pin("pre_readback_source_freeze_snapshot", snapshot_freeze, EXPECTED["run02_source_freeze_sha256"])
        snapshot_manifest_pin = file_pin(
            "pre_readback_snapshot_manifest", PRE_READBACK_SNAPSHOT_MANIFEST,
            EXPECTED["pre_readback_snapshot_manifest_sha256"],
        )

        prior_receipt_pin = file_pin("original_run02_failure_receipt", ORIGINAL_RUN02_RECEIPT, EXPECTED["run02_receipt_sha256"])
        original_receipt = json.loads(ORIGINAL_RUN02_RECEIPT.read_text(encoding="utf-8"))
        if original_receipt.get("status") != "UNKNOWN_OR_FAIL":
            raise RuntimeError("original run02 failure receipt no longer has its preserved failure status")
        if original_receipt.get("error") != "name 'COLOR_FINITE_SAMPLE_TOL' is not defined":
            raise RuntimeError("original run02 failure receipt differs from the preserved readback NameError")

        input_pins = [file_pin(name, path, expected) for name, path, expected in IMMUTABLE_INPUTS]
        baseline = load_npz(BASELINE_PATH)
        local_b = load_npz(LOCAL_B_NPZ)
        saved_candidate = load_npz(SAVED_CANDIDATE_NPZ)
        local_b_checks = json.loads(LOCAL_B_CHECKS.read_text(encoding="utf-8"))
        cases = json.loads(OLD_CASES.read_text(encoding="utf-8"))

        sys.path.insert(0, str(HERE))
        from focused_checks import render_saved_meshes, run_focused_checks
        from focused_checks import summarize_triangle_quality

        checks = run_focused_checks(baseline, local_b, saved_candidate, cases, local_b_checks)
        if time.perf_counter() - started_clock > MAX_WALL_CLOCK_SECONDS:
            raise TimeoutError("readback exceeded the fixed 120-second completion cap")
        checks_path = OUTPUT_DIR / "checks.json"
        write_json(checks_path, checks)

        input_quality = summarize_triangle_quality(
            np.asarray(local_b["vertices_relief_xyz_mm"], dtype=np.float64),
            np.asarray(local_b["faces"], dtype=np.int64),
        )
        candidate_quality = summarize_triangle_quality(
            np.asarray(saved_candidate["vertices_relief_xyz_mm"], dtype=np.float64),
            np.asarray(saved_candidate["faces"], dtype=np.int64),
        )

        os.environ["MPLCONFIGDIR"] = str(OUTPUT_DIR / ".matplotlib")
        render_saved_meshes(saved_candidate, OUTPUT_DIR, cases)
        if time.perf_counter() - started_clock > MAX_WALL_CLOCK_SECONDS:
            raise TimeoutError("saved-mesh rendering exceeded the fixed 120-second completion cap")

        focused_pass = bool(checks.get("focused_checks_pass", False))
        completion_label = (
            "RECOVERED_CANDIDATE_READBACK_FROM_FAILED_RUN"
            if focused_pass
            else "RECOVERED_READBACK_WITH_DISCREPANCY"
        )
        candidate_manifest = {
            "completion_label": completion_label,
            "candidate_id": "global_mesh_quality_candidate_20261005",
            "source_run_id": "run02_v2bugfix",
            "source_run_status": "UNKNOWN_OR_FAIL; preserved and not rewritten",
            "saved_candidate_sha256": EXPECTED["saved_candidate_sha256"],
            "original_run02_receipt_sha256": prior_receipt_pin["sha256"],
            "source_freeze_sha256": freeze_pin["sha256"],
            "source_pins": [
                candidate_source_pin, checker_pin, snapshot_checker_pin, snapshot_freeze_pin,
                snapshot_manifest_pin,
            ],
            "input_pins": input_pins,
            "baseline_quality": input_quality,
            "candidate_quality": candidate_quality,
            "input_floor_quality": checks["input_floor_quality"],
            "candidate_floor_quality": checks["candidate_floor_quality"],
            "candidate_nonfloor_quality": checks["candidate_nonfloor_quality"],
            "focused_checks_pass": focused_pass,
            "floor_patch_parent_count_max": checks["floor_patch_lineage"]["per_output_face_patch_records_max"],
            "quarantine_status": "EXPERIMENT_ONLY_NOT_FOR_PRODUCTION",
            "legacy_reader_compatibility": "UNKNOWN; schema-v1 aliases are absent",
            "interpretation": "Saved analytic fixture triangle geometry only; not tet quality, solver h, mechanics, fracture, or material validation.",
            "candidate_generation_invoked": False,
            "candidate_main_invoked": False,
            "cad_or_solver_invoked": False,
            "automatic_retry": False,
            "execution_cap_seconds": MAX_WALL_CLOCK_SECONDS,
            "pngs": {
                name: {"sha256": sha256_file(OUTPUT_DIR / name), "bytes": (OUTPUT_DIR / name).stat().st_size}
                for name in ("global_equal_aspect_actual_mesh.png", "floor_equal_aspect_actual_mesh.png")
            },
        }
        write_json(OUTPUT_DIR / "completion_manifest.json", candidate_manifest)
        finished_at = datetime.now(timezone.utc).isoformat()
        original_receipt_sha_after = sha256_file(ORIGINAL_RUN02_RECEIPT)
        candidate_sha_after = sha256_file(SAVED_CANDIDATE_NPZ)
        if original_receipt_sha_after != EXPECTED["run02_receipt_sha256"]:
            raise RuntimeError("original run02 failure receipt changed during readback")
        if candidate_sha_after != EXPECTED["saved_candidate_sha256"]:
            raise RuntimeError("saved run02 candidate NPZ changed during readback")
        receipt.update({
            "completion_label": completion_label,
            "status": "READBACK_COMPLETE",
            "focused_checks_pass": focused_pass,
            "candidate_generation_invoked": False,
            "candidate_main_invoked": False,
            "cad_or_solver_invoked": False,
            "original_run02_receipt_sha256_after": original_receipt_sha_after,
            "saved_candidate_sha256_after": candidate_sha_after,
            "checks_sha256": sha256_file(checks_path),
            "completion_manifest_sha256": sha256_file(OUTPUT_DIR / "completion_manifest.json"),
            "finished_at_utc": finished_at,
            "elapsed_seconds": time.perf_counter() - started_clock,
            "automatic_retry": False,
        })
        write_json(OUTPUT_DIR / "readback_receipt.json", receipt)
        print(json.dumps({"completion_label": completion_label, "focused_checks_pass": focused_pass}, sort_keys=True))
        return 0 if focused_pass else 1
    except Exception as exc:
        receipt.update({
            "completion_label": "READBACK_DISCREPANCY",
            "status": "UNKNOWN_OR_FAIL",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": time.perf_counter() - started_clock,
            "candidate_generation_invoked": False,
            "candidate_main_invoked": False,
            "cad_or_solver_invoked": False,
            "automatic_retry": False,
        })
        if output_dir_created:
            write_json(OUTPUT_DIR / "readback_receipt.json", receipt)
        print(json.dumps({"completion_label": "READBACK_DISCREPANCY", "error": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
