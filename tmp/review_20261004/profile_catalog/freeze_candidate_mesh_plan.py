"""Freeze the exact profile inputs and runner sources before OCC generation."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import cadquery
import matplotlib
import numpy

ROOT = Path(r"C:\Users\xiemo\Desktop\ShardForge")
REVIEW = ROOT / "vesselforge" / "tmp" / "review_20261004" / "profile_catalog"
PYTHON = ROOT / "third_party" / "vesselforge-runtime" / "venv" / "Scripts" / "python.exe"
sys.path.insert(0, str(ROOT / "vesselforge" / "src"))
from vesselforge.profile_catalog import PROFILE_CATALOG_VERSION, build_profile  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> int:
    profiles = []
    for family in ("bowl", "beaker", "jar"):
        profile = build_profile(family)
        record = {
            "family": profile.family,
            "parameters": profile.parameters,
            "parameter_ranges_mm": profile.parameter_ranges_mm,
            "parameter_sources": profile.parameter_sources,
            "outer_profile_mm": [[r, z] for r, z in profile.outer_profile_mm],
            "inner_profile_mm": [[r, z] for r, z in profile.inner_profile_mm],
            "closed_material_section_mm": [[r, z] for r, z in profile.closed_material_section_mm],
            "geometry_only_qualification": profile.geometry_only_qualification,
        }
        record["profile_sha256"] = canonical_sha256(record)
        profiles.append(record)
    inputs = {
        "schema": "vesselforge.profile_catalog.frozen_mesh_inputs/0.1.0",
        "profile_catalog_schema": PROFILE_CATALOG_VERSION,
        "units": {"length": "mm"},
        "families_in_execution_order": ["bowl", "beaker", "jar"],
        "profiles": profiles,
        "operation": {
            "one_OCC_revolve_per_family": True,
            "linear_deflection_mm": 0.5,
            "angular_tolerance_rad": 0.2,
            "purpose": "coarse vessel form preview only",
            "qualification_exclusions": ["thin walls", "curvature", "solver readiness", "real vessel match", "physical properties"],
            "solver_used": False,
        },
    }
    inputs_path = REVIEW / "mesh_inputs.json"
    inputs_path.write_text(json.dumps(inputs, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    source_files = (
        "vesselforge/src/vesselforge/profile_catalog.py",
        "vesselforge/src/vesselforge/geometry.py",
        "vesselforge/tests/test_profile_catalog.py",
        "vesselforge/pyproject.toml",
        "vesselforge/tmp/review_20261004/profile_catalog/generate_candidate_meshes.py",
        "vesselforge/tmp/review_20261004/profile_catalog/run_candidate_meshes.ps1",
        "vesselforge/tmp/review_20261004/profile_catalog/freeze_candidate_mesh_plan.py",
        "vesselforge/tmp/review_20261004/profile_catalog/run_freeze_candidate_mesh_plan.ps1",
        "third_party/vesselforge-runtime/venv/Scripts/python.exe",
    )
    locked_sources = {relative: sha256(ROOT / relative) for relative in source_files}
    runner_invocation = {
        "shell": "PowerShell",
        "script": "vesselforge/tmp/review_20261004/profile_catalog/run_candidate_meshes.ps1",
        "child_executable": str(PYTHON),
        "child_argv": [str(REVIEW / "generate_candidate_meshes.py")],
        "working_directory": str(ROOT),
    }
    receipt = {
        "schema": "vesselforge.profile_catalog.mesh_preflight_receipt/0.1.0",
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "working_directory": str(ROOT),
        "runner_invocation": runner_invocation,
        "locked_inputs_path": str(inputs_path),
        "locked_inputs_sha256": sha256(inputs_path),
        "locked_source_sha256": locked_sources,
        "runtime": {
            "python_version": sys.version,
            "cadquery_version": cadquery.__version__,
            "numpy_version": numpy.__version__,
            "matplotlib_version": matplotlib.__version__,
            "platform": platform.platform(),
            "python_executable_sha256": locked_sources[
                "third_party/vesselforge-runtime/venv/Scripts/python.exe"
            ],
        },
        "expected_outputs": [
            "vesselforge/tmp/review_20261004/profile_catalog/meshes/bowl.stl",
            "vesselforge/tmp/review_20261004/profile_catalog/meshes/beaker.stl",
            "vesselforge/tmp/review_20261004/profile_catalog/meshes/jar.stl",
            "vesselforge/tmp/review_20261004/profile_catalog/candidate_profiles_mesh.png",
            "vesselforge/tmp/review_20261004/profile_catalog/candidate_meshes.json",
        ],
        "prelaunch_status": "FROZEN_BEFORE_OCC",
    }
    receipt_path = REVIEW / "mesh_preflight_receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": receipt["prelaunch_status"],
                "input_sha256": receipt["locked_inputs_sha256"],
                "sources": locked_sources,
                "receipt": str(receipt_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
