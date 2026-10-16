from __future__ import annotations

import copy
import os
from pathlib import Path
import sys

import pytest

from vesselforge.face_witness import (
    imprint_native_face_witnesses,
    load_native_face_witness_manifest,
    validate_cut_witness_parent_map,
)
from vesselforge.named_step import (
    export_named_step_faces,
    export_native_face_witnesses,
    face_entity_name,
    sha256_file,
)
from vesselforge.step_partition import ResourceCaps, _resource_forecast


def _load_gmsh():
    sdk = Path(__file__).resolve().parents[2] / "third_party/pgfrag-geometry-runtime/sdk/gmsh-4.15.2-Windows64-sdk/lib"
    if not sdk.is_dir():
        pytest.skip("repository Gmsh SDK is unavailable")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(sdk))
    if str(sdk) not in sys.path:
        sys.path.insert(0, str(sdk))
    try:
        import gmsh  # type: ignore[import-not-found]
    except ImportError as error:
        pytest.skip(f"repository Gmsh module is unavailable: {error}")
    return gmsh


@pytest.fixture(scope="module")
def gmsh():
    module = _load_gmsh()
    module.initialize()
    module.option.setNumber("General.Terminal", 0)
    module.option.setNumber("General.NumThreads", 1)
    yield module
    module.finalize()


@pytest.fixture
def box_witnesses(tmp_path: Path):
    cq = pytest.importorskip("cadquery")
    shape = cq.Workplane("XY").box(10.0, 20.0, 30.0).val()
    rows = [
        {"source_face_id": f"box-face-{index}", "role": "base" if index == 0 else "wall"}
        for index in range(len(shape.Faces()))
    ]
    body_path = tmp_path / "canonical_box.step"
    body = export_named_step_faces(shape, rows, body_path)
    manifest = export_native_face_witnesses(
        shape,
        rows,
        tmp_path / "witnesses",
        source_step_sha256="c" * 64,
        lineage_sha256="d" * 64,
        native_body_step_sha256=body["step_sha256"],
    )
    return shape, body_path, manifest


def _import_body(gmsh, body_path: Path) -> int:
    gmsh.clear()
    gmsh.model.add("face_witness_test")
    gmsh.option.setString("Geometry.OCCTargetUnit", "M")
    gmsh.option.setNumber("Geometry.OCCBoundsUseStl", 1)
    imported = gmsh.model.occ.importShapes(str(body_path), highestDimOnly=True)
    gmsh.model.occ.synchronize()
    volumes = [int(tag) for dim, tag in imported if int(dim) == 3]
    assert len(volumes) == 1
    return volumes[0]


def _rewrite_witness(source: Path, output: Path, name: str, translation_mm=(0.0, 0.0, 0.0)) -> str:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
    from OCP.TCollection import TCollection_HAsciiString
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.gp import gp_Trsf, gp_Vec

    reader = STEPControl_Reader()
    assert reader.ReadFile(str(source)) == IFSelect_RetDone
    assert int(reader.TransferRoots()) == 1
    explorer = TopExp_Explorer(reader.OneShape(), TopAbs_FACE)
    faces = []
    while explorer.More():
        faces.append(explorer.Current())
        explorer.Next()
    assert len(faces) == 1
    face = faces[0]
    if any(float(value) != 0.0 for value in translation_mm):
        transform = gp_Trsf()
        transform.SetTranslation(gp_Vec(*map(float, translation_mm)))
        face = BRepBuilderAPI_Transform(face, transform, True).Shape()
    writer = STEPControl_Writer()
    assert writer.Transfer(face, STEPControl_AsIs) == IFSelect_RetDone
    advanced = [
        writer.Model().Value(i)
        for i in range(1, writer.Model().NbEntities() + 1)
        if writer.Model().Value(i).IsKind("StepShape_AdvancedFace")
    ]
    assert len(advanced) == 1
    advanced[0].SetName(TCollection_HAsciiString(name))
    assert writer.Write(str(output)) == IFSelect_RetDone
    return sha256_file(output)


