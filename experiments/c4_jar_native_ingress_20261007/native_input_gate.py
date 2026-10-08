"""Pinned-input gates only; this module imports no CAD or solver packages."""
from __future__ import annotations

import importlib.metadata
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable


def input_preflight(case: dict[str, Any], pins: dict[str, Any], report: dict[str, Any], *, root: Path, experiment: Path, case_path: Path, sha256_file: Callable[[Path], str], read_json: Callable[[Path], Any], gate: Callable[..., None]) -> dict[str, Any]:
    local_sources = {"driver": Path(__file__).with_name("native_c4_ingress.py"), "case": case_path, "runner": experiment / "capture_once.py", "input_gate": Path(__file__)}
    for label, source in local_sources.items():
        expected = pins["source_files"][label]["sha256"]
        actual = sha256_file(source)
        if actual != expected:
            raise RuntimeError(f"{label} source hash mismatch: expected {expected}, got {actual}")
    for label, artifact in case["inputs"].items():
        if pins["inputs"][label] != artifact:
            raise RuntimeError(f"case/pins input record differs for {label}")
        actual = sha256_file(root / artifact["path"])
        if actual != artifact["sha256"]:
            raise RuntimeError(f"input hash mismatch for {label}: got {actual}")
    for label, artifact in pins.get("preserved_files", {}).items():
        if sha256_file(root / artifact["path"]) != artifact["sha256"]:
            raise RuntimeError(f"preserved design source changed: {label}")
    for label, artifact in pins["tooling"].items():
        if sha256_file(root / artifact["path"]) != artifact["sha256"]:
            raise RuntimeError(f"tooling reference changed: {label}")
    version = importlib.metadata.version("cadquery-ocp")
    if version != pins["runtime"]["cadquery_ocp_version"]:
        raise RuntimeError(f"OCP runtime version mismatch: {version}")

    outer = read_json(root / case["inputs"]["outer_result"]["path"])
    audit = read_json(root / case["inputs"]["independent_audit"]["path"])
    offset = read_json(root / case["inputs"]["normal_offset_result"]["path"])
    strip = read_json(root / case["inputs"]["normal_strip_result"]["path"])
    wall = read_json(root / case["inputs"]["global_wall_result"]["path"])
    family, cert = outer["families"]["jar"], outer["families"]["jar"]["exact_geometry_certificate"]
    controls, spans, joins = family["control_points_rz_mm"], cert["spans"], cert["joins"]
    gate(report, "saved_outer_candidate_status", outer["status"] == "GEOMETRY_ENGINEERING_CANDIDATE_ONLY", outer["status"])
    gate(report, "exact_controls_shape", len(controls) == 17 and all(len(p) == 2 for p in controls), {"pole_count": len(controls)})
    exact_controls = [[Fraction(x), Fraction(y)] for x, y in controls]
    gate(report, "exact_controls_endpoints", exact_controls[0] == [0, 0] and exact_controls[-1] == [26, 120], {"first": controls[0], "last": controls[-1]})
    saved_cert_ok = cert["all_C4"] and cert["all_spans_regular_proved"] and cert["all_features_exact"] and cert["all_hulls_proved"]
    gate(report, "saved_candidate_certificate", saved_cert_ok, {"all_C4": cert["all_C4"], "regular": cert["all_spans_regular_proved"], "features": cert["all_features_exact"], "hulls": cert["all_hulls_proved"]})
    gate(report, "saved_span_and_join_evidence", len(spans) == 12 and len(joins) == 11 and all(s["open_span_regular"] for s in spans) and all(j["exact_C4"] for j in joins), {"spans": len(spans), "joins": len(joins)})
    side_r9 = [spans[i]["radius_9mm_status"] for i in range(1, 11)]
    semantic_ok = spans[0]["semantic_base_flat"] and spans[11]["semantic_neck_cylindrical"] and all(x == "PROVED_R9_ON_CLOSED_NONFLAT_SPAN" for x in side_r9)
    gate(report, "saved_semantic_and_R9_map", semantic_ok, {"base": spans[0]["semantic_base_flat"], "neck": spans[11]["semantic_neck_cylindrical"], "side_statuses": side_r9})

    audit_jar = audit["families"]["jar"]
    audit_features, audit_samples = audit_jar["features"], audit_jar["direct_Cox_vs_Bezier_spot_checks"]
    audit_input_paths = [str(x).casefold() for x in audit["input_sha256"]]
    outer_absolute = str((root / case["inputs"]["outer_result"]["path"]).resolve()).casefold()
    audit_ok = audit["status"] == "PASS_RECONSTRUCTION" and audit_jar["geometry_status"] == "GEOMETRY_SCREENS_PROVED" and audit_jar["saved_reconstruction_matches"] is True and audit_jar["engineering_screens_all_pass"] is True and outer_absolute in audit_input_paths
    audit_ok = audit_ok and len(audit_jar["joins"]) == 11 and all(j["matches_saved"] and all(j["D0_to_D4"]) for j in audit_jar["joins"])
    audit_ok = audit_ok and len(audit_features) == 5 and all(f["exact"] and f["matches_saved"] for f in audit_features) and len(audit_samples) == 24 and all(p["match"] for p in audit_samples)
    gate(report, "independent_saved_reconstruction", audit_ok, {"status": audit["status"], "geometry_status": audit_jar["geometry_status"], "join_count": len(audit_jar["joins"]), "feature_count": len(audit_features), "direct_Cox_spot_checks": len(audit_samples), "pinned_outer_path_present": outer_absolute in audit_input_paths})
    gate(report, "saved_normal_offset_candidate", offset["status"] == "INNER_MERIDIAN_LOCAL_OFFSET_CANDIDATE" and len(offset["spans"]) == 12 and offset["global_wall_status"] == "UNKNOWN", {"status": offset["status"], "span_count": len(offset["spans"]), "global_wall": offset["global_wall_status"]})
    strip_joins = strip["shared_geometry_binding"]["actual_controls_global_u_C4_joins"]
    strip_pins = strip["input_pins"]
    strip_inputs_match = strip_pins.get("independent_audit") == case["inputs"]["independent_audit"]["sha256"] and strip_pins.get("offset_result") == case["inputs"]["normal_offset_result"]["sha256"] and strip_pins.get("outer_result") == case["inputs"]["outer_result"]["sha256"]
    strip_ok = strip["status"] == "GLOBAL_MERIDIAN_STRIP_INJECTIVITY_PROVED_CONDITIONAL" and len(strip_joins) == 11 and all(j["global_u_derivative_orders_equal"] == [0, 1, 2, 3, 4] for j in strip_joins)
    strip_ok = strip_ok and strip_inputs_match and strip["native_brep"] == "UNKNOWN" and strip["global_minimum_euclidean_wall"] == "UNKNOWN"
    gate(report, "saved_normal_strip_binding", strip_ok, {"status": strip["status"], "joins": len(strip_joins), "inputs_match": strip_inputs_match, "native_brep": strip["native_brep"], "global_wall": strip["global_minimum_euclidean_wall"]})
    wall_pins = wall["input_pins"]
    wall_expected = {"outer_result": case["inputs"]["outer_result"]["sha256"], "offset_result": case["inputs"]["normal_offset_result"]["sha256"], "monostrip_result": case["inputs"]["normal_strip_result"]["sha256"]}
    wall_ok = wall["status"] == "MERIDIAN_CURVE_PAIR_MINIMUM_EXACTLY_3_MM" and wall["scope"] == "min over outer meridian c(u) and inner meridian F(v,3), pinned jar, exact 2D model only" and wall["curve_pair_minimum_mm"] == "EXACTLY_3"
    wall_ok = wall_ok and all(wall_pins.get(k) == v for k, v in wall_expected.items()) and wall["native_B_rep"] == "UNKNOWN" and wall["production_wall_qualification"] == "UNKNOWN"
    gate(report, "saved_global_wall_scope", wall_ok, {"status": wall["status"], "scope": wall["scope"], "ideal_curve_pair_mm": wall["curve_pair_minimum_mm"], "native_B_rep": wall["native_B_rep"], "production_wall": wall["production_wall_qualification"]})
    return {"input_sha256": {name: item["sha256"] for name, item in case["inputs"].items()}, "outer_status": outer["status"], "independent_audit_status": audit["status"], "normal_offset_status": offset["status"], "normal_strip_status": strip["status"], "global_wall_result_status": wall["status"], "global_native_wall": "UNKNOWN", "exact_controls_rz_mm": controls, "degree": 5, "span_count": 12, "C4_join_count": 11}
