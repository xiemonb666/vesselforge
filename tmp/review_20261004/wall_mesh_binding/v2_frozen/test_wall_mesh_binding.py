from __future__ import annotations

import hashlib

import numpy as np
import pytest
from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_OUT

from vesselforge import wall_mesh_binding as binding


def _policy() -> binding.BindingPolicy:
    return binding.BindingPolicy(
        target_linear_deflection_mm=0.05,
        target_angular_deflection_rad=0.05,
        weld_tolerance_mm=5e-6,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_linear_deflection_mm", True),
        ("target_angular_deflection_rad", np.nan),
        ("weld_tolerance_mm", 0.0),
        ("cad_numeric_tolerance_mm", "1e-7"),
        ("cad_numeric_angle_tolerance_rad", -1e-4),
    ],
)
def test_public_binding_policy_rejects_boolean_nonreal_nonfinite_or_nonpositive(
    field: str, value: object,
) -> None:
    values = {
        "target_linear_deflection_mm": 0.05,
        "target_angular_deflection_rad": 0.05,
        "weld_tolerance_mm": 5e-6,
    }
    values[field] = value
    with pytest.raises(ValueError):
        binding.BindingPolicy(**values)


@pytest.mark.parametrize(
    ("source", "key"),
    [
        ("parameters", "tessellation_linear_mm"),
        ("parameters", "tessellation_angular_rad"),
        ("tessellation", "linear_chord_deflection_mm"),
        ("tessellation", "angular_tolerance_rad"),
        ("report", "tessellation_chord_deflection_target_mm"),
        ("report", "tessellation_angular_tolerance_rad"),
    ],
)
def test_manifest_deflection_sources_reject_boolean_before_float_conversion(
    source: str, key: str,
) -> None:
    manifest: dict[str, object] = {
        "provenance": {"spec": {
            "parameters": {"tessellation_linear_mm": 0.05, "tessellation_angular_rad": 0.05},
            "tessellation": {"linear_chord_deflection_mm": 0.05,
                             "angular_tolerance_rad": 0.05},
        }},
    }
    report: dict[str, object] = {
        "tessellation_chord_deflection_target_mm": 0.05,
        "tessellation_angular_tolerance_rad": 0.05,
    }
    if source == "parameters":
        manifest["provenance"]["spec"]["parameters"][key] = True  # type: ignore[index]
    elif source == "tessellation":
        manifest["provenance"]["spec"]["tessellation"][key] = True  # type: ignore[index]
    else:
        report[key] = True
    with pytest.raises(ValueError, match="TESSELLATION_DEFLECTION_SOURCE_INVALID"):
        binding._load_binding_policy(manifest, report)


def test_angular_threshold_is_labeled_as_policy_not_measured_error_bound() -> None:
    serialized = _policy().as_dict()
    assert serialized["normal_angle_policy_id"] == binding.NORMAL_ANGLE_POLICY_ID
    assert "acceptance threshold" in serialized["normal_angle_limit_semantics"]
    assert "not a measured error or global error bound" in serialized["normal_angle_limit_semantics"]
    assert "normal_angle_error_rad" not in serialized


def _station(
    station_id: str,
    face_index: int,
    role: str,
    point: tuple[float, float, float],
    outward: tuple[float, float, float],
    *,
    uv_state: str = "IN",
) -> dict[str, object]:
    return {
        "station_id": station_id,
        "source_wall_face_index_zero_based": face_index,
        "wall_role": role,
        "u": 0.25,
        "v": 0.75,
        "trimmed_uv_state": uv_state,
        "step_point_mm": list(point),
        "outward_from_material": list(outward),
        "recorded_point_mm": list(point),
        "recorded_outward_normal": list(outward),
    }