def _validated_manifest(body_path: Path, manifest: dict):
    return load_native_face_witness_manifest(
        manifest,
        canonical_step_path=body_path,
        expected_upstream_source_step_sha256="c" * 64,
        expected_source_face_lineage_sha256="d" * 64,
    )[0]


def test_manifest_binds_exact_body_upstream_chain_and_round_trip_areas(box_witnesses) -> None:
    _shape, body_path, manifest = box_witnesses
    validated, report = load_native_face_witness_manifest(
        manifest,
        canonical_step_path=body_path,
        expected_upstream_source_step_sha256="c" * 64,
        expected_source_face_lineage_sha256="d" * 64,
    )
    assert report["status"] == "VALIDATED_NATIVE_FACE_WITNESS_MANIFEST"
    assert report["canonical_step_sha256"] == sha256_file(body_path)
    assert report["upstream_source_step_sha256"] == "c" * 64
    assert len(validated["witnesses"]) == 6
    assert all(row["step_round_trip_relative_area_error_observed"] <= 1e-8 for row in validated["witnesses"])


def test_manifest_rejects_canonical_body_and_upstream_hash_mismatch(box_witnesses, tmp_path: Path) -> None:
    _shape, body_path, manifest = box_witnesses
    corrupted = copy.deepcopy(manifest)
    corrupted["native_body_step_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="body SHA-256 does not match"):
        load_native_face_witness_manifest(corrupted, canonical_step_path=body_path)
    with pytest.raises(ValueError, match="upstream source STEP SHA-256 mismatch"):
        load_native_face_witness_manifest(
            manifest,
            canonical_step_path=body_path,
            expected_upstream_source_step_sha256="e" * 64,
        )
    corrupted = copy.deepcopy(manifest)
    corrupted["witnesses"][0]["witness_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="file SHA-256 mismatch"):
        load_native_face_witness_manifest(corrupted, canonical_step_path=body_path)


def test_manifest_caps_bytes_and_face_count_before_witness_parsing(box_witnesses) -> None:
    _shape, body_path, manifest = box_witnesses
    with pytest.raises(ValueError, match="manifest is .* limit is"):
        load_native_face_witness_manifest(
            manifest, canonical_step_path=body_path, max_manifest_bytes=1
        )
    with pytest.raises(ValueError, match="source face cap is 5"):
        load_native_face_witness_manifest(
            manifest, canonical_step_path=body_path, max_source_faces=5
        )
    with pytest.raises(ValueError, match="files total .* limit is 1"):
        load_native_face_witness_manifest(
            manifest, canonical_step_path=body_path, max_total_witness_bytes=1
        )


def test_manifest_rejects_duplicate_ids_and_negative_round_trip_error(box_witnesses) -> None:
    _shape, body_path, manifest = box_witnesses
    duplicate = copy.deepcopy(manifest)
    duplicate["witnesses"][1] = copy.deepcopy(duplicate["witnesses"][0])
    with pytest.raises(ValueError, match="duplicate source_face_id"):
        load_native_face_witness_manifest(duplicate, canonical_step_path=body_path)

    corrupted = copy.deepcopy(manifest)
    corrupted["witnesses"][0]["step_round_trip_relative_area_error"] = -1e-12
    with pytest.raises(ValueError, match="invalid STEP round-trip area error"):
        load_native_face_witness_manifest(corrupted, canonical_step_path=body_path)


def test_imprint_requires_manifest_to_name_the_exact_canonical_body(gmsh, box_witnesses) -> None:
    _shape, body_path, raw_manifest = box_witnesses
    manifest = _validated_manifest(body_path, raw_manifest)
    body_tag = _import_body(gmsh, body_path)
    with pytest.raises(ValueError, match="does not match imprinted solid"):
        imprint_native_face_witnesses(
            gmsh, body_tag, manifest, canonical_body_step_sha256="0" * 64
        )


def test_imprint_rejects_coherent_missing_witness_by_full_boundary_coverage(gmsh, box_witnesses) -> None:
    _shape, body_path, raw_manifest = box_witnesses
    manifest = _validated_manifest(body_path, raw_manifest)
    manifest["witnesses"] = manifest["witnesses"][:-1]
    manifest["witness_count"] = len(manifest["witnesses"])
    manifest["native_solid_face_count"] = len(manifest["witnesses"])
    body_tag = _import_body(gmsh, body_path)
    with pytest.raises(ValueError, match="does not cover every exterior surface"):
        imprint_native_face_witnesses(
            gmsh, body_tag, manifest, canonical_body_step_sha256=sha256_file(body_path)
        )


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("native_face_area_mm2", float("nan"), "native area must be a finite positive number"),
        ("step_round_trip_face_area_mm2", float("inf"), "STEP round-trip area must be a finite positive number"),
    ],
)
def test_imprint_rejects_nonfinite_declared_areas_before_gmsh(box_witnesses, field, value, error) -> None:
    _shape, body_path, raw_manifest = box_witnesses
    manifest = _validated_manifest(body_path, raw_manifest)
    manifest["witnesses"][0][field] = value
    with pytest.raises(ValueError, match=error):
        imprint_native_face_witnesses(
            object(), 1, manifest, canonical_body_step_sha256=sha256_file(body_path)
        )


