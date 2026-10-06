"""Bounded outer-profile diagnostic and PNG plan; deliberately not executed.

The caller must wait for root's explicit READY. This driver handles only the
16 rational outer spans in fixed_cases.json. It does not construct the ten
inner spans, a normal-offset curve, CAD, STEP, a mesh, or a solver result.
"""

from __future__ import annotations

import hashlib
import json
import math
from fractions import Fraction
from math import comb
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from .profile_design import Jet3, SpanJet3, degree7_controls
except ImportError:
    from profile_design import Jet3, SpanJet3, degree7_controls


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
CASE_FILE = HERE / "fixed_cases.json"
OUTPUT_ROOT = REPO_ROOT / "tmp" / "review_20261006" / "whole_body_c2_profiles_20261006" / "fixed_outer_trial"

# Eight fixed parameters per span; these same samples feed the review PNG.
PROFILE_PARAMETERS = tuple(Fraction(i, 7) for i in range(8))
BERNSTEIN_INTERVALS = (
    (Fraction(0), Fraction(1, 4)),
    (Fraction(1, 4), Fraction(1, 2)),
    (Fraction(1, 2), Fraction(3, 4)),
    (Fraction(3, 4), Fraction(1)),
)

NORMAL_PROBE_PARAMETERS = {
    "bowl": (
        ("outer_lower_body", Fraction(1, 4)),
        ("outer_lower_body", Fraction(1, 2)),
        ("outer_lower_body", Fraction(3, 4)),
        ("outer_mid_body", Fraction(1, 4)),
        ("outer_mid_body", Fraction(1, 2)),
        ("outer_mid_body", Fraction(3, 4)),
        ("outer_apex_in", Fraction(1, 2)),
        ("outer_apex_out_to_mouth", Fraction(1, 2)),
    ),
    "jar": (
        ("outer_body_to_apex", Fraction(1, 4)),
        ("outer_body_to_apex", Fraction(1, 2)),
        ("outer_body_to_apex", Fraction(3, 4)),
        ("outer_apex_to_shoulder", Fraction(1, 4)),
        ("outer_apex_to_shoulder", Fraction(1, 2)),
        ("outer_apex_to_shoulder", Fraction(3, 4)),
        ("outer_shoulder", Fraction(1, 2)),
        ("outer_neck", Fraction(1, 2)),
    ),
}


Point = tuple[Fraction, Fraction]


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _scale(a: Point, value: Fraction) -> Point:
    return (a[0] * value, a[1] * value)


def _dot(a: Point, b: Point) -> Fraction:
    return a[0] * b[0] + a[1] * b[1]


def _cross(a: Point, b: Point) -> Fraction:
    return a[0] * b[1] - a[1] * b[0]


def _eval_bezier(points: Sequence[Point], t: Fraction) -> Point:
    work = list(points)
    while len(work) > 1:
        work = [
            _add(_scale(work[i], 1 - t), _scale(work[i + 1], t))
            for i in range(len(work) - 1)
        ]
    return work[0]


def _split_bezier(
    points: Sequence[Point], t: Fraction
) -> tuple[tuple[Point, ...], tuple[Point, ...]]:
    levels: list[list[Point]] = [list(points)]
    while len(levels[-1]) > 1:
        prior = levels[-1]
        levels.append([
            _add(_scale(prior[i], 1 - t), _scale(prior[i + 1], t))
            for i in range(len(prior) - 1)
        ])
    left = tuple(level[0] for level in levels)
    right = tuple(level[-1] for level in reversed(levels))
    return left, right


def _four_fixed_subnets(points: Sequence[Point]) -> tuple[tuple[Point, ...], ...]:
    first, rest = _split_bezier(points, Fraction(1, 4))
    second, rest = _split_bezier(rest, Fraction(1, 3))
    third, rest = _split_bezier(rest, Fraction(1, 2))
    return (first, second, third, rest)


