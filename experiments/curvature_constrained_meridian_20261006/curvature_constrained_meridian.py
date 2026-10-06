"""One-shot constrained design plan for the frozen semantic meridian seeds.

Importing this module is inert.  The only optimizer call is behind the explicit
run_constrained_design(root_ready=True) entry point; this turn does not call it.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import math
import time
from decimal import Decimal
from fractions import Fraction as F
from math import comb
from pathlib import Path
from typing import Any, Sequence

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VF = ROOT / "vesselforge"
DRIVER_PATH = VF / "experiments" / "semantic_base_neck_bspline_20261006" / "semantic_base_neck_driver.py"
CASE_PATH = DRIVER_PATH.with_name("fixed_cases.json")
SEED_PATH = (VF / "tmp" / "review_20261006" / "semantic_base_neck_bspline_20261006" /
             "minimum_jerk_candidate" / "semantic_minimum_jerk_result.json")
OUTPUT_ROOT = VF / "tmp" / "review_20261006" / "curvature_constrained_meridian_20261006"
PINS_PATH = OUTPUT_ROOT / "source_pins.json"
RESULT_PATH = OUTPUT_ROOT / "curvature_constrained_meridian_result.json"
STARTED_PATH = OUTPUT_ROOT / "run_started.json"
DESIGN_CASE_PATH = HERE / "design_cases.json"

DRIVER_SHA256 = "038974cbbe3965f7f03f1ad0199d0aba00b56294840e411ca9a21fbde42466a3"
CASE_SHA256 = "4e18dbeaecbf13a54a87b3f1409e1c0f7fe54c3606122a01880689d9e3a6a83c"
SEED_SHA256 = "1e882451d691430c01653617e997b115291a10996e273434b7fd9c71ab787e11"
SCIPY_VERSION = "1.18.1"
DESIGN_CASE_SHA256 = "d1bb74bfc90de5937884854fd4e5e62c4dbf01f33e2f1f7be5dbf931ee35c8eb"
MAX_SECONDS = 60.0
MAX_ITERATIONS = 80
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
FINITE_DIFFERENCE_STEP_MM = 1e-4
SCALE_MM = 9.0
DESIGN_RADIUS_MM = F(909, 100)
DESIGN_RADIUS_SCALED = float(DESIGN_RADIUS_MM / F(9))


class BudgetExpired(RuntimeError):
    """The single shared optimizer deadline has been reached."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rref_with_rhs(matrix: Sequence[Sequence[F]], rhs: Sequence[F]) -> tuple[list[list[F]], tuple[int, ...]]:
    if not matrix or len(matrix) != len(rhs) or any(len(row) != len(matrix[0]) for row in matrix):
        raise ValueError("BAD_EXACT_EQUALITY_SHAPE")
    n = len(matrix[0])
    rows = [list(row) + [value] for row, value in zip(matrix, rhs, strict=True)]
    pivot_columns: list[int] = []
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
        pivot_columns.append(column)
        pivot_row += 1
        if pivot_row == len(rows):
            break
    if any(not any(row[:n]) and row[n] for row in rows):
        raise ValueError("EXACT_EQUALITIES_INCONSISTENT")
    return rows, tuple(pivot_columns)


