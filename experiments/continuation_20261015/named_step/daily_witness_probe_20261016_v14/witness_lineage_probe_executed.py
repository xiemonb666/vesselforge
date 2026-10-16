"""Bounded native-face witness ancestry probe for the daily Aberdeen candidate.

This experiment rebuilds one frozen daily candidate from its serialized meridian,
ties the rebuilt faces to the frozen face lineage by unique source-segment identity,
and tests OCC parent maps after STEP import. It does not mesh or run fracture
physics, and it does not claim literal TopoDS identity across STEP serialization.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import copy
import platform
from pathlib import Path
import sys
import traceback
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ASSET = ROOT / "vesselforge/experiments/continuation_20261015/reference_forms/outputs/daily_aberdeen_108x53_v6_final"
OUTPUT = HERE / "daily_witness_probe_20261016_v14"
GMSH_LIB = ROOT / "third_party/pgfrag-geometry-runtime/sdk/gmsh-4.15.2-Windows64-sdk/lib"
sys.path.insert(0, str(ROOT / "vesselforge/src"))

from vesselforge.named_step import (  # noqa: E402
    export_named_step_faces,
    export_native_face_witnesses,
    exact_gmsh_boundary_bindings,
    face_entity_name,
    sha256_file,
)
from vesselforge.revolved_profile import MeridianSection, MeridianSegment, build_revolved_solid  # noqa: E402


OCC_TOLERANCES = {
    "gmsh_geometry_tolerance_m": 1e-8,
    "gmsh_occ_bounds_use_stl": 1,
    "volume_relative": 5e-8,
    "cut_volume_conservation_relative": 1e-6,
    "surface_area_relative": 1e-5,
    "step_round_trip_face_area_relative": 1e-8,
    "bounds_relative_to_body_span": 2e-5,
    "half_volume_relative_to_equal_halves": 5e-5,
    "interpretation": "declared CAD-kernel comparison tolerances; not metrology bounds",
}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _environment_receipt(gmsh: Any) -> dict[str, Any]:
    return {
        "python_version": platform.python_version(),
        "cadquery_version": importlib.metadata.version("cadquery"),
        "opencascade_ocp_version": importlib.metadata.version("cadquery-ocp"),
        "numpy_version": importlib.metadata.version("numpy"),
        "gmsh_python_module_version": str(gmsh.__version__),
        "gmsh_api_version": [int(gmsh.GMSH_API_VERSION_MAJOR), int(gmsh.GMSH_API_VERSION_MINOR), int(gmsh.GMSH_API_VERSION_PATCH)],
        "gmsh_sdk_library_directory": str(GMSH_LIB),
    }


def _load_gmsh() -> Any:
    if not GMSH_LIB.is_dir():
        raise FileNotFoundError(f"Gmsh SDK not found: {GMSH_LIB}")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(GMSH_LIB))
    sys.path.insert(0, str(GMSH_LIB))
    import gmsh  # type: ignore[import-not-found]

    return gmsh


def _section_from_json(path: Path) -> MeridianSection:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema") != "vf.meridian_section.v1":
        raise ValueError("frozen source section has an unsupported schema")
    segments = tuple(
        MeridianSegment(
            role=str(row["role"]),
            kind=str(row["curve"]),
            points=tuple(tuple(point) for point in row["points_rz_mm"]),
        )
        for row in raw["segments"]
    )
    section = MeridianSection(segments=segments, name=str(raw["name"]))
    section.validate()
    return section


def _source_face_rows(
    native_shape: Any,
    original_lineage: dict[str, Any],
    rebuilt_lineage: dict[str, Any],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    source_faces = original_lineage.get("faces")
    rebuilt_faces = original_lineage.get("face_count")
    if not isinstance(source_faces, dict) or original_lineage.get("status") != "PASS":
        raise ValueError("frozen source face lineage is missing or not PASS")

    def identity_map(face_records: dict[str, Any], *, label: str) -> dict[tuple[str, tuple[int, ...]], int]:
        by_identity: dict[tuple[str, tuple[int, ...]], int] = {}
        for face_key, record in face_records.items():
            face_index = int(face_key)
            role = str(record["role"])
            segment_ids = tuple(sorted(int(v) for v in record["source_segment_indices"]))
            identity = (role, segment_ids)
            if not segment_ids or identity in by_identity:
                raise ValueError(f"{label} lineage has missing or duplicate segment identity {identity}")
            by_identity[identity] = face_index
        return by_identity

    frozen_map = identity_map(source_faces, label="frozen")
    # This lineage was returned with the exact same native shape passed here;
    # the face index is used only to retrieve that native child, never as an
    # identity across STEP import.
    if int(rebuilt_lineage["face_count"]) != int(rebuilt_faces):
        raise ValueError("reconstructed native face count differs from the frozen lineage artifact")
    rebuilt_map = identity_map(rebuilt_lineage["faces"], label="rebuilt")
    if rebuilt_map.keys() != frozen_map.keys():
        raise ValueError("rebuilt and frozen lineages do not have identical unique segment-role identities")
    if len(native_shape.Faces()) != len(frozen_map):
        raise ValueError("rebuilt body face count differs from its frozen source face lineage")

    old_index_by_new_index = {
        new_index: frozen_map[identity]
        for identity, new_index in rebuilt_map.items()
    }
    rows: list[dict[str, str]] = []
    identity_rows: list[dict[str, Any]] = []
    for new_index in range(len(native_shape.Faces())):
        old_index = old_index_by_new_index[new_index]
        identity_record = source_faces[str(old_index)]
        role = str(identity_record["role"])
        segment_ids = sorted(int(v) for v in identity_record["source_segment_indices"])
        rows.append({
            "source_face_id": f"original-brep-face-{old_index:03d}",
            "role": role,
        })
        identity_rows.append({
            "native_face_index": new_index,
            "source_original_brep_face_id": f"original-brep-face-{old_index:03d}",
            "source_original_brep_face_index": old_index,
            "role": role,
            "source_segment_indices": segment_ids,
            "identity_basis": "unique (role, sorted source_segment_indices) tuple in frozen and rebuilt native lineage",
        })
    return rows, identity_rows


def _bounding_box(gmsh: Any, dim: int, tag: int) -> list[float]:
    return [float(v) for v in gmsh.model.getBoundingBox(dim, tag)]


def _surface_area(gmsh: Any, tag: int) -> float:
    return float(gmsh.model.occ.getMass(2, int(tag)))


def _volume(gmsh: Any, tag: int) -> float:
    return float(gmsh.model.occ.getMass(3, int(tag)))


def _relative_difference(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1e-300)


def _set_model(gmsh: Any, name: str) -> None:
    gmsh.clear()
    gmsh.model.add(name)
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.option.setNumber("General.NumThreads", 1)
    gmsh.option.setNumber("Geometry.OCCImportLabels", 1)
    gmsh.option.setNumber("Geometry.Tolerance", OCC_TOLERANCES["gmsh_geometry_tolerance_m"])
    gmsh.option.setNumber("Geometry.OCCBoundsUseStl", OCC_TOLERANCES["gmsh_occ_bounds_use_stl"])
    gmsh.option.setString("Geometry.OCCTargetUnit", "M")


def _labels_failure_receipt(gmsh: Any, body_step: Path, rows: list[dict[str, str]], upstream_sha: str, lineage_sha: str) -> dict[str, Any]:
    _set_model(gmsh, "daily_named_step_label_probe")
    imported = gmsh.model.occ.importShapes(str(body_step), highestDimOnly=True)
    volumes = [int(tag) for dim, tag in imported if int(dim) == 3]
    if len(volumes) != 1:
        raise ValueError(f"labeled STEP probe imported {len(volumes)} volumes")
    gmsh.model.occ.synchronize()
    surfaces = sorted(
        abs(int(tag)) for dim, tag in gmsh.model.getBoundary([(3, volumes[0])], oriented=False, recursive=False)
        if int(dim) == 2
    )
    names = {str(tag): str(gmsh.model.getEntityName(2, tag)) for tag in surfaces}
    try:
        binding = exact_gmsh_boundary_bindings(
            gmsh,
            volumes[0],
            rows,
            step_path=body_step,
            upstream_step_sha256=upstream_sha,
            lineage_sha256=lineage_sha,
            labels_option_enabled=True,
        )
    except ValueError as error:
        return {
            "status": "FAIL_UNRESOLVED_GMSH_FACE_LABELS",
            "step_sha256": sha256_file(body_step),
            "gmsh_occ_import_labels": 1,
            "imported_volume_count": len(volumes),
            "imported_boundary_surface_count": len(surfaces),
            "imported_surface_entity_names": names,
            "failure": str(error),
            "interpretation": "STEP advanced-face names did not bind to Gmsh OCC boundary surfaces; witness ancestry is evaluated separately",
        }
    return {
        "status": "PASS_EXACT_GMSH_FACE_LABELS",
        "step_sha256": sha256_file(body_step),
        "imported_surface_entity_names": names,
        "binding": binding,
    }


def _import_one(gmsh: Any, path: Path, expected_dim: int) -> tuple[int, float]:
    entities = gmsh.model.occ.importShapes(str(path), highestDimOnly=True)
    expected = [(int(dim), int(tag)) for dim, tag in entities if int(dim) == expected_dim]
    if len(expected) != 1 or len(entities) != 1:
        raise ValueError(f"{path.name} must import as exactly one dimension-{expected_dim} entity; got {entities}")
    tag = expected[0][1]
    return tag, float(gmsh.model.occ.getMass(expected_dim, tag))


def _fragment_witnesses(
    gmsh: Any,
    body_step: Path,
    witness_manifest: dict[str, Any],
    *,
    expected_native_volume_m3: float,
    expected_native_bounds_m: list[float],
) -> dict[str, Any]:
    _set_model(gmsh, "daily_native_face_witness_imprint")
    body_entities = gmsh.model.occ.importShapes(str(body_step), highestDimOnly=True)
    body_volumes = [int(tag) for dim, tag in body_entities if int(dim) == 3]
    if len(body_volumes) != 1 or len(body_entities) != 1:
        raise ValueError(f"new body STEP must import as exactly one volume: {body_entities}")
    gmsh.model.occ.synchronize()
    body_tag = body_volumes[0]
    pre_volume = _volume(gmsh, body_tag)
    pre_bounds = _bounding_box(gmsh, 3, body_tag)
    import_volume_error = _relative_difference(expected_native_volume_m3, pre_volume)
    source_span = max(expected_native_bounds_m[i + 3] - expected_native_bounds_m[i] for i in range(3))
    import_bounds_error = max(abs(a - b) for a, b in zip(expected_native_bounds_m, pre_bounds, strict=True)) / max(source_span, 1e-300)
    if import_volume_error > OCC_TOLERANCES["volume_relative"]:
        raise ValueError(f"Gmsh STEP import volume differs from rebuilt native source: {import_volume_error}")
    if import_bounds_error > OCC_TOLERANCES["bounds_relative_to_body_span"]:
        raise ValueError(f"Gmsh STEP import bounds differ from rebuilt native source: {import_bounds_error}")
    manifest_rows = witness_manifest.get("witnesses")
    if witness_manifest.get("schema") != "vesselforge.native_face_witness_manifest.v1" or not isinstance(manifest_rows, list):
        raise ValueError("native witness manifest schema or rows are invalid")
    if witness_manifest.get("mapping_status") != "EXACT_NATIVE_FACE_WITNESSES":
        raise ValueError("native witness manifest is not marked exact")
    if str(witness_manifest.get("native_body_step_sha256", "")).lower() != sha256_file(body_step).lower():
        raise ValueError("native witness manifest is not bound to the exact body STEP being fragmented")
    for hash_key in ("source_step_sha256", "source_face_lineage_sha256"):
        if len(str(witness_manifest.get(hash_key, ""))) != 64:
            raise ValueError(f"native witness manifest has invalid {hash_key}")
    witness_inputs: list[tuple[int, int]] = []
    witness_records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in manifest_rows:
        face_id = str(row.get("source_face_id", ""))
        role = str(row.get("role", ""))
        expected_name = f"VF_FACE_{face_id}__{role}"
        path = Path(str(row.get("witness_path", ""))).resolve(strict=True)
        if face_id in seen_ids or row.get("step_entity_name") != expected_name:
            raise ValueError(f"duplicate or semantically inconsistent witness row {face_id!r}")
        seen_ids.add(face_id)
        if sha256_file(path) != str(row.get("witness_sha256", "")).lower():
            raise ValueError(f"witness content hash changed for {face_id}")
        text = path.read_text(encoding="ascii", errors="strict")
        if text.count(expected_name) != 1:
            raise ValueError(f"witness {face_id} does not contain one exact semantic ADVANCED_FACE name")
        tag, area = _import_one(gmsh, path, 2)
        native_area_mm2 = row.get("native_face_area_mm2")
        step_round_trip_area_mm2 = row.get("step_round_trip_face_area_mm2")
        if (
            isinstance(native_area_mm2, bool)
            or not isinstance(native_area_mm2, (int, float))
            or not math.isfinite(float(native_area_mm2))
            or float(native_area_mm2) <= 0.0
        ):
            raise ValueError(f"native witness manifest has invalid native face area for {face_id}")
        if (
            isinstance(step_round_trip_area_mm2, bool)
            or not isinstance(step_round_trip_area_mm2, (int, float))
            or not math.isfinite(float(step_round_trip_area_mm2))
            or float(step_round_trip_area_mm2) <= 0.0
        ):
            raise ValueError(f"native witness manifest has invalid STEP round-trip face area for {face_id}")
        if (
            isinstance(row.get("step_round_trip_relative_area_error"), bool)
            or not isinstance(row.get("step_round_trip_relative_area_error"), (int, float))
            or not math.isfinite(float(row["step_round_trip_relative_area_error"]))
            or float(row["step_round_trip_relative_area_error"])
            > OCC_TOLERANCES["step_round_trip_face_area_relative"]
        ):
            raise ValueError(f"native face STEP round-trip area differs beyond OCC tolerance for {face_id}")
        native_area_m2 = float(native_area_mm2) * 1e-6
        step_round_trip_area_m2 = float(step_round_trip_area_mm2) * 1e-6
        imported_vs_native_error = _relative_difference(area, native_area_m2)
        imported_vs_step_round_trip_error = _relative_difference(area, step_round_trip_area_m2)
        if imported_vs_native_error > OCC_TOLERANCES["surface_area_relative"]:
            raise ValueError(
                f"Gmsh-imported witness area differs from native face area for {face_id}: "
                f"relative_error={imported_vs_native_error}"
            )
        if imported_vs_step_round_trip_error > OCC_TOLERANCES["surface_area_relative"]:
            raise ValueError(
                f"Gmsh-imported witness area differs from STEP round-trip face area for {face_id}: "
                f"relative_error={imported_vs_step_round_trip_error}"
            )
        witness_inputs.append((2, tag))
        witness_records.append({
            "source_face_id": face_id,
            "role": role,
            "witness_step_sha256": row["witness_sha256"],
            "input_surface_tag": tag,
            "input_area_m2": area,
            "native_face_area_mm2": float(native_area_mm2),
            "expected_native_face_area_m2": native_area_m2,
            "step_round_trip_face_area_mm2": float(step_round_trip_area_mm2),
            "step_round_trip_face_area_m2": step_round_trip_area_m2,
            "step_round_trip_relative_area_error": float(row["step_round_trip_relative_area_error"]),
            "relative_imported_area_error_vs_native": imported_vs_native_error,
            "relative_imported_area_error_vs_step_round_trip": imported_vs_step_round_trip_error,
            "raw_parent_map_descendants": None,
        })
    if len(witness_records) != int(witness_manifest.get("witness_count", -1)) or not witness_records:
        raise ValueError("native witness manifest count is inconsistent")

    _, parent_map = gmsh.model.occ.fragment(
        [(3, body_tag)], witness_inputs, removeObject=True, removeTool=True
    )
    if len(parent_map) != 1 + len(witness_inputs):
        raise ValueError(f"OCC fragment parent map has wrong row count: {len(parent_map)}")
    volume_descendants = [(int(dim), abs(int(tag))) for dim, tag in parent_map[0]]
    volumes = sorted({tag for dim, tag in volume_descendants if dim == 3})
    if len(volumes) != 1 or any(dim != 3 for dim, _ in volume_descendants):
        raise ValueError(f"witness imprint changed the source into {volume_descendants}")
    gmsh.model.occ.synchronize()
    output_volume = volumes[0]
    boundary = sorted({
        abs(int(tag)) for dim, tag in gmsh.model.getBoundary([(3, output_volume)], oriented=False, recursive=False)
        if int(dim) == 2
    })
    if not boundary:
        raise ValueError("witness imprint produced a volume with no boundary surfaces")
    witness_to_surfaces: dict[str, list[int]] = {}
    surface_sources: dict[int, list[str]] = {}
    for index, record in enumerate(witness_records):
        raw_signed_map = [(int(dim), int(tag)) for dim, tag in parent_map[index + 1]]
        raw_map = [(dim, abs(tag)) for dim, tag in raw_signed_map]
        record["raw_parent_map_descendants"] = [
            {"dim": dim, "signed_tag": signed_tag, "tag": abs(signed_tag)}
            for dim, signed_tag in raw_signed_map
        ]
        if not raw_map or any(dim != 2 for dim, _ in raw_map):
            raise ValueError(f"witness {record['source_face_id']} has lost, internal, or non-surface raw descendants: {raw_map}")
        tags = [tag for _, tag in raw_map]
        if len(tags) != len(set(tags)) or not set(tags).issubset(boundary):
            raise ValueError(f"witness {record['source_face_id']} has duplicate or non-exterior descendants: {raw_map}")
        witness_to_surfaces[record["source_face_id"]] = tags
        for tag in tags:
            surface_sources.setdefault(tag, []).append(record["source_face_id"])
        desc_area = sum(_surface_area(gmsh, tag) for tag in tags)
        rel_area = _relative_difference(float(record["input_area_m2"]), desc_area)
        desc_native_error = _relative_difference(float(record["expected_native_face_area_m2"]), desc_area)
        record["descendant_area_m2"] = desc_area
        record["relative_area_error"] = rel_area
        record["relative_descendant_area_error_vs_native"] = desc_native_error
        if rel_area > OCC_TOLERANCES["surface_area_relative"]:
            raise ValueError(f"witness {record['source_face_id']} area changed beyond OCC tolerance: {rel_area}")
        if desc_native_error > OCC_TOLERANCES["surface_area_relative"]:
            raise ValueError(
                f"witness {record['source_face_id']} descendant area differs from native face area: "
                f"{desc_native_error}"
            )
    if set(surface_sources) != set(boundary):
        raise ValueError(f"witness ancestry does not cover all exterior surfaces: uncovered={sorted(set(boundary)-set(surface_sources))}")
    if any(len(ids) != 1 for ids in surface_sources.values()):
        raise ValueError(f"an exterior output surface has multiple source-witness parents: {surface_sources}")
    all_surfaces = sorted(int(tag) for dim, tag in gmsh.model.getEntities(2) if int(dim) == 2)
    if all_surfaces != boundary:
        raise ValueError(f"witness imprint has loose or unbound surface entities: boundary={boundary}, all={all_surfaces}")

    post_volume = _volume(gmsh, output_volume)
    post_bounds = _bounding_box(gmsh, 3, output_volume)
    rel_volume = _relative_difference(pre_volume, post_volume)
    body_span = max(pre_bounds[i + 3] - pre_bounds[i] for i in range(3))
    rel_bounds = max(abs(a - b) for a, b in zip(pre_bounds, post_bounds, strict=True)) / max(body_span, 1e-300)
    if rel_volume > OCC_TOLERANCES["volume_relative"] or rel_bounds > OCC_TOLERANCES["bounds_relative_to_body_span"]:
        raise ValueError(f"witness imprint changed source body: relative_volume={rel_volume}, relative_bounds={rel_bounds}")
    return {
        "status": "PASS_CAD_PARENT_MAP_WITHIN_DECLARED_OCC_TOLERANCES",
        "interpretation": "conditional CAD ancestry through STEP-imported exact native-face witnesses and OCC boolean parent maps; not literal TopoDS identity across STEP or exact metrology",
        "input_body_volume_m3": pre_volume,
        "relative_import_volume_error_vs_native": import_volume_error,
        "input_body_bounds_method": "Geometry.OCCBoundsUseStl=1; tessellation-derived OCC bounds",
        "relative_import_bounds_error_vs_native": import_bounds_error,
        "output_body_volume_m3": post_volume,
        "relative_volume_error": rel_volume,
        "input_body_bounds_m": pre_bounds,
        "output_body_bounds_m": post_bounds,
        "relative_bounds_error_to_body_span": rel_bounds,
        "output_volume_tags": volumes,
        "exterior_surface_tags": boundary,
        "all_model_surfaces_are_exterior": True,
        "all_exterior_surfaces_have_exactly_one_witness_parent": True,
        "witness_surface_ancestry": witness_records,
        "witness_to_exterior_surface_tags": witness_to_surfaces,
        "source_by_exterior_surface": {str(tag): ids[0] for tag, ids in sorted(surface_sources.items())},
        "raw_volume_parent_map": [
            {"dim": int(dim), "signed_tag": int(tag), "tag": abs(int(tag))}
            for dim, tag in parent_map[0]
        ],
    }


def _cut_and_compose_witness_ancestry(gmsh: Any, imprint: dict[str, Any]) -> dict[str, Any]:
    current_volume = int(imprint["output_volume_tags"][0])
    old_surface_to_source = {
        int(tag): str(source_id)
        for tag, source_id in imprint["source_by_exterior_surface"].items()
    }


    old_surfaces = sorted(old_surface_to_source)
    old_bounds = _bounding_box(gmsh, 3, current_volume)
    span = max(old_bounds[i + 3] - old_bounds[i] for i in range(3))
    plane = gmsh.model.occ.addRectangle(-2.0 * span, -2.0 * span, 0.0, 4.0 * span, 4.0 * span)
    gmsh.model.occ.rotate([(2, plane)], 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.5 * 3.141592653589793)
    objects = [(3, current_volume)] + [(2, tag) for tag in old_surfaces]
    _, parent_map = gmsh.model.occ.fragment(objects, [(2, plane)], removeObject=True, removeTool=True)
    if len(parent_map) != len(objects) + 1:
        raise ValueError("cut parent map does not have one row per body, witness-surface, and plane input")
    raw_signed_map = [[(int(dim), int(tag)) for dim, tag in row] for row in parent_map]
    raw_map = [[(dim, abs(tag)) for dim, tag in row] for row in raw_signed_map]
    gmsh.model.occ.synchronize()
    volume_desc = raw_map[0]
    cut_volumes = sorted({tag for dim, tag in volume_desc if dim == 3})
    if len(cut_volumes) != 2 or any(dim != 3 for dim, _ in volume_desc):
        raise ValueError(f"center-plane cut did not create exactly two volume descendants: {volume_desc}")
    plane_raw = raw_map[-1]
    if not plane_raw or any(dim != 2 for dim, _ in plane_raw):
        raise ValueError(f"plane has missing or non-surface raw parent descendants: {plane_raw}")
    plane_surfaces = {tag for _, tag in plane_raw}
    if len(plane_surfaces) != len(plane_raw):
        raise ValueError("plane parent map contains duplicate output surfaces")

    composed: dict[int, list[str]] = {}
    raw_surface_rows = []
    for offset, old_tag in enumerate(old_surfaces, start=1):
        descendants = raw_map[offset]
        raw_surface_rows.append({
            "input_imprinted_exterior_surface_tag": old_tag,
            "source_face_id": old_surface_to_source[old_tag],
            "raw_parent_map_descendants": [
                {"dim": dim, "signed_tag": signed_tag, "tag": abs(signed_tag)}
                for dim, signed_tag in raw_signed_map[offset]
            ],
        })
        if not descendants or any(dim != 2 for dim, _ in descendants):
            raise ValueError(f"exterior witness surface {old_tag} has lost/internal/non-surface descendants: {descendants}")
        for _, tag in descendants:
            composed.setdefault(tag, []).append(old_surface_to_source[old_tag])

    boundary_by_volume: list[set[int]] = []
    for volume_tag in cut_volumes:
        boundary_by_volume.append({
            abs(int(tag)) for dim, tag in gmsh.model.getBoundary([(3, volume_tag)], oriented=False, recursive=False)
            if int(dim) == 2
        })
    shared = boundary_by_volume[0] & boundary_by_volume[1]
    exterior = boundary_by_volume[0] ^ boundary_by_volume[1]
    if not shared or not shared.issubset(plane_surfaces):
        raise ValueError(f"raw plane parent map does not cover the interface: shared={sorted(shared)}, plane={sorted(plane_surfaces)}")
    if shared & set(composed):
        raise ValueError("interface has witness ancestry; plane interface must have zero source-witness ancestry")
    if set(composed) != exterior:
        raise ValueError(
            "source witness descendants do not exactly cover cut exterior: "
            f"uncovered={sorted(exterior - set(composed))}, extra={sorted(set(composed) - exterior)}"
        )
    if any(len(ids) != 1 for ids in composed.values()):
        raise ValueError(f"cut exterior surface has multiple witness parents: {composed}")
    plane_remainders = sorted(plane_surfaces - shared)
    plane_remainder_records = []
    for tag in plane_remainders:
        if tag in composed:
            raise ValueError(f"a non-interface plane descendant unexpectedly has source-witness ancestry: {tag}")
        plane_remainder_records.append({
            "surface_tag": tag,
            "area_m2": _surface_area(gmsh, tag),
            "bounds_m": _bounding_box(gmsh, 2, tag),
            "disposition": "removed as non-body remainder of the finite plane tool after preserving its raw parent map",
        })
    if plane_remainders:
        gmsh.model.occ.remove([(2, tag) for tag in plane_remainders], recursive=False)
        gmsh.model.occ.synchronize()
    all_surfaces = {int(tag) for dim, tag in gmsh.model.getEntities(2) if int(dim) == 2}
    if all_surfaces != shared | exterior:
        raise ValueError(f"cut leaves loose surfaces: boundary={sorted(shared|exterior)}, all={sorted(all_surfaces)}")
    pre_cut_area_by_source: dict[str, float] = {}
    for record in imprint["witness_surface_ancestry"]:
        source_id = str(record["source_face_id"])
        if source_id in pre_cut_area_by_source:
            raise ValueError(f"imprint ancestry repeats source face ID {source_id!r}")
        pre_cut_area_by_source[source_id] = float(record["descendant_area_m2"])
    post_cut_area_by_source = {source_id: 0.0 for source_id in pre_cut_area_by_source}
    for surface_tag, source_ids in composed.items():
        if len(source_ids) != 1:
            raise ValueError(f"cut exterior surface has multiple witness parents: {surface_tag}: {source_ids}")
        source_id = source_ids[0]
        if source_id not in post_cut_area_by_source:
            raise ValueError(f"cut ancestry contains unknown source face ID {source_id!r}")
        post_cut_area_by_source[source_id] += _surface_area(gmsh, surface_tag)
    if set(post_cut_area_by_source) != set(pre_cut_area_by_source):
        raise ValueError("cut source-face ancestry does not preserve the complete pre-cut source ID set")
    source_face_area_conservation = []
    for source_id in sorted(pre_cut_area_by_source):
        before_area = pre_cut_area_by_source[source_id]
        after_area = post_cut_area_by_source[source_id]
        relative_error = _relative_difference(before_area, after_area)
        if relative_error > OCC_TOLERANCES["surface_area_relative"]:
            raise ValueError(
                f"cut changed source face area beyond OCC tolerance for {source_id}: "
                f"before={before_area}, after={after_area}, relative_error={relative_error}"
            )
        source_face_area_conservation.append({
            "source_face_id": source_id,
            "pre_cut_imprinted_exterior_area_m2": before_area,
            "post_cut_exterior_descendant_area_sum_m2": after_area,
            "relative_area_error": relative_error,
            "declared_relative_tolerance": OCC_TOLERANCES["surface_area_relative"],
        })
    volume_values = [_volume(gmsh, tag) for tag in cut_volumes]
    total_before = float(imprint["output_body_volume_m3"])
    total_after = sum(volume_values)
    volume_sum_error = _relative_difference(total_before, total_after)
    half_rel_error = _relative_difference(volume_values[0], volume_values[1])
    if volume_sum_error > OCC_TOLERANCES["cut_volume_conservation_relative"]:
        raise ValueError(
            "cut failed volume conservation: "
            f"before={total_before}, after={total_after}, relative_error={volume_sum_error}"
        )
    if half_rel_error > OCC_TOLERANCES["half_volume_relative_to_equal_halves"]:
        raise ValueError(f"rotational vessel center cut was not two equal halves: {half_rel_error}")
    interface_area = sum(_surface_area(gmsh, tag) for tag in sorted(shared))
    if interface_area <= 0.0:
        raise ValueError("center cut interface has nonpositive area")
    return {
        "status": "PASS_CAD_PARENT_MAP_WITHIN_DECLARED_OCC_TOLERANCES",
        "cut_plane": {"equation": "x=0 m", "tool_surface_tag": plane, "interface_surface_tags": sorted(shared)},
        "cut_volume_tags": cut_volumes,
        "cut_volume_m3": volume_values,
        "relative_cut_volume_sum_error": volume_sum_error,
        "relative_equal_half_volume_error": half_rel_error,
        "interface_area_m2": interface_area,
        "source_face_area_conservation": source_face_area_conservation,
        "exterior_surface_tags": sorted(exterior),
        "witness_ancestry_covers_all_exterior": True,
        "interface_has_zero_witness_ancestry": True,
        "raw_plane_tool_remainder_surfaces": plane_remainder_records,
        "all_model_surfaces_are_volume_boundaries": True,
        "composed_source_by_exterior_surface": {str(tag): ids[0] for tag, ids in sorted(composed.items())},
        "raw_cut_parent_map_by_input": [
            {
                "input_index": index,
                "raw_descendants": [
                    {"dim": dim, "signed_tag": signed_tag, "tag": abs(signed_tag)}
                    for dim, signed_tag in row
                ],
            }
            for index, row in enumerate(raw_signed_map)
        ],
        "raw_witness_surface_parent_map_rows": raw_surface_rows,
        "raw_plane_parent_map": [
            {"dim": dim, "signed_tag": signed_tag, "tag": abs(signed_tag)}
            for dim, signed_tag in raw_signed_map[-1]
        ],
    }


def _rewrite_witness(
    source: Path,
    output: Path,
    entity_name: str,
    *,
    translation_mm: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> str:
    """Re-export one witness face, optionally translating it, under a new STEP name."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
    from OCP.TCollection import TCollection_HAsciiString
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.gp import gp_Trsf, gp_Vec

    reader = STEPControl_Reader()
    if reader.ReadFile(str(source)) != IFSelect_RetDone or int(reader.TransferRoots()) != 1:
        raise RuntimeError("could not read source witness for translated negative control")
    explorer = TopExp_Explorer(reader.OneShape(), TopAbs_FACE)
    faces = []
    while explorer.More():
        faces.append(explorer.Current())
        explorer.Next()
    if len(faces) != 1:
        raise ValueError("translated negative control requires exactly one source face")
    if any(float(value) != 0.0 for value in translation_mm):
        transform = gp_Trsf()
        transform.SetTranslation(gp_Vec(*map(float, translation_mm)))
        witness_face = BRepBuilderAPI_Transform(faces[0], transform, True).Shape()
    else:
        witness_face = faces[0]
    writer = STEPControl_Writer()
    if writer.Transfer(witness_face, STEPControl_AsIs) != IFSelect_RetDone:
        raise RuntimeError("could not STEP-export rewritten negative-control face")
    model = writer.Model()
    advanced_faces = [
        model.Value(i) for i in range(1, model.NbEntities() + 1)
        if model.Value(i).IsKind("StepShape_AdvancedFace")
    ]
    if len(advanced_faces) != 1:
        raise ValueError("rewritten negative-control STEP must have one ADVANCED_FACE")
    advanced_faces[0].SetName(TCollection_HAsciiString(entity_name))
    if writer.Write(str(output)) != IFSelect_RetDone:
        raise RuntimeError("could not write rewritten negative-control STEP")
    if output.read_text(encoding="ascii", errors="strict").count(entity_name) != 1:
        raise ValueError("rewritten negative-control STEP lost its semantic name")
    return sha256_file(output)