def _first_derivative_poles(points: Sequence[Point]) -> tuple[Point, ...]:
    degree = len(points) - 1
    return tuple(_scale(_sub(points[i + 1], points[i]), Fraction(degree)) for i in range(degree))


def _second_derivative_poles(points: Sequence[Point]) -> tuple[Point, ...]:
    first = _first_derivative_poles(points)
    degree = len(first) - 1
    return tuple(_scale(_sub(first[i + 1], first[i]), Fraction(degree)) for i in range(degree))


def _determinant_bernstein_coefficients(points: Sequence[Point]) -> tuple[Fraction, ...]:
    """Exact Bernstein coefficients of det(C_t,C_tt), degree 11 for degree 7."""

    first = _first_derivative_poles(points)
    second = _second_derivative_poles(points)
    degree_first = len(first) - 1
    degree_second = len(second) - 1
    degree_product = degree_first + degree_second
    coefficients: list[Fraction] = []
    for k in range(degree_product + 1):
        value = Fraction(0)
        for i, a in enumerate(first):
            j = k - i
            if 0 <= j < len(second):
                weight = Fraction(
                    comb(degree_first, i) * comb(degree_second, j),
                    comb(degree_product, k),
                )
                value += weight * _cross(a, second[j])
        coefficients.append(value)
    return tuple(coefficients)


def _curvature_upper_on_subnet(
    points: Sequence[Point],
    projection_w: Point,
    projection_norm_upper: Fraction,
) -> dict[str, Any]:
    first = _first_derivative_poles(points)
    min_projection = min(_dot(projection_w, vector) for vector in first)
    norm_sq = _dot(projection_w, projection_w)
    if projection_norm_upper <= 0 or projection_norm_upper * projection_norm_upper < norm_sq:
        return {
            "status": "INVALID_PROJECTION_NORM_UPPER",
            "min_projection": str(min_projection),
            "curvature_upper_per_mm": None,
        }
    if min_projection <= 0:
        return {
            "status": "UNKNOWN_NO_STRICT_PROJECTION_BOUND",
            "min_projection": str(min_projection),
            "curvature_upper_per_mm": None,
        }

    determinant_coefficients = _determinant_bernstein_coefficients(points)
    numerator_upper = max((abs(value) for value in determinant_coefficients), default=Fraction(0))
    speed_lower = min_projection / projection_norm_upper
    curvature_upper = (
        Fraction(0)
        if numerator_upper == 0
        else numerator_upper / (speed_lower * speed_lower * speed_lower)
    )
    return {
        "status": "RATIONAL_BOUND",
        "min_projection": str(min_projection),
        "speed_lower_local_parameter": str(speed_lower),
        "determinant_abs_upper": str(numerator_upper),
        "curvature_upper_per_mm": str(curvature_upper),
    }


def _load_case_spans(case: Mapping[str, Any]) -> list[tuple[Mapping[str, Any], SpanJet3, tuple[Point, ...]]]:
    stations = case["outer_stations"]
    result = []
    previous_end = None
    for row in case["outer_spans"]:
        start_record = stations[row["from"]]
        end_record = stations[row["to"]]
        start = Jet3.from_record(start_record)
        end = Jet3.from_record(end_record)
        if previous_end is not None and previous_end != start:
            raise ValueError(f"SHARED_C3_JET_MISMATCH:{row['semantic']}")
        span = SpanJet3(
            semantic=row["semantic"],
            parameter_length_mm=Fraction(row["h_mm"]),
            start=start,
            end=end,
        )
        controls = degree7_controls(span)
        previous_end = end
        result.append((row, span, controls))
    if len(result) != 8:
        raise ValueError(f"FIXED_CASE_OUTER_SPAN_COUNT_MISMATCH:{len(result)}")
    return result


