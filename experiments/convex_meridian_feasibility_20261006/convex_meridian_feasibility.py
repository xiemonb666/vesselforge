"""Source-only convex feasibility prototype for semantic meridian controls.

Importing this module is inert.  A future solve requires the explicit
run_feasibility(root_ready=True) gate; this source review does not call it.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import time
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction as F
from pathlib import Path
from typing import Any, Sequence

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VF = ROOT / "vesselforge"
REVIEW = VF / "tmp" / "review_20261006" / "convex_meridian_feasibility_20261006"
PINS_PATH = REVIEW / "source_pins.json"
RESULT_PATH = REVIEW / "convex_meridian_feasibility_result.json"
RUN_STARTED_PATH = REVIEW / "run_started.json"
DRIVER_PATH = VF / "experiments" / "semantic_base_neck_bspline_20261006" / "semantic_base_neck_driver.py"
FIXED_CASE_PATH = DRIVER_PATH.with_name("fixed_cases.json")
SEED_PATH = (VF / "tmp" / "review_20261006" / "semantic_base_neck_bspline_20261006" /
             "minimum_jerk_candidate" / "semantic_minimum_jerk_result.json")
DESIGN_PATH = VF / "experiments" / "curvature_constrained_meridian_20261006" / "design_cases.json"
REFERENCE_SOURCE_PATH = (VF / "experiments" / "curvature_constrained_meridian_20261006" /
                         "curvature_constrained_meridian.py")

DRIVER_SHA256 = "038974cbbe3965f7f03f1ad0199d0aba00b56294840e411ca9a21fbde42466a3"
FIXED_CASE_SHA256 = "4e18dbeaecbf13a54a87b3f1409e1c0f7fe54c3606122a01880689d9e3a6a83c"
SEED_SHA256 = "1e882451d691430c01653617e997b115291a10996e273434b7fd9c71ab787e11"
DESIGN_SHA256 = "d1bb74bfc90de5937884854fd4e5e62c4dbf01f33e2f1f7be5dbf931ee35c8eb"
REFERENCE_SOURCE_SHA256 = "96875bb6592a6fd57ceef4dc326c35faeb3f96de16607faa816c7d3fed1e08ce"
SCIPY_VERSION = "1.18.1"
DESIGN_RADIUS = F(909, 100)
MAX_FAMILY_SECONDS = 20.0
MAX_TOTAL_SECONDS = 60.0
MAX_OUTPUT_BYTES = 8 * 1024 * 1024

@dataclass(frozen=True)
class Row:
    """One exact affine inequality: coefficients dot alpha <= rhs."""
    label: str
    coefficients: tuple[F, ...]
    rhs: F

    def value(self, alpha: Sequence[F]) -> F:
        return sum((a * x for a, x in zip(self.coefficients, alpha, strict=True)), F(0))

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _rref(matrix: Sequence[Sequence[F]], rhs: Sequence[F]) -> tuple[list[list[F]], tuple[int, ...]]:
    if not matrix or len(matrix) != len(rhs) or any(len(row) != len(matrix[0]) for row in matrix):
        raise ValueError("BAD_EXACT_EQUALITY_SHAPE")
    n = len(matrix[0])
    rows = [list(row) + [value] for row, value in zip(matrix, rhs, strict=True)]
    pivots: list[int] = []
    pivot_row = 0
    for column in range(n):
        found = next((r for r in range(pivot_row, len(rows)) if rows[r][column]), None)
        if found is None:
            continue
        rows[pivot_row], rows[found] = rows[found], rows[pivot_row]
        pivot = rows[pivot_row][column]
        rows[pivot_row] = [value / pivot for value in rows[pivot_row]]
        for r in range(len(rows)):
            if r != pivot_row and rows[r][column]:
                scale = rows[r][column]
                rows[r] = [x - scale * y for x, y in zip(rows[r], rows[pivot_row], strict=True)]
        pivots.append(column)
        pivot_row += 1
        if pivot_row == len(rows):
            break
    if any(not any(row[:n]) and row[n] for row in rows):
        raise ValueError("EXACT_EQUALITIES_INCONSISTENT")
    return rows, tuple(pivots)

def _coordinate_basis(driver: Any, case: dict[str, Any], coordinate: str,
                      seed: Sequence[tuple[F, F]]) -> tuple[tuple[tuple[F, F], ...], ...]:
    axis = 0 if coordinate == "r" else 1
    fixed = {int(i): F(value) for i, value in case["fixed_poles"][coordinate].items()}
    free = tuple(i for i in range(driver.CONTROL_COUNT) if i not in fixed)
    eqs = driver.exact_case_rows(case, coordinate)
    matrix = tuple(tuple(row[i] for i in free) for _, row, _ in eqs)
    rhs = tuple(target - sum((row[i] * value for i, value in fixed.items()), F(0))
                for _, row, target in eqs)
    reduced, pivots = _rref(matrix, rhs)
    if len(eqs) != 3 or len(pivots) != 3 or len(free) != (10 if axis == 0 else 11):
        raise ValueError("EXACT_RREF_OR_FIXED_POLE_DIMENSION_MISMATCH")
    if any(seed[i][axis] != value for i, value in fixed.items()):
        raise ValueError("ACTUAL_SEED_FIXED_POLE_MISMATCH")
    free_seed = tuple(seed[i][axis] for i in free)
    residual = tuple(target - sum((row[k] * free_seed[k] for k in range(len(free))), F(0))
                     for row, target in zip(matrix, rhs, strict=True))
    correction, correction_pivots = _rref(matrix, residual)
    if correction_pivots != pivots:
        raise ValueError("AFFINE_CORRECTION_RANK_MISMATCH")
    compatible = list(seed)
    for r, pivot in enumerate(pivots):
        pole = free[pivot]
        point = list(compatible[pole])
        point[axis] += correction[r][-1]
        compatible[pole] = (point[0], point[1])
    if any(sum((row[i] * compatible[i][axis] for i in range(driver.CONTROL_COUNT)), F(0)) != target
           for _, row, target in eqs):
        raise ValueError("EXACT_AFFINE_Q0_CORRECTION_FAILED")
    basis: list[tuple[tuple[F, F], ...]] = []
    for column in (i for i in range(len(free)) if i not in pivots):
        delta = [F(0)] * len(free)
        delta[column] = F(1)
        for r, pivot in enumerate(pivots):
            delta[pivot] = -reduced[r][column]
        full = [[F(0), F(0)] for _ in range(driver.CONTROL_COUNT)]
        for k, pole in enumerate(free):
            full[pole][axis] = delta[k]
        basis.append(tuple(map(tuple, full)))
    if len(basis) != (7 if coordinate == "r" else 8):
        raise ValueError("EXPECTED_15_TOTAL_NULLSPACE_PARAMETERS")
    return tuple(compatible), tuple(basis)

def _load_inputs() -> tuple[Any, dict[str, Any], dict[str, Any]]:
    pins = json.loads(PINS_PATH.read_text(encoding="utf-8"))
    if pins.get("implementation", {}).get("sha256") != _sha256(Path(__file__)):
        raise ValueError("IMPLEMENTATION_HASH_MISMATCH")
    expected = ((DRIVER_PATH, DRIVER_SHA256), (FIXED_CASE_PATH, FIXED_CASE_SHA256),
                (SEED_PATH, SEED_SHA256), (DESIGN_PATH, DESIGN_SHA256),
                (REFERENCE_SOURCE_PATH, REFERENCE_SOURCE_SHA256))
    if any(_sha256(path) != digest for path, digest in expected):
        raise ValueError("FROZEN_INPUT_HASH_MISMATCH")
    if importlib.metadata.version("scipy") != SCIPY_VERSION:
        raise RuntimeError("PINNED_SCIPY_METADATA_VERSION_MISMATCH")
    frozen = json.loads(FIXED_CASE_PATH.read_text(encoding="utf-8"))
    seed_data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    design = json.loads(DESIGN_PATH.read_text(encoding="utf-8"))
    if (frozen.get("schema") != "vesselforge.semantic_base_neck_bspline.fixed_cases.v1" or
            seed_data.get("source_sha256", {}).get(str(DRIVER_PATH.resolve())) != DRIVER_SHA256 or
            design.get("schema") != "vesselforge.curvature_constrained_meridian.design_cases.v1" or
            design.get("source_fixed_case_sha256") != FIXED_CASE_SHA256 or
            set(frozen.get("cases", {})) != {"bowl", "jar"} or
            set(seed_data.get("cases", {})) != {"bowl", "jar"} or
            set(design.get("cases", {})) != {"bowl", "jar"}):
        raise ValueError("INPUT_SCHEMA_OR_SEED_PROVENANCE_MISMATCH")
    proposed = design["cases"]
    for family in ("bowl", "jar"):
        expected_case = json.loads(json.dumps(frozen["cases"][family]))
        if family == "bowl":
            expected_case["apex"]["rz_mm"][1] = proposed[family]["apex"]["rz_mm"][1]
            for feature in expected_case["features"]:
                if feature["name"] == "max_radius_apex":
                    feature["rz_mm"][1] = proposed[family]["apex"]["rz_mm"][1]
            row = next(row for row in expected_case["linear_equalities"] if row["name"] == "apex_height")
            row["rhs"] = proposed[family]["apex"]["rz_mm"][1]
        if proposed[family] != expected_case:
            raise ValueError("UNAPPROVED_DESIGN_CASE_CHANGE")
    spec = importlib.util.spec_from_file_location("_frozen_semantic_meridian_driver", DRIVER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError("PINNED_DRIVER_IMPORT_UNAVAILABLE")
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    return driver, proposed, seed_data["cases"]

def _make_model(driver: Any, case: dict[str, Any],
                seed_case: dict[str, Any]) -> dict[str, Any]:
    actual = tuple((F(r), F(z)) for r, z in seed_case["control_points_rz_mm"])
    if len(actual) != driver.CONTROL_COUNT:
        raise ValueError("ACTUAL_SEED_CONTROL_COUNT_MISMATCH")
    r0, rb = _coordinate_basis(driver, case, "r", actual)
    z0, zb = _coordinate_basis(driver, case, "z", actual)
    q0 = tuple((r0[i][0], z0[i][1]) for i in range(driver.CONTROL_COUNT))
    directions = rb + zb
    extraction = driver.exact_bezier_extraction()
    q0_spans = driver._controls_to_spans(extraction, q0)
    direction_spans = tuple(driver._controls_to_spans(extraction, direction)
                            for direction in directions)
    actual_spans = driver._controls_to_spans(extraction, actual)
    references: list[tuple[F, F]] = []
    speed_floors: list[F] = []
    for i, span in enumerate(actual_spans):
        h = driver.BREAKS[i + 1] - driver.BREAKS[i]
        velocity = driver._derivative_poles(span, h, 1)
        endpoint_sum = tuple(velocity[0][a] + velocity[-1][a] for a in range(2))
        norm1 = abs(endpoint_sum[0]) + abs(endpoint_sum[1])
        if not norm1:
            raise ValueError("ACTUAL_SEED_REFERENCE_DIRECTION_UNDEFINED")
        e = (endpoint_sum[0] / norm1, endpoint_sum[1] / norm1)
        if e[0] * e[0] + e[1] * e[1] > 1:
            raise ValueError("REFERENCE_DIRECTION_L2_BOUND_FAILURE")
        chord = tuple(span[-1][a] - span[0][a] for a in range(2))
        floor = max(F(1), F(1, 2) * sum((chord[a] * e[a] for a in range(2)), F(0)) / h)
        references.append(e)
        speed_floors.append(floor)
    if len(directions) != 15 or len(references) != 12 or any(s <= 0 for s in speed_floors):
        raise ValueError("MODEL_DIMENSION_OR_POSITIVE_SPEED_FLOOR_FAILURE")
    return {"q0": q0, "directions": directions, "q0_spans": q0_spans,
            "direction_spans": direction_spans, "extraction": extraction,
            "references": tuple(references), "speed_floors": tuple(speed_floors),
            "apex_span": driver.BREAKS.index(F(case["apex"]["u"]))}

def _affine_poles(base: Sequence[Any], directions: Sequence[Sequence[Any]]) -> tuple[Any, ...]:
    return tuple((base[k], tuple(direction[k] for direction in directions))
                 for k in range(len(base)))

def _coordinate_affine(pole: Any, axis: int) -> tuple[F, tuple[F, ...]]:
    return pole[0][axis], tuple(direction[axis] for direction in pole[1])

def _add_lower(rows: list[Row], label: str, form: tuple[F, tuple[F, ...]], lower: F) -> None:
    intercept, coefficients = form
    rows.append(Row(label, tuple(-x for x in coefficients), intercept - lower))

def _add_upper(rows: list[Row], label: str, form: tuple[F, tuple[F, ...]], upper: F) -> None:
    intercept, coefficients = form
    rows.append(Row(label, coefficients, upper - intercept))

def _assemble_rows(driver: Any, case: dict[str, Any], model: dict[str, Any]) -> list[Row]:
    rows: list[Row] = []
    max_r, mouth_z = F(case["max_outer_radius_mm"]), F(case["mouth_z_mm"])
    for i, q0_span in enumerate(model["q0_spans"]):
        h = driver.BREAKS[i + 1] - driver.BREAKS[i]
        span_dirs = tuple(spans[i] for spans in model["direction_spans"])
        poles = _affine_poles(q0_span, span_dirs)
        for k, pole in enumerate(poles):
            _add_lower(rows, f"bbox.r.lower.s{i}.p{k}", _coordinate_affine(pole, 0), F(0))
            _add_upper(rows, f"bbox.r.upper.s{i}.p{k}", _coordinate_affine(pole, 0), max_r)
            _add_lower(rows, f"bbox.z.lower.s{i}.p{k}", _coordinate_affine(pole, 1), F(0))
            _add_upper(rows, f"bbox.z.upper.s{i}.p{k}", _coordinate_affine(pole, 1), mouth_z)
        base_v = driver._derivative_poles(q0_span, h, 1)
        direction_v = tuple(driver._derivative_poles(span, h, 1) for span in span_dirs)
        velocity = _affine_poles(base_v, direction_v)
        sign = F(1) if i < model["apex_span"] else F(-1)
        for k, pole in enumerate(velocity):
            _add_lower(rows, f"monotone.z.s{i}.p{k}", _coordinate_affine(pole, 1), F(0))
            radial = _coordinate_affine(pole, 0)
            if sign > 0:
                _add_lower(rows, f"monotone.r.s{i}.p{k}", radial, F(0))
            else:
                _add_upper(rows, f"monotone.r.s{i}.p{k}", radial, F(0))
            e = model["references"][i]
            intercept = sum((e[a] * pole[0][a] for a in range(2)), F(0))
            coefficients = tuple(sum((e[a] * pole[1][j][a] for a in range(2)), F(0))
                                 for j in range(15))
            _add_lower(rows, f"regularity.projection.s{i}.p{k}",
                       (intercept, coefficients), model["speed_floors"][i])
        if 1 <= i <= 10:
            base_a = driver._derivative_poles(q0_span, h, 2)
            direction_a = tuple(driver._derivative_poles(span, h, 2) for span in span_dirs)
            acceleration = _affine_poles(base_a, direction_a)
            bound = model["speed_floors"][i] ** 2 / DESIGN_RADIUS
            for k, pole in enumerate(acceleration):
                ar, az = (_coordinate_affine(pole, axis) for axis in range(2))
                for sr in (-1, 1):
                    for sz in (-1, 1):
                        intercept = sr * ar[0] + sz * az[0]
                        coefficients = tuple(sr * ar[1][j] + sz * az[1][j] for j in range(15))
                        _add_upper(rows, f"curvature.L1.s{i}.p{k}.{sr}.{sz}",
                                   (intercept, coefficients), bound)
    return rows

def _controls(q0: Sequence[tuple[F, F]], directions: Sequence[Sequence[tuple[F, F]]],
              alpha: Sequence[F]) -> tuple[tuple[F, F], ...]:
    return tuple(tuple(q0[i][axis] +
                       sum((directions[j][i][axis] * alpha[j] for j in range(15)), F(0))
                       for axis in range(2)) for i in range(17))

def _exact_audit(driver: Any, case: dict[str, Any], model: dict[str, Any],
                 rows: Sequence[Row], alpha: Sequence[F]) -> dict[str, Any]:
    references = tuple({"span": i, "e_rz_exact": tuple(map(str, e)),
                        "speed_floor_mm_per_global_u_exact": str(floor)}
                       for i, (e, floor) in enumerate(zip(model["references"],
                                                          model["speed_floors"], strict=True)))
    if len(alpha) != 15:
        return {"status": "EXACT_ALPHA_DIMENSION_FAILURE",
                "alpha_exact_decimal_fraction": tuple(map(str, alpha)),
                "control_points_rz_mm": None, "fixed_reference_direction_speed_floor": references,
                "exact_linear_violation_count": None, "worst_exact_linear_violations": ()}
    controls = _controls(model["q0"], model["directions"], alpha)
    margins = tuple((row.rhs - row.value(alpha), row) for row in rows)
    violations = tuple((margin, row) for margin, row in margins if margin < 0)
    preserved = {"alpha_exact_decimal_fraction": tuple(map(str, alpha)), "control_points_rz_mm": tuple(tuple(map(str, p)) for p in controls),
                 "fixed_reference_direction_speed_floor": references,
                 "exact_linear_violation_count": len(violations),
                 "worst_exact_linear_violations": tuple(
                     {"label": row.label, "margin_exact": str(margin)}
                     for margin, row in sorted(violations, key=lambda item: item[0])[:10])}
    if violations:
        return {"status": "EXACT_LINEAR_RECHECK_FAILED",
                "all_linear_rows_exact": False, **preserved}
    geometry = driver.certify_controls(case, controls, model["extraction"])
    spans = driver._controls_to_spans(model["extraction"], controls)
    proof_rows = []
    for i, span in enumerate(spans):
        h = driver.BREAKS[i + 1] - driver.BREAKS[i]
        velocities = driver._derivative_poles(span, h, 1)
        e, floor = model["references"][i], model["speed_floors"][i]
        projections = tuple(sum((e[a] * v[a] for a in range(2)), F(0)) for v in velocities)
        item: dict[str, Any] = {
            "span": i, "e_rz_exact": tuple(map(str, e)),
            "speed_floor_mm_per_global_u_exact": str(floor),
            "minimum_projected_velocity_exact": str(min(projections)),
            "projection_pass": min(projections) >= floor,
            "whole_span_regular_by_projection": min(projections) >= floor > 0,
        }
        if 1 <= i <= 10:
            accelerations = driver._derivative_poles(span, h, 2)
            maximum_l1 = max(abs(a[0]) + abs(a[1]) for a in accelerations)
            bound = floor * floor / DESIGN_RADIUS
            item.update({"maximum_acceleration_l1_exact": str(maximum_l1),
                         "acceleration_l1_bound_exact": str(bound),
                         "curvature_radius_lower_bound_mm": str(DESIGN_RADIUS),
                         "full_span_curvature_proof": maximum_l1 <= bound})
        else:
            item["curvature_scope"] = "STRAIGHT_BASE_OR_NECK_EXCLUDED_FROM_ACCELERATION_BOUND"
        proof_rows.append(item)
    exact_ok = (geometry["all_features_exact"] and geometry["all_C4"] and
                geometry["all_hulls_proved"] and geometry["all_spans_regular_proved"] and
                geometry["straight_meridian_exclusions_proved"] and geometry["all_strict_point_checks_pass"] and
                all(row["z_derivative_poles_nonnegative"] and
                    row["radial_direction_poles_match_apex"] for row in geometry["spans"]) and
                all(row["whole_span_regular_by_projection"] for row in proof_rows) and
                all(row.get("full_span_curvature_proof", True) for row in proof_rows))
    return {"status": "EXACT_CONVEX_FEASIBILITY_CANDIDATE" if exact_ok else "EXACT_RECHECK_NOT_PASSED",
            **preserved, "all_linear_rows_exact": True, "geometry_certificate": geometry,
            "independent_full_span_L1_projection_proof": tuple(proof_rows),
            "P_R_certificate_scope": {
                "radius_mm": "9",
                "per_screen_span_status": tuple(
                    {"span": i, "status": geometry["spans"][i]["radius_9mm_status"],
                     "coefficients_exact": geometry["spans"][i]["P_R_degree24_coefficients"]}
                    for i in case["curvature_screen_span_indices_zero_based"]),
                "policy": "reported_independently; UNKNOWN does not invalidate the separate exact 9.09 mm L1/projection proof"
            }}

def _solve_one(driver: Any, family: str, case: dict[str, Any],
               seed_case: dict[str, Any], call_deadline: float) -> dict[str, Any]:
    family_started = time.monotonic()
    model = _make_model(driver, case, seed_case)
    rows = _assemble_rows(driver, case, model)
    remaining = min(MAX_FAMILY_SECONDS - (time.monotonic() - family_started),
                    call_deadline - time.monotonic())
    if remaining <= 0:
        return {"family": family, "status": "BUDGET_EXPIRED_BEFORE_LP",
                "constraint_rows": len(rows)}
    from scipy.optimize import linprog

    aub = [list(map(float, row.coefficients)) + [0.0] * 15 for row in rows]
    bub = [float(row.rhs) for row in rows]
    for j in range(15):
        positive = [0.0] * 30
        positive[j], positive[15 + j] = 1.0, -1.0
        negative = [0.0] * 30
        negative[j], negative[15 + j] = -1.0, -1.0
        aub.extend((positive, negative))
        bub.extend((0.0, 0.0))
    objective = [0.0] * 15 + [1.0] * 15
    solved = linprog(objective, A_ub=aub, b_ub=bub,
                     bounds=[(None, None)] * 15 + [(0.0, None)] * 15,
                     method="highs", options={"time_limit": remaining})
    elapsed = time.monotonic() - family_started
    record: dict[str, Any] = {
        "family": family, "solver": "scipy.optimize.linprog(method='highs')",
        "solver_status": int(solved.status), "solver_message": str(solved.message),
        "solver_success": bool(solved.success), "family_elapsed_seconds": elapsed,
        "constraint_rows": len(rows), "absolute_value_epigraph_variables": 15,
        "one_lp_attempt": True}
    if not solved.success or solved.x is None:
        record["status"] = "LP_DID_NOT_RETURN_CANDIDATE_INFEASIBILITY_NOT_PROVED"
        return record
    alpha = tuple(F(Decimal(str(float(x)))) for x in solved.x[:15])
    audit = _exact_audit(driver, case, model, rows, alpha)
    record.update({"status": audit["status"], "objective_sum_abs_alpha_exact": str(sum(map(abs, alpha), F(0))),
                   "audit": audit})
    return record

def run_feasibility(*, root_ready: bool = False) -> dict[str, Any]:
    """Future one-shot entry point. This source-only turn does not call it."""
    if root_ready is not True:
        return {"status": "NOT_RUN_ROOT_READY_FALSE", "case_authorized": False}
    pins = json.loads(PINS_PATH.read_text(encoding="utf-8"))
    if pins.get("case_authorized") is not True:
        return {"status": "NOT_RUN_CASE_UNAUTHORIZED", "case_authorized": False}
    if RESULT_PATH.exists():
        raise ValueError("RESULT_PATH_ALREADY_EXISTS")
    REVIEW.mkdir(parents=True, exist_ok=True)
    try:
        with RUN_STARTED_PATH.open("x", encoding="utf-8") as marker:
            marker.write(json.dumps({
                "schema": "vesselforge.convex_meridian_feasibility.run_started.v1",
                "implementation_sha256": _sha256(Path(__file__)),
                "case_authorized": True,
                "started_unix_seconds": time.time()}, sort_keys=True))
    except FileExistsError as exc:
        raise ValueError("RUN_ALREADY_STARTED_MARKER_EXISTS") from exc
    started = time.monotonic()
    deadline = started + MAX_TOTAL_SECONDS
    driver, cases, seeds = _load_inputs()
    families = {}
    for family in ("bowl", "jar"):
        if time.monotonic() >= deadline:
            families[family] = {"status": "SHARED_BUDGET_EXPIRED"}
            continue
        families[family] = _solve_one(driver, family, cases[family], seeds[family], deadline)
    payload = {
        "schema": "vesselforge.convex_meridian_feasibility.result.v1",
        "case_authorized": True,
        "status": "SOURCE_IMPLEMENTATION_RESULT_NOT_PHYSICS_READY",
        "solver": "one scipy.optimize.linprog(method='highs') attempt per family",
        "radius_design_mm": str(DESIGN_RADIUS),
        "per_family_limit_seconds": MAX_FAMILY_SECONDS,
        "shared_limit_seconds": MAX_TOTAL_SECONDS,
        "families": families, "elapsed_seconds": time.monotonic() - started,
        "wall_inner_lip_style_material": "NOT_COMPUTED",
        "novelty": "novelty_unconfirmed", "physics_readiness": "NOT_PHYSICS_READY"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) >= MAX_OUTPUT_BYTES:
        raise ValueError("RESULT_EXCEEDS_8_MIB")
    RESULT_PATH.write_bytes(encoded)
    return payload

if __name__ == "__main__":
    raise SystemExit("Use run_feasibility(root_ready=True) only after explicit case authorization.")
