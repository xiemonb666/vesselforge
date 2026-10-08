"""Source-bound wall reference stations derived from canonical STEP semantics.

This module records one auditable interior sample per explicitly classified
outer/inner canonical B-rep face. It does not map stations to a fragment mesh or
measure wall thickness.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any


WALL_REFERENCE_SCHEMA = "vf.wall-reference.v1"
WALL_REFERENCE_ALGORITHM = "vf.wall-reference/canonical-step-face-stations/1.0.0"
FACE_SEMANTICS_SCHEMA = "vf.brep-face-semantics.v1"
FACE_CLASSIFIER_PREFIX = "vf.canonical-step-face-semantics/"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_SCOPES = {"mother_surface", "analytic_fixture_mother"}
_ROLE_BY_REGION = {"body_outer": "outer", "body_inner": "inner"}
_KNOWN_REGIONS = {
    "body_outer": 1,
    "body_inner": 2,
    "natural_rim": 3,
    "base": 4,
    "handle": 5,
}
_NORMAL_TOLERANCE = 1e-5
_EVIDENCE_TOLERANCE = 1e-7


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _finite_vector(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 3
        and all(_number(component) for component in value)
    )


def _number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def _station_id(source_hash: str, face_index: int, role: str) -> str:
    return f"wr1-{source_hash[:16]}-{role}-f{face_index:05d}"


def _wall_role(region: Any) -> str | None:
    return _ROLE_BY_REGION.get(region) if isinstance(region, str) else None


def _radial_dot(position: list[float], direction: list[float]) -> float:
    return float(position[0]) * float(direction[0]) + float(position[1]) * float(direction[1])


def _base_coverage(face_semantics: Any) -> dict[str, Any]:
    rows = face_semantics.get("faces") if isinstance(face_semantics, Mapping) else None
    rows = rows if isinstance(rows, list) else []
    outer_count = sum(isinstance(row, Mapping) and row.get("region_name") == "body_outer" for row in rows)
    inner_count = sum(isinstance(row, Mapping) and row.get("region_name") == "body_inner" for row in rows)
    face_count = face_semantics.get("canonical_step_face_count") if isinstance(face_semantics, Mapping) else None
    face_count = face_count if isinstance(face_count, int) and not isinstance(face_count, bool) else None
    unknown_count = sum(not isinstance(row, Mapping) or row.get("status") != "CLASSIFIED" for row in rows)
    return {
        "canonical_step_face_count": face_count,
        "semantics_row_count": len(rows),
        "unknown_or_pending_face_count": unknown_count,
        "explicit_body_outer_face_count": int(outer_count),
        "explicit_body_inner_face_count": int(inner_count),
        "station_count": 0,
        "wall_face_station_coverage_fraction": 0.0,
        "coverage_basis": "finite canonical STEP B-rep wall faces; one interior sample per explicitly classified wall face; not area coverage or a global thickness bound",
    }


def _unknown_record(
    face_semantics: Any,
    *,
    source_geometry_sha256: Any,
    units: Any,
    frame: Any,
    source_scope: Any,
    reasons: list[str],
) -> dict[str, Any]:
    scope = source_scope if isinstance(source_scope, str) else None
    qualification = {
        "status": "UNKNOWN",
        "mesh_binding_status": "UNKNOWN",
        "fragment_mapping_status": "UNKNOWN",
        "global_minimum_wall_status": "NOT_ESTABLISHED",
        "physics_status": "NOT_ASSESSED",
        "global_minimum_wall_claim": False,
        "physics_claim": False,
    }
    return {
        "schema": WALL_REFERENCE_SCHEMA,
        "status": "UNKNOWN",
        "source_geometry_kind": "canonical_step",
        "source_geometry_sha256": source_geometry_sha256 if _is_sha256(source_geometry_sha256) else None,
        "algorithm": WALL_REFERENCE_ALGORITHM,
        "units": dict(units) if isinstance(units, Mapping) else None,
        "frame": frame if isinstance(frame, str) else None,
        "source_scope": scope,
        "source_semantics": {
            "schema": face_semantics.get("schema") if isinstance(face_semantics, Mapping) else None,
            "status": face_semantics.get("status") if isinstance(face_semantics, Mapping) else None,
            "classifier": face_semantics.get("classifier") if isinstance(face_semantics, Mapping) else None,
            "canonical_step_sha256": face_semantics.get("canonical_step_sha256") if isinstance(face_semantics, Mapping) else None,
        },
        "coverage": _base_coverage(face_semantics),
        "qualification": qualification,
        "stations": [],
        "unknown_reasons": sorted(set(reasons)),
    }


def _source_errors(
    face_semantics: Any,
    *,
    source_geometry_sha256: Any,
    units: Any,
    frame: Any,
    source_scope: Any,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(face_semantics, Mapping):
        return ["SOURCE_SEMANTICS_MISSING_OR_NOT_AN_OBJECT"]
    if face_semantics.get("schema") != FACE_SEMANTICS_SCHEMA:
        errors.append("SOURCE_SEMANTICS_SCHEMA_UNSUPPORTED")
    if face_semantics.get("status") != "PASS":
        errors.append("SOURCE_SEMANTICS_NOT_COMPLETE_PASS")
    classifier = face_semantics.get("classifier")
    if not isinstance(classifier, str) or not classifier.startswith(FACE_CLASSIFIER_PREFIX):
        errors.append("SOURCE_CLASSIFIER_UNSUPPORTED")
    if not _is_sha256(source_geometry_sha256):
        errors.append("SOURCE_STEP_FILE_SHA256_MISSING_OR_INVALID")
    if not _is_sha256(face_semantics.get("canonical_step_sha256")):
        errors.append("SOURCE_SEMANTICS_STEP_SHA256_MISSING_OR_INVALID")
    elif _is_sha256(source_geometry_sha256) and face_semantics.get("canonical_step_sha256") != source_geometry_sha256:
        errors.append("STALE_SOURCE_STEP_SHA256")
    if not isinstance(units, Mapping) or units.get("length") != "mm":
        errors.append("SOURCE_LENGTH_UNIT_MUST_BE_MM")
    if frame != "right_handed_z_up":
        errors.append("SOURCE_FRAME_UNSUPPORTED")
    if not isinstance(source_scope, str) or source_scope not in _SOURCE_SCOPES:
        errors.append("SOURCE_SCOPE_MISSING_OR_UNSUPPORTED")

    rows = face_semantics.get("faces")
    face_count = face_semantics.get("canonical_step_face_count")
    if (
        not isinstance(face_count, int)
        or isinstance(face_count, bool)
        or face_count < 1
        or not isinstance(rows, list)
        or len(rows) != face_count
    ):
        errors.append("SOURCE_FACE_INVENTORY_INCOMPLETE")
        return errors

    for expected_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            errors.append(f"SOURCE_FACE_{expected_index}_NOT_AN_OBJECT")
            continue
        if row.get("face_index_zero_based") != expected_index or isinstance(row.get("face_index_zero_based"), bool):
            errors.append(f"SOURCE_FACE_{expected_index}_INDEX_INVALID")
        if row.get("status") != "CLASSIFIED":
            errors.append(f"SOURCE_FACE_{expected_index}_NOT_CLASSIFIED")
            continue
        if row.get("classifier_version") != classifier:
            errors.append(f"SOURCE_FACE_{expected_index}_CLASSIFIER_MISMATCH")
        if row.get("canonical_step_sha256") != source_geometry_sha256:
            errors.append(f"SOURCE_FACE_{expected_index}_STALE_STEP_SHA256")
        region = row.get("region_name")
        role = _wall_role(region)
        if not isinstance(region, str) or region not in _KNOWN_REGIONS:
            errors.append(f"SOURCE_FACE_{expected_index}_REGION_UNKNOWN")
            continue
        region_code = row.get("region_code")
        if isinstance(region_code, bool) or not isinstance(region_code, int) or region_code != _KNOWN_REGIONS[region]:
            errors.append(f"SOURCE_FACE_{expected_index}_REGION_CODE_MISMATCH")
        if role is None:
            continue
        basis = row.get("classification_basis")
        evidence = row.get("classification_evidence")
        sample = row.get("interior_sample")
        if not isinstance(basis, str) or not basis.strip() or not isinstance(evidence, Mapping):
            errors.append(f"SOURCE_FACE_{expected_index}_WALL_CLASSIFICATION_EVIDENCE_MISSING")
            continue
        if (
            not isinstance(sample, Mapping)
            or not isinstance(sample.get("uv_state"), str)
            or sample.get("uv_state") not in {"IN_OR_ON", "ON"}
        ):
            errors.append(f"SOURCE_FACE_{expected_index}_WALL_INTERIOR_SAMPLE_MISSING")
            continue
        position = sample.get("point_mm")
        normal = sample.get("oriented_outward_normal")
        if not _finite_vector(position):
            errors.append(f"SOURCE_FACE_{expected_index}_WALL_POSITION_INVALID")
        if not _finite_vector(normal):
            errors.append(f"SOURCE_FACE_{expected_index}_WALL_NORMAL_INVALID")
        if not _finite_vector(position) or not _finite_vector(normal):
            continue
        if not _number(sample.get("u")) or not _number(sample.get("v")):
            errors.append(f"SOURCE_FACE_{expected_index}_WALL_UV_SAMPLE_INVALID")
        norm = math.sqrt(sum(float(component) ** 2 for component in normal))
        if not math.isfinite(norm) or abs(norm - 1.0) > _NORMAL_TOLERANCE:
            errors.append(f"SOURCE_FACE_{expected_index}_WALL_NORMAL_NOT_UNIT_LENGTH")
        axis_offset = evidence.get("axis_offset_from_global_z_mm")
        radial_dot = evidence.get("oriented_radial_normal_dot_mm")
        if not _number(axis_offset) or abs(float(axis_offset)) > 1e-5:
            errors.append(f"SOURCE_FACE_{expected_index}_WALL_AXIS_EVIDENCE_INVALID")
        if not _number(radial_dot):
            errors.append(f"SOURCE_FACE_{expected_index}_WALL_RADIAL_EVIDENCE_INVALID")
            continue
        computed_dot = _radial_dot(list(position), list(normal))
        if not math.isclose(float(radial_dot), computed_dot, rel_tol=0.0, abs_tol=_EVIDENCE_TOLERANCE):
            errors.append(f"SOURCE_FACE_{expected_index}_WALL_RADIAL_EVIDENCE_MISMATCH")
        if region == "body_outer" and float(radial_dot) <= 1e-4:
            errors.append(f"SOURCE_FACE_{expected_index}_OUTER_NORMAL_ROLE_MISMATCH")
        if region == "body_inner" and float(radial_dot) >= -1e-4:
            errors.append(f"SOURCE_FACE_{expected_index}_INNER_NORMAL_ROLE_MISMATCH")

    wall_rows = [row for row in rows if isinstance(row, Mapping) and _wall_role(row.get("region_name")) is not None]
    if not any(row.get("region_name") == "body_outer" for row in wall_rows):
        errors.append("EXPLICIT_OUTER_WALL_SOURCE_MISSING")
    if not any(row.get("region_name") == "body_inner" for row in wall_rows):
        errors.append("EXPLICIT_INNER_WALL_SOURCE_MISSING")
    return errors


def build_wall_reference(
    face_semantics: Mapping[str, Any] | None,
    *,
    source_geometry_sha256: str | None,
    units: Mapping[str, Any] | None,
    frame: str | None,
    source_scope: str | None,
) -> dict[str, Any]:
    """Build a mother-source reference, or a structured UNKNOWN record.

    ``source_geometry_sha256`` must be the SHA-256 of the canonical STEP file,
    supplied independently by its manifest/file inventory. A face-semantics
    report alone does not establish a mesh binding or a fragment wall map.
    """
    reasons = _source_errors(
        face_semantics,
        source_geometry_sha256=source_geometry_sha256,
        units=units,
        frame=frame,
        source_scope=source_scope,
    )
    if reasons:
        return _unknown_record(
            face_semantics,
            source_geometry_sha256=source_geometry_sha256,
            units=units,
            frame=frame,
            source_scope=source_scope,
            reasons=reasons,
        )

    assert isinstance(face_semantics, Mapping)
    assert isinstance(units, Mapping)
    assert isinstance(source_geometry_sha256, str)
    rows = face_semantics["faces"]
    stations: list[dict[str, Any]] = []
    for row in rows:
        region = row["region_name"]
        if region not in _ROLE_BY_REGION:
            continue
        role = _ROLE_BY_REGION[region]
        sample = row["interior_sample"]
        stations.append(
            {
                "station_id": _station_id(source_geometry_sha256, row["face_index_zero_based"], role),
                "source_wall_face_index_zero_based": row["face_index_zero_based"],
                "wall_role": role,
                "position_mm": [float(value) for value in sample["point_mm"]],
                "outward_from_material": [float(value) for value in sample["oriented_outward_normal"]],
                "source_classification_evidence": {
                    "schema": face_semantics["schema"],
                    "classifier": face_semantics["classifier"],
                    "classifier_version": row["classifier_version"],
                    "canonical_step_sha256": row["canonical_step_sha256"],
                    "region_name": region,
                    "classification_basis": row["classification_basis"],
                    "classification_evidence": dict(row["classification_evidence"]),
                    "interior_sample": {
                        "u": float(sample["u"]),
                        "v": float(sample["v"]),
                        "uv_state": sample["uv_state"],
                        "point_mm": [float(value) for value in sample["point_mm"]],
                        "oriented_outward_normal": [float(value) for value in sample["oriented_outward_normal"]],
                    },
                },
            }
        )

    outer_count = sum(station["wall_role"] == "outer" for station in stations)
    inner_count = sum(station["wall_role"] == "inner" for station in stations)
    coverage = _base_coverage(face_semantics)
    coverage.update(
        {
            "station_count": len(stations),
            "explicit_body_outer_face_count": outer_count,
            "explicit_body_inner_face_count": inner_count,
            "wall_face_station_coverage_fraction": 1.0,
        }
    )
    source_semantics = {
        "schema": face_semantics["schema"],
        "status": face_semantics["status"],
        "classifier": face_semantics["classifier"],
        "canonical_step_sha256": face_semantics["canonical_step_sha256"],
        "canonical_step_face_count": face_semantics["canonical_step_face_count"],
        "wall_face_inventory": [
            {
                "source_wall_face_index_zero_based": row["face_index_zero_based"],
                "wall_role": _ROLE_BY_REGION[row["region_name"]],
            }
            for row in rows
            if isinstance(row.get("region_name"), str) and row["region_name"] in _ROLE_BY_REGION
        ],
    }
    return {
        "schema": WALL_REFERENCE_SCHEMA,
        "status": "MOTHER_SOURCE_ONLY",
        "source_geometry_kind": "canonical_step",
        "source_geometry_sha256": source_geometry_sha256,
        "algorithm": WALL_REFERENCE_ALGORITHM,
        "units": {"length": "mm", "direction": "dimensionless"},
        "frame": frame,
        "source_scope": source_scope,
        "source_semantics": source_semantics,
        "coverage": coverage,
        "qualification": {
            "status": "MOTHER_SOURCE_ONLY",
            "mesh_binding_status": "NOT_SUPPLIED",
            "fragment_mapping_status": "UNAVAILABLE",
            "global_minimum_wall_status": "NOT_ESTABLISHED",
            "physics_status": "NOT_ASSESSED",
            "global_minimum_wall_claim": False,
            "physics_claim": False,
            "scope_note": "finite source-face stations only; no source-to-fragment-mesh binding, global minimum wall, or physics qualification",
        },
        "stations": stations,
    }


def validate_wall_reference(
    record: Mapping[str, Any] | None,
    *,
    expected_source_geometry_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate record structure and source binding without claiming physics.

    When the caller knows the current STEP file hash, pass it as
    ``expected_source_geometry_sha256`` to detect a stale persisted record.
    """
    errors: list[str] = []
    if not isinstance(record, Mapping):
        return {"status": "UNKNOWN", "errors": ["WALL_REFERENCE_MISSING_OR_NOT_AN_OBJECT"]}
    if record.get("schema") != WALL_REFERENCE_SCHEMA:
        errors.append("WALL_REFERENCE_SCHEMA_UNSUPPORTED")
    if record.get("status") != "MOTHER_SOURCE_ONLY":
        errors.append("WALL_REFERENCE_NOT_QUALIFIED_MOTHER_SOURCE_ONLY")
    if record.get("algorithm") != WALL_REFERENCE_ALGORITHM:
        errors.append("WALL_REFERENCE_ALGORITHM_UNSUPPORTED")
    if record.get("source_geometry_kind") != "canonical_step":
        errors.append("SOURCE_GEOMETRY_KIND_UNSUPPORTED")
    source_hash = record.get("source_geometry_sha256")
    if not _is_sha256(source_hash):
        errors.append("SOURCE_STEP_FILE_SHA256_MISSING_OR_INVALID")
    if expected_source_geometry_sha256 is not None:
        if not _is_sha256(expected_source_geometry_sha256) or source_hash != expected_source_geometry_sha256:
            errors.append("STALE_SOURCE_STEP_SHA256")
    source_semantics = record.get("source_semantics")
    if not isinstance(source_semantics, Mapping) or source_semantics.get("schema") != FACE_SEMANTICS_SCHEMA:
        errors.append("SOURCE_SEMANTICS_REFERENCE_INVALID")
    elif source_semantics.get("status") != "PASS" or source_semantics.get("canonical_step_sha256") != source_hash:
        errors.append("SOURCE_SEMANTICS_STEP_BINDING_INVALID")
    units = record.get("units")
    if not isinstance(units, Mapping) or units.get("length") != "mm" or units.get("direction") != "dimensionless":
        errors.append("WALL_REFERENCE_UNITS_INVALID")
    if record.get("frame") != "right_handed_z_up":
        errors.append("WALL_REFERENCE_FRAME_INVALID")
    if not isinstance(record.get("source_scope"), str) or record.get("source_scope") not in _SOURCE_SCOPES:
        errors.append("WALL_REFERENCE_SOURCE_SCOPE_INVALID")

    qualification = record.get("qualification")
    expected_qualification = {
        "status": "MOTHER_SOURCE_ONLY",
        "mesh_binding_status": "NOT_SUPPLIED",
        "fragment_mapping_status": "UNAVAILABLE",
        "global_minimum_wall_status": "NOT_ESTABLISHED",
        "physics_status": "NOT_ASSESSED",
        "global_minimum_wall_claim": False,
        "physics_claim": False,
    }
    if not isinstance(qualification, Mapping):
        errors.append("WALL_REFERENCE_QUALIFICATION_MISSING")
    else:
        for key, value in expected_qualification.items():
            actual_value = qualification.get(key)
            if (isinstance(value, bool) and actual_value is not value) or (not isinstance(value, bool) and actual_value != value):
                errors.append(f"WALL_REFERENCE_QUALIFICATION_{key.upper()}_INVALID")

    stations = record.get("stations")
    if not isinstance(stations, list) or not stations:
        errors.append("WALL_REFERENCE_STATIONS_MISSING")
        stations = []
    seen_ids: set[str] = set()
    seen_indices: set[int] = set()
    role_counts = {"outer": 0, "inner": 0}
    for station_number, station in enumerate(stations):
        if not isinstance(station, Mapping):
            errors.append(f"STATION_{station_number}_NOT_AN_OBJECT")
            continue
        face_index = station.get("source_wall_face_index_zero_based")
        role = station.get("wall_role")
        station_id = station.get("station_id")
        if not isinstance(face_index, int) or isinstance(face_index, bool) or face_index < 0:
            errors.append(f"STATION_{station_number}_FACE_INDEX_INVALID")
            continue
        if face_index in seen_indices:
            errors.append(f"STATION_{station_number}_DUPLICATE_FACE_INDEX")
        seen_indices.add(face_index)
        if isinstance(source_semantics, Mapping):
            source_face_count = source_semantics.get("canonical_step_face_count")
            if isinstance(source_face_count, int) and not isinstance(source_face_count, bool) and face_index >= source_face_count:
                errors.append(f"STATION_{station_number}_FACE_INDEX_OUT_OF_SOURCE_RANGE")
        if not isinstance(role, str) or role not in {"outer", "inner"}:
            errors.append(f"STATION_{station_number}_WALL_ROLE_UNKNOWN")
            continue
        role_counts[role] += 1
        if not _is_sha256(source_hash) or station_id != _station_id(source_hash, face_index, role):
            errors.append(f"STATION_{station_number}_STABLE_ID_INVALID")
        if isinstance(station_id, str):
            if station_id in seen_ids:
                errors.append(f"STATION_{station_number}_DUPLICATE_STATION_ID")
            seen_ids.add(station_id)
        position = station.get("position_mm")
        normal = station.get("outward_from_material")
        if not _finite_vector(position):
            errors.append(f"STATION_{station_number}_POSITION_INVALID")
        if not _finite_vector(normal):
            errors.append(f"STATION_{station_number}_DIRECTION_NONFINITE_OR_INVALID")
        if not _finite_vector(position) or not _finite_vector(normal):
            continue
        norm = math.sqrt(sum(float(component) ** 2 for component in normal))
        if abs(norm - 1.0) > _NORMAL_TOLERANCE:
            errors.append(f"STATION_{station_number}_DIRECTION_NOT_UNIT_LENGTH")

        evidence = station.get("source_classification_evidence")
        if not isinstance(evidence, Mapping):
            errors.append(f"STATION_{station_number}_CLASSIFICATION_EVIDENCE_MISSING")
            continue
        if (
            not isinstance(source_semantics, Mapping)
            or not isinstance(source_semantics.get("classifier"), str)
            or not source_semantics["classifier"].startswith(FACE_CLASSIFIER_PREFIX)
            or evidence.get("schema") != FACE_SEMANTICS_SCHEMA
            or evidence.get("classifier") != source_semantics.get("classifier")
        ):
            errors.append(f"STATION_{station_number}_CLASSIFIER_REFERENCE_INVALID")
        if evidence.get("canonical_step_sha256") != source_hash:
            errors.append(f"STATION_{station_number}_STALE_STEP_SHA256")
        classification_evidence = evidence.get("classification_evidence")
        expected_region = "body_outer" if role == "outer" else "body_inner"
        if not isinstance(classification_evidence, Mapping):
            errors.append(f"STATION_{station_number}_CLASSIFICATION_EVIDENCE_INCOMPLETE")
        elif not _number(classification_evidence.get("oriented_radial_normal_dot_mm")):
            errors.append(f"STATION_{station_number}_RADIAL_EVIDENCE_INVALID")
        if evidence.get("region_name") != expected_region:
            errors.append(f"STATION_{station_number}_WALL_ROLE_EVIDENCE_MISMATCH")
        if evidence.get("classifier_version") != evidence.get("classifier"):
            errors.append(f"STATION_{station_number}_CLASSIFIER_VERSION_INVALID")
        basis = evidence.get("classification_basis")
        sample = evidence.get("interior_sample")
        if not isinstance(basis, str) or not basis.strip() or not isinstance(classification_evidence, Mapping):
            errors.append(f"STATION_{station_number}_CLASSIFICATION_EVIDENCE_INCOMPLETE")
            continue
        if (
            not isinstance(sample, Mapping)
            or not isinstance(sample.get("uv_state"), str)
            or sample.get("uv_state") not in {"IN_OR_ON", "ON"}
            or not _number(sample.get("u"))
            or not _number(sample.get("v"))
        ):
            errors.append(f"STATION_{station_number}_INTERIOR_SAMPLE_INVALID")
            continue
        if sample.get("point_mm") != position or sample.get("oriented_outward_normal") != normal:
            errors.append(f"STATION_{station_number}_SAMPLE_VECTOR_MISMATCH")
        axis_offset = classification_evidence.get("axis_offset_from_global_z_mm")
        radial_dot = classification_evidence.get("oriented_radial_normal_dot_mm")
        if not _number(axis_offset) or abs(float(axis_offset)) > 1e-5:
            errors.append(f"STATION_{station_number}_AXIS_EVIDENCE_INVALID")
        if not _number(radial_dot):
            errors.append(f"STATION_{station_number}_RADIAL_EVIDENCE_INVALID")
        else:
            computed_dot = _radial_dot(list(position), list(normal))
            if not math.isclose(float(radial_dot), computed_dot, rel_tol=0.0, abs_tol=_EVIDENCE_TOLERANCE):
                errors.append(f"STATION_{station_number}_RADIAL_EVIDENCE_MISMATCH")
            if role == "outer" and float(radial_dot) <= 1e-4:
                errors.append(f"STATION_{station_number}_OUTER_DIRECTION_ROLE_MISMATCH")
            if role == "inner" and float(radial_dot) >= -1e-4:
                errors.append(f"STATION_{station_number}_INNER_DIRECTION_ROLE_MISMATCH")

    if role_counts["outer"] < 1 or role_counts["inner"] < 1:
        errors.append("WALL_REFERENCE_REQUIRES_EXPLICIT_OUTER_AND_INNER_STATIONS")
    coverage = record.get("coverage")
    if not isinstance(coverage, Mapping):
        errors.append("WALL_REFERENCE_COVERAGE_MISSING")
    else:
        if coverage.get("station_count") != len(stations):
            errors.append("WALL_REFERENCE_COVERAGE_STATION_COUNT_MISMATCH")
        if coverage.get("explicit_body_outer_face_count") != role_counts["outer"]:
            errors.append("WALL_REFERENCE_COVERAGE_OUTER_COUNT_MISMATCH")
        if coverage.get("explicit_body_inner_face_count") != role_counts["inner"]:
            errors.append("WALL_REFERENCE_COVERAGE_INNER_COUNT_MISMATCH")
        if coverage.get("wall_face_station_coverage_fraction") != 1.0:
            errors.append("WALL_REFERENCE_COVERAGE_FRACTION_INVALID")
        source_face_count = coverage.get("canonical_step_face_count")
        if (
            not isinstance(source_face_count, int)
            or isinstance(source_face_count, bool)
            or source_face_count < 1
            or coverage.get("semantics_row_count") != source_face_count
            or coverage.get("unknown_or_pending_face_count") != 0
        ):
            errors.append("WALL_REFERENCE_SOURCE_COVERAGE_INCOMPLETE")
        if isinstance(source_semantics, Mapping):
            if source_semantics.get("canonical_step_face_count") != source_face_count:
                errors.append("WALL_REFERENCE_SOURCE_FACE_COUNT_MISMATCH")
            inventory = source_semantics.get("wall_face_inventory")
            if not isinstance(inventory, list):
                errors.append("WALL_REFERENCE_WALL_FACE_INVENTORY_MISSING")
            else:
                expected_inventory: set[tuple[int, str]] = set()
                for item in inventory:
                    if not isinstance(item, Mapping):
                        errors.append("WALL_REFERENCE_WALL_FACE_INVENTORY_INVALID")
                        continue
                    index = item.get("source_wall_face_index_zero_based")
                    role = item.get("wall_role")
                    if (
                        not isinstance(index, int)
                        or isinstance(index, bool)
                        or index < 0
                        or not isinstance(role, str)
                        or role not in {"outer", "inner"}
                    ):
                        errors.append("WALL_REFERENCE_WALL_FACE_INVENTORY_INVALID")
                        continue
                    expected_inventory.add((index, role))
                actual_inventory = {
                    (station.get("source_wall_face_index_zero_based"), station.get("wall_role"))
                    for station in stations
                    if isinstance(station, Mapping)
                    and isinstance(station.get("source_wall_face_index_zero_based"), int)
                    and not isinstance(station.get("source_wall_face_index_zero_based"), bool)
                    and isinstance(station.get("wall_role"), str)
                }
                if expected_inventory != actual_inventory or len(expected_inventory) != len(inventory):
                    errors.append("WALL_REFERENCE_STATION_INVENTORY_MISMATCH")

    return {"status": "VALID" if not errors else "UNKNOWN", "errors": sorted(set(errors))}