def _run_negative_witness_controls(
    gmsh: Any,
    body_step: Path,
    manifest: dict[str, Any],
    *,
    expected_native_volume_m3: float,
    expected_native_bounds_m: list[float],
    output_dir: Path,
) -> dict[str, Any]:
    controls: list[dict[str, Any]] = []

    def expect_rejection(label: str, bad_manifest: dict[str, Any], marker: str) -> None:
        try:
            _fragment_witnesses(
                gmsh,
                body_step,
                bad_manifest,
                expected_native_volume_m3=expected_native_volume_m3,
                expected_native_bounds_m=expected_native_bounds_m,
            )
        except ValueError as error:
            controls.append({"control": label, "status": "PASS_REJECTED", "rejection": str(error)})
            if marker.lower() not in str(error).lower():
                raise AssertionError(f"{label} failed for an unexpected reason: {error}") from error
            return
        raise AssertionError(f"negative witness control {label} was accepted")

    missing = copy.deepcopy(manifest)
    missing["witnesses"] = missing["witnesses"][:-1]
    missing["witness_count"] = len(missing["witnesses"])
    expect_rejection("coherent_missing_witness", missing, "cover")

    duplicate = copy.deepcopy(manifest)
    duplicate["witnesses"][-1] = copy.deepcopy(duplicate["witnesses"][0])
    expect_rejection("duplicate_witness_identity", duplicate, "duplicate")

    translated = copy.deepcopy(manifest)
    negative_dir = output_dir / "negative_controls"
    negative_dir.mkdir(exist_ok=False)
    row = translated["witnesses"][0]
    translated_path = negative_dir / "translated_witness.step"
    translated_hash = _rewrite_witness(
        Path(row["witness_path"]),
        translated_path,
        str(row["step_entity_name"]),
        translation_mm=(250.0, 0.0, 0.0),
    )
    row["witness_path"] = str(translated_path)
    row["witness_sha256"] = translated_hash
    expect_rejection("translated_noncoincident_witness", translated, "witness")
    overlap = copy.deepcopy(manifest)
    source_row = overlap["witnesses"][0]
    overlap_face_id = "overlap-control"
    overlap_name = face_entity_name(overlap_face_id, str(source_row["role"]))
    overlap_path = negative_dir / "coincident_distinct_identity_witness.step"
    overlap_hash = _rewrite_witness(
        Path(source_row["witness_path"]), overlap_path, overlap_name
    )
    overlap_row = copy.deepcopy(source_row)
    overlap_row.update({
        "source_face_id": overlap_face_id,
        "step_entity_name": overlap_name,
        "witness_path": str(overlap_path),
        "witness_sha256": overlap_hash,
        "witness_bytes": overlap_path.stat().st_size,
        "native_face_child_verified": False,
        "synthetic_duplicate_geometry_negative_control": True,
    })
    overlap["witnesses"].append(overlap_row)
    overlap["witness_count"] = len(overlap["witnesses"])
    expect_rejection(
        "coincident_geometry_with_distinct_source_identity",
        overlap,
        "multiple source-witness parents",
    )
    return {
        "status": "PASS_ALL_NEGATIVE_WITNESS_CONTROLS_REJECTED",
        "controls": controls,
        "translated_witness_sha256": translated_hash,
        "translated_witness_translation_mm": [250.0, 0.0, 0.0],
        "coincident_duplicate_witness_sha256": overlap_hash,
        "coincident_duplicate_source_face_id": overlap_face_id,
        "coincident_duplicate_geometry_identity": "re-exported from an existing witness with zero translation and a distinct STEP semantic name; adversarial control only",
    }