def test_imprint_rejects_coincident_geometry_with_distinct_fid(gmsh, box_witnesses, tmp_path: Path) -> None:
    _shape, body_path, raw_manifest = box_witnesses
    manifest = _validated_manifest(body_path, raw_manifest)
    original = copy.deepcopy(manifest["witnesses"][0])
    face_id = "overlap-control"
    name = face_entity_name(face_id, original["role"])
    overlap_path = tmp_path / "coincident_distinct_identity.step"
    overlap_hash = _rewrite_witness(Path(original["witness_path"]), overlap_path, name)
    original.update({
        "source_face_id": face_id,
        "step_entity_name": name,
        "witness_path": str(overlap_path),
        "witness_sha256": overlap_hash,
        "witness_bytes": overlap_path.stat().st_size,
    })
    manifest["witnesses"].append(original)
    manifest["witness_count"] = len(manifest["witnesses"])
    manifest["native_solid_face_count"] = len(manifest["witnesses"])
    validated, _ = load_native_face_witness_manifest(manifest, canonical_step_path=body_path)
    body_tag = _import_body(gmsh, body_path)
    with pytest.raises(ValueError, match="multiple source-witness parents"):
        imprint_native_face_witnesses(
            gmsh, body_tag, validated, canonical_body_step_sha256=sha256_file(body_path)
        )


def test_imprint_rejects_translated_noncoincident_witness(gmsh, box_witnesses, tmp_path: Path) -> None:
    _shape, body_path, raw_manifest = box_witnesses
    manifest = _validated_manifest(body_path, raw_manifest)
    row = manifest["witnesses"][0]
    translated_path = tmp_path / "translated_witness.step"
    translated_hash = _rewrite_witness(
        Path(row["witness_path"]), translated_path, row["step_entity_name"], (250.0, 0.0, 0.0)
    )
    row["witness_path"] = str(translated_path)
    row["witness_sha256"] = translated_hash
    row["witness_bytes"] = translated_path.stat().st_size
    validated, _ = load_native_face_witness_manifest(manifest, canonical_step_path=body_path)
    body_tag = _import_body(gmsh, body_path)
    with pytest.raises(ValueError, match="duplicate or non-exterior raw descendants"):
        imprint_native_face_witnesses(
            gmsh, body_tag, validated, canonical_body_step_sha256=sha256_file(body_path)
        )


