from __future__ import annotations

from pathlib import Path

import pytest

from vesselforge.named_step import (
    exact_gmsh_boundary_bindings,
    export_named_step_faces,
    export_native_face_witnesses,
    face_entity_name,
    normalize_face_rows,
    parse_face_entity_name,
    sha256_file,
    validate_exact_binding_metadata,
)


class _FakeModel:
    def __init__(self, names: dict[int, str], *, volume: int = 1, surfaces: list[int] | None = None):
        self.names = names
        self.volume = volume
        self.surfaces = surfaces or sorted(names)

    def getBoundary(self, dim_tags, *, oriented, recursive):
        assert dim_tags == [(3, self.volume)]
        assert oriented is False
        assert recursive is False
        return [(2, tag) for tag in self.surfaces]

    def getEntities(self, dim):
        return [(3, self.volume)] if dim == 3 else [(2, tag) for tag in self.surfaces]

    def getEntityName(self, dim, tag):
        assert dim == 2
        return self.names[tag]


class _FakeGmsh:
    def __init__(self, names: dict[int, str], *, volume: int = 1, surfaces: list[int] | None = None):
        self.model = _FakeModel(names, volume=volume, surfaces=surfaces)


def _rows() -> list[dict[str, str]]:
    return [
        {"source_face_id": "source-wall-a", "role": "body_outer"},
        {"source_face_id": "source-rim", "role": "rim"},
    ]


def _valid_names() -> dict[int, str]:
    return {
        11: "Shapes/VF_FACE_source-wall-a__body_outer",
        12: "Shapes/VF_FACE_source-rim__rim",
    }


def _bind(gmsh, step_path: Path):
    return exact_gmsh_boundary_bindings(
        gmsh,
        1,
        _rows(),
        step_path=step_path,
        upstream_step_sha256="a" * 64,
        lineage_sha256="b" * 64,
        labels_option_enabled=True,
    )


def test_face_name_parser_and_row_validation_are_lossless() -> None:
    name = face_entity_name("source-wall-a", "body_outer")
    assert name == "VF_FACE_source-wall-a__body_outer"
    assert parse_face_entity_name(f"Shapes/{name}") == ("source-wall-a", "body_outer")
    assert parse_face_entity_name("Shapes/untrusted-name") is None
    with pytest.raises(ValueError, match="duplicate source_face_id"):
        normalize_face_rows([_rows()[0], _rows()[0]])
    with pytest.raises(ValueError, match="requires source_face_id and role"):
        normalize_face_rows([{"source_face_id": "source-wall-a"}])


def test_exact_boundary_binding_accepts_only_complete_named_boundary(tmp_path: Path) -> None:
    step = tmp_path / "body.step"
    step.write_text("fixture body STEP bytes", encoding="ascii")
    metadata = _bind(_FakeGmsh(_valid_names()), step)
    assert metadata["mapping_status"] == "EXACT"
    assert metadata["imported_surface_count"] == 2
    assert {row["source_face_id"] for row in metadata["faces"]} == {"source-wall-a", "source-rim"}
    validate_exact_binding_metadata(
        metadata,
        imported_step_path=step,
        expected_upstream_step_sha256="a" * 64,
    )
    step.write_text("mutated STEP bytes", encoding="ascii")
    with pytest.raises(ValueError, match="hash does not match"):
        validate_exact_binding_metadata(
            metadata,
            imported_step_path=step,
            expected_upstream_step_sha256="a" * 64,
        )


@pytest.mark.parametrize(
    ("names", "message"),
    [
        ({11: "", 12: "Shapes/VF_FACE_source-rim__rim"}, "unique complete boundary coverage"),
        ({11: "Shapes/VF_FACE_source-wall-a__body_outer", 12: "Shapes/VF_FACE_source-wall-a__body_outer"}, "labels multiple"),
        ({11: "Shapes/VF_FACE_source-wall-a__body_outer", 12: "Shapes/VF_FACE_foreign__rim"}, "unique complete boundary coverage"),
        ({11: "Shapes/VF_FACE_source-wall-a__body_inner", 12: "Shapes/VF_FACE_source-rim__rim"}, "role mismatch"),
    ],
)
def test_missing_duplicate_foreign_or_malicious_labels_fail_closed(tmp_path: Path, names, message) -> None:
    step = tmp_path / "body.step"
    step.write_text("fixture body STEP bytes", encoding="ascii")
    with pytest.raises(ValueError, match=message):
        _bind(_FakeGmsh(names), step)


def test_exact_binding_rejects_loose_surfaces_and_multiple_volumes(tmp_path: Path) -> None:
    step = tmp_path / "body.step"
    step.write_text("fixture body STEP bytes", encoding="ascii")
    loose = _FakeGmsh(_valid_names(), surfaces=[11, 12, 13])
    loose.model.getBoundary = lambda *args, **kwargs: [(2, 11), (2, 12)]
    with pytest.raises(ValueError, match="loose or duplicate surfaces"):
        _bind(loose, step)

    gmsh = _FakeGmsh(_valid_names())
    gmsh.model.getEntities = lambda dim: ([(3, 1), (3, 2)] if dim == 3 else [(2, 11), (2, 12)])
    with pytest.raises(ValueError, match="exactly the supplied single imported volume"):
        _bind(gmsh, step)


def test_native_step_exporters_preserve_one_solid_and_exact_face_witnesses(tmp_path: Path) -> None:
    cq = pytest.importorskip("cadquery")
    native_shape = cq.Workplane("XY").box(10.0, 20.0, 30.0).val()
    rows = [
        {"source_face_id": f"box-face-{index}", "role": "box_side"}
        for index in range(len(native_shape.Faces()))
    ]
    body = export_named_step_faces(native_shape, rows, tmp_path / "named_box.step")
    assert body["round_trip"]["valid_closed_solid"] is True
    assert body["round_trip"]["solid_count"] == 1
    assert body["round_trip"]["relative_volume_error"] == pytest.approx(0.0, abs=1e-12)
    assert body["named_advanced_face_entity_count"] == 6

    witnesses = export_native_face_witnesses(
        native_shape,
        rows,
        tmp_path / "witnesses",
        source_step_sha256="c" * 64,
        lineage_sha256="d" * 64,
        native_body_step_sha256=body["step_sha256"],
    )
    assert witnesses["mapping_status"] == "EXACT_NATIVE_FACE_WITNESSES"
    assert witnesses["witness_count"] == 6
    assert all(row["native_face_child_verified"] for row in witnesses["witnesses"])
    for row in witnesses["witnesses"]:
        assert row["native_face_area_mm2"] > 0.0
        assert row["step_round_trip_face_area_mm2"] > 0.0
        assert row["step_round_trip_relative_area_error"] <= 1e-8
        witness_path = Path(row["witness_path"])
        assert sha256_file(witness_path) == row["witness_sha256"]
        assert witness_path.read_text(encoding="ascii").count(row["step_entity_name"]) == 1