def _load_inputs() -> tuple[Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
    pins = json.loads(PINS_PATH.read_text(encoding="utf-8"))
    if pins.get("implementation", {}).get("sha256") != _sha256(Path(__file__)):
        raise ValueError("IMPLEMENTATION_HASH_MISMATCH")
    if _sha256(DRIVER_PATH) != DRIVER_SHA256 or _sha256(CASE_PATH) != CASE_SHA256 or _sha256(SEED_PATH) != SEED_SHA256:
        raise ValueError("FROZEN_CASE_OR_SEED_HASH_MISMATCH")
    if _sha256(DESIGN_CASE_PATH) != DESIGN_CASE_SHA256:
        raise ValueError("EXPLICIT_DESIGN_CASE_HASH_MISMATCH")
    if importlib.metadata.version("scipy") != SCIPY_VERSION:
        raise RuntimeError("PINNED_SCIPY_METADATA_VERSION_MISMATCH")
    case_data = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    seed_data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    design_data = json.loads(DESIGN_CASE_PATH.read_text(encoding="utf-8"))
    if (case_data.get("schema") != "vesselforge.semantic_base_neck_bspline.fixed_cases.v1" or
            design_data.get("schema") != "vesselforge.curvature_constrained_meridian.design_cases.v1" or
            any(set(data.get("cases", {})) != {"bowl", "jar"} for data in (case_data, seed_data, design_data)) or
            seed_data.get("source_sha256", {}).get(str(DRIVER_PATH.resolve())) != DRIVER_SHA256):
        raise ValueError("INPUT_SCHEMA_OR_SEED_PROVENANCE_MISMATCH")
    spec = importlib.util.spec_from_file_location("_pinned_semantic_base_neck_driver", DRIVER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError("PINNED_DRIVER_IMPORT_UNAVAILABLE")
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    return driver, case_data["cases"], seed_data["cases"], design_data["cases"]


def _coordinate_basis(driver: Any, case: dict[str, Any], coordinate: str, seed: Sequence[tuple[F, F]]) -> Any:
    axis = 0 if coordinate == "r" else 1
    fixed = {int(i): F(value) for i, value in case["fixed_poles"][coordinate].items()}
    free = tuple(i for i in range(driver.CONTROL_COUNT) if i not in fixed)
    equality_rows = driver.exact_case_rows(case, coordinate)
    matrix = tuple(tuple(row[i] for i in free) for _, row, _ in equality_rows)
    rhs = tuple(target - sum((row[i] * value for i, value in fixed.items()), F(0)) for _, row, target in equality_rows)
    reduced, pivots = _rref_with_rhs(matrix, rhs)
    if len(pivots) != 3 or len(equality_rows) != 3 or len(free) != (10 if axis == 0 else 11):
        raise ValueError("EXACT_RREF_OR_FIXED_POLE_DIMENSION_MISMATCH")
    if any(seed[i][axis] != value for i, value in fixed.items()):
        raise ValueError("ACTUAL_SEED_FIXED_POLE_MISMATCH")
    seed_free = tuple(seed[i][axis] for i in free)
    residual = tuple(target - sum((row[k] * seed_free[k] for k in range(len(free))), F(0))
                     for row, target in zip(matrix, rhs, strict=True))
    correction_rows, correction_pivots = _rref_with_rhs(matrix, residual)
    if correction_pivots != pivots:
        raise ValueError("AFFINE_CORRECTION_RANK_MISMATCH")
    compatible = list(seed)
    for r, pivot in enumerate(pivots):
        i, point = free[pivot], list(compatible[free[pivot]])
        point[axis] += correction_rows[r][-1]
        compatible[i] = (point[0], point[1])
    if any(sum((row[i] * compatible[i][axis] for i in range(driver.CONTROL_COUNT)), F(0)) != target
           for _, row, target in equality_rows):
        raise ValueError("EXACT_AFFINE_WARM_START_CORRECTION_FAILED")
    nonpivots = tuple(i for i in range(len(free)) if i not in pivots)
    basis: list[tuple[tuple[F, F], ...]] = []
    for column in nonpivots:
        free_delta = [F(0)] * len(free)
        free_delta[column] = F(1)
        for r, pivot_column in enumerate(pivots):
            free_delta[pivot_column] = -reduced[r][column]
        full = [[F(0), F(0)] for _ in range(driver.CONTROL_COUNT)]
        for k, pole in enumerate(free):
            full[pole][axis] = free_delta[k]
        basis.append(tuple(map(tuple, full)))
    expected_nullity = 7 if coordinate == "r" else 8
    if len(basis) != expected_nullity:
        raise ValueError("EXPECTED_15_TOTAL_NULLSPACE_PARAMETERS")
    return tuple(compatible), tuple(basis)


def _model_for_family(driver: Any, case: dict[str, Any], seed_case: dict[str, Any]) -> dict[str, Any]:
    actual_seed = tuple((F(r), F(z)) for r, z in seed_case["control_points_rz_mm"])
    if len(actual_seed) != driver.CONTROL_COUNT:
        raise ValueError("ACTUAL_SEED_CONTROL_COUNT_MISMATCH")
    r_seed, r_basis = _coordinate_basis(driver, case, "r", actual_seed)
    z_seed, z_basis = _coordinate_basis(driver, case, "z", actual_seed)
    seed = tuple((r_seed[i][0], z_seed[i][1]) for i in range(driver.CONTROL_COUNT))
    directions = r_basis + z_basis
    if len(directions) != 15:
        raise ValueError("EXPECTED_15_TOTAL_NULLSPACE_PARAMETERS")
    spans = driver._controls_to_spans(driver.exact_bezier_extraction(), seed)
    references = []
    for span_index, span in enumerate(spans):
        h = driver.BREAKS[span_index + 1] - driver.BREAKS[span_index]
        velocity_poles = driver._derivative_poles(span, h, 1)
        vector = tuple(velocity_poles[0][axis] + velocity_poles[-1][axis] for axis in range(2))
        norm_l1 = abs(vector[0]) + abs(vector[1])
        if not norm_l1:
            raise ValueError("SEED_REFERENCE_DIRECTION_UNDEFINED")
        references.append(tuple(value / norm_l1 for value in vector))
    correction = tuple(tuple(seed[i][a] - actual_seed[i][a] for a in range(2)) for i in range(17))
    return {"seed": seed, "actual_seed": actual_seed, "warm_start_correction": correction,
            "directions": directions, "references": tuple(references),
            "apex_span": driver.BREAKS.index(F(case["apex"]["u"])),
            "screen_spans": tuple(map(int, case["curvature_screen_span_indices_zero_based"]))}


def _controls(seed: Sequence[tuple[F, F]], directions: Sequence[Sequence[tuple[F, F]]],
              alpha: Sequence[float], exact: bool = False) -> tuple[tuple[Any, Any], ...]:
    weights = tuple(F(Decimal(str(float(x)))) if exact else float(x) for x in alpha)
    return tuple(tuple(seed[i][a] + sum((directions[j][i][a] * weights[j] for j in range(15)), F(0))
                        if exact else float(seed[i][a]) +
                        sum(float(directions[j][i][a]) * weights[j] for j in range(15))
                        for a in range(2)) for i in range(17))


def _float_spans(extraction: Sequence[Sequence[Sequence[F]]], controls: Sequence[tuple[float, float]]) -> Any:
    return tuple(tuple(tuple(sum(float(row[i]) * controls[i][axis] for i in range(17))
                             for axis in range(2)) for row in span) for span in extraction)


def _d1(points: Sequence[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    degree = len(points) - 1
    return tuple(tuple(degree * (points[i + 1][axis] - points[i][axis]) for axis in range(2))
                 for i in range(degree))


def _bprod(a: Sequence[float], b: Sequence[float]) -> tuple[float, ...]:
    m, n = len(a) - 1, len(b) - 1
    return tuple(sum(comb(m, i) * comb(n, k - i) / comb(m + n, k) * a[i] * b[k - i]
                     for i in range(max(0, k - n), min(m, k) + 1)) for k in range(m + n + 1))


def _elevate(a: Sequence[float], target_degree: int) -> tuple[float, ...]:
    out = tuple(a)
    while len(out) - 1 < target_degree:
        degree = len(out) - 1
        out = tuple((i / (degree + 1) * out[i - 1] if i else 0.0) +
                    ((degree + 1 - i) / (degree + 1) * out[i] if i <= degree else 0.0)
                    for i in range(degree + 2))
    if len(out) - 1 != target_degree:
        raise ValueError("BERNSTEIN_ELEVATION_TARGET_TOO_SMALL")
    return out


def _scaled_radius_polynomial(points: Sequence[tuple[float, float]]) -> tuple[float, ...]:
    first = _d1(points)
    second = _d1(first)
    r1, z1 = tuple(p[0] for p in first), tuple(p[1] for p in first)
    r2, z2 = tuple(p[0] for p in second), tuple(p[1] for p in second)
    speed2 = tuple(a + b for a, b in zip(_bprod(r1, r1), _bprod(z1, z1), strict=True))
    left, right = _bprod(r1, z2), _bprod(z1, r2)
    det = tuple(x - y for x, y in zip(left, right, strict=True))
    speed6 = _bprod(_bprod(speed2, speed2), speed2)
    det2 = _elevate(_bprod(det, det), 24)
    radius_ratio_sq = DESIGN_RADIUS_SCALED ** 2
    return tuple(a - radius_ratio_sq * b for a, b in zip(speed6, det2, strict=True))


def _objective_factory(model: dict[str, Any], check_deadline: Any) -> Any:
    directions = model["directions"]
    gram = tuple(tuple(sum(float(directions[a][i][axis]) * float(directions[b][i][axis])
                           for i in range(17) for axis in range(2)) / (SCALE_MM ** 2)
                         for b in range(15)) for a in range(15))

    def objective(alpha: Sequence[float]) -> float:
        check_deadline()
        return sum(alpha[a] * gram[a][b] * alpha[b] for a in range(15) for b in range(15))
    return objective


def _constraint_factory(driver: Any, case: dict[str, Any], model: dict[str, Any],
                        extraction: Any, check_deadline: Any) -> Any:
    def inequalities(alpha: Sequence[float]) -> tuple[float, ...]:
        check_deadline()
        controls = _controls(model["seed"], model["directions"], alpha)
        spans = _float_spans(extraction, controls)
        rows: list[float] = []
        max_r, mouth_z = float(F(case["max_outer_radius_mm"])), float(F(case["mouth_z_mm"]))
        for i, span in enumerate(spans):
            for r, z in span:
                rows.extend((r / SCALE_MM, (max_r - r) / SCALE_MM,
                             z / SCALE_MM, (mouth_z - z) / SCALE_MM))
            first = _d1(span)
            rows.extend(v[1] / SCALE_MM for v in first)
            sign = 1.0 if i < model["apex_span"] else -1.0
            rows.extend(sign * v[0] / SCALE_MM for v in first)
            h = float(driver.BREAKS[i + 1] - driver.BREAKS[i])
            reference = model["references"][i]
            for v in first:
                global_velocity = (v[0] / h, v[1] / h)
                rows.append(global_velocity[0] * float(reference[0]) +
                            global_velocity[1] * float(reference[1]) - 1.0)
            if i in model["screen_spans"]:
                normalized = tuple((r / SCALE_MM, z / SCALE_MM) for r, z in span)
                rows.extend(_scaled_radius_polynomial(normalized))
        return tuple(rows)
    return inequalities


def _exact_speed_gates(driver: Any, model: dict[str, Any],
                       controls: Sequence[tuple[F, F]]) -> tuple[dict[str, Any], ...]:
    spans = driver._controls_to_spans(driver.exact_bezier_extraction(), controls)
    gates = []
    for i, span in enumerate(spans):
        h = driver.BREAKS[i + 1] - driver.BREAKS[i]
        velocities = driver._derivative_poles(span, h, 1)
        dots = tuple(v[0] * model["references"][i][0] + v[1] * model["references"][i][1] for v in velocities)
        gates.append({"span": i, "reference_direction_dot_mm_per_global_u": dots,
                      "all_at_least_1": all(value >= 1 for value in dots)})
    return tuple(gates)


def _exact_gate(geometry: dict[str, Any], screen_spans: Sequence[int],
                speed_gates: Sequence[dict[str, Any]], optimizer_success: bool = True) -> tuple[str, list[str]]:
    target_rows = [geometry["spans"][i] for i in screen_spans]
    target_statuses = [row["radius_9mm_status"] for row in target_rows]
    gates = ((geometry["all_features_exact"], "EXACT_FEATURE_EQUALITY_FAILURE"),
             (geometry["all_C4"], "EXACT_C4_JET_FAILURE"),
             (geometry["all_strict_point_checks_pass"], "STRICT_POINT_COUNTEREXAMPLE"))
    exact_failures = [label for passed, label in gates if not passed]
    if "POINT_COUNTEREXAMPLE_AT_SPAN_ENDPOINT" in target_statuses:
        exact_failures.append("EXACT_R9_ENDPOINT_COUNTEREXAMPLE")
    if any(not row["all_at_least_1"] for row in speed_gates):
        exact_failures.append("EXACT_REFERENCE_DIRECTION_SPEED_BOUND_FAILURE")
    if exact_failures:
        return "EXACTFAIL_NOT_PROMOTED", exact_failures
    gates = ((geometry["all_hulls_proved"], "CONTROL_HULL_BBOX_NOT_PROVED"),
             (geometry["all_spans_regular_proved"], "EXACT_FULL_SPAN_REGULARITY_NOT_PROVED"),
             (geometry["straight_meridian_exclusions_proved"], "STRAIGHT_MERIDIAN_EXCLUSIONS_NOT_PROVED"))
    unknown = [label for passed, label in gates if not passed]
    if any(not row["z_derivative_poles_nonnegative"] or
           not row["radial_direction_poles_match_apex"] for row in geometry["spans"]):
        unknown.append("MONOTONICITY_POLE_CERTIFICATE_NOT_PROVED")
    if any(status != "PROVED_R9_ON_CLOSED_NONFLAT_SPAN" for status in target_statuses):
        unknown.append("R9_WHOLE_SPAN_CERTIFICATE_NOT_PROVED")
    if unknown:
        return "EXACTUNKNOWN_NOT_PROMOTED", unknown
    if optimizer_success:
        return "GEOMETRY_ENGINEERING_CANDIDATE_NOT_PHYSICS_READY", []
    return "OPTIMIZER_UNSUCCESSFUL_NOT_PROMOTED", ["SLSQP_SUCCESS_FALSE"]


def _pairwise_height_gate(case: dict[str, Any]) -> dict[str, Any]:
    apex_r, apex_z = (F(x) for x in case["apex"]["rz_mm"])
    neck_r, neck_z = (F(x) for x in case["neck_start"]["rz_mm"])
    retreat, rise, radius = apex_r - neck_r, neck_z - apex_z, F(9)
    row = {"radial_retreat_mm": retreat, "vertical_rise_mm": rise, "radius_mm": radius,
           "bound": "H^2 >= 4*R*D - D^2 when 0 < D <= 2*R", "scope": "necessary_pairwise_height_bound"}
    if retreat <= 0 or retreat > 2 * radius:
        reason = ("D_ZERO_STRAIGHT_PAIR" if retreat == 0 else "D_GREATER_THAN_2R"
                  if retreat > 2 * radius else "NONPOSITIVE_RADIAL_RETREAT")
        return {**row, "status": "NOT_APPLICABLE", "reason": reason}
    required = 4 * radius * retreat - retreat * retreat
    row.update({"required_rise_squared_mm2": required, "rise_squared_mm2": rise * rise})
    status = "PASS_NECESSARY_BOUND" if rise >= 0 and rise * rise >= required else "FAIL_INCOMPATIBLE_HEIGHT"
    return {**row, "status": status}


def _validate_design_cases(frozen: dict[str, Any], proposed: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(proposed, dict) or set(proposed) != {"bowl", "jar"}:
        raise ValueError("EXPLICIT_BOWL_AND_JAR_DESIGN_CASES_REQUIRED")
    for family in ("bowl", "jar"):
        actual = proposed[family]
        expected = json.loads(json.dumps(frozen[family]))
        if family == "bowl":
            expected["apex"]["rz_mm"][1] = actual["apex"]["rz_mm"][1]
            for row in expected["features"]:
                if row["name"] == "max_radius_apex":
                    row["rz_mm"][1] = actual["apex"]["rz_mm"][1]
            apex_row = next(row for row in expected["linear_equalities"] if row["name"] == "apex_height")
            apex_row["rhs"] = actual["apex"]["rz_mm"][1]
        if actual != expected:
            raise ValueError("DESIGN_CASE_CHANGES_FROZEN_TARGETS_OTHER_THAN_EXPLICIT_BOWL_APEX_Z")
    return proposed


def run_constrained_design(*, root_ready: bool = False,
                           design_cases: dict[str, Any] | None = None) -> dict[str, Any]:
    """Future one-shot SLSQP call; root_ready must be explicitly true."""
    if root_ready is not True:
        raise PermissionError("ROOT_READY_REQUIRED_FOR_CONSTRAINED_DESIGN")
    if STARTED_PATH.exists() or RESULT_PATH.exists():
        raise FileExistsError("ONE_SHOT_MARKER_OR_RESULT_EXISTS_REFUSING_RERUN")
    driver, frozen_cases, seed_cases, approved_cases = _load_inputs()
    cases = _validate_design_cases(frozen_cases, approved_cases if design_cases is None else design_cases)
    height_gates = {family: _pairwise_height_gate(case) for family, case in cases.items()}
    incompatible = [family for family, check in height_gates.items() if check["status"] == "FAIL_INCOMPATIBLE_HEIGHT"]
    if incompatible:
        raise ValueError("EXACT_PAIRWISE_HEIGHT_GATE_BLOCKED: " + ",".join(incompatible))
    start = time.monotonic()
    deadline = start + MAX_SECONDS
    with STARTED_PATH.open("x", encoding="utf-8") as stream:
        json.dump({"status": "RUN_STARTED_ONE_SHOT", "max_seconds": MAX_SECONDS,
                   "max_iterations_per_family": MAX_ITERATIONS}, stream)

    def check_deadline() -> None:
        if time.monotonic() >= deadline:
            raise BudgetExpired("SHARED_60_SECOND_DEADLINE")

    extraction = driver.exact_bezier_extraction()
    from scipy.optimize import minimize
    families: dict[str, Any] = {}
    for family in ("bowl", "jar"):
        if time.monotonic() >= deadline:
            families[family] = {"optimizer_status": "NOT_STARTED_BUDGET_EXHAUSTED",
                                "reason": "SHARED_60_SECOND_DEADLINE"}
            continue
        case, seed_case = cases[family], seed_cases[family]
        model = _model_for_family(driver, case, seed_case)
        objective = _objective_factory(model, check_deadline)
        constraints = _constraint_factory(driver, case, model, extraction, check_deadline)
        call_started = time.monotonic()
        record: dict[str, Any] = {}
        try:
            result = minimize(objective, (0.0,) * 15, method="SLSQP", jac=None,
                              constraints=({"type": "ineq", "fun": constraints},),
                              options={"maxiter": MAX_ITERATIONS, "ftol": 1e-9,
                                       "eps": FINITE_DIFFERENCE_STEP_MM, "disp": False})
            alpha = tuple(float(value) for value in result.x)
            if len(alpha) != 15 or any(not math.isfinite(value) for value in alpha):
                raise ValueError("OPTIMIZER_RETURNED_NONFINITE_OR_WRONG_DIMENSION_ALPHA")
            fun_value = float(result.fun)
            record["optimizer_status"] = {"success": bool(result.success), "status": int(result.status),
                "message": str(result.message), "nit": int(result.nit), "nfev": int(result.nfev),
                "njev": int(getattr(result, "njev", 0)),
                "objective_value": fun_value if math.isfinite(fun_value) else None}
            decimals = tuple(Decimal(str(value)) for value in alpha)
            exact_controls = _controls(model["seed"], model["directions"], alpha, exact=True)
            record.update({"alpha_decimal": decimals, "alpha_exact_decimal_fraction": tuple(F(x) for x in decimals),
                "compatible_q0_control_points_rz_mm": model["seed"],
                "warm_start_correction_rz_mm": model["warm_start_correction"],
                "control_points_rz_mm": exact_controls, "optimizer_elapsed_seconds": time.monotonic() - call_started})
            if time.monotonic() >= deadline:
                record.update({"promotion_status": "EXACTUNKNOWN_NOT_PROMOTED",
                               "promotion_reasons": ["DEADLINE_BEFORE_EXACT_CERTIFICATE"]})
            else:
                geometry = driver.certify_controls(case, exact_controls, extraction)
                speed_gates = _exact_speed_gates(driver, model, exact_controls)
                gate_status, gate_reasons = _exact_gate(
                    geometry, model["screen_spans"], speed_gates, bool(result.success))
                if time.monotonic() > deadline:
                    gate_status, gate_reasons = "EXACTUNKNOWN_NOT_PROMOTED", [
                        "DEADLINE_DURING_OR_AFTER_EXACT_CERTIFICATE"]
                record.update({"promotion_status": gate_status, "promotion_reasons": gate_reasons,
                               "exact_geometry_certificate": geometry, "exact_reference_speed_gates": speed_gates})
        except BudgetExpired as error:
            record.update({"optimizer_status": record.get("optimizer_status", "DEADLINE_REACHED"),
                           "reason": str(error), "promotion_status": "EXACTUNKNOWN_NOT_PROMOTED"})
        except Exception as error:
            record.update({"optimizer_status": record.get("optimizer_status", "OPTIMIZER_OR_CERTIFICATION_EXCEPTION"),
                           "reason": f"{type(error).__name__}: {error}",
                           "promotion_status": "EXACTUNKNOWN_NOT_PROMOTED"})
        families[family] = record

    payload = {"schema": "vesselforge.curvature_constrained_meridian.result.v1",
               "status": "GEOMETRY_ENGINEERING_CANDIDATE_ONLY",
               "claim_limits": ["NOT_PHYSICS_READY", "NOT_STYLE_CALIBRATED", "NOVELTY_UNCONFIRMED",
                                "NO_INNER_WALL_OR_LIP", "MERIDIAN_CURVATURE_ONLY"],
               "source_pins": json.loads(PINS_PATH.read_text(encoding="utf-8")),
               "solver": {"objective": "squared_distance_from_exact_compatible_Q0_scaled_by_9mm",
                 "nullspace_parameters": {"r": 7, "z": 8}, "constraints_passed_to_slsqp": True,
                 "inequality_counts": {"bbox": 288, "z_derivative": 60, "radial_direction": 60,
                                       "reference_speed": 60, "P_R_9.09": 250, "total": 718},
                 "finite_difference_step_mm": FINITE_DIFFERENCE_STEP_MM,
                 "budget": {"shared_seconds": MAX_SECONDS, "iterations_per_family": MAX_ITERATIONS,
                            "calls_per_family": 1, "result_limit_bytes": MAX_OUTPUT_BYTES},
                 "design_radius_mm": str(DESIGN_RADIUS_MM), "final_certificate_radius_mm": "9",
                 "curvature_scale": "local_Bezier_t_and_rz_over_9mm",
                 "exact_certificate": "frozen_driver_exact_extraction_and_whole_span_P_R"},
               "explicit_design_cases": cases,
               "pairwise_height_gates_before_scipy_import": height_gates,
               "families": families, "elapsed_seconds": time.monotonic() - start}
    encoded = (json.dumps(payload, default=str, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > MAX_OUTPUT_BYTES:
        raise ValueError("OUTPUT_EXCEEDS_8MIB")
    with RESULT_PATH.open("xb") as stream:
        stream.write(encoded)
    return payload