def test_cut_raw_map_rejects_interface_ancestry_before_exterior_filter(gmsh, box_witnesses) -> None:
    _shape, body_path, raw_manifest = box_witnesses
    manifest = _validated_manifest(body_path, raw_manifest)
    body_tag = _import_body(gmsh, body_path)
    imprint = imprint_native_face_witnesses(
        gmsh, body_tag, manifest, canonical_body_step_sha256=sha256_file(body_path)
    )
    old_surfaces = [int(tag) for tag in imprint["exterior_surface_tags"]]
    plane = gmsh.model.occ.addRectangle(-0.1, -0.1, 0.0, 0.2, 0.2)
    gmsh.model.occ.rotate([(2, plane)], 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.5 * 3.141592653589793)
    objects = [(3, int(imprint["output_volume_tag"]))] + [(2, tag) for tag in old_surfaces]
    _, parent_map = gmsh.model.occ.fragment(objects, [(2, plane)], removeObject=True, removeTool=True)
    gmsh.model.occ.synchronize()
    volumes = sorted({abs(int(tag)) for dim, tag in parent_map[0] if int(dim) == 3})
    boundaries = [
        {abs(int(tag)) for dim, tag in gmsh.model.getBoundary([(3, volume)], oriented=False, recursive=False) if int(dim) == 2}
        for volume in volumes
    ]
    shared = boundaries[0] & boundaries[1]
    exterior = boundaries[0] ^ boundaries[1]
    corrupted = copy.deepcopy(parent_map)
    source_row = next(index for index, values in enumerate(corrupted[1:-1], start=1) if values)
    corrupted[source_row].append((2, min(shared)))
    info_by_tag = {
        int(tag): type("Face", (), {"source_face_id": row["source_face_id"], "role": row["role"]})()
        for tag, row in imprint["source_info_by_surface_tag"].items()
    }
    with pytest.raises(ValueError, match="interface plane surface has source-witness ancestry"):
        validate_cut_witness_parent_map(
            gmsh,
            parent_map=corrupted,
            source_surface_tags=old_surfaces,
            source_info_by_surface_tag=info_by_tag,
            partition_volume_tags=volumes,
            shared_surface_tags=sorted(shared),
            exterior_surface_tags=sorted(exterior),
            imprint_report=imprint,
        )


def test_cut_raw_map_rejects_nonfinite_area_tolerance_before_parent_map_read() -> None:
    with pytest.raises(ValueError, match="area_relative_tolerance must be a finite positive number"):
        validate_cut_witness_parent_map(
            None,
            parent_map=[],
            source_surface_tags=[],
            source_info_by_surface_tag={},
            partition_volume_tags=[],
            shared_surface_tags=[],
            exterior_surface_tags=[],
            imprint_report={},
            area_relative_tolerance=float("nan"),
        )


def test_witness_mapping_drives_exact_role_local_size_forecast(gmsh, box_witnesses) -> None:
    shape, body_path, raw_manifest = box_witnesses
    manifest = _validated_manifest(body_path, raw_manifest)
    body_tag = _import_body(gmsh, body_path)
    imprint = imprint_native_face_witnesses(
        gmsh, body_tag, manifest, canonical_body_step_sha256=sha256_file(body_path)
    )
    info_by_tag = {
        int(tag): type("Face", (), {
            "source_face_id": row["source_face_id"],
            "role": row["role"],
        })()
        for tag, row in imprint["source_info_by_surface_tag"].items()
    }
    areas_by_tag = {
        int(tag): float(area)
        for tag, area in imprint["source_area_by_surface_tag_m2"].items()
    }
    forecast = _resource_forecast(
        source_volume_m3=float(shape.Volume()) * 1e-9,
        mesh_size_m=0.012,
        source_surface_areas_m2=areas_by_tag,
        interface_area_m2=1e-4,
        source_face_info=info_by_tag,
        boundary_size_by_source_face_m={},
        boundary_size_by_role_m={"base": 0.005},
        interface_size_m=0.01,
        caps=ResourceCaps(
            max_step_bytes=2_000_000,
            max_tetrahedra=100_000,
            max_memory_bytes=2 * 1024**3,
        ),
    )
    source_info = imprint["source_info_by_surface_tag"]
    actual_base_tags = {
        tag for tag, row in source_info.items() if row["role"] == "base"
    }
    assert len(actual_base_tags) == 1
    for tag, row in source_info.items():
        expected_size = 0.005 if row["role"] == "base" else 0.012
        assert forecast["boundary_mesh_size_by_imported_surface_tag_m"][tag] == pytest.approx(expected_size)
    assert forecast["estimated_tetrahedra"] > 0
