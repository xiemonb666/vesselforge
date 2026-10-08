"""Planned read-only saved-result checker; intentionally not executed here."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from fractions import Fraction as F
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / "vesselforge" / "experiments" / "convex_meridian_feasibility_20261006" / "convex_meridian_feasibility.py"
PINS = HERE / "source_pins.json"
RESULT = HERE / "convex_meridian_feasibility_result.json"
RUN_STARTED = HERE / "run_started.json"
MAX_BYTES = 8 * 1024 * 1024


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_saved_result() -> dict[str, object]:
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    if pins.get("case_authorized") is not True:
        raise ValueError("CASE_UNAUTHORIZED")
    marker = json.loads(RUN_STARTED.read_text(encoding="utf-8"))
    if (marker.get("implementation_sha256") != pins["implementation"]["sha256"] or
            marker.get("case_authorized") is not True):
        raise ValueError("RUN_STARTED_MARKER_MISMATCH")
    if RESULT.stat().st_size >= MAX_BYTES:
        raise ValueError("RESULT_EXCEEDS_8_MIB")
    if sha256(SOURCE) != pins["implementation"]["sha256"]:
        raise ValueError("IMPLEMENTATION_HASH_MISMATCH")
    payload = json.loads(RESULT.read_text(encoding="utf-8"))
    if payload.get("schema") != "vesselforge.convex_meridian_feasibility.result.v1":
        raise ValueError("RESULT_SCHEMA_MISMATCH")
    spec = importlib.util.spec_from_file_location("_convex_meridian_source", SOURCE)
    if spec is None or spec.loader is None:
        raise ImportError("SOURCE_IMPORT_UNAVAILABLE")
    source = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(source)
    driver, cases, seeds = source._load_inputs()
    checked = {}
    for family in ("bowl", "jar"):
        record = payload["families"][family]
        if not record.get("one_lp_attempt", False):
            raise ValueError("EXPECTED_ONE_LP_PER_FAMILY")
        if record.get("solver_success") is not True:
            checked[family] = {"status": record.get("status"),
                               "infeasibility_proved": False}
            continue
        embedded = record.get("audit", {})
        if "alpha_exact_decimal_fraction" not in embedded or not embedded.get("control_points_rz_mm"):
            raise ValueError(f"CANDIDATE_EVIDENCE_MISSING:{family}")
        alpha = tuple(F(value) for value in embedded["alpha_exact_decimal_fraction"])
        model = source._make_model(driver, cases[family], seeds[family])
        rows = source._assemble_rows(driver, cases[family], model)
        audit = source._exact_audit(driver, cases[family], model, rows, alpha)
        normalized = json.loads(json.dumps(audit))
        if record.get("status") != audit.get("status"):
            raise ValueError(f"RESULT_AUDIT_STATUS_MISMATCH:{family}")
        if any(normalized.get(key) != embedded.get(key) for key in (
                "status", "alpha_exact_decimal_fraction", "control_points_rz_mm",
                "fixed_reference_direction_speed_floor", "exact_linear_violation_count",
                "worst_exact_linear_violations")):
            raise ValueError(f"SAVED_CANDIDATE_EVIDENCE_MISMATCH:{family}")
        checked[family] = {
            "status": audit["status"],
            "all_linear_rows_exact": audit.get("all_linear_rows_exact"),
            "candidate_preserved_for_posthoc_review": True,
            "features_C4_monotonicity_and_full_span_proof_rechecked":
                audit["status"] == "EXACT_CONVEX_FEASIBILITY_CANDIDATE"}
    return {"status": "READ_ONLY_RECHECK_COMPLETE", "families": checked,
            "solver_imported": False}
