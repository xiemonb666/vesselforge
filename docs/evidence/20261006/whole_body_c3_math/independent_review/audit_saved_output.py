"""Read-only audit of the already-saved fixed outer diagnostic; no candidate imports."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from decimal import Decimal
from fractions import Fraction
from pathlib import Path


ROOT = Path(r"C:\Users\xiemo\Desktop\ShardForge")
CASE_PATH = ROOT / "vesselforge/experiments/whole_body_c2_profiles_20261006/fixed_cases.json"
DRIVER_PATH = ROOT / "vesselforge/experiments/whole_body_c2_profiles_20261006/diagnostic_driver_source_only.py"
MANIFEST_PATH = ROOT / "tmp/review_20261006/whole_body_c2_profiles_20261006/FREEZE_MANIFEST.json"
TRIAL = ROOT / "tmp/review_20261006/whole_body_c2_profiles_20261006/fixed_outer_trial"
DATA_PATH = TRIAL / "outer_math_diagnostic.json"
PNG_PATH = TRIAL / "outer_profiles_equal_rz.png"
EXECUTION_RECEIPT_PATH = TRIAL / "execution_receipt.json"
OUT_DIR = ROOT / "vesselforge/tmp/review_20261006/whole_body_c3_independent"

EXPECTED_HASHES = {
    CASE_PATH: "e1e9c3cf659dbc59d99a18c4b70694201518be4f3aba09a57806402e732cf95a",
    DRIVER_PATH: "d1d327f298dad639e0529edf45d4a5d4c6a6fe6b7cf7ac2773a3fcd48adb66a7",
    MANIFEST_PATH: "4905c92d580aadd0b92d861d88fb49ab2d57ce680fbdf314ad1b47f8b8be775d",
    DATA_PATH: "eb60138fc559d5a06ab2b4febf82fdc6654e6bbeab84f05f847c65934ffbbd4f",
    PNG_PATH: "118fae2c92c679fcd45409462ed6638d6d4043711ae8995513e6fe7813d58eda",
}
PROBES = {
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream, parse_float=Decimal)


def require(condition: bool, code: str) -> None:
    if not condition:
        raise AssertionError(code)


def main() -> None:
    observed_hashes = {str(path.relative_to(ROOT)): sha256(path) for path in EXPECTED_HASHES}
    for path, expected in EXPECTED_HASHES.items():
        require(observed_hashes[str(path.relative_to(ROOT))] == expected, f"HASH_MISMATCH:{path}")

    cases_source = read_json(CASE_PATH)
    result = read_json(DATA_PATH)
    execution = read_json(EXECUTION_RECEIPT_PATH)
    manifest = read_json(MANIFEST_PATH)

    require(result["status"] == "PURE_MATH_OUTER_PROFILE_ONLY", "WRONG_RESULT_STATUS")
    require(result["inner_profile_status"] == "NOT_CONSTRUCTED_SOURCE_ONLY", "INNER_SCOPE_MISMATCH")
    require(result["global_minimum_wall_status"] == "UNKNOWN", "GLOBAL_WALL_STATUS_MISMATCH")
    require(result["cad_step_solver_status"] == "NOT_RUN", "CAD_SOLVER_STATUS_MISMATCH")
    require(result["sample_budget"] == {
        "fixed_outer_spans": 16,
        "fixed_profile_parameters": 128,
        "fixed_normal_offset_point_probes": 16,
        "total": 144,
        "ceiling": 256,
    }, "SAVED_BUDGET_MISMATCH")
    require(manifest["bounded_future_run"]["total_evaluations"] == 144, "MANIFEST_BUDGET_MISMATCH")

    source_pre = execution["source_pins_pre_sha256"]
    source_post = execution["source_pins_post_sha256"]
    require(source_pre == source_post, "EXECUTION_RECEIPT_SOURCE_PIN_DRIFT")
    for path, expected in EXPECTED_HASHES.items():
        if path in (DATA_PATH, PNG_PATH):
            continue
        key = path.relative_to(ROOT).as_posix()
        require(source_pre.get(key) == expected, f"RECEIPT_PREPIN_MISMATCH:{key}")

    hull_count = Counter()
    interval_count = Counter()
    target_count = Counter()
    offset_bound_count = Counter()
    all_spans = {}
    per_case = {}
    profile_sample_counts = {}
    for family in ("bowl", "jar"):
        case = cases_source["cases"][family]
        output_case = result["cases"][family]
        rows = output_case["spans"]
        require(len(rows) == len(case["outer_spans"]) == 8, f"SPAN_COUNT:{family}")
        require(output_case["outer_span_count"] == 8, f"SAVED_SPAN_COUNT:{family}")
        require(output_case["candidate_bbox_height_mm"] == case["candidate_bbox_height_mm"], f"HEIGHT_MISMATCH:{family}")
        require(output_case["profile_parameter_evaluation_count"] == 64, f"PROFILE_SITE_COUNT:{family}")
        require(output_case["normal_offset_point_probe_count"] == 8, f"PROBE_COUNT:{family}")
        source_rows = {row["semantic"]: row for row in case["outer_spans"]}
        profile_sample_counts[family] = sum(len(row["profile_samples_rz_mm"]) for row in rows)
        require(profile_sample_counts[family] == 64, f"SAVED_PROFILE_SAMPLE_COUNT:{family}")
        for row in rows:
            semantic = row["semantic"]
            require(semantic in source_rows, f"UNBOUND_SPAN:{family}:{semantic}")
            all_spans[(family, semantic)] = row
            hull_count[row["feature_hull_status"]] += 1
            target_count[row["curvature_target_status"]] += 1
            offset_bound_count[row["normal_offset_status"]] += 1
            intervals = row["curvature_intervals"]
            require(len(intervals) == 4, f"INTERVAL_COUNT:{family}:{semantic}")
            for interval in intervals:
                interval_count[interval["status"]] += 1
                require(interval["status"] == "RATIONAL_BOUND", f"INTERVAL_NOT_BOUNDED:{family}:{semantic}")
                value = Fraction(interval["curvature_upper_per_mm"])
                require(value >= 0, f"NEGATIVE_ABS_CURVATURE_BOUND:{family}:{semantic}")
            hull = row["control_hull_rz_mm"]
            require(Fraction(hull["r_min"]) >= 0, f"NEGATIVE_R_HULL:{family}:{semantic}")
            require(Fraction(hull["r_max"]) <= Fraction(case["catalog_defaults"]["max_radius_mm"]), f"R_HULL_EXCEEDS_CATALOG:{family}:{semantic}")
            require(Fraction(hull["z_min"]) >= 0, f"NEGATIVE_Z_HULL:{family}:{semantic}")
            require(Fraction(hull["z_max"]) <= Fraction(case["candidate_bbox_height_mm"]), f"Z_HULL_EXCEEDS_CRESt:{family}:{semantic}")

        probes = output_case["normal_offset_point_probes"]
        expected = PROBES[family]
        require(len(probes) == len(expected) == 8, f"PROBE_LIST_COUNT:{family}")
        actual_probe_keys = []
        probe_results = []
        side_names = set(case["normal_offset_side_spans"])
        for probe in probes:
            semantic = probe["span"]
            t = Fraction(probe["t"])
            actual_probe_keys.append((semantic, t))
            require(semantic in side_names, f"PROBE_OUTSIDE_SIDE_SPANS:{family}:{semantic}")
            require(probe["status"] == "FINITE_POINT_PROBE_ONLY", f"PROBE_STATUS:{family}:{semantic}:{t}")
            require(probe["candidate_offset_distance_mm"] == Decimal("3.0"), f"OFFSET_DISTANCE:{family}:{semantic}:{t}")
            curvature = Fraction(probe["sampled_signed_curvature_per_mm"])
            factor = Fraction(probe["sampled_offset_tangent_factor"])
            require(abs(factor - (1 - 3 * curvature)) <= Fraction(1, 10**13), f"TANGENT_FACTOR_IDENTITY:{family}:{semantic}:{t}")
            normal = tuple(Fraction(value) for value in probe["inward_unit_normal_rz"])
            normal_norm_sq = normal[0] * normal[0] + normal[1] * normal[1]
            require(abs(normal_norm_sq - 1) <= Fraction(1, 10**13), f"NORMAL_NOT_UNIT:{family}:{semantic}:{t}")
            outer = tuple(Fraction(value) for value in probe["outer_rz_mm"])
            actual_offset = tuple(Fraction(value) for value in probe["candidate_offset_point_rz_mm"])
            predicted_offset = (outer[0] + 3 * normal[0], outer[1] + 3 * normal[1])
            require(all(abs(actual_offset[i] - predicted_offset[i]) <= Fraction(1, 10**13) for i in (0, 1)), f"OFFSET_POINT_IDENTITY:{family}:{semantic}:{t}")
            require(factor > 0, f"NONPOSITIVE_POINT_FACTOR:{family}:{semantic}:{t}")
            probe_results.append({
                "span": semantic,
                "t": str(t),
                "saved_curvature_per_mm": str(curvature),
                "saved_tangent_factor": str(factor),
                "factor_identity_verified": True,
                "normal_unit_verified": True,
                "distance_mm": "3",
            })
        require(sorted(actual_probe_keys) == sorted(expected), f"PROBE_PARAMETERS_MISMATCH:{family}")
        per_case[family] = {
            "outer_spans": len(rows),
            "profile_sites": profile_sample_counts[family],
            "point_probes": len(probes),
            "probes": probe_results,
        }

    require(hull_count == Counter({"BOUND_WITHIN_CASE_RADIAL_AND_HEIGHT_LIMITS": 16}), "HULL_STATUS_COUNTS")
    require(interval_count == Counter({"RATIONAL_BOUND": 64}), "CURVATURE_INTERVAL_COUNTS")
    require(target_count == Counter({
        "BOUND_PROVES_TARGET": 2,
        "UNKNOWN_BOUND_TOO_LOOSE_OR_TARGET_NOT_PROVED": 10,
        "REPORT_ONLY_NO_RADIUS_TARGET": 4,
    }), "CURVATURE_TARGET_COUNTS")
    non_side_offset = offset_bound_count.get("NOT_A_NORMAL_OFFSET_SPAN", 0)
    unknown_offset = sum(value for key, value in offset_bound_count.items() if key.startswith("UNKNOWN_"))
    require(
        non_side_offset == 8
        and offset_bound_count.get("BOUND_PROVES_LOCAL_OFFSET_REGULARITY", 0) == 3
        and unknown_offset == 5
        and sum(offset_bound_count.values()) == 16,
        "OFFSET_BOUND_COUNTS",
    )

    # A saved finite point strictly above 1/R is a counterexample to that radius floor.
    problematic = next(
        row for row in result["cases"]["jar"]["normal_offset_point_probes"]
        if row["span"] == "outer_apex_to_shoulder" and Fraction(row["t"]) == Fraction(1, 4)
    )
    kappa = Fraction(problematic["sampled_signed_curvature_per_mm"])
    target_radius = Fraction(cases_source["curvature_targets"]["body_and_shoulder_minimum_radius_mm"])
    require(target_radius == 9 and kappa > 1 / target_radius, "EXPECTED_POINT_COUNTEREXAMPLE_MISSING")
    local_radius = 1 / kappa
    point_counterexample = {
        "family": "jar",
        "span": "outer_apex_to_shoulder",
        "t": "1/4",
        "saved_kappa_per_mm": str(kappa),
        "radius_target_mm": str(target_radius),
        "local_radius_from_saved_probe_mm": str(float(local_radius)),
        "comparison": "KAPPA_EXCEEDS_1_OVER_9; SAVED_POINT_COUNTEREXAMPLE_TO_9_MM_RADIUS_FLOOR",
        "saved_span_target_status": all_spans[("jar", "outer_apex_to_shoulder")]["curvature_target_status"],
        "saved_offset_factor": str(problematic["sampled_offset_tangent_factor"]),
        "scope": "pointwise counterexample only; does not bound the complete span or prove global wall behavior",
    }

    summary = {
        "schema": "vesselforge.whole_body_c3_saved_readback.v1",
        "status": "PASS_SAVED_JSON_INTERNAL_ARITHMETIC_WITH_POINT_COUNTEREXAMPLE",
        "input_sha256": observed_hashes,
        "original_execution_receipt": {
            "status": execution["status"],
            "exit_code": execution["exit_code"],
            "elapsed_seconds": execution["elapsed_seconds"],
            "stdout_bytes": execution["stdout_bytes"],
            "stderr_bytes": execution["stderr_bytes"],
            "pre_post_source_pins_equal": source_pre == source_post,
        },
        "saved_output_status": {
            "top_level": result["status"],
            "global_minimum_wall": result["global_minimum_wall_status"],
            "inner_profile": result["inner_profile_status"],
            "cad_step_solver": result["cad_step_solver_status"],
        },
        "counts": {
            "hull_pass_spans": sum(hull_count.values()),
            "curvature_rational_intervals": sum(interval_count.values()),
            "curvature_interval_statuses": dict(interval_count),
            "curvature_target_statuses": dict(target_count),
            "side_span_offset_bound_statuses": dict(offset_bound_count),
            "not_a_normal_offset_span_count": non_side_offset,
            "designated_side_span_count": 8,
            "side_span_offset_bound_pass_count": 3,
            "side_span_offset_bound_unknown_count": unknown_offset,
            "point_probes": 16,
            "positive_point_tangent_factors": 16,
            "outer_profile_sites": 128,
            "total_fixed_evaluations": 144,
        },
        "per_case": per_case,
        "point_counterexample": point_counterexample,
        "interpretation": [
            "All 16 hull and 64 rational-interval statuses agree with the saved check structure; no curve was reconstructed in this readback.",
            "The eight listed offset spans split into three full-span bounds that prove local regularity and five UNKNOWN bounds.",
            "All 16 saved point factors are positive and internally satisfy factor=1-3*kappa; point probes cannot prove span-wide regularity.",
            "The jar outer_apex_to_shoulder t=1/4 saved probe has curvature greater than 1/9 per mm, directly contradicting its 9 mm minimum-radius target at that point, although the span-level saved status is UNKNOWN.",
            "Global minimum wall, section self-intersection, and physical qualification remain UNKNOWN; the inner profile is unconstructed.",
        ],
        "png_visual_readback": {
            "sha256": observed_hashes[str(PNG_PATH.relative_to(ROOT))],
            "observation": "equal-scale two-panel bowl/jar outer meridian plot; labels readable; math-source visualization only; no inner profile or CAD evidence",
        },
        "execution": "READ_ONLY_SAVED_JSON_AND_SOURCE_METADATA; NO_CURVE_CONSTRUCTOR; NO_SAMPLING; NO_CAD; NO_SOLVER",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "saved_readback.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    report = """# Saved output independent readback