def _analyze_span(
    case: Mapping[str, Any],
    row: Mapping[str, Any],
    controls: Sequence[Point],
    target_radius_mm: Fraction | None,
    wall_side_span_names: set[str],
) -> tuple[dict[str, Any], list[tuple[float, float]]]:
    max_radius = Fraction(case["catalog_defaults"]["max_radius_mm"])
    bbox_height = Fraction(case["candidate_bbox_height_mm"])
    rz_poles_ok = all(
        Fraction(0) <= point[0] <= max_radius
        and Fraction(0) <= point[1] <= bbox_height
        for point in controls
    )

    projection_w = tuple(Fraction(value) for value in row["projection_w"])
    projection_norm_upper = Fraction(row["projection_norm_upper"])
    interval_rows = []
    for interval, subnet in zip(BERNSTEIN_INTERVALS, _four_fixed_subnets(controls), strict=True):
        bound = _curvature_upper_on_subnet(subnet, projection_w, projection_norm_upper)
        bound["parameter_interval"] = [str(interval[0]), str(interval[1])]
        interval_rows.append(bound)

    all_intervals_bounded = all(row["status"] == "RATIONAL_BOUND" for row in interval_rows)
    curvature_upper = (
        max(Fraction(row["curvature_upper_per_mm"]) for row in interval_rows)
        if all_intervals_bounded
        else None
    )
    if target_radius_mm is None:
        curvature_target_status = "REPORT_ONLY_NO_RADIUS_TARGET"
    elif curvature_upper is None:
        curvature_target_status = "UNKNOWN_FULL_SPAN_BOUND_UNAVAILABLE"
    else:
        curvature_target_status = (
            "BOUND_PROVES_TARGET"
            if curvature_upper <= 1 / target_radius_mm
            else "UNKNOWN_BOUND_TOO_LOOSE_OR_TARGET_NOT_PROVED"
        )

    offset_status = "NOT_A_NORMAL_OFFSET_SPAN"
    if row["semantic"] in wall_side_span_names:
        offset_status = (
            "UNKNOWN_FULL_SPAN_CURVATURE_BOUND_UNAVAILABLE"
            if curvature_upper is None
            else "BOUND_PROVES_LOCAL_OFFSET_REGULARITY"
            if 3 * curvature_upper < 1
            else "UNKNOWN_BOUND_DOES_NOT_PROVE_ABS_3KAPPA_LT_1"
        )

    samples = [
        (float(point[0]), float(point[1]))
        for point in (_eval_bezier(controls, t) for t in PROFILE_PARAMETERS)
    ]
    return (
        {
            "semantic": row["semantic"],
            "region": row["region"],
            "control_pole_count": len(controls),
            "control_hull_rz_mm": {
                "r_min": str(min(point[0] for point in controls)),
                "r_max": str(max(point[0] for point in controls)),
                "z_min": str(min(point[1] for point in controls)),
                "z_max": str(max(point[1] for point in controls)),
            },
            "feature_hull_status": "BOUND_WITHIN_CASE_RADIAL_AND_HEIGHT_LIMITS" if rz_poles_ok else "FAIL_FEATURE_HULL",
            "strict_projection_w": [str(value) for value in projection_w],
            "curvature_intervals": interval_rows,
            "full_span_curvature_upper_per_mm": None if curvature_upper is None else str(curvature_upper),
            "curvature_target_radius_mm": None if target_radius_mm is None else str(target_radius_mm),
            "curvature_target_status": curvature_target_status,
            "normal_offset_status": offset_status,
            "profile_samples_rz_mm": [list(point) for point in samples],
        },
        samples,
    )


