from __future__ import annotations

import inspect
import json

import numpy as np
import pytest

from vesselforge.step_partition import (
    ResourceCaps,
    _fragment_descendant_ancestry,
    _load_source_face_metadata,
    _positive_oriented_tetrahedra,
    _rejected_mesh_diagnostics,
    _resource_forecast,
    _step_length_unit,
    _tetra_face_records,
    partition_step_at_x,
)


def _caps(**overrides: object) -> ResourceCaps:
    values: dict[str, object] = {
        "max_step_bytes": 1_000_000,
        "max_tetrahedra": 100_000,
        "max_memory_bytes": 2 * 1024**3,
    }
    values.update(overrides)
    return ResourceCaps(**values)  # type: ignore[arg-type]


def test_step_unit_parser_reads_mm_and_m(tmp_path) -> None:
    step_mm = tmp_path / "millimetres.step"
    step_mm.write_text(
        "ISO-10303-21;\nDATA;\n#908 = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) );\nENDSEC;",
        encoding="ascii",
    )
    assert _step_length_unit(step_mm) == "mm"

    step_m = tmp_path / "metres.step"
    step_m.write_text(
        "ISO-10303-21;\nDATA;\n#908 = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT($,.METRE.) );\nENDSEC;",
        encoding="ascii",
    )
    assert _step_length_unit(step_m) == "m"


def test_step_unit_parser_rejects_missing_unit(tmp_path) -> None:
    step = tmp_path / "no_units.step"
    step.write_text("ISO-10303-21;\nDATA;\nENDSEC;", encoding="ascii")
    with pytest.raises(ValueError, match="no recognized declared length unit"):
        _step_length_unit(step)


def test_face_metadata_requires_and_preserves_exact_import_tags(tmp_path) -> None:
    path = tmp_path / "faces.json"
    path.write_text(json.dumps({
        "schema": "vesselforge.step_source_face_metadata.v1",
        "mapping_status": "EXACT",
        "mapping_basis": "STEP transfer map supplied by CAD importer",
        "faces": [
            {"imported_surface_tag": 8, "source_face_id": "f-rim", "role": "rim"},
            {"imported_surface_tag": 9, "source_face_id": 11, "role": "body_outer"},
        ],
    }), encoding="utf-8")
    rows, report = _load_source_face_metadata(path)
    assert rows[8].source_face_id == "f-rim"
    assert rows[8].role == "rim"
    assert rows[9].source_face_id == "11"
    assert report["status"] == "EXACT_INPUT_BINDINGS"


def test_legacy_lineage_without_entity_binding_is_unknown(tmp_path) -> None:
    path = tmp_path / "face_lineage.json"
    path.write_text(json.dumps({
        "schema": "vf.native_meridian_face_lineage.v1",
        "faces": {"0": {"role": "base"}, "1": {"role": "rim"}},
    }), encoding="utf-8")
    rows, report = _load_source_face_metadata(path)
    assert rows == {}
    assert report["status"] == "PRESENT_BUT_UNBOUND"
    assert report["unbound_face_records"] == 2


def test_fragment_parent_map_preserves_only_explicit_source_face_ancestry() -> None:
    exact = {
        7: type("Face", (), {"source_face_id": "source-rim", "role": "rim"})(),
    }
    source_descendants, ancestry = _fragment_descendant_ancestry(
        source_surface_tags=[7, 8],
        # Entry 0 is the source volume; entries 1 and 2 are original surfaces.
        parent_map=[
            [(3, 90), (3, 91)],
            [(2, 100), (2, 101), (2, 500)],
            [(2, 102), (2, 500)],
        ],
        exterior_surface_tags={100, 101, 102},
        face_info_by_import_tag=exact,
    )
    assert source_descendants == {7: {100, 101}, 8: {102}}
    assert ancestry[100][0][1].source_face_id == "source-rim"
    assert ancestry[101][0][1].role == "rim"
    assert 102 not in ancestry
    assert 500 not in ancestry


def test_fragment_parent_map_requires_map_entry_for_each_source_face() -> None:
    with pytest.raises(ValueError, match="missing one or more source surfaces"):
        _fragment_descendant_ancestry([1, 2], [[(3, 10)], [(2, 20)]], {20}, {})


def test_resource_forecast_includes_local_refinement_and_caps() -> None:
    caps = _caps(max_tetrahedra=10_000, max_memory_bytes=256 * 1024**2)
    base = _resource_forecast(
        source_volume_m3=1e-6,
        mesh_size_m=0.01,
        source_surface_areas_m2={1: 0.01},
        interface_area_m2=0.002,
        source_face_info={},
        boundary_size_by_source_face_m={},
        boundary_size_by_role_m={},
        interface_size_m=None,
        caps=caps,
    )
    assert base["estimated_tetrahedra"] == 50
    assert base["within_caps"] is True

    exact_info = {1: type("Face", (), {"source_face_id": "f1", "role": "rim"})()}
    refined = _resource_forecast(
        source_volume_m3=1e-6,
        mesh_size_m=0.01,
        source_surface_areas_m2={1: 0.01},
        interface_area_m2=0.002,
        source_face_info=exact_info,
        boundary_size_by_source_face_m={"f1": 0.001},
        boundary_size_by_role_m={},
        interface_size_m=None,
        caps=caps,
    )
    assert refined["estimated_tetrahedra"] > base["estimated_tetrahedra"]
    assert refined["within_caps"] is False


