"""One-shot exact reduced-equality rank check; never forms H or a KKT system."""
from __future__ import annotations

import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
EXPERIMENT = ROOT / "vesselforge" / "experiments" / "semantic_base_neck_bspline_20261006"
DRIVER_PATH = EXPERIMENT / "semantic_base_neck_driver.py"
CASE_PATH = EXPERIMENT / "fixed_cases.json"
OLD_CASE_PATH = HERE / "prior_10_12_freeze" / "fixed_cases.json"
OUTPUT = HERE / "actual_rank_precheck"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reduced_system(driver, case: dict, coordinate: str) -> dict:
    fixed = {int(index): Fraction(value) for index, value in case["fixed_poles"][coordinate].items()}
    free = tuple(index for index in range(driver.CONTROL_COUNT) if index not in fixed)
    rows = []
    rhs = []
    names = []
    for row in case["linear_equalities"]:
        if row["coordinate"] != coordinate:
            continue
        full = driver.basis_row(Fraction(row["u"]), int(row["order"]))
        rows.append(tuple(full[index] for index in free))
        rhs.append(Fraction(row["rhs"]) - sum((full[index] * value for index, value in fixed.items()), Fraction(0)))
        names.append(row["name"])
    augmented = tuple(tuple(values) + (target,) for values, target in zip(rows, rhs, strict=True))
    rank_a = driver._rank(tuple(rows))
    rank_augmented = driver._rank(augmented)
    return {
        "coordinate": coordinate,
        "row_names": names,
        "free_control_indices": free,
        "reduced_matrix_exact": tuple(tuple(map(str, row)) for row in rows),
        "reduced_rhs_exact": tuple(map(str, rhs)),
        "rank_A": rank_a,
        "rank_augmented": rank_augmented,
        "row_count": len(rows),
        "consistent_full_row_rank": rank_a == len(rows) and rank_augmented == rank_a,
        "inconsistent": rank_augmented > rank_a,
    }


def main() -> int:
    if OUTPUT.exists():
        raise FileExistsError("RANK_PRECHECK_OUTPUT_EXISTS_REFUSING_OVERWRITE")
    sys.path.insert(0, str(EXPERIMENT))
    import semantic_base_neck_driver as driver

    cases = json.loads(CASE_PATH.read_text(encoding="utf-8"))["cases"]
    old_case = json.loads(OLD_CASE_PATH.read_text(encoding="utf-8"))["cases"]["bowl"]
    current = {
        family: {coordinate: reduced_system(driver, case, coordinate) for coordinate in ("r", "z")}
        for family, case in cases.items()
    }
    historical = reduced_system(driver, old_case, "r")
    result = {
        "scope": "exact Fraction rank of fixed-pole-reduced equalities only",
        "call_allowlist": ["basis_row", "_rank"],
        "hessian": "NOT_COMPUTED",
        "kkt": "NOT_FORMED_OR_SOLVED",
        "curve_extraction_or_evaluation": "NOT_RUN",
        "cad_or_render": "NOT_RUN",
        "source_sha256": sha256(DRIVER_PATH),
        "current_case_sha256": sha256(CASE_PATH),
        "archived_10_12_case_sha256": sha256(OLD_CASE_PATH),
        "current_cases": current,
        "all_four_current_systems_consistent_full_row_rank": all(
            current[family][coordinate]["consistent_full_row_rank"]
            for family in current for coordinate in ("r", "z")
        ),
        "historical_bowl_10_12_radial_system": historical,
        "historical_bowl_10_12_infeasible_witness": (
            historical["rank_augmented"] > historical["rank_A"]
        ),
    }
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    OUTPUT.mkdir(parents=False, exist_ok=False)
    (OUTPUT / "result.json").write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["all_four_current_systems_consistent_full_row_rank"] and result["historical_bowl_10_12_infeasible_witness"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