def _sample_normal_offset_point(
    controls: Sequence[Point], t: Fraction, distance_mm: float = 3.0
) -> dict[str, Any]:
    first = _first_derivative_poles(controls)
    second = _second_derivative_poles(controls)
    point = _eval_bezier(controls, t)
    d1 = _eval_bezier(first, t)
    d2 = _eval_bezier(second, t)
    dr, dz = float(d1[0]), float(d1[1])
    speed = math.hypot(dr, dz)
    if not math.isfinite(speed) or speed <= 0:
        return {"status": "UNKNOWN_NONREGULAR_OR_NONFINITE_SAMPLE", "t": str(t)}
    normal = (-dz / speed, dr / speed)
    offset = (float(point[0]) + distance_mm * normal[0], float(point[1]) + distance_mm * normal[1])
    curvature = (dr * float(d2[1]) - dz * float(d2[0])) / speed**3
    factor = 1.0 - distance_mm * curvature
    finite_payload = (dr, dz, *offset, curvature, factor, *normal)
    if not all(math.isfinite(value) for value in finite_payload):
        return {"status": "UNKNOWN_NONFINITE_OFFSET_PROBE", "t": str(t)}
    factor_status = (
        "FAIL_NONPOSITIVE_TANGENT_FACTOR_AT_PROBE"
        if factor <= 0.0
        else "FINITE_POSITIVE_TANGENT_FACTOR_AT_PROBE"
    )
    return {
        "status": "FINITE_POINT_PROBE_ONLY",
        "t": str(t),
        "outer_rz_mm": [float(point[0]), float(point[1])],
        "inward_unit_normal_rz": list(normal),
        "candidate_offset_point_rz_mm": list(offset),
        "candidate_offset_distance_mm": distance_mm,
        "sampled_signed_curvature_per_mm": curvature,
        "sampled_offset_tangent_factor": factor,
        "sampled_offset_tangent_factor_status": factor_status,
        "interpretation": "one local point probe; not an inner curve, wall certificate, or global minimum",
    }


def _target_for_region(
    region: str,
    family: str,
    target_record: Mapping[str, Any],
) -> Fraction | None:
    if region in {"base", "base_transition"}:
        return Fraction(target_record["base_and_inner_base_fairing_minimum_radius_mm"][family])
    if region == "lip_closure":
        return None
    return Fraction(target_record["body_and_shoulder_minimum_radius_mm"])


def analyze_outer_case(
    family: str,
    case: Mapping[str, Any],
    curvature_targets: Mapping[str, Any],
) -> dict[str, Any]:
    spans = _load_case_spans(case)
    wall_spans = set(case["normal_offset_side_spans"])
    rows = []
    sampled_controls: dict[str, tuple[Point, ...]] = {}
    total_profile_parameters = 0
    for row, _span, controls in spans:
        target = _target_for_region(row["region"], family, curvature_targets)
        analysis, _samples = _analyze_span(case, row, controls, target, wall_spans)
        rows.append(analysis)
        sampled_controls[row["semantic"]] = controls
        total_profile_parameters += len(PROFILE_PARAMETERS)

    probes = []
    for semantic, t in NORMAL_PROBE_PARAMETERS[family]:
        probes.append({
            "span": semantic,
            **_sample_normal_offset_point(sampled_controls[semantic], t),
        })
    return {
        "family": family,
        "scope": "fixed rational outer spans only",
        "outer_span_count": len(spans),
        "profile_parameter_evaluation_count": total_profile_parameters,
        "candidate_bbox_height_mm": case["candidate_bbox_height_mm"],
        "catalog_height_role": "mouth/body datum only",
        "fixed_features": case["fixed_features"],
        "shared_c3_jet_status": "EXACT_RATIONAL_SOURCE_JETS_MATCHED" if len(spans) == len(case["outer_spans"]) else "UNKNOWN",
        "spans": rows,
        "normal_offset_point_probe_count": len(probes),
        "normal_offset_point_probes": probes,
        "inner_profile_status": "NOT_CONSTRUCTED_SOURCE_ONLY",
        "global_minimum_wall_status": "UNKNOWN",
        "cad_or_native_geometry_status": "NOT_RUN",
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_equal_scale_profile_png(
    case_rows: Mapping[str, Mapping[str, Any]],
    output_path: Path,
    *,
    root_ready: bool,
) -> None:
    """Write one unembellished RZ source-curve plot after explicit approval."""

    if root_ready is not True:
        raise PermissionError("ROOT_READY_REQUIRED_FOR_PLOT")

    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(12, 6))
    marks = {
        "bowl": (
            ("fixed_apex", (60.0, 77.4)),
            ("mouth datum", (57.0, 90.0)),
            ("lip crest", (55.5, 92.0)),
        ),
        "jar": (
            ("fixed apex", (54.0, 62.0)),
            ("mouth datum", (26.0, 120.0)),
            ("lip crest", (24.5, 122.0)),
        ),
    }
    for axis, family in zip(axes, ("bowl", "jar"), strict=True):
        row = case_rows[family]
        for span in row["spans"]:
            points = span["profile_samples_rz_mm"]
            axis.plot(
                [point[0] for point in points],
                [point[1] for point in points],
                color="#315a7d",
                linewidth=1.6,
            )
        for label, point in marks[family]:
            axis.scatter([point[0]], [point[1]], s=20, label=label)
        axis.set_title(f"{family}: fixed outer profile source")
        axis.set_xlabel("radius r (mm)")
        axis.set_ylabel("height z (mm)")
        axis.set_aspect("equal", adjustable="box")
        axis.grid(True, linewidth=0.35, alpha=0.4)
        axis.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=8)
    figure.suptitle("Whole-body C3 meridian proposal — mathematical source, not CAD")
    figure.tight_layout(rect=(0, 0, 0.86, 0.95))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(figure)