def run() -> dict[str, Any]:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to overwrite probe evidence directory: {OUTPUT}")
    OUTPUT.mkdir(parents=True)
    executed_probe_source = OUTPUT / "witness_lineage_probe_executed.py"
    executed_probe_source.write_bytes(Path(__file__).resolve().read_bytes())
    executed_probe_source_sha256 = sha256_file(executed_probe_source)
    section_path = ASSET / "geometry/section.json"
    original_step = ASSET / "geometry/solid.step"
    lineage_path = ASSET / "geometry/face_lineage.json"
    report_path = ASSET / "geometry_report.json"
    for path in (section_path, original_step, lineage_path, report_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    source_hashes = {path.name: sha256_file(path) for path in (section_path, original_step, lineage_path, report_path)}
    import cadquery as cq

    section = _section_from_json(section_path)
    native_shape, new_lineage = build_revolved_solid(section)
    frozen_lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    face_rows, face_identity = _source_face_rows(native_shape, frozen_lineage, new_lineage)
    if int(new_lineage["face_count"]) != len(face_rows):
        raise ValueError("new native builder lineage does not cover every reconstructed face")
    original_shape = cq.importers.importStep(str(original_step)).val()
    if not original_shape.isValid() or len(original_shape.Solids()) != 1:
        raise ValueError("frozen source STEP is not one valid solid")
    original_metrics = {"volume_mm3": float(original_shape.Volume()), "bounds_mm": [
        float(original_shape.BoundingBox().xmin), float(original_shape.BoundingBox().ymin), float(original_shape.BoundingBox().zmin),
        float(original_shape.BoundingBox().xmax), float(original_shape.BoundingBox().ymax), float(original_shape.BoundingBox().zmax),
    ]}
    rebuilt_metrics = {"volume_mm3": float(native_shape.Volume()), "bounds_mm": [
        float(native_shape.BoundingBox().xmin), float(native_shape.BoundingBox().ymin), float(native_shape.BoundingBox().zmin),
        float(native_shape.BoundingBox().xmax), float(native_shape.BoundingBox().ymax), float(native_shape.BoundingBox().zmax),
    ]}
    source_metrics = json.loads(report_path.read_text(encoding="utf-8"))["measurements"]
    body_relative_volume = _relative_difference(original_metrics["volume_mm3"], rebuilt_metrics["volume_mm3"])
    body_span_mm = max(original_metrics["bounds_mm"][i + 3] - original_metrics["bounds_mm"][i] for i in range(3))
    body_relative_bounds = max(abs(a - b) for a, b in zip(original_metrics["bounds_mm"], rebuilt_metrics["bounds_mm"], strict=True)) / body_span_mm
    if body_relative_volume > 1e-8 or body_relative_bounds > 2e-7:
        raise ValueError(f"rebuilt native body differs from frozen STEP beyond validation: volume={body_relative_volume}, bounds={body_relative_bounds}")
    report_volume = float(source_metrics["solid_volume_mm3"])
    if _relative_difference(report_volume, rebuilt_metrics["volume_mm3"]) > 1e-8:
        raise ValueError("rebuilt volume differs from frozen geometry report")

    body_step = OUTPUT / "daily_native_named.step"
    body_export = export_named_step_faces(native_shape, face_rows, body_step)
    witness_manifest = export_native_face_witnesses(
        native_shape,
        face_rows,
        OUTPUT / "native_face_witnesses",
        source_step_sha256=source_hashes["solid.step"],
        lineage_sha256=source_hashes["face_lineage.json"],
        native_body_step_sha256=body_export["step_sha256"],
    )
    _write_json(OUTPUT / "native_face_identity.json", {
        "schema": "vesselforge.daily_native_face_identity.v1",
        "source_asset_relative_path": str(ASSET.relative_to(ROOT)),
        "source_hashes": source_hashes,
        "face_identity_basis": "unique role + sorted source_segment_indices tuple joined between frozen face_lineage.json and a fresh build_revolved_solid(section.json)",
        "faces": face_identity,
    })
    _write_json(OUTPUT / "witness_manifest.json", witness_manifest)

    gmsh = _load_gmsh()
    gmsh.initialize()
    producer_environment = _environment_receipt(gmsh)
    producer_code_sha256 = {
        "named_step.py": sha256_file(ROOT / "vesselforge/src/vesselforge/named_step.py"),
        "revolved_profile.py": sha256_file(ROOT / "vesselforge/src/vesselforge/revolved_profile.py"),
        "witness_lineage_probe.py": sha256_file(Path(__file__).resolve()),
        "witness_lineage_probe_executed.py": executed_probe_source_sha256,
    }
    native_identity_sha = sha256_file(OUTPUT / "native_face_identity.json")
    witness_manifest_sha = sha256_file(OUTPUT / "witness_manifest.json")
    receipt: dict[str, Any] = {
        "schema": "vesselforge.daily_native_face_witness_probe.v1",
        "status": "RUNNING",
        "source_asset_relative_path": str(ASSET.relative_to(ROOT)),
        "source_hashes": source_hashes,
        "producer_environment": producer_environment,
        "producer_code_sha256": producer_code_sha256,
        "executed_probe_source_path": str(executed_probe_source),
        "executed_probe_source_sha256": executed_probe_source_sha256,
        "native_body_step_sha256": body_export["step_sha256"],
        "native_face_identity_sha256": native_identity_sha,
        "native_face_witness_manifest_sha256": witness_manifest_sha,
        "witness_step_sha256_by_source_face": {
            str(row["source_face_id"]): str(row["witness_sha256"])
            for row in witness_manifest["witnesses"]
        },
        "source_geometry_validation": {
            "native_face_count": len(face_rows),
            "source_segment_identity_rows": face_identity,
            "original_step_metrics": original_metrics,
            "rebuilt_native_metrics": rebuilt_metrics,
            "relative_volume_difference": body_relative_volume,
            "relative_bounds_difference_to_body_span": body_relative_bounds,
            "geometry_report_volume_mm3": report_volume,
            "geometry_report_relative_volume_difference": _relative_difference(report_volume, rebuilt_metrics["volume_mm3"]),
        },
        "new_native_body_step": body_export,
        "native_face_witness_manifest": witness_manifest,
        "declared_occ_tolerances": OCC_TOLERANCES,
        "label_import": None,
        "witness_imprint": None,
        "plane_cut_and_composed_ancestry": None,
        "physics_or_mesh": "NOT_RUN",
    }
    try:
        receipt["label_import"] = _labels_failure_receipt(
            gmsh, body_step, face_rows, source_hashes["solid.step"], source_hashes["face_lineage.json"]
        )
        _write_json(OUTPUT / "label_import_receipt.json", {
            "schema": "vesselforge.daily_named_step_label_probe.v1",
            "source_hashes": source_hashes,
            "producer_environment": producer_environment,
            "producer_code_sha256": producer_code_sha256,
            "executed_probe_source_path": str(executed_probe_source),
            "executed_probe_source_sha256": executed_probe_source_sha256,
            "native_body_step_sha256": body_export["step_sha256"],
            "result": receipt["label_import"],
        })
        imprint = _fragment_witnesses(
            gmsh,
            body_step,
            witness_manifest,
            expected_native_volume_m3=rebuilt_metrics["volume_mm3"] * 1e-9,
            expected_native_bounds_m=[value * 1e-3 for value in rebuilt_metrics["bounds_mm"]],
        )
        receipt["witness_imprint"] = imprint
        receipt["plane_cut_and_composed_ancestry"] = _cut_and_compose_witness_ancestry(gmsh, imprint)
        receipt["negative_witness_controls"] = _run_negative_witness_controls(
            gmsh,
            body_step,
            witness_manifest,
            expected_native_volume_m3=rebuilt_metrics["volume_mm3"] * 1e-9,
            expected_native_bounds_m=[value * 1e-3 for value in rebuilt_metrics["bounds_mm"]],
            output_dir=OUTPUT,
        )
        receipt["status"] = "PASS_CAD_PARENT_MAP_WITHIN_DECLARED_OCC_TOLERANCES"
    except BaseException as error:
        receipt["status"] = "FAIL"
        receipt["failure"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
        raise
    finally:
        _write_json(OUTPUT / "receipt.json", receipt)
        _write_json(OUTPUT / "witness_ancestry_receipt.json", {
            "schema": "vesselforge.daily_native_face_witness_probe.v1",
            "status": receipt["status"],
            "source_hashes": source_hashes,
            "native_body_step_sha256": body_export["step_sha256"],
            "native_face_identity_sha256": native_identity_sha,
            "native_face_witness_manifest_sha256": witness_manifest_sha,
            "label_import_receipt_sha256": sha256_file(OUTPUT / "label_import_receipt.json"),
            "producer_environment": producer_environment,
            "producer_code_sha256": producer_code_sha256,
            "declared_occ_tolerances": OCC_TOLERANCES,
            "source_geometry_validation": receipt["source_geometry_validation"],
            "witness_imprint": receipt["witness_imprint"],
            "plane_cut_and_composed_ancestry": receipt["plane_cut_and_composed_ancestry"],
            "negative_witness_controls": receipt.get("negative_witness_controls"),
            "failure": receipt.get("failure"),
            "physics_or_mesh": "NOT_RUN",
        })
        gmsh.finalize()
    return receipt


if __name__ == "__main__":
    result = run()
    print(json.dumps({
        "status": result["status"],
        "output": str(OUTPUT),
        "label_import_status": result["label_import"]["status"],
        "imprint_status": result["witness_imprint"]["status"],
        "cut_status": result["plane_cut_and_composed_ancestry"]["status"],
        "source_face_count": result["source_geometry_validation"]["native_face_count"],
    }, indent=2))