Status: **PASS for the saved-array arithmetic/count review, with one pointwise radius-target counterexample.** This readback consumed the frozen JSON, fixed-case source, execution receipt and existing PNG only. It did not call the candidate, construct controls, evaluate a curve, resample, run CAD, or run a solver.

## Verified saved structure

- The diagnostic JSON and PNG match their supplied SHA-256 pins. The author receipt records rc=0, 2.147634 s, empty stdout/stderr, and identical pre/post hashes for all seven frozen inputs.
- The saved result contains 16/16 feature-hull passes and 64/64 exact rational curvature-bound interval records (four per span). The interval statuses and rational values parse consistently.
- The saved target counts are 2 `BOUND_PROVES_TARGET`, 10 `UNKNOWN_BOUND_TOO_LOOSE_OR_TARGET_NOT_PROVED`, and 4 lip `REPORT_ONLY_NO_RADIUS_TARGET`. On the eight designated side spans, 3 bounds prove local 3 mm offset regularity and 5 remain UNKNOWN.
- There are 128 outer profile sites and 16 designated point probes. Each of the 16 saved probes uses a 3 mm offset, has a unit normal and positive tangent factor, and satisfies the independent arithmetic identity `factor = 1 − 3κ` within roundoff. Each stored offset point agrees with `outer point + 3 normal` within roundoff. This verifies internal saved-value consistency, not the unrecorded curve derivatives independently.

## Pointwise counterexample to the 9 mm target

The saved jar `outer_apex_to_shoulder` probe at `t=1/4` has `κ = 0.11222216144789537 mm⁻¹`, which exceeds `1/9 mm⁻¹`; the corresponding local radius is about 8.91 mm. This is a **pointwise counterexample** to the 9 mm minimum-radius target, even though the saved span-level status is the broad `UNKNOWN_BOUND_TOO_LOOSE_OR_TARGET_NOT_PROVED`. The record should be read as target not satisfied at this probe, while the full-span curvature maximum and exact violation extent remain unknown. Its saved offset tangent factor is positive (~0.66333), a point value only.

The existing PNG was visually checked. It shows the two fixed outer meridian profiles with equal radial/height scale and readable labels. It is a plot of the sampled mathematical source, not a CAD render; no inner wall is drawn.

Global minimum wall, section nonintersection, inner profile, material/physical suitability, and full-span qualification remain UNKNOWN. The original diagnostic JSON and PNG were not modified.
"""
    (OUT_DIR / "saved_readback.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": summary["status"], "point_counterexample": point_counterexample}, ensure_ascii=False))


if __name__ == "__main__":
    main()