def run_fixed_outer_source_plan(
    case_file: Path = CASE_FILE,
    output_root: Path = OUTPUT_ROOT,
    *,
    root_ready: bool = False,
) -> dict[str, Any]:
    """Source-only entry point; do not call until root sends explicit READY."""

    if root_ready is not True:
        raise PermissionError("ROOT_READY_REQUIRED_FOR_FIXED_DIAGNOSTIC")
    if case_file.resolve() != CASE_FILE.resolve():
        raise ValueError("FIXED_CASE_PATH_OVERRIDE_FORBIDDEN")
    if output_root.resolve() != OUTPUT_ROOT.resolve():
        raise ValueError("FIXED_OUTPUT_PATH_OVERRIDE_FORBIDDEN")
    expected_outputs = (
        output_root / "outer_math_diagnostic.json",
        output_root / "outer_profiles_equal_rz.png",
    )
    if any(path.exists() for path in expected_outputs):
        raise FileExistsError("FIXED_TRIAL_OUTPUT_ALREADY_EXISTS")

    source_data = json.loads(case_file.read_text(encoding="utf-8"))
    cases = source_data["cases"]
    results = {
        family: analyze_outer_case(family, cases[family], source_data["curvature_targets"])
        for family in ("bowl", "jar")
    }
    total_profile_samples = sum(
        int(result["profile_parameter_evaluation_count"]) for result in results.values()
    )
    total_offset_probes = sum(
        int(result["normal_offset_point_probe_count"]) for result in results.values()
    )
    total_outer_spans = sum(int(result["outer_span_count"]) for result in results.values())
    if total_outer_spans != 16 or total_profile_samples != 128 or total_offset_probes != 16:
        raise ValueError("FIXED_144_EVALUATION_BUDGET_MISMATCH")

    source_paths = (Path(__file__).resolve(), HERE / "profile_design.py", case_file.resolve())
    receipt = {
        "status": "PURE_MATH_OUTER_PROFILE_ONLY",
        "phase": "requires_root_READY_before_call",
        "source_sha256": {str(path): _sha256(path) for path in source_paths},
        "sample_budget": {
            "fixed_outer_spans": total_outer_spans,
            "fixed_profile_parameters": total_profile_samples,
            "fixed_normal_offset_point_probes": total_offset_probes,
            "total": total_profile_samples + total_offset_probes,
            "ceiling": 256,
        },
        "cases": results,
        "inner_profile_status": "NOT_CONSTRUCTED_SOURCE_ONLY",
        "global_minimum_wall_status": "UNKNOWN",
        "cad_step_solver_status": "NOT_RUN",
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "outer_math_diagnostic.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    save_equal_scale_profile_png(
        results,
        output_root / "outer_profiles_equal_rz.png",
        root_ready=True,
    )
    return receipt
