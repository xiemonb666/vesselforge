"""Single fixed inner-base-span candidate using the frozen v2 math engine.

This wrapper only supplies an explicit fixed case to the reviewed pure-math
module. It does not create CAD geometry or import CadQuery/OCP.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any


EXPERIMENT_DIR = Path(__file__).resolve().parent
CASE_FILE = EXPERIMENT_DIR / "fixed_case_beaker_single_inner_fairing_v1.json"
PARENT_EXPERIMENT_DIR = EXPERIMENT_DIR.parent / "smooth_surface_coupled_design_20261005"
PARENT_CASE_FILE = PARENT_EXPERIMENT_DIR / "fixed_case_beaker_coupled_v2.json"
PARENT_MATH_FILE = PARENT_EXPERIMENT_DIR / "coupled_profile_math.py"
EXPECTED_PARENT_CASE_SHA256 = "7e65d490c5cf1a5fa80d9964b1c89392c06a30290768bf00bfad03b4e757d391"
EXPECTED_PARENT_MATH_SHA256 = "4a90264b83e465af8bdb4dc7771f61ab4cb8314bc8d4d0ef540952310f3cb85b"
FIXED_CURVATURE_SAMPLES_PER_SPAN = 1001
FIXED_NORMAL_RAY_SAMPLES_PER_SPAN = 101

if str(PARENT_EXPERIMENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_EXPERIMENT_DIR))
import coupled_profile_math as profile  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_case() -> dict[str, Any]:
    actual_parent_case_sha = _sha256(PARENT_CASE_FILE)
    actual_parent_math_sha = _sha256(PARENT_MATH_FILE)
    if actual_parent_case_sha != EXPECTED_PARENT_CASE_SHA256:
        raise RuntimeError("frozen v2 parent case SHA-256 changed")
    if actual_parent_math_sha != EXPECTED_PARENT_MATH_SHA256:
        raise RuntimeError("frozen v2 pure-math source SHA-256 changed")

    parent = _read_json(PARENT_CASE_FILE)
    case = _read_json(CASE_FILE)
    basis = case.get("design_basis", {})
    if basis.get("parent_fixed_case_sha256") != actual_parent_case_sha:
        raise RuntimeError("candidate does not name the exact frozen v2 case")
    if basis.get("parent_math_source_sha256") != actual_parent_math_sha:
        raise RuntimeError("candidate does not name the exact frozen v2 math source")

    normalized = copy.deepcopy(case)
    normalized.pop("design_basis")
    for key in ("candidate_id", "status", "scope"):
        normalized[key] = parent[key]
    normalized["inner_base_fairing"] = copy.deepcopy(parent["inner_base_fairing"])
    candidate_bounds = normalized["parameter_bounds_for_this_candidate_only"]
    candidate_bounds.pop("inner_base_fairing_parameter_width_mm")
    candidate_bounds["inner_base_transition_rz_mm"] = copy.deepcopy(
        parent["parameter_bounds_for_this_candidate_only"]["inner_base_transition_rz_mm"]
    )
    normalized["acceptance_constraints"].pop("inner_base_exact_convexity")
    normalized["acceptance_constraints"].pop("inner_base_curvature_target")
    if normalized != parent:
        raise RuntimeError("candidate changed a v2 field outside the approved inner-base edit")

    stations = case["inner_base_fairing"]["stations"]
    widths = case["inner_base_fairing"]["parameter_widths"]
    if [row["name"] for row in stations] != ["inner_wall_root", "inner_floor_tangent"]:
        raise RuntimeError("the candidate must contain only the shared root and floor stations")
    if len(widths) != 1 or profile._q(widths[0]) != Fraction(4, 5):
        raise RuntimeError("the single fairing width must remain exactly 0.8")
    if stations != [parent["inner_base_fairing"]["stations"][0], parent["inner_base_fairing"]["stations"][-1]]:
        raise RuntimeError("the single-span endpoint jets must match frozen v2 exactly")
    if sum((profile._q(value) for value in parent["inner_base_fairing"]["parameter_widths"]), Fraction(0)) != Fraction(4, 5):
        raise RuntimeError("single-span width no longer equals the sum of parent widths")
    return case


def _inner_base_exact_convexity_report(model: dict[str, Any], base_report: dict[str, Any]) -> dict[str, Any]:
    spans = model["inner_base_fairing"]
    if len(spans) != 1:
        raise RuntimeError("exact inner-base certificate requires exactly one span")
    span = spans[0]
    controls = span.controls
    dr_controls = tuple(5 * (controls[index + 1][0] - controls[index][0]) for index in range(5))
    dz_controls = tuple(5 * (controls[index + 1][1] - controls[index][1]) for index in range(5))
    curvature_numerator = profile._curvature_numerator_bernstein(span)

    radial_strictly_decreasing = all(value < 0 for value in dr_controls)
    z_nonincreasing = all(value <= 0 for value in dz_controls) and any(value < 0 for value in dz_controls)
    same_nonzero_curvature_sign = (
        all(value >= 0 for value in curvature_numerator)
        or all(value <= 0 for value in curvature_numerator)
    ) and any(value != 0 for value in curvature_numerator)
    regular_exact = radial_strictly_decreasing
    convex_no_inflection_exact = regular_exact and same_nonzero_curvature_sign
    simple_arc_exact = radial_strictly_decreasing

    sample_rows = [
        row
        for row in base_report["curvature_sampling"]["spans"]
        if row["span"] == span.role
    ]
    if len(sample_rows) != 1:
        raise RuntimeError("diagnostic report is missing the single inner-base span")
    sample = sample_rows[0]
    finite_sample_target_pass = (
        sample["all_samples_finite_and_non_degenerate"]
        and (
            sample["minimum_finite_sampled_curvature_radius_mm"] is None
            or sample["minimum_finite_sampled_curvature_radius_mm"]
            >= float(base_report["curvature_sampling"]["base_lowerbody_sample_target_mm"])
        )
    )
    exact_geometry_pass = radial_strictly_decreasing and z_nonincreasing and convex_no_inflection_exact and simple_arc_exact
    return {
        "span": span.role,
        "parameter_width_exact": str(span.parameter_width),
        "degree": 5,
        "radial_derivative_bernstein_controls_exact_mm_per_local_parameter": [str(value) for value in dr_controls],
        "z_derivative_bernstein_controls_exact_mm_per_local_parameter": [str(value) for value in dz_controls],
        "radial_strictly_decreasing_exact": radial_strictly_decreasing,
        "z_nonincreasing_exact": z_nonincreasing,
        "regularity_proof": "all radial-derivative Bernstein controls are strictly negative, so r'(t)<0 over the closed parameter interval and speed cannot vanish",
        "regular_exact": regular_exact,
        "curvature_numerator_definition": "r' z'' - z' r''; its sign equals signed curvature because speed cubed is positive",
        "curvature_numerator_bernstein_coefficients_exact": [str(value) for value in curvature_numerator],
        "curvature_numerator_bernstein_signs_exact": ["+" if value > 0 else "-" if value < 0 else "0" for value in curvature_numerator],
        "same_nonzero_curvature_sign_exact": same_nonzero_curvature_sign,
        "convex_no_inflection_regular_arc_proved_exact": convex_no_inflection_exact,
        "simple_arc_proved_by_strict_radius_monotonicity_exact": simple_arc_exact,
        "sampled_curvature_samples_per_span": sample["sample_count"],
        "all_sampled_derivatives_finite_and_non_degenerate": sample["all_samples_finite_and_non_degenerate"],
        "minimum_sampled_curvature_radius_mm": sample["minimum_finite_sampled_curvature_radius_mm"],
        "sampled_curvature_target_mm": base_report["curvature_sampling"]["base_lowerbody_sample_target_mm"],
        "sampled_curvature_target_pass": finite_sample_target_pass,
        "exact_geometry_constraints_pass": exact_geometry_pass,
        "exact_geometry_and_sampled_target_pass": exact_geometry_pass and finite_sample_target_pass,
        "scope": "exact Bernstein sign and derivative-control certificates for this single section curve; sampled curvature remains finite-only and is not a whole-span radius bound",
    }


def run_candidate_diagnostics(case: dict[str, Any]) -> dict[str, Any]:
    base_report = profile.run_diagnostics(
        case,
        curvature_samples_per_span=FIXED_CURVATURE_SAMPLES_PER_SPAN,
        ray_samples_per_span=FIXED_NORMAL_RAY_SAMPLES_PER_SPAN,
    )
    model = profile.build_model(case)
    inner_certificate = _inner_base_exact_convexity_report(model, base_report)
    success = (
        base_report["status"] == "PURE_MATH_TARGETS_MET_FINITE_ONLY"
        and inner_certificate["exact_geometry_and_sampled_target_pass"]
    )
    base_report["schema"] = "vesselforge.smooth_surface_single_inner_fairing.math_diagnostics/0.1.0"
    base_report["parent_diagnostic_status"] = base_report["status"]
    base_report["status"] = (
        "PURE_MATH_TARGETS_MET_FINITE_ONLY_WITH_EXACT_INNER_BASE_CERTIFICATE"
        if success
        else "PURE_MATH_DIAGNOSTIC_NEEDS_REVIEW"
    )
    base_report["cad_or_step_run"] = False
    base_report["inner_base_fairing_exact_convexity_certificate"] = inner_certificate
    base_report["source_provenance"] = {
        "wrapper_source_sha256": _sha256(Path(__file__).resolve()),
        "parent_v2_math_source_sha256": _sha256(PARENT_MATH_FILE),
        "parent_v2_fixed_case_sha256": _sha256(PARENT_CASE_FILE),
        "candidate_fixed_case_sha256": _sha256(CASE_FILE),
        "parent_candidate_id": "beaker-coupled-fairing-math-v2",
        "geometry_engine_imported": False,
    }
    base_report["scope"] = {
        "candidate": "one fixed beaker analytic section with a single degree-5 inner base fairing span",
        "style_and_material": "UNKNOWN_NOT_VALIDATED",
        "radial_gap_is_normal_wall_thickness": False,
        "global_minimum_normal_wall": "UNKNOWN",
        "cad_or_step_validation": "NOT_RUN",
    }
    return base_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"refusing to overwrite existing output: {args.output}")
    case = load_case()
    report = run_candidate_diagnostics(case)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"candidate_id": report["candidate_id"], "status": report["status"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["status"] == "PURE_MATH_TARGETS_MET_FINITE_ONLY_WITH_EXACT_INNER_BASE_CERTIFICATE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
