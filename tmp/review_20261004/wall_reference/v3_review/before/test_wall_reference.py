from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import cadquery as cq
import pytest

from vesselforge.schema import sha256_file
from vesselforge.semantics import classify_canonical_faces
from vesselforge.wall_reference import build_wall_reference, validate_wall_reference


@pytest.fixture(scope="module")
def analytic_hollow_cylinder_reference(tmp_path_factory):
    """A real STEP mother fixture; extrusion uses nested wires and no Boolean."""
    root = tmp_path_factory.mktemp("wall-reference-cylinder")
    step_path = root / "analytic_hollow_cylinder.step"
    outer = cq.Wire.makeCircle(10.0, cq.Vector(0, 0, 0), cq.Vector(0, 0, 1))
    inner = cq.Wire.makeCircle(8.0, cq.Vector(0, 0, 0), cq.Vector(0, 0, 1))
    fixture_shape = cq.Solid.extrudeLinear(outer, [inner], cq.Vector(0, 0, 10.0))
    cq.exporters.export(fixture_shape, str(step_path), exportType="STEP")
    canonical = cq.importers.importStep(str(step_path)).val()
    source_hash = sha256_file(step_path)
    semantics = classify_canonical_faces(
        canonical,
        SimpleNamespace(
            body_height_mm=10.0,
            wall_mm=2.0,
            body_width_mm=20.0,
            handle_low_z_mm=3.0,
            handle_high_z_mm=8.0,
            handle_radius_mm=1.0,
            handle_outreach_mm=12.0,
        ),
        source_hash,
    )
    assert semantics["status"] == "PASS"
    assert semantics["counts"]["body_outer"] == 1
    assert semantics["counts"]["body_inner"] == 1
    record = build_wall_reference(
        semantics,
        source_geometry_sha256=source_hash,
        units={"length": "mm", "time": "s", "mass": "kg"},
        frame="right_handed_z_up",
        source_scope="analytic_fixture_mother",
    )
    return record, source_hash


def test_analytic_hollow_cylinder_records_both_material_outward_wall_directions(analytic_hollow_cylinder_reference):
    record, source_hash = analytic_hollow_cylinder_reference
    assert record["status"] == "MOTHER_SOURCE_ONLY"
    assert record["source_geometry_kind"] == "canonical_step"
    assert record["source_geometry_sha256"] == source_hash
    assert record["source_scope"] == "analytic_fixture_mother"
    assert record["qualification"]["mesh_binding_status"] == "NOT_SUPPLIED"
    assert record["qualification"]["fragment_mapping_status"] == "UNAVAILABLE"
    assert record["qualification"]["global_minimum_wall_claim"] is False
    stations = {station["wall_role"]: station for station in record["stations"]}
    outer = stations["outer"]
    inner = stations["inner"]
    assert outer["outward_from_material"] == outer["source_classification_evidence"]["interior_sample"]["oriented_outward_normal"]
    assert inner["outward_from_material"] == inner["source_classification_evidence"]["interior_sample"]["oriented_outward_normal"]
    assert outer["source_classification_evidence"]["classification_evidence"]["oriented_radial_normal_dot_mm"] > 0
    assert inner["source_classification_evidence"]["classification_evidence"]["oriented_radial_normal_dot_mm"] < 0
    assert validate_wall_reference(record, expected_source_geometry_sha256=source_hash)["status"] == "VALID"
    print(json.dumps(record, sort_keys=True, indent=2))


def test_stale_step_file_hash_returns_unknown(analytic_hollow_cylinder_reference):
    record, _source_hash = analytic_hollow_cylinder_reference
    result = validate_wall_reference(record, expected_source_geometry_sha256="b" * 64)
    assert result["status"] == "UNKNOWN"
    assert "STALE_SOURCE_STEP_SHA256" in result["errors"]


def test_wrong_length_unit_returns_unknown(analytic_hollow_cylinder_reference):
    record, _source_hash = analytic_hollow_cylinder_reference
    altered = copy.deepcopy(record)
    altered["units"]["length"] = "cm"
    result = validate_wall_reference(altered)
    assert result["status"] == "UNKNOWN"
    assert "WALL_REFERENCE_UNITS_INVALID" in result["errors"]


def test_unknown_wall_role_returns_unknown(analytic_hollow_cylinder_reference):
    record, _source_hash = analytic_hollow_cylinder_reference
    altered = copy.deepcopy(record)
    altered["stations"][0]["wall_role"] = "interface"
    result = validate_wall_reference(altered)
    assert result["status"] == "UNKNOWN"
    assert "STATION_0_WALL_ROLE_UNKNOWN" in result["errors"]


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("position_mm", [float("nan"), 0.0, 5.0], "STATION_0_POSITION_INVALID"),
        ("outward_from_material", [float("inf"), 0.0, 0.0], "STATION_0_DIRECTION_NONFINITE_OR_INVALID"),
    ],
)
def test_nonfinite_station_or_direction_returns_unknown(analytic_hollow_cylinder_reference, field, value, error):
    record, _source_hash = analytic_hollow_cylinder_reference
    altered = copy.deepcopy(record)
    altered["stations"][0][field] = value
    result = validate_wall_reference(altered)
    assert result["status"] == "UNKNOWN"
    assert error in result["errors"]


def test_interface_normal_report_is_not_a_wall_reference_source(analytic_hollow_cylinder_reference):
    _record, source_hash = analytic_hollow_cylinder_reference
    result = build_wall_reference(
        {"schema": "vf.interface-normal.v1", "status": "PASS", "normal": [1.0, 0.0, 0.0]},
        source_geometry_sha256=source_hash,
        units={"length": "mm"},
        frame="right_handed_z_up",
        source_scope="mother_surface",
    )
    assert result["status"] == "UNKNOWN"
    assert result["stations"] == []
    assert "SOURCE_SEMANTICS_SCHEMA_UNSUPPORTED" in result["unknown_reasons"]


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        (
            "explicit_body_outer_face_count",
            True,
            "WALL_REFERENCE_COVERAGE_EXPLICIT_BODY_OUTER_FACE_COUNT_INVALID",
        ),
        (
            "unknown_or_pending_face_count",
            False,
            "WALL_REFERENCE_COVERAGE_UNKNOWN_OR_PENDING_FACE_COUNT_INVALID",
        ),
        ("wall_face_station_coverage_fraction", True, "WALL_REFERENCE_COVERAGE_FRACTION_INVALID"),
    ],
)
def test_coverage_rejects_booleans_as_counts_or_fraction(analytic_hollow_cylinder_reference, field, value, error):
    record, _source_hash = analytic_hollow_cylinder_reference
    altered = copy.deepcopy(record)
    altered["coverage"][field] = value
    result = validate_wall_reference(altered)
    assert result["status"] == "UNKNOWN"
    assert error in result["errors"]

