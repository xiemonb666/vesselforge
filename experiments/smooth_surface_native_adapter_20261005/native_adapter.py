"""Source-only-gated adapter for one frozen meridian candidate.

Default invocation is plan-only. Native CadQuery/OCP work requires a matching
root decision, exact frozen input hashes, and a one-use run id under this
experiment's tmp directory. This adapter never fits or interpolates curves.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
import traceback
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping


sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2].resolve()
VF_SOURCE_ROOT = REPO_ROOT / "vesselforge" / "src"
if not (VF_SOURCE_ROOT / "vesselforge").is_dir():
    raise RuntimeError(f"ADAPTER_REPOSITORY_ROOT_INVALID:{REPO_ROOT}")
if str(VF_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(VF_SOURCE_ROOT))
TMP = HERE / "tmp"
FROZEN_INPUTS_PATH = TMP / "FROZEN_CANDIDATE_INPUTS.json"
APPROVAL_PATH = TMP / "ROOT_NATIVE_CAD_APPROVAL.json"
EXPECTED_INPUT_STATUS = "FROZEN_INPUTS_MATH_ACCEPTED_WAITING_FOR_ROOT_REVIEW"
EXPECTED_MATH_STATUS = "PURE_MATH_TARGETS_MET_FINITE_ONLY_WITH_EXACT_INNER_BASE_CERTIFICATE"
EXPECTED_SAMPLED_CURVATURE_TARGET_MM = 1.25
IDENTITY_TOLERANCE_MM = 1e-7
APPROVAL_SCHEMA = "vesselforge.native_adapter.root_approval/1"
REVIEW_SCHEMA = "vesselforge.native_adapter.root_review/1"
FROZEN_FILE_ROLES = {
    "wrapper_source",
    "candidate_case",
    "plot_source",
    "design_note",
    "review_budget",
    "parent_math_source",
    "parent_case",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _adapter_sha256() -> str:
    return _sha256(Path(__file__).resolve())


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path.name}")
    return value


def _repo_file(value: Any, label: str) -> Path:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{label}_PATH_MISSING")
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError(f"{label}_PATH_MUST_BE_REPOSITORY_RELATIVE")
    path = (REPO_ROOT / relative).resolve(strict=True)
    if not path.is_file() or not path.is_relative_to(REPO_ROOT):
        raise ValueError(f"{label}_PATH_OUTSIDE_REPOSITORY_OR_NOT_FILE")
    return path


def _require_sha256(value: Any, label: str) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{label}_SHA256_INVALID")
    return value


def _parse_freeze_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})\s+(.+)", line.strip())
        if match is None:
            continue
        digest, relative_path = match.groups()
        if relative_path in entries:
            raise ValueError("FROZEN_MANIFEST_DUPLICATE_PATH")
        entries[relative_path] = digest
    if set(entries.values()) == set():
        raise ValueError("FROZEN_MANIFEST_HAS_NO_SHA256_ENTRIES")
    return entries


def _validate_math_acceptance_report(
    report: Mapping[str, Any],
    files_by_role: Mapping[str, Path],
    report_sha256: str,
) -> None:
    if report.get("schema") != "vesselforge.smooth_surface_single_inner_fairing.math_diagnostics/0.1.0":
        raise ValueError("FROZEN_MATH_REPORT_SCHEMA_UNSUPPORTED")
    if (
        report.get("status") != EXPECTED_MATH_STATUS
        or report.get("parent_diagnostic_status") != "PURE_MATH_TARGETS_MET_FINITE_ONLY"
    ):
        raise ValueError("FROZEN_MATH_REPORT_STATUS_NOT_ACCEPTED")
    provenance = report.get("source_provenance")
    expected_provenance = {
        "wrapper_source_sha256": _sha256(files_by_role["wrapper_source"]),
        "parent_v2_math_source_sha256": _sha256(files_by_role["parent_math_source"]),
        "parent_v2_fixed_case_sha256": _sha256(files_by_role["parent_case"]),
        "candidate_fixed_case_sha256": _sha256(files_by_role["candidate_case"]),
    }
    if not isinstance(provenance, Mapping):
        raise ValueError("FROZEN_MATH_REPORT_SOURCE_PROVENANCE_MISSING")
    if any(provenance.get(key) != expected for key, expected in expected_provenance.items()):
        raise ValueError("FROZEN_MATH_REPORT_SOURCE_PROVENANCE_MISMATCH")
    if provenance.get("geometry_engine_imported") is not False or report.get("cad_or_step_run") is not False:
        raise ValueError("FROZEN_MATH_REPORT_CAD_SCOPE_INVALID")
    if report.get("all_non_axis_c2_exact") is not True or report.get("all_exact_control_constraints_pass") is not True:
        raise ValueError("FROZEN_MATH_REPORT_EXACT_GEOMETRY_CHECK_FAILED")

    control = report.get("control_polygon_constraints")
    if not isinstance(control, Mapping):
        raise ValueError("FROZEN_MATH_REPORT_CONTROL_CONSTRAINTS_MISSING")
    if control.get("all_outer_side_base_monotone_exact") is not True:
        raise ValueError("FROZEN_MATH_REPORT_OUTER_MONOTONICITY_FAILED")
    if control.get("inner_side_control_radii_positive_exact") is not True:
        raise ValueError("FROZEN_MATH_REPORT_INNER_RADII_NOT_POSITIVE")
    if control.get("paired_z_controls_identical_exact") is not True:
        raise ValueError("FROZEN_MATH_REPORT_PAIRED_Z_MISMATCH")
    if control.get("rim_gap_transition_matches_declared_exact") is not True:
        raise ValueError("FROZEN_MATH_REPORT_RIM_GAP_MISMATCH")
    if control.get("section_closed_endpoint_exact") is not True or control.get("all_adjoining_section_positions_exact") is not True:
        raise ValueError("FROZEN_MATH_REPORT_SECTION_CLOSURE_INVALID")
    if control.get("signed_section_area_positive_exact") is not True:
        raise ValueError("FROZEN_MATH_REPORT_SECTION_ORIENTATION_INVALID")
    if control.get("simple_nonselfintersecting_section_proved") is not False:
        raise ValueError("FROZEN_MATH_REPORT_FULL_SECTION_SCOPE_CHANGED")
    lip = control.get("lip")
    inner = control.get("inner_base_fairing")
    if not isinstance(lip, Mapping) or lip.get("regular_convex_one_turn_proved_exact") is not True:
        raise ValueError("FROZEN_MATH_REPORT_LIP_EXACT_CERTIFICATE_FAILED")
    if not isinstance(inner, Mapping) or inner.get("monotone_exact") is not True:
        raise ValueError("FROZEN_MATH_REPORT_INNER_BASE_MONOTONICITY_FAILED")

    certificate = report.get("inner_base_fairing_exact_convexity_certificate")
    if not isinstance(certificate, Mapping):
        raise ValueError("FROZEN_MATH_REPORT_INNER_BASE_CERTIFICATE_MISSING")
    if certificate.get("degree") != 5 or certificate.get("parameter_width_exact") != "4/5":
        raise ValueError("FROZEN_MATH_REPORT_INNER_BASE_DEFINITION_MISMATCH")
    for key in (
        "regular_exact",
        "radial_strictly_decreasing_exact",
        "z_nonincreasing_exact",
        "same_nonzero_curvature_sign_exact",
        "convex_no_inflection_regular_arc_proved_exact",
        "simple_arc_proved_by_strict_radius_monotonicity_exact",
        "all_sampled_derivatives_finite_and_non_degenerate",
        "sampled_curvature_target_pass",
        "exact_geometry_and_sampled_target_pass",
    ):
        if certificate.get(key) is not True:
            raise ValueError(f"FROZEN_MATH_REPORT_INNER_BASE_CERTIFICATE_FAILED:{key}")
    target = certificate.get("sampled_curvature_target_mm")
    minimum = certificate.get("minimum_sampled_curvature_radius_mm")
    if (
        type(target) not in (int, float)
        or isinstance(target, bool)
        or not math.isfinite(float(target))
        or float(target) != EXPECTED_SAMPLED_CURVATURE_TARGET_MM
        or type(minimum) not in (int, float)
        or isinstance(minimum, bool)
        or not math.isfinite(float(minimum))
        or float(minimum) < float(target)
    ):
        raise ValueError("FROZEN_MATH_REPORT_INNER_BASE_SAMPLED_RADIUS_INVALID")

    scope = report.get("scope")
    if (
        not isinstance(scope, Mapping)
        or scope.get("global_minimum_normal_wall") != "UNKNOWN"
        or scope.get("radial_gap_is_normal_wall_thickness") is not False
        or scope.get("cad_or_step_validation") != "NOT_RUN"
        or report.get("global_minimum_normal_wall") != "UNKNOWN"
        or report.get("physical_or_style_validation") != "NOT_VALIDATED"
    ):
        raise ValueError("FROZEN_MATH_REPORT_SCOPE_CLAIMS_INVALID")
    if type(report_sha256) is not str or len(report_sha256) != 64:
        raise ValueError("FROZEN_MATH_REPORT_HASH_INVALID")


def _resolve_frozen_inputs(record: Mapping[str, Any]) -> dict[str, Any]:
    if record.get("schema") != "vesselforge.native_adapter.frozen_inputs/1":
        raise ValueError("FROZEN_INPUTS_SCHEMA_UNSUPPORTED")
    if record.get("status") != EXPECTED_INPUT_STATUS:
        raise ValueError("FROZEN_CANDIDATE_MATH_ACCEPTED_WAITING_FOR_ROOT_REVIEW")
    target = record.get("expected_sampled_curvature_target_mm")
    if (
        type(target) not in (int, float)
        or isinstance(target, bool)
        or float(target) != EXPECTED_SAMPLED_CURVATURE_TARGET_MM
    ):
        raise ValueError("FROZEN_INPUTS_CURVATURE_TARGET_NOT_PINNED")
    frozen_files = record.get("frozen_files")
    if not isinstance(frozen_files, list) or len(frozen_files) != len(FROZEN_FILE_ROLES):
        raise ValueError("FROZEN_CANDIDATE_FILES_INVALID")
    files_by_role: dict[str, Path] = {}
    sha_by_role: dict[str, str] = {}
    manifest_expected: dict[str, str] = {}
    for row in frozen_files:
        if not isinstance(row, Mapping) or set(row) != {"role", "path", "sha256"}:
            raise ValueError("FROZEN_CANDIDATE_FILE_ENTRY_INVALID")
        role = row.get("role")
        if type(role) is not str or role not in FROZEN_FILE_ROLES or role in files_by_role:
            raise ValueError("FROZEN_CANDIDATE_FILE_ROLE_INVALID")
        path = _repo_file(row.get("path"), role.upper())
        digest = _require_sha256(row.get("sha256"), role.upper())
        if _sha256(path) != digest:
            raise ValueError(f"FROZEN_CANDIDATE_FILE_HASH_MISMATCH:{role}")
        files_by_role[role] = path
        sha_by_role[role] = digest
        manifest_expected[str(path.relative_to(REPO_ROOT)).replace("\\", "/")] = digest
    if set(files_by_role) != FROZEN_FILE_ROLES:
        raise ValueError("FROZEN_CANDIDATE_FILE_ROLE_SET_MISMATCH")

    freeze_manifest_path = _repo_file(record.get("freeze_manifest_path"), "FREEZE_MANIFEST")
    freeze_manifest_sha = _require_sha256(record.get("freeze_manifest_sha256"), "FREEZE_MANIFEST")
    if _sha256(freeze_manifest_path) != freeze_manifest_sha:
        raise ValueError("FROZEN_MANIFEST_HASH_MISMATCH")
    if _parse_freeze_manifest(freeze_manifest_path) != manifest_expected:
        raise ValueError("FROZEN_MANIFEST_FILE_SET_OR_HASH_MISMATCH")

    wrapper_dir = files_by_role["wrapper_source"].parent
    if files_by_role["candidate_case"] != wrapper_dir / "fixed_case_beaker_single_inner_fairing_v1.json":
        raise ValueError("WRAPPER_CANDIDATE_CASE_BINDING_MISMATCH")
    parent_dir = wrapper_dir.parent / "smooth_surface_coupled_design_20261005"
    if (
        files_by_role["parent_math_source"] != parent_dir / "coupled_profile_math.py"
        or files_by_role["parent_case"] != parent_dir / "fixed_case_beaker_coupled_v2.json"
    ):
        raise ValueError("WRAPPER_PARENT_DEPENDENCY_BINDING_MISMATCH")

    math_report_path = _repo_file(record.get("math_diagnostics_report_path"), "MATH_DIAGNOSTICS_REPORT")
    math_report_sha = _require_sha256(record.get("math_diagnostics_report_sha256"), "MATH_DIAGNOSTICS_REPORT")
    if _sha256(math_report_path) != math_report_sha:
        raise ValueError("FROZEN_MATH_REPORT_HASH_MISMATCH")
    math_report = _read_json(math_report_path)
    _validate_math_acceptance_report(math_report, files_by_role, math_report_sha)
    accepted_scope = record.get("accepted_math_scope")
    certificate = math_report["inner_base_fairing_exact_convexity_certificate"]
    if (
        not isinstance(accepted_scope, Mapping)
        or accepted_scope.get("math_diagnostics_status") != math_report["status"]
        or accepted_scope.get("inner_base_minimum_sampled_curvature_radius_mm")
        != certificate["minimum_sampled_curvature_radius_mm"]
        or accepted_scope.get("inner_base_exact_regular_convex_arc") is not True
        or accepted_scope.get("full_section_simple_nonselfintersection_proved") is not False
        or accepted_scope.get("normal_wall_status") != "UNKNOWN"
        or accepted_scope.get("style_material_physics_status") != "NOT_VALIDATED"
        or accepted_scope.get("cad_step_status") != "NOT_RUN"
        or record.get("native_cad_status") != "NOT_AUTHORIZED_PENDING_ROOT_ADAPTER_REVIEW"
        or type(record.get("native_normal_rays")) is not int
        or record.get("native_normal_rays") != 0
        or type(record.get("mesh_generations")) is not int
        or record.get("mesh_generations") != 0
        or type(record.get("solver_runs")) is not int
        or record.get("solver_runs") != 0
        or type(record.get("retries")) is not int
        or record.get("retries") != 0
    ):
        raise ValueError("FROZEN_INPUTS_MATH_OR_NATIVE_SCOPE_MISMATCH")

    api = record.get("api")
    if not isinstance(api, Mapping):
        raise ValueError("FROZEN_CANDIDATE_API_MISSING")
    for key in (
        "case_loader",
        "builder",
        "ordered_section_key",
        "controls_attribute",
        "exact_c2_report",
        "monotonicity_report",
        "signed_area_twice",
    ):
        if type(api.get(key)) is not str or not api[key]:
            raise ValueError(f"FROZEN_CANDIDATE_API_INVALID:{key}")
    expected_api = {
        "case_loader": "load_case",
        "builder": "profile.build_model",
        "ordered_section_key": "ordered_section",
        "controls_attribute": "controls",
        "exact_c2_report": "profile._exact_c2_report",
        "monotonicity_report": "profile._monotonicity_report",
        "signed_area_twice": "profile._exact_section_signed_area_twice",
    }
    if dict(api) != expected_api:
        raise ValueError("FROZEN_CANDIDATE_API_NOT_APPROVED")
    if record.get("required_true_report_paths") != [
        "all_outer_side_base_monotone_exact",
        "lip.regular_convex_one_turn_proved_exact",
        "inner_side_control_radii_positive_exact",
        "paired_z_controls_identical_exact",
        "rim_gap_transition_matches_declared_exact",
        "inner_base_fairing.monotone_exact",
    ]:
        raise ValueError("FROZEN_CANDIDATE_REQUIRED_PREDICATES_NOT_PINNED")
    return {
        "record": dict(record),
        "files_by_role": files_by_role,
        "sha256_by_role": sha_by_role,
        "wrapper_path": files_by_role["wrapper_source"],
        "case_path": files_by_role["candidate_case"],
        "wrapper_sha256": sha_by_role["wrapper_source"],
        "case_sha256": sha_by_role["candidate_case"],
        "freeze_manifest_path": freeze_manifest_path,
        "freeze_manifest_sha256": freeze_manifest_sha,
        "math_report_path": math_report_path,
        "math_report_sha256": math_report_sha,
        "math_report": math_report,
        "api": dict(api),
    }


def _load_candidate_module(path: Path, source_sha256: str) -> Any:
    module_name = f"_vf_frozen_candidate_{source_sha256[:16]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError("FROZEN_CANDIDATE_MODULE_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _resolve_dotted_attribute(root: Any, dotted_path: Any, label: str) -> Any:
    if type(dotted_path) is not str or not dotted_path:
        raise ValueError(f"FROZEN_CANDIDATE_API_INVALID:{label}")
    parts = dotted_path.split(".")
    if any(
        re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) is None
        or part.startswith("__")
        or part.endswith("__")
        for part in parts
    ):
        raise ValueError(f"FROZEN_CANDIDATE_API_PATH_INVALID:{label}")
    current = root
    for part in parts:
        try:
            current = getattr(current, part)
        except AttributeError as exc:
            raise ValueError(f"FROZEN_CANDIDATE_API_PATH_UNRESOLVED:{label}:{dotted_path}") from exc
    return current


def _get_path(value: Mapping[str, Any], dotted_path: str) -> Any:
    current: Any = value
    for component in dotted_path.split("."):
        if not isinstance(current, Mapping) or component not in current:
            raise ValueError(f"REQUIRED_MATH_PREDICATE_MISSING:{dotted_path}")
        current = current[component]
    return current


def _validate_exact_candidate(inputs: Mapping[str, Any]) -> dict[str, Any]:
    expected_snapshot = dict(inputs["sha256_by_role"])
    expected_snapshot["freeze_manifest"] = inputs["freeze_manifest_sha256"]
    expected_snapshot["math_diagnostics_report"] = inputs["math_report_sha256"]
    if _input_hash_snapshot(inputs) != expected_snapshot:
        raise ValueError("FROZEN_INPUT_BYTES_CHANGED_BEFORE_NATIVE_IMPORT")
    cached_profile = sys.modules.get("coupled_profile_math")
    if cached_profile is not None:
        cached_path = Path(getattr(cached_profile, "__file__", "")).resolve()
        if cached_path != inputs["files_by_role"]["parent_math_source"]:
            raise ValueError("UNPINNED_PARENT_MATH_MODULE_ALREADY_LOADED")
        if _sha256(cached_path) != inputs["sha256_by_role"]["parent_math_source"]:
            raise ValueError("CACHED_PARENT_MATH_MODULE_HASH_MISMATCH")
    module = _load_candidate_module(inputs["wrapper_path"], inputs["wrapper_sha256"])
    expected_files = inputs["files_by_role"]
    actual_profile_path = Path(module.profile.__file__).resolve(strict=True)
    if actual_profile_path != expected_files["parent_math_source"]:
        raise ValueError("WRAPPER_IMPORTED_UNPINNED_PARENT_MATH_SOURCE")
    if Path(module.CASE_FILE).resolve(strict=True) != inputs["case_path"]:
        raise ValueError("WRAPPER_LOADED_UNPINNED_CANDIDATE_CASE")
    if Path(module.PARENT_CASE_FILE).resolve(strict=True) != expected_files["parent_case"]:
        raise ValueError("WRAPPER_LOADED_UNPINNED_PARENT_CASE")
    if Path(module.PARENT_MATH_FILE).resolve(strict=True) != expected_files["parent_math_source"]:
        raise ValueError("WRAPPER_REFERENCES_UNPINNED_PARENT_MATH_SOURCE")
    if _input_hash_snapshot(inputs) != expected_snapshot:
        raise ValueError("FROZEN_INPUT_BYTES_CHANGED_DURING_NATIVE_IMPORT")
    api = inputs["api"]
    case_loader = _resolve_dotted_attribute(module, api["case_loader"], "case_loader")
    builder = _resolve_dotted_attribute(module, api["builder"], "builder")
    c2_fn = _resolve_dotted_attribute(module, api["exact_c2_report"], "exact_c2_report")
    monotonicity_fn = _resolve_dotted_attribute(module, api["monotonicity_report"], "monotonicity_report")
    area_fn = _resolve_dotted_attribute(module, api["signed_area_twice"], "signed_area_twice")
    if not all(callable(function) for function in (case_loader, builder, c2_fn, monotonicity_fn, area_fn)):
        raise ValueError("FROZEN_CANDIDATE_API_NOT_CALLABLE")
    case = case_loader()
    if not isinstance(case, Mapping):
        raise ValueError("FROZEN_CANDIDATE_CASE_LOADER_INVALID")
    model = builder(case)
    if not isinstance(model, Mapping):
        raise ValueError("FROZEN_CANDIDATE_MODEL_INVALID")
    if not isinstance(model.get("inner_base_fairing"), (list, tuple)) or len(model["inner_base_fairing"]) != 1:
        raise ValueError("FROZEN_CANDIDATE_EXPECTED_ONE_INNER_BASE_FAIRING")

    section = model.get(api["ordered_section_key"])
    if not isinstance(section, (list, tuple)) or not section:
        raise ValueError("FROZEN_CANDIDATE_ORDERED_SECTION_INVALID")
    controls_attribute = api["controls_attribute"]
    exact_controls: list[tuple[tuple[Fraction, Fraction], ...]] = []
    for index, span in enumerate(section):
        controls = getattr(span, controls_attribute, None)
        if not isinstance(controls, (list, tuple)) or len(controls) != 6:
            raise ValueError(f"FROZEN_CANDIDATE_EXPECTED_SIX_QUINTIC_POLES:{index}")
        exact_span: list[tuple[Fraction, Fraction]] = []
        for pole in controls:
            if not isinstance(pole, (list, tuple)) or len(pole) != 2:
                raise ValueError(f"FROZEN_CANDIDATE_POLE_INVALID:{index}")
            coordinates: list[Fraction] = []
            for coordinate in pole:
                if isinstance(coordinate, Fraction):
                    coordinates.append(coordinate)
                elif type(coordinate) is int:
                    coordinates.append(Fraction(coordinate))
                else:
                    raise ValueError(f"FROZEN_CANDIDATE_POLE_NOT_EXACT_RATIONAL:{index}")
            exact_span.append((coordinates[0], coordinates[1]))
        exact_controls.append(tuple(exact_span))

    for index, (left, right) in enumerate(zip(exact_controls, exact_controls[1:])):
        if left[-1] != right[0]:
            raise ValueError(f"FROZEN_CANDIDATE_ENDPOINT_DISCONTINUITY:{index}")
    if exact_controls[-1][-1] != exact_controls[0][0]:
        raise ValueError("FROZEN_CANDIDATE_SECTION_NOT_EXACTLY_CLOSED")

    c2_rows = c2_fn(model)
    if not isinstance(c2_rows, (list, tuple)) or not c2_rows:
        raise ValueError("FROZEN_CANDIDATE_C2_REPORT_INVALID")
    if any(not isinstance(row, Mapping) or row.get("pass_exact_rational") is not True for row in c2_rows):
        raise ValueError("FROZEN_CANDIDATE_NON_AXIS_C2_CHECK_FAILED")
    monotonicity = monotonicity_fn(model, case)
    if not isinstance(monotonicity, Mapping):
        raise ValueError("FROZEN_CANDIDATE_MONOTONICITY_REPORT_INVALID")
    required_paths = inputs["record"].get("required_true_report_paths", [])
    if (
        not isinstance(required_paths, list)
        or not required_paths
        or any(type(path) is not str or not path for path in required_paths)
    ):
        raise ValueError("FROZEN_CANDIDATE_REQUIRED_PREDICATES_INVALID")
    for dotted_path in required_paths:
        if _get_path(monotonicity, dotted_path) is not True:
            raise ValueError(f"FROZEN_CANDIDATE_EXACT_PREDICATE_FAILED:{dotted_path}")
    area_twice = area_fn(section)
    if not isinstance(area_twice, Fraction) or area_twice <= 0:
        raise ValueError("FROZEN_CANDIDATE_ORIENTATION_OR_MATERIAL_AREA_INVALID")

    return {
        "module": module,
        "case": dict(case),
        "model": model,
        "section": section,
        "exact_controls": exact_controls,
        "c2_report": list(c2_rows),
        "monotonicity_report": dict(monotonicity),
        "signed_area_twice_exact": str(area_twice),
        "inner_base_math_certificate": inputs["math_report"]["inner_base_fairing_exact_convexity_certificate"],
    }


def _shape_inventory(shape: Any, brep_bounds_mm: Any) -> list[dict[str, Any]]:
    inventory = []
    for index, face in enumerate(shape.Faces()):
        center = [float(value) for value in face.Center().toTuple()]
        bounds = [float(value) for value in brep_bounds_mm(face)]
        area = float(face.Area())
        if len(center) != 3 or len(bounds) != 6 or not all(math.isfinite(value) for value in center + bounds):
            raise ValueError(f"NATIVE_FACE_INVENTORY_NONFINITE:{index}")
        if not math.isfinite(area) or area < 0.0:
            raise ValueError(f"NATIVE_FACE_AREA_INVALID:{index}")
        inventory.append(
            {
                "index_zero_based": index,
                "geom_type": face.geomType(),
                "center_mm": center,
                "bbox_mm": bounds,
                "area_mm2": area,
            }
        )
    if not inventory:
        raise ValueError("NATIVE_FACE_INVENTORY_EMPTY")
    return inventory


def _validate_solid(shape: Any, phase: str) -> None:
    solids = shape.Solids()
    shells = shape.Shells()
    if (
        shape.isNull()
        or not shape.isValid()
        or len(solids) != 1
        or len(shells) != 1
        or not all(bool(shell.Closed()) for shell in shells)
        or not solids[0].isValid()
        or not math.isfinite(float(shape.Volume()))
        or float(shape.Volume()) <= 0.0
    ):
        raise ValueError(f"{phase}_NOT_ONE_VALID_CLOSED_POSITIVE_SOLID")


def _bounds_delta(before: list[float], after: list[float]) -> float:
    if len(before) != 6 or len(after) != 6:
        raise ValueError("GEOMETRY_ONLY_BOUNDS_SHAPE_INVALID")
    if not all(math.isfinite(value) for value in before + after):
        raise ValueError("GEOMETRY_ONLY_BOUNDS_NONFINITE")
    return max(abs(left - right) for left, right in zip(before, after))


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _check_approval(inputs: Mapping[str, Any], input_record_sha256: str) -> tuple[dict[str, Any], Path]:
    approval = _read_json(APPROVAL_PATH)
    if approval.get("schema") != APPROVAL_SCHEMA or approval.get("status") != "APPROVED_ONE_NATIVE_CAD_PILOT":
        raise ValueError("ROOT_NATIVE_CAD_APPROVAL_NOT_GRANTED")
    if approval.get("adapter_sha256") != _adapter_sha256():
        raise ValueError("ROOT_APPROVAL_ADAPTER_HASH_MISMATCH")
    if approval.get("frozen_inputs_record_sha256") != input_record_sha256:
        raise ValueError("ROOT_APPROVAL_INPUT_RECORD_HASH_MISMATCH")
    for approval_key, input_key in (
        ("wrapper_source_sha256", "wrapper_source"),
        ("candidate_case_sha256", "candidate_case"),
        ("parent_math_source_sha256", "parent_math_source"),
        ("parent_case_sha256", "parent_case"),
    ):
        if approval.get(approval_key) != inputs["sha256_by_role"][input_key]:
            raise ValueError("ROOT_APPROVAL_CANDIDATE_HASH_MISMATCH")
    if approval.get("freeze_manifest_sha256") != inputs["freeze_manifest_sha256"]:
        raise ValueError("ROOT_APPROVAL_FREEZE_MANIFEST_HASH_MISMATCH")
    if approval.get("math_diagnostics_report_sha256") != inputs["math_report_sha256"]:
        raise ValueError("ROOT_APPROVAL_MATH_REPORT_HASH_MISMATCH")
    accepted_minimum = inputs["math_report"]["inner_base_fairing_exact_convexity_certificate"]["minimum_sampled_curvature_radius_mm"]
    if (
        approval.get("math_diagnostics_status") != EXPECTED_MATH_STATUS
        or approval.get("inner_base_sampled_curvature_minimum_mm") != accepted_minimum
        or approval.get("inner_base_sampled_curvature_target_mm") != EXPECTED_SAMPLED_CURVATURE_TARGET_MM
        or approval.get("full_section_simple_nonselfintersection_proved") is not False
        or approval.get("global_minimum_normal_wall_status") != "UNKNOWN"
        or approval.get("physics_status") != "NOT_ASSESSED"
    ):
        raise ValueError("ROOT_APPROVAL_CLAIM_SCOPE_INVALID")
    approved_file_hashes = approval.get("frozen_file_sha256_by_role")
    if not isinstance(approved_file_hashes, Mapping) or dict(approved_file_hashes) != inputs["sha256_by_role"]:
        raise ValueError("ROOT_APPROVAL_FROZEN_FILE_SET_MISMATCH")
    run_id = approval.get("run_id")
    if type(run_id) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,47}", run_id) is None:
        raise ValueError("ROOT_APPROVAL_RUN_ID_INVALID")
    budget = approval.get("budget")
    expected_budget = {
        "native_body_builds": 1,
        "step_exports": 1,
        "step_imports": 1,
        "normal_rays": 0,
        "mesh_generations": 0,
        "solver_runs": 0,
        "retries": 0,
    }
    if not isinstance(budget, Mapping) or set(budget) != set(expected_budget):
        raise ValueError("ROOT_APPROVAL_BUDGET_INVALID")
    if any(type(budget[key]) is not int or budget[key] != value for key, value in expected_budget.items()):
        raise ValueError("ROOT_APPROVAL_BUDGET_OUTSIDE_FIXED_PILOT")
    review_path = _repo_file(approval.get("review_record_path"), "ROOT_REVIEW_RECORD")
    review_sha = _require_sha256(approval.get("review_record_sha256"), "ROOT_REVIEW_RECORD")
    if _sha256(review_path) != review_sha:
        raise ValueError("ROOT_REVIEW_RECORD_HASH_MISMATCH")
    review = _read_json(review_path)
    if (
        review.get("schema") != REVIEW_SCHEMA
        or review.get("decision") != "APPROVE_ONE_NATIVE_CAD_PILOT"
        or review.get("wrapper_source_sha256") != inputs["sha256_by_role"]["wrapper_source"]
        or review.get("candidate_case_sha256") != inputs["sha256_by_role"]["candidate_case"]
        or review.get("parent_math_source_sha256") != inputs["sha256_by_role"]["parent_math_source"]
        or review.get("parent_case_sha256") != inputs["sha256_by_role"]["parent_case"]
        or review.get("freeze_manifest_sha256") != inputs["freeze_manifest_sha256"]
        or review.get("math_diagnostics_report_sha256") != inputs["math_report_sha256"]
        or review.get("adapter_sha256") != _adapter_sha256()
        or review.get("math_diagnostics_status") != EXPECTED_MATH_STATUS
        or review.get("inner_base_sampled_curvature_minimum_mm") != accepted_minimum
        or review.get("inner_base_sampled_curvature_target_mm") != EXPECTED_SAMPLED_CURVATURE_TARGET_MM
        or review.get("full_section_simple_nonselfintersection_proved") is not False
        or review.get("global_minimum_normal_wall_status") != "UNKNOWN"
    ):
        raise ValueError("ROOT_REVIEW_RECORD_DOES_NOT_APPROVE_FROZEN_CANDIDATE")
    return approval, review_path


def _input_hash_snapshot(inputs: Mapping[str, Any]) -> dict[str, str]:
    snapshot = {role: _sha256(path) for role, path in inputs["files_by_role"].items()}
    snapshot["freeze_manifest"] = _sha256(inputs["freeze_manifest_path"])
    snapshot["math_diagnostics_report"] = _sha256(inputs["math_report_path"])
    return snapshot


def _build_and_roundtrip(candidate: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    import OCP
    import cadquery as cq

    from vesselforge.brep_identity import (
        BREP_FACE_BOUNDS_POLICY_ID,
        brep_bounds_mm,
        brep_face_bounds_policy_record,
    )
    from vesselforge.wall_mesh_binding import _check_face_inventory

    edges = []
    for index, controls in enumerate(candidate["exact_controls"]):
        points = []
        for radius, z in controls:
            point = cq.Vector(float(radius), 0.0, float(z))
            if not all(math.isfinite(value) for value in point.toTuple()):
                raise ValueError(f"NATIVE_CONTROL_POLE_NONFINITE:{index}")
            points.append(point)
        edge = cq.Edge.makeBezier(points)
        if not edge.isValid():
            raise ValueError(f"NATIVE_QUINTIC_BEZIER_EDGE_INVALID:{index}")
        edges.append(edge)

    wire = cq.Wire.assembleEdges(edges)
    if not wire.isValid() or not wire.IsClosed():
        raise ValueError("NATIVE_EXACT_POLE_CHAIN_DID_NOT_FORM_CLOSED_WIRE")
    face = cq.Face.makeFromWires(wire)
    if not face.isValid() or not math.isfinite(float(face.Area())) or float(face.Area()) <= 0.0:
        raise ValueError("NATIVE_CLOSED_SECTION_DID_NOT_FORM_POSITIVE_FACE")

    body = (
        cq.Workplane("XZ")
        .newObject([wire])
        .toPending()
        .revolve(360.0, (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), combine=False)
        .val()
    )
    _validate_solid(body, "NATIVE_REVOLVE")
    body_bounds = [float(value) for value in brep_bounds_mm(body)]
    native_inventory = _shape_inventory(body, brep_bounds_mm)

    step_path = output_dir / "candidate.step"
    cq.exporters.export(body, str(step_path), exportType="STEP")
    if not step_path.is_file() or step_path.stat().st_size == 0:
        raise ValueError("STEP_EXPORT_MISSING_OR_EMPTY")
    step_sha256 = _sha256(step_path)
    canonical = cq.importers.importStep(str(step_path)).val()
    _validate_solid(canonical, "STEP_ROUNDTRIP")
    canonical_bounds = [float(value) for value in brep_bounds_mm(canonical)]
    bbox_delta = _bounds_delta(body_bounds, canonical_bounds)
    if bbox_delta > IDENTITY_TOLERANCE_MM:
        raise ValueError("STEP_ROUNDTRIP_GEOMETRY_ONLY_BOUNDS_MISMATCH")

    policy = brep_face_bounds_policy_record()
    if policy.get("policy_id") != BREP_FACE_BOUNDS_POLICY_ID:
        raise ValueError("SHARED_BREP_BOUNDS_POLICY_UNEXPECTED")
    _check_face_inventory(canonical, native_inventory, IDENTITY_TOLERANCE_MM, policy)

    return {
        "cadquery_version": str(cq.__version__),
        "ocp_module_version": str(getattr(OCP, "__version__", "")) or None,
        "step_sha256": step_sha256,
        "step_bytes": step_path.stat().st_size,
        "solid_count": len(canonical.Solids()),
        "shell_count": len(canonical.Shells()),
        "all_shells_closed": all(bool(shell.Closed()) for shell in canonical.Shells()),
        "native_face_count": len(native_inventory),
        "step_face_count": len(canonical.Faces()),
        "geometry_only_bounds_policy": policy,
        "native_bbox_mm_xmin_xmax_ymin_ymax_zmin_zmax": body_bounds,
        "step_bbox_mm_xmin_xmax_ymin_ymax_zmin_zmax": canonical_bounds,
        "max_step_bbox_delta_mm": bbox_delta,
        "face_inventory_checker": "vesselforge.wall_mesh_binding._check_face_inventory",
        "face_inventory_status": "PASS_AT_1E-7_MM",
        "identity_tolerance_mm": IDENTITY_TOLERANCE_MM,
        "normal_wall_status": "UNKNOWN_NOT_RUN_NO_APPROVED_PRODUCTION_BREP_RAY_CHECKER",
        "wall_mesh_binding_status": "NOT_RUN_NO_FORGE_ASSET_OR_PARENT_MESH_PACKAGE",
        "global_self_intersection_status": "UNKNOWN_NOT_ESTABLISHED_BY_TOPOLOGY_OR_STEP_ROUNDTRIP",
        "physics_status": "NOT_ASSESSED",
        "radial_control_gap_is_normal_wall_thickness": False,
        "nominal_rim_z_is_bbox_max": False,
    }


def _run_once(inputs: Mapping[str, Any], approval: Mapping[str, Any], review_path: Path) -> dict[str, Any]:
    run_id = approval["run_id"]
    output_dir = TMP / "runs" / run_id
    if output_dir.exists():
        raise ValueError("APPROVED_RUN_ID_ALREADY_EXISTS_NO_RETRY_OR_OVERWRITE")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir()

    receipt: dict[str, Any] = {
        "schema": "vesselforge.native_adapter.run_receipt/1",
        "status": "RUNNING",
        "run_id": run_id,
        "adapter_sha256_before": _adapter_sha256(),
        "frozen_file_sha256_before": _input_hash_snapshot(inputs),
        "freeze_manifest_sha256": inputs["freeze_manifest_sha256"],
        "math_diagnostics_report_sha256": inputs["math_report_sha256"],
        "root_review_record_path": str(review_path.relative_to(REPO_ROOT)),
        "root_review_record_sha256": approval["review_record_sha256"],
        "budget": dict(approval["budget"]),
        "units": "mm",
        "curve_construction": "exact degree-5 Bezier control poles passed directly to CadQuery Edge.makeBezier; no fitting/interpolation",
        "revolve_axis": "global Z, via Workplane XZ local Y axis",
        "regular_c2_scope": "frozen math source exact non-axis joins only; revolution-axis singular joins are excluded from regular-C2 claims",
        "identity_tolerance_mm": IDENTITY_TOLERANCE_MM,
        "normal_wall_status": "UNKNOWN_NOT_RUN_NO_APPROVED_PRODUCTION_BREP_RAY_CHECKER",
        "math_review_status": EXPECTED_MATH_STATUS,
        "inner_base_sampled_curvature_minimum_mm": inputs["math_report"]["inner_base_fairing_exact_convexity_certificate"]["minimum_sampled_curvature_radius_mm"],
        "inner_base_sampled_curvature_target_mm": EXPECTED_SAMPLED_CURVATURE_TARGET_MM,
        "full_section_simple_nonselfintersection_proved": False,
        "global_minimum_normal_wall_status": "UNKNOWN",
    }
    try:
        candidate = _validate_exact_candidate(inputs)
        native = _build_and_roundtrip(candidate, output_dir)
        receipt.update(
            {
                "status": "PASS_NATIVE_TOPOLOGY_STEP_AND_FACE_IDENTITY_ONLY",
                "frozen_file_sha256_after": _input_hash_snapshot(inputs),
                "adapter_sha256_after": _adapter_sha256(),
                "exact_non_axis_c2_rows": candidate["c2_report"],
                "exact_meridian_orientation_area_twice": candidate["signed_area_twice_exact"],
                "required_exact_monotonicity_report": candidate["monotonicity_report"],
                "native_step": native,
            }
        )
        if (
            receipt["adapter_sha256_before"] != receipt["adapter_sha256_after"]
            or receipt["frozen_file_sha256_before"] != receipt["frozen_file_sha256_after"]
        ):
            receipt["status"] = "UNKNOWN_INPUT_BYTES_CHANGED_DURING_RUN"
    except Exception as exc:  # Preserve one bounded attempt and its first failure.
        receipt.update(
            {
                "status": "FAIL_OR_UNKNOWN_NATIVE_PILOT",
                "failure_type": type(exc).__name__,
                "failure_reason": str(exc),
                "traceback": traceback.format_exc(),
                "adapter_sha256_after": _adapter_sha256(),
                "frozen_file_sha256_after": _input_hash_snapshot(inputs),
            }
        )
    _write_json(output_dir / "run_receipt.json", receipt)
    return receipt


def _plan() -> dict[str, Any]:
    plan: dict[str, Any] = {
        "status": "SOURCE_ONLY_MATH_ACCEPTED_WAITING_FOR_ROOT_ADAPTER_REVIEW",
        "adapter_path": str(Path(__file__).resolve()),
        "adapter_sha256": _adapter_sha256(),
        "frozen_inputs_record_path": str(FROZEN_INPUTS_PATH),
        "root_approval_path": str(APPROVAL_PATH),
        "native_execution_in_this_invocation": False,
        "fixed_future_pilot_budget": {
            "native_body_builds": 1,
            "step_exports": 1,
            "step_imports": 1,
            "normal_rays": 0,
            "mesh_generations": 0,
            "solver_runs": 0,
            "retries": 0,
        },
        "identity_tolerance_mm": IDENTITY_TOLERANCE_MM,
        "normal_wall_status": "UNKNOWN_NOT_RUN",
        "physics_status": "NOT_ASSESSED",
    }
    record = _read_json(FROZEN_INPUTS_PATH)
    plan["frozen_inputs_record_sha256"] = _sha256(FROZEN_INPUTS_PATH)
    plan["candidate_status"] = record.get("status")
    if record.get("status") == EXPECTED_INPUT_STATUS:
        inputs = _resolve_frozen_inputs(record)
        plan.update(
            {
                "status": "SOURCE_ONLY_READY_FOR_ROOT_ADAPTER_REVIEW",
                "wrapper_source_path": str(inputs["wrapper_path"]),
                "wrapper_source_sha256": inputs["wrapper_sha256"],
                "case_file_path": str(inputs["case_path"]),
                "case_sha256": inputs["case_sha256"],
                "frozen_file_sha256_by_role": inputs["sha256_by_role"],
                "freeze_manifest_path": str(inputs["freeze_manifest_path"]),
                "freeze_manifest_sha256": inputs["freeze_manifest_sha256"],
                "math_diagnostics_report_path": str(inputs["math_report_path"]),
                "math_diagnostics_report_sha256": inputs["math_report_sha256"],
                "math_diagnostics_status": inputs["math_report"]["status"],
                "inner_base_sampled_curvature_minimum_mm": inputs["math_report"]["inner_base_fairing_exact_convexity_certificate"]["minimum_sampled_curvature_radius_mm"],
                "inner_base_sampled_curvature_target_mm": EXPECTED_SAMPLED_CURVATURE_TARGET_MM,
                "root_cad_approval_present": APPROVAL_PATH.is_file(),
            }
        )
    else:
        plan["wait_reason"] = "Frozen candidate input record is not in the math-accepted pending-root-review state."
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="requires the matching root approval file")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(_plan(), indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    try:
        record = _read_json(FROZEN_INPUTS_PATH)
        inputs_record_sha = _sha256(FROZEN_INPUTS_PATH)
        inputs = _resolve_frozen_inputs(record)
        approval, review_path = _check_approval(inputs, inputs_record_sha)
        receipt = _run_once(inputs, approval, review_path)
        print(json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False))
        return 0 if receipt.get("status") == "PASS_NATIVE_TOPOLOGY_STEP_AND_FACE_IDENTITY_ONLY" else 1
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED_BEFORE_NATIVE_RUN",
                    "reason": str(exc),
                    "native_execution_started": False,
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