def test_resource_caps_reject_nonpositive_or_boolean_limits() -> None:
    with pytest.raises(ValueError, match="positive integers"):
        _caps(max_tetrahedra=0).validate()
    with pytest.raises(ValueError, match="positive integers"):
        _caps(max_step_bytes=True).validate()


def test_partition_cad_volume_tolerance_is_bounded_before_gmsh_use(tmp_path) -> None:
    step = tmp_path / "placeholder.step"
    step.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="ascii")
    with pytest.raises(ValueError, match="finite, positive, and <= 1e-6"):
        partition_step_at_x(
            object(),
            step,
            "0" * 64,
            tmp_path / "out",
            resource_caps=_caps(),
            cad_partition_volume_relative_tolerance=1.1e-6,
        )


def test_legacy_partition_cad_volume_tolerance_default_stays_conservative() -> None:
    default = inspect.signature(partition_step_at_x).parameters[
        "cad_partition_volume_relative_tolerance"
    ].default
    assert default == 1e-7


def test_tetra_orientation_reorders_negative_cells_and_computes_volume() -> None:
    nodes = np.asarray([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ])
    oriented, volume = _positive_oriented_tetrahedra(nodes, np.asarray([[0, 2, 1, 3]]))
    assert np.linalg.det((nodes[oriented[0, 1:]] - nodes[oriented[0, 0]]).T) > 0
    assert volume[0] == pytest.approx(1.0 / 6.0)


@pytest.mark.parametrize(
    "cells, message",
    [
        (np.asarray([[0, 1, 1, 3]]), "repeated node"),
        (np.asarray([[0, 1, 2, 4]]), "missing node"),
    ],
)
def test_tetra_orientation_rejects_malformed_connectivity(cells, message: str) -> None:
    nodes = np.asarray([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ])
    with pytest.raises(ValueError, match=message):
        _positive_oriented_tetrahedra(nodes, cells)


def test_tetra_faces_distinguish_closed_boundary_from_two_parent_interface() -> None:
    nodes = np.asarray([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.0, 0.0, -1.0],
    ])
    raw = np.asarray([[0, 1, 2, 3], [0, 2, 1, 4]])
    tets, _ = _positive_oriented_tetrahedra(nodes, raw)
    records, exterior, interfaces = _tetra_face_records(tets, np.asarray([0, 1]))
    assert len(exterior) == 6
    assert len(interfaces) == 1
    first, second, face = interfaces[0]
    assert first != second
    assert records[tuple(sorted(face))][0][2] != records[tuple(sorted(face))][1][2]


def test_tetra_faces_reject_nonmanifold_three_parent_face() -> None:
    cells = np.asarray([
        [0, 1, 2, 3],
        [0, 2, 1, 4],
        [0, 1, 2, 5],
    ])
    with pytest.raises(ValueError, match="more than two parents"):
        _tetra_face_records(cells, np.asarray([0, 0, 1]))


def test_rejected_mesh_diagnostics_keep_exact_boundary_ids_and_two_interface_parents() -> None:
    nodes = np.asarray([
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0], [0.0, 0.0, -1.0],
    ])
    tets = np.asarray([[0, 1, 2, 3], [0, 2, 1, 4]], dtype=np.int64)
    partition = np.asarray([0, 1], dtype=np.int32)
    _records, exterior, interfaces = _tetra_face_records(tets, partition)
    node_index = {100 + index: index for index in range(len(nodes))}
    interface_face = interfaces[0][2]
    surface_rows: dict[int, list[tuple[int, int, int]]] = {
        900: [tuple(100 + int(index) for index in interface_face)],
    }
    ancestry = {}
    for index, (_cell, face) in enumerate(exterior):
        tag = 10 + index
        surface_rows[tag] = [tuple(100 + int(vertex) for vertex in face)]
        ancestry[tag] = [(1000 + index, type("Face", (), {
            "source_face_id": f"fid-{index}", "role": f"role-{index}",
        })())]

    class FakeMesh:
        @staticmethod
        def getElements(dim: int, tag: int):
            assert dim == 2
            rows = surface_rows[tag]
            return [2], [list(range(1, len(rows) + 1))], [np.asarray(rows, dtype=np.int64).reshape(-1)]

    fake_gmsh = type("FakeGmsh", (), {
        "model": type("Model", (), {"mesh": FakeMesh()})(),
    })()
    diagnostics = _rejected_mesh_diagnostics(
        fake_gmsh,
        nodes_m=nodes,
        tets=tets,
        cell_volume_m3=np.asarray([1.0 / 6.0, 1.0 / 6.0]),
        partition=partition,
        original_node_tags=np.arange(100, 105),
        original_cell_tags=np.asarray([201, 202]),
        parts=[301, 302],
        node_index=node_index,
        shared_surfaces=[900],
        exterior_surfaces=sorted(surface_rows.keys() - {900}),
        descendant_ancestry=ancestry,
        witness_imprint_report={"status": "VERIFIED"},
        witness_cut_report={"status": "VERIFIED"},
    )
    assert diagnostics["diagnostic_status"] == "FAILED_GEOMETRY_NOT_FOR_SIMULATION"
    assert diagnostics["interface_triangles"].shape == (1, 3)
    assert diagnostics["interface_parents"].shape == (1, 2)
    assert set(diagnostics["interface_parent_partition"][0]) == {0, 1}
    assert set(diagnostics["exterior_source_face_ids"].tolist()) == {f"fid-{i}" for i in range(6)}
    assert diagnostics["exterior_ancestry_exact"].all()