def _plane_pair_mesh(
    first_x: float = 0.0,
    second_x: float = 2.0,
    *,
    second_face_id: int = 1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    # Both triangles have +X winding and include their respective sample at the centroid.
    vertices = np.asarray([
        [first_x, -1.0, -1.0], [first_x, 1.0, -1.0], [first_x, 0.0, 2.0],
        [second_x, -1.0, -1.0], [second_x, 1.0, -1.0], [second_x, 0.0, 2.0],
    ], dtype=np.float64)
    faces = np.asarray([[0, 1, 2], [3, 4, 5]], dtype=np.int32)
    lineage = np.asarray([0, second_face_id], dtype=np.int32)
    return vertices, faces, lineage


def test_parent_mesh_content_hash_normalizes_storage_endianness_and_index_width() -> None:
    vertices = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    faces32 = np.asarray([[0, 1, 2], [0, 3, 1]], dtype=np.int32)
    source32 = np.asarray([0, 1], dtype=np.int32)
    hash_a = binding.parent_mesh_content_sha256(vertices, faces32, source32)
    hash_b = binding.parent_mesh_content_sha256(
        vertices.astype(">f8"), faces32.astype(np.int64), source32.astype(">i8"))
    assert hash_a == hash_b
    assert hash_a != binding.parent_mesh_content_sha256(vertices, faces32[:, ::-1], source32)


def test_step_semantics_and_surface_file_hash_slots_cannot_be_interchanged(tmp_path) -> None:
    step = tmp_path / "solid.step"
    semantics = tmp_path / "face_semantics.json"
    step.write_bytes(b"step-bytes")
    semantics.write_bytes(b"semantics-bytes")
    expected_step = hashlib.sha256(step.read_bytes()).hexdigest()
    expected_semantics = hashlib.sha256(semantics.read_bytes()).hexdigest()
    manifest = {"files": {
        "geometry/solid.step": {"sha256": expected_semantics, "bytes": step.stat().st_size},
        "metadata/face_semantics.json": {"sha256": expected_step, "bytes": semantics.stat().st_size},
    }}
    with pytest.raises(ValueError, match="FILE_HASH_MISMATCH"):
        binding._verify_package_file_hash(manifest, "geometry/solid.step", step)
    with pytest.raises(ValueError, match="FILE_HASH_MISMATCH"):
        binding._verify_package_file_hash(manifest, "metadata/face_semantics.json", semantics)


def test_wrong_units_and_bad_triangle_lineage_fail_closed() -> None:
    vertices, faces, lineage = _plane_pair_mesh()
    with pytest.raises(ValueError, match="requires mm/right_handed_z_up"):
        binding.parent_mesh_content_sha256(vertices, faces, lineage, units="cm")
    assert binding._validate_mesh_arrays(vertices, faces, np.asarray([0, 3]), 2) == \
        "TRIANGLE_LINEAGE_FACE_INDEX_OUT_OF_RANGE"


def test_wrong_face_lineage_cannot_fall_back_to_global_nearest() -> None:
    vertices, faces, lineage = _plane_pair_mesh(first_x=0.0, second_x=1.0)
    # Exchange the source face IDs: the station on face 0 is geometrically closest to triangles
    # labelled face 1. The exact-face candidate is too far and the other face is never a fallback.
    lineage = np.asarray([1, 0], dtype=np.int32)
    row = binding.bind_station_to_parent_mesh(
        _station("outer-0", 0, "outer", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
        vertices, faces, lineage, canonical_face_count=2, policy=_policy())
    assert row["status"] == "UNKNOWN"
    assert row["reason"] in {
        "STATION_PROJECTION_ERROR_EXCEEDS_LIMIT",
        "DIFFERENT_FACE_CLEARLY_NEARER_THAN_DECLARED_FACE",
    }


def test_nearby_distinct_wall_faces_are_ambiguous_not_combined() -> None:
    vertices, faces, lineage = _plane_pair_mesh(first_x=0.0, second_x=0.02)
    row = binding.bind_station_to_parent_mesh(
        _station("outer-0", 0, "outer", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
        vertices, faces, lineage, canonical_face_count=2, policy=_policy())
    assert row["status"] == "UNKNOWN"
    assert row["reason"] == "AMBIGUOUS_FACE_LINEAGE"
    assert row["nearest_other_face_index"] == 1


@pytest.mark.parametrize("state", [TopAbs_ON, TopAbs_OUT])
def test_trimmed_face_boundary_or_outside_uv_is_not_accepted(monkeypatch, state) -> None:
    class FakeClassifier:
        def __init__(self, *_args):
            pass

        def State(self):
            return state

    monkeypatch.setattr(binding, "BRepClass_FaceClassifier", FakeClassifier)
    row = binding._reevaluate_station_on_step_face(
        face=object(),
        station={
            "station_id": "outer-0",
            "position_mm": [0.0, 0.0, 0.0],
            "outward_from_material": [1.0, 0.0, 0.0],
            "source_classification_evidence": {"interior_sample": {"u": 0.2, "v": 0.4}},
        },
        face_index=0,
        policy=_policy(),
    )
    assert row["status"] == "UNKNOWN"
    assert row["reason"] == "TRIMMED_UV_NOT_IN"
    assert row["trimmed_uv_state"] == ("ON" if state == TopAbs_ON else "OUT")


def test_reversed_parent_triangle_normal_is_unknown() -> None:
    vertices = np.asarray([
        [0.0, -1.0, -1.0], [0.0, 0.0, 2.0], [0.0, 1.0, -1.0],
    ], dtype=np.float64)
    faces = np.asarray([[0, 1, 2]], dtype=np.int32)  # -X, opposite to the recorded wall normal.
    lineage = np.asarray([0], dtype=np.int32)
    row = binding.bind_station_to_parent_mesh(
        _station("outer-0", 0, "outer", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
        vertices, faces, lineage, canonical_face_count=1, policy=_policy())
    assert row["status"] == "UNKNOWN"
    assert row["reason"] == "MESH_NORMAL_MISMATCH"


def test_same_brep_face_edge_tie_is_deterministic_and_keeps_candidates() -> None:
    vertices = np.asarray([
        [0.0, -1.0, -1.0], [0.0, 1.0, -1.0], [0.0, 1.0, 1.0], [0.0, -1.0, 1.0],
    ], dtype=np.float64)
    faces = np.asarray([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    lineage = np.asarray([0, 0], dtype=np.int32)
    row = binding.bind_station_to_parent_mesh(
        _station("outer-0", 0, "outer", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
        vertices, faces, lineage, canonical_face_count=1, policy=_policy())
    assert row["status"] == "BOUND"
    assert row["parent_triangle_index"] == 0
    assert row["same_face_tie_triangle_indices"] == [0, 1]
    assert row["station_projection_error_mm"] == pytest.approx(0.0)


def test_internal_aggregation_of_bound_outer_and_inner_stations_preserves_opposite_normals() -> None:
    vertices = np.asarray([
        [10.0, -1.0, -1.0], [10.0, 1.0, -1.0], [10.0, 0.0, 2.0],
        [8.0, -1.0, -1.0], [8.0, 1.0, -1.0], [8.0, 0.0, 2.0],
    ], dtype=np.float64)
    faces = np.asarray([[0, 1, 2], [3, 5, 4]], dtype=np.int32)
    lineage = np.asarray([0, 1], dtype=np.int32)
    stations = [
        _station("outer-0", 0, "outer", (10.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
        _station("inner-1", 1, "inner", (8.0, 0.0, 0.0), (-1.0, 0.0, 0.0)),
    ]
    # The private aggregator tests already-resolved internal rows; it does not authenticate an
    # external mesh or source. Only build_wall_mesh_binding may use this status in a verified report.
    record = binding._aggregate_bound_stations(
        stations, vertices, faces, lineage, canonical_face_count=2,
        parent_mesh_content_hash="a" * 64, policy=_policy())
    assert record["status"] == "PASS_MOTHER_STATION_BINDING"
    assert record["coverage"]["station_mapping_fraction"] == 1.0
    assert [row["wall_role"] for row in record["stations"]] == ["outer", "inner"]
    assert np.dot(record["stations"][0]["outward_from_material"],
                  record["stations"][1]["outward_from_material"]) == pytest.approx(-1.0)
    assert record["qualification"]["global_minimum_wall_claim"] is False
    assert record["qualification"]["physics_claim"] is False
    assert record["qualification"]["stage_2_fragment_lineage_status"] == "UNIMPLEMENTED"
    assert record["qualification"]["global_wall_status"] == "UNVERIFIED"
    assert record["qualification"]["physical_qualification_status"] == "UNKNOWN"


def test_internal_aggregation_keeps_any_unbound_requested_station_unknown() -> None:
    vertices, faces, lineage = _plane_pair_mesh()
    stations = [
        _station("outer-0", 0, "outer", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
        _station("bad-uv", 1, "inner", (2.0, 0.0, 0.0), (-1.0, 0.0, 0.0), uv_state="ON"),
    ]
    record = binding._aggregate_bound_stations(
        stations, vertices, faces, lineage, canonical_face_count=2,
        parent_mesh_content_hash="b" * 64, policy=_policy())
    assert record["status"] == "UNKNOWN"
    assert record["coverage"]["stations_requested"] == 2
    assert record["coverage"]["stations_bound"] == 1
    assert record["coverage"]["station_mapping_fraction"] == 0.5


def test_parent_binding_aggregator_is_private_and_marks_aggregation_only_scope() -> None:
    assert "bind_stations_to_parent_mesh" not in binding.__all__
    assert not hasattr(binding, "bind_stations_to_parent_mesh")
    assert "_aggregate_bound_stations" not in binding.__all__
    record = binding._aggregate_bound_stations(
        [{"station_id": "already-bound", "status": "BOUND"}],
        np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64),
        np.asarray([[0, 1, 2], [0, 3, 1], [0, 2, 3], [1, 3, 2]], dtype=np.int32),
        np.asarray([0, 0, 0, 0], dtype=np.int32),
        canonical_face_count=1,
        parent_mesh_content_hash="c" * 64,
        policy=_policy(),
    )
    assert record["status"] == "PASS_MOTHER_STATION_BINDING"
    assert record["aggregation_scope"] == (
        "internal_station_status_aggregation_only_not_external_source_authentication"
    )
