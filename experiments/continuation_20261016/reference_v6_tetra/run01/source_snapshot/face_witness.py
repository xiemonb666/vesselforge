"""Verified OCC ancestry from individually exported native STEP face witnesses.

This module maps semantic source-face IDs through exact CAD boolean parent maps.
It never derives identity from coordinates, tessellation, proximity, or entity
ordering. STEP round-tripping does not preserve literal ``TopoDS`` identity; the
certificate is conditional on the declared OpenCascade tolerances.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from .named_step import face_entity_name, sha256_file


NATIVE_FACE_WITNESS_SCHEMA = "vesselforge.native_face_witness_manifest.v1"
DEFAULT_WITNESS_TOLERANCES = {
    "step_round_trip_face_area_relative": 1e-8,
    "surface_area_relative": 1e-5,
    "volume_relative": 5e-8,
    "bounds_relative_to_body_span": 2e-5,
    "interpretation": "declared CAD-kernel tolerances; not exact metrology or literal TopoDS identity",
}
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


class FaceWitnessInfo:
    """The semantic identity propagated from one witness input face."""

    __slots__ = ("source_face_id", "role")

    def __init__(self, source_face_id: str, role: str):
        self.source_face_id = source_face_id
        self.role = role


def _relative_difference(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1e-300)


def _finite_positive(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite positive number")
    converted = float(value)
    if not math.isfinite(converted) or converted <= 0.0:
        raise ValueError(f"{label} must be a finite positive number")
    return converted


def _read_manifest(source: str | Path | Mapping[str, Any]) -> tuple[dict[str, Any], Path | None, str]:
    if isinstance(source, (str, Path)):
        path = Path(source).expanduser().resolve(strict=True)
        raw = json.loads(path.read_text(encoding="utf-8"))
        digest = sha256_file(path)
        base = path.parent
    elif isinstance(source, Mapping):
        raw = dict(source)
        encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        base = None
    else:
        raise TypeError("native_face_witness_manifest must be a JSON path or mapping")
    if not isinstance(raw, dict):
        raise ValueError("native face witness manifest must contain a JSON object")
    return raw, base, digest


def _inspect_step_surface(path: Path) -> float:
    """Validate a one-face open STEP witness and return its area in STEP units²."""
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise ValueError(f"OCP could not read witness STEP {path}")
    if int(reader.NbRootsForTransfer()) != 1 or int(reader.TransferRoots()) != 1:
        raise ValueError(f"witness STEP {path.name} must have exactly one transfer root")
    shape = reader.OneShape()
    faces: list[Any] = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        faces.append(explorer.Current())
        explorer.Next()
    solids = TopExp_Explorer(shape, TopAbs_SOLID)
    if len(faces) != 1 or solids.More():
        raise ValueError(f"witness STEP {path.name} must be exactly one open surface face")
    if not BRepCheck_Analyzer(faces[0]).IsValid():
        raise ValueError(f"witness STEP {path.name} contains an invalid face")
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(faces[0], props)
    return _finite_positive(float(props.Mass()), f"round-trip area in {path.name}")


def load_native_face_witness_manifest(
    source: str | Path | Mapping[str, Any],
    *,
    canonical_step_path: str | Path,
    expected_upstream_source_step_sha256: str | None = None,
    expected_source_face_lineage_sha256: str | None = None,
    tolerances: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate a witness manifest against the exact canonical body and files."""
    tolerance_values = dict(DEFAULT_WITNESS_TOLERANCES)
    if tolerances is not None:
        tolerance_values.update(tolerances)
    step_area_tol = _finite_positive(
        tolerance_values["step_round_trip_face_area_relative"],
        "step_round_trip_face_area_relative",
    )
    canonical_step = Path(canonical_step_path).expanduser().resolve(strict=True)
    canonical_hash = sha256_file(canonical_step)
    manifest, base, manifest_hash = _read_manifest(source)
    if manifest.get("schema") != NATIVE_FACE_WITNESS_SCHEMA:
        raise ValueError("native face witness manifest has an unsupported schema")
    if manifest.get("mapping_status") != "EXACT_NATIVE_FACE_WITNESSES":
        raise ValueError("native face witness manifest is not marked exact")
    body_hash = str(manifest.get("native_body_step_sha256", ""))
    if not _SHA256.fullmatch(body_hash) or body_hash.lower() != canonical_hash.lower():
        raise ValueError(
            "native face witness manifest body SHA-256 does not match canonical STEP input"
        )
    upstream_hash = str(manifest.get("source_step_sha256", ""))
    lineage_hash = str(manifest.get("source_face_lineage_sha256", ""))
    if not _SHA256.fullmatch(upstream_hash):
        raise ValueError("native face witness manifest has invalid upstream source STEP SHA-256")
    if not _SHA256.fullmatch(lineage_hash):
        raise ValueError("native face witness manifest has invalid source-face lineage SHA-256")
    for label, expected, actual in (
        ("upstream source STEP", expected_upstream_source_step_sha256, upstream_hash),
        ("source-face lineage", expected_source_face_lineage_sha256, lineage_hash),
    ):
        if expected is not None:
            if not _SHA256.fullmatch(str(expected)):
                raise ValueError(f"expected {label} SHA-256 must be a 64-character hex digest")
            if str(expected).lower() != actual.lower():
                raise ValueError(f"native face witness manifest {label} SHA-256 mismatch")

    rows = manifest.get("witnesses")
    if not isinstance(rows, list) or not rows:
        raise ValueError("native face witness manifest must contain witness rows")
    count = manifest.get("witness_count")
    if isinstance(count, bool) or not isinstance(count, int) or count != len(rows):
        raise ValueError("native face witness manifest witness_count is inconsistent")
    native_count = manifest.get("native_solid_face_count")
    if isinstance(native_count, bool) or not isinstance(native_count, int) or native_count <= 0:
        raise ValueError("native face witness manifest has invalid native_solid_face_count")

    seen_ids: set[str] = set()
    validated_rows: list[dict[str, Any]] = []
    for index, original_row in enumerate(rows):
        if not isinstance(original_row, Mapping):
            raise ValueError(f"native face witness row {index} must be an object")
        row = dict(original_row)
        face_id = str(row.get("source_face_id", ""))
        role = str(row.get("role", ""))
        if not face_id.strip() or not role.strip():
            raise ValueError(f"native face witness row {index} has an empty source ID or role")
        expected_name = face_entity_name(face_id, role)
        if face_id in seen_ids:
            raise ValueError(f"duplicate source_face_id in native face witness manifest: {face_id}")
        seen_ids.add(face_id)
        if row.get("native_face_child_verified") is not True:
            raise ValueError(f"native face witness {face_id} lacks exact native-child verification")
        if row.get("step_entity_name") != expected_name:
            raise ValueError(f"native face witness {face_id} has inconsistent semantic STEP name")
        if row.get("witness_face_entity_count") != 1 or row.get("witness_solid_count") != 0:
            raise ValueError(f"native face witness {face_id} is not one open STEP face")
        native_area_mm2 = _finite_positive(row.get("native_face_area_mm2"), f"{face_id} native area")
        declared_round_trip_area_mm2 = _finite_positive(
            row.get("step_round_trip_face_area_mm2"), f"{face_id} STEP round-trip area"
        )
        declared_error = row.get("step_round_trip_relative_area_error")
        if (
            isinstance(declared_error, bool)
            or not isinstance(declared_error, (int, float))
            or not math.isfinite(float(declared_error))
            or float(declared_error) > step_area_tol
        ):
            raise ValueError(f"native face witness {face_id} declares an invalid STEP round-trip area error")
        witness_path = Path(str(row.get("witness_path", ""))).expanduser()
        if not witness_path.is_absolute() and base is not None:
            witness_path = base / witness_path
        witness_path = witness_path.resolve(strict=True)
        witness_hash = str(row.get("witness_sha256", ""))
        if not _SHA256.fullmatch(witness_hash) or sha256_file(witness_path).lower() != witness_hash.lower():
            raise ValueError(f"native face witness {face_id} file SHA-256 mismatch")
        step_text = witness_path.read_text(encoding="ascii", errors="strict")
        if step_text.count(expected_name) != 1:
            raise ValueError(f"native face witness {face_id} must contain its exact STEP name once")
        observed_area_mm2 = _inspect_step_surface(witness_path)
        observed_error = _relative_difference(native_area_mm2, observed_area_mm2)
        declared_area_error = _relative_difference(declared_round_trip_area_mm2, observed_area_mm2)
        if observed_error > step_area_tol or declared_area_error > step_area_tol:
            raise ValueError(
                f"native and STEP round-trip areas disagree for {face_id}: "
                f"native_error={observed_error}, declared_error={declared_area_error}"
            )
        row.update({
            "witness_path": str(witness_path),
            "native_face_area_mm2": native_area_mm2,
            "step_round_trip_face_area_mm2": observed_area_mm2,
            "step_round_trip_relative_area_error_observed": observed_error,
        })
        validated_rows.append(row)
    manifest["witnesses"] = validated_rows
    report = {
        "status": "VALIDATED_NATIVE_FACE_WITNESS_MANIFEST",
        "manifest_sha256": manifest_hash,
        "manifest_path": str(Path(source).resolve()) if isinstance(source, (str, Path)) else None,
        "canonical_step_path": str(canonical_step),
        "canonical_step_sha256": canonical_hash,
        "native_body_step_sha256": body_hash.lower(),
        "upstream_source_step_sha256": upstream_hash.lower(),
        "source_face_lineage_sha256": lineage_hash.lower(),
        "native_solid_face_count": native_count,
        "witness_count": count,
        "step_round_trip_area_relative_tolerance": step_area_tol,
    }
    return manifest, report


def _raw_parent_rows(parent_map: Sequence[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for input_index, descendants in enumerate(parent_map):
        raw_descendants: list[dict[str, int]] = []
        for raw_dim, raw_tag in descendants:
            dim, signed_tag = int(raw_dim), int(raw_tag)
            if dim < 0 or signed_tag == 0:
                raise ValueError("OCC parent map contains an invalid dimension or zero tag")
            raw_descendants.append({"dim": dim, "signed_tag": signed_tag, "tag": abs(signed_tag)})
        rows.append({"input_index": input_index, "raw_descendants": raw_descendants})
    return rows


def imprint_native_face_witnesses(
    gmsh: Any,
    body_volume_tag: int,
    manifest: Mapping[str, Any],
    *,
    canonical_body_step_sha256: str,
    area_relative_tolerance: float = 1e-5,
    volume_relative_tolerance: float = 5e-8,
    bounds_relative_to_body_span_tolerance: float = 2e-5,
) -> dict[str, Any]:
    """Import and OCC-imprint exact surface witnesses onto one canonical solid."""
    if not _SHA256.fullmatch(str(canonical_body_step_sha256)):
        raise ValueError("canonical_body_step_sha256 must be a 64-character SHA-256 digest")
    if str(manifest.get("native_body_step_sha256", "")).lower() != str(canonical_body_step_sha256).lower():
        raise ValueError("native face witness manifest body SHA-256 does not match imprinted solid")
    if manifest.get("schema") != NATIVE_FACE_WITNESS_SCHEMA or manifest.get("mapping_status") != "EXACT_NATIVE_FACE_WITNESSES":
        raise ValueError("imprint requires a validated exact native-face witness manifest")
    if manifest.get("witness_count") != len(manifest.get("witnesses", [])):
        raise ValueError("imprint witness rows do not match manifest witness_count")
    for name, value in (
        ("area_relative_tolerance", area_relative_tolerance),
        ("volume_relative_tolerance", volume_relative_tolerance),
        ("bounds_relative_to_body_span_tolerance", bounds_relative_to_body_span_tolerance),
    ):
        _finite_positive(value, name)
    body_volume_tag = int(body_volume_tag)
    body_entities = [(3, body_volume_tag)]
    body_surfaces = sorted({
        abs(int(tag))
        for dim, tag in gmsh.model.getBoundary(body_entities, oriented=False, recursive=False)
        if int(dim) == 2
    })
    if not body_surfaces:
        raise ValueError("canonical solid has no boundary surfaces before witness imprint")
    before_volume = float(gmsh.model.occ.getMass(3, body_volume_tag))
    if not math.isfinite(before_volume) or before_volume <= 0.0:
        raise ValueError("canonical solid has invalid volume before witness imprint")
    before_bounds = [float(value) for value in gmsh.model.getBoundingBox(3, body_volume_tag)]
    if len(before_bounds) != 6 or not all(math.isfinite(value) for value in before_bounds):
        raise ValueError("canonical solid has invalid bounds before witness imprint")
    span = max(before_bounds[i + 3] - before_bounds[i] for i in range(3))
    if not math.isfinite(span) or span <= 0.0:
        raise ValueError("canonical solid has degenerate bounds before witness imprint")

    witness_inputs: list[tuple[int, int]] = []
    witness_records: list[dict[str, Any]] = []
    for row in manifest["witnesses"]:
        face_id = str(row["source_face_id"])
        role = str(row["role"])
        expected_name = face_entity_name(face_id, role)
        if row.get("native_face_child_verified") is not True or row.get("step_entity_name") != expected_name:
            raise ValueError(f"witness {face_id} lacks exact native-child/name verification")
        witness_path = Path(str(row["witness_path"])).expanduser().resolve(strict=True)
        if sha256_file(witness_path).lower() != str(row.get("witness_sha256", "")).lower():
            raise ValueError(f"witness file hash changed for {face_id}")
        if witness_path.read_text(encoding="ascii", errors="strict").count(expected_name) != 1:
            raise ValueError(f"witness {face_id} does not have one exact STEP entity name")
        entities = gmsh.model.occ.importShapes(str(row["witness_path"]), highestDimOnly=True)
        surfaces = [(int(dim), int(tag)) for dim, tag in entities if int(dim) == 2]
        if len(entities) != 1 or len(surfaces) != 1:
            raise ValueError(f"witness {face_id} must import as exactly one surface entity")
        input_tag = surfaces[0][1]
        input_area = float(gmsh.model.occ.getMass(2, input_tag))
        native_area_m2 = float(row["native_face_area_mm2"]) * 1e-6
        step_area_m2 = float(row["step_round_trip_face_area_mm2"]) * 1e-6
        if not math.isfinite(input_area) or input_area <= 0.0:
            raise ValueError(f"Gmsh-imported witness {face_id} has invalid surface area")
        import_native_error = _relative_difference(input_area, native_area_m2)
        import_step_error = _relative_difference(input_area, step_area_m2)
        if import_native_error > area_relative_tolerance or import_step_error > area_relative_tolerance:
            raise ValueError(
                f"Gmsh witness area differs from native/STEP area for {face_id}: "
                f"native_error={import_native_error}, step_error={import_step_error}"
            )
        witness_inputs.append((2, input_tag))
        witness_records.append({
            "source_face_id": face_id,
            "role": role,
            "step_entity_name": str(row["step_entity_name"]),
            "witness_step_sha256": str(row["witness_sha256"]).lower(),
            "input_surface_tag": input_tag,
            "native_face_area_mm2": float(row["native_face_area_mm2"]),
            "native_face_area_m2": native_area_m2,
            "step_round_trip_face_area_mm2": float(row["step_round_trip_face_area_mm2"]),
            "step_round_trip_face_area_m2": step_area_m2,
            "gmsh_imported_area_m2": input_area,
            "relative_import_area_error_vs_native": import_native_error,
            "relative_import_area_error_vs_step_round_trip": import_step_error,
            "raw_parent_map_descendants": None,
        })

    if len({tag for dim, tag in witness_inputs if dim == 2}) != len(witness_inputs):
        raise ValueError("native face witnesses did not receive unique Gmsh surface tags")
    _, parent_map = gmsh.model.occ.fragment(
        [(3, body_volume_tag)], witness_inputs, removeObject=True, removeTool=True
    )
    raw_rows = _raw_parent_rows(parent_map)
    if len(parent_map) != len(witness_inputs) + 1:
        raise ValueError("OCC witness imprint returned an incomplete raw parent map")
    body_raw = raw_rows[0]["raw_descendants"]
    body_desc = [(row["dim"], row["tag"]) for row in body_raw]
    if not body_desc or any(dim != 3 for dim, _ in body_desc):
        raise ValueError(f"witness imprint body parent map contains non-volume/lost descendants: {body_desc}")
    output_volumes = sorted({tag for _dim, tag in body_desc})
    if len(output_volumes) != 1:
        raise ValueError(f"witness imprint must preserve exactly one solid volume: {output_volumes}")
    gmsh.model.occ.synchronize()
    output_volume = output_volumes[0]
    boundary = sorted({
        abs(int(tag))
        for dim, tag in gmsh.model.getBoundary([(3, output_volume)], oriented=False, recursive=False)
        if int(dim) == 2
    })
    if not boundary:
        raise ValueError("witness imprint output solid has no boundary surfaces")

    source_by_surface: dict[int, list[dict[str, str]]] = defaultdict(list)
    witness_to_surfaces: dict[str, list[int]] = {}
    source_face_area_by_fid: dict[str, float] = defaultdict(float)
    witness_parent_rows: list[dict[str, Any]] = []
    for index, record in enumerate(witness_records, start=1):
        raw_descendants = raw_rows[index]["raw_descendants"]
        record["raw_parent_map_descendants"] = raw_descendants
        dims = [row["dim"] for row in raw_descendants]
        tags = [row["tag"] for row in raw_descendants]
        if not raw_descendants or any(dim != 2 for dim in dims):
            raise ValueError(
                f"witness {record['source_face_id']} has lost/internal/non-surface raw descendants: {raw_descendants}"
            )
        if len(tags) != len(set(tags)) or not set(tags).issubset(boundary):
            raise ValueError(
                f"witness {record['source_face_id']} has duplicate or non-exterior raw descendants: {raw_descendants}"
            )
        witness_to_surfaces[record["source_face_id"]] = tags
        for tag in tags:
            source_by_surface[tag].append({
                "source_face_id": record["source_face_id"],
                "role": record["role"],
            })
        descendant_areas = [float(gmsh.model.occ.getMass(2, tag)) for tag in tags]
        if not all(math.isfinite(area) and area > 0.0 for area in descendant_areas):
            raise ValueError(f"witness {record['source_face_id']} has a nonfinite or nonpositive descendant area")
        descendant_area = sum(descendant_areas)
        import_area = float(record["gmsh_imported_area_m2"])
        native_area = float(record["native_face_area_m2"])
        import_error = _relative_difference(import_area, descendant_area)
        native_error = _relative_difference(native_area, descendant_area)
        if import_error > area_relative_tolerance or native_error > area_relative_tolerance:
            raise ValueError(
                f"witness {record['source_face_id']} descendant area differs beyond tolerance: "
                f"import_error={import_error}, native_error={native_error}"
            )
        record.update({
            "descendant_area_m2": descendant_area,
            "relative_descendant_area_error_vs_import": import_error,
            "relative_descendant_area_error_vs_native": native_error,
        })
        source_face_area_by_fid[record["source_face_id"]] += descendant_area
        witness_parent_rows.append({
            "input_index": index,
            "source_face_id": record["source_face_id"],
            "role": record["role"],
            "raw_descendants": raw_descendants,
        })

    if set(source_by_surface) != set(boundary):
        raise ValueError(
            "witness ancestry does not cover every exterior surface: "
            f"uncovered={sorted(set(boundary) - set(source_by_surface))}, "
            f"extra={sorted(set(source_by_surface) - set(boundary))}"
        )
    ambiguous = {tag: rows for tag, rows in source_by_surface.items() if len(rows) != 1}
    if ambiguous:
        raise ValueError(f"an exterior output surface has multiple source-witness parents: {ambiguous}")
    all_surfaces = {int(tag) for dim, tag in gmsh.model.getEntities(2) if int(dim) == 2}
    if all_surfaces != set(boundary):
        raise ValueError(
            f"witness imprint leaves loose/unbound surfaces: boundary={sorted(boundary)}, all={sorted(all_surfaces)}"
        )

    after_volume = float(gmsh.model.occ.getMass(3, output_volume))
    after_bounds = [float(value) for value in gmsh.model.getBoundingBox(3, output_volume)]
    if not math.isfinite(after_volume) or after_volume <= 0.0:
        raise ValueError("witness imprint output body has invalid volume")
    if len(after_bounds) != 6 or not all(math.isfinite(value) for value in after_bounds):
        raise ValueError("witness imprint output body has invalid bounds")
    volume_error = _relative_difference(before_volume, after_volume)
    bounds_error = max(abs(a - b) for a, b in zip(before_bounds, after_bounds, strict=True)) / span
    if not math.isfinite(volume_error) or not math.isfinite(bounds_error):
        raise ValueError("witness imprint volume or bounds comparison is nonfinite")
    if volume_error > volume_relative_tolerance:
        raise ValueError(f"witness imprint changed solid volume beyond tolerance: {volume_error}")
    if bounds_error > bounds_relative_to_body_span_tolerance:
        raise ValueError(f"witness imprint changed solid bounds beyond tolerance: {bounds_error}")

    info_by_surface = {
        tag: FaceWitnessInfo(rows[0]["source_face_id"], rows[0]["role"])
        for tag, rows in source_by_surface.items()
    }
    area_by_surface = {tag: float(gmsh.model.occ.getMass(2, tag)) for tag in boundary}
    if not all(math.isfinite(area) and area > 0.0 for area in area_by_surface.values()):
        raise ValueError("witness imprint output has a nonfinite or nonpositive boundary surface area")
    return {
        "status": "VERIFIED_OCC_WITNESS_ANCESTRY",
        "interpretation": (
            "CAD ancestry through individually exported STEP surface witnesses and OCC boolean parent maps; "
            "within declared OCC tolerances, not literal TopoDS identity across STEP or exact metrology"
        ),
        "input_body_volume_m3": before_volume,
        "output_body_volume_m3": after_volume,
        "relative_volume_error": volume_error,
        "input_body_bounds_m": before_bounds,
        "output_body_bounds_m": after_bounds,
        "relative_bounds_error_to_body_span": bounds_error,
        "declared_occ_tolerances": {
            "surface_area_relative": area_relative_tolerance,
            "volume_relative": volume_relative_tolerance,
            "bounds_relative_to_body_span": bounds_relative_to_body_span_tolerance,
        },
        "output_volume_tag": output_volume,
        "exterior_surface_tags": boundary,
        "source_info_by_surface_tag": {
            str(tag): {"source_face_id": info.source_face_id, "role": info.role}
            for tag, info in sorted(info_by_surface.items())
        },
        "source_area_by_surface_tag_m2": {str(tag): area for tag, area in sorted(area_by_surface.items())},
        "source_face_area_by_fid_m2": dict(sorted(source_face_area_by_fid.items())),
        "witness_to_exterior_surface_tags": witness_to_surfaces,
        "all_exterior_surfaces_have_one_witness_parent": True,
        "all_model_surfaces_are_exterior": True,
        "witness_surface_ancestry": witness_records,
        "raw_imprint_parent_map_by_input": raw_rows,
        "raw_witness_surface_parent_map_rows": witness_parent_rows,
    }


def validate_cut_witness_parent_map(
    gmsh: Any,
    *,
    parent_map: Sequence[Any],
    source_surface_tags: Sequence[int],
    source_info_by_surface_tag: Mapping[int, Any],
    partition_volume_tags: Sequence[int],
    shared_surface_tags: Sequence[int],
    exterior_surface_tags: Sequence[int],
    imprint_report: Mapping[str, Any],
    area_relative_tolerance: float = 1e-5,
) -> dict[str, Any]:
    """Validate every signed cut-parent row before classifying exterior descendants."""
    raw_rows = _raw_parent_rows(parent_map)
    if len(parent_map) != len(source_surface_tags) + 2:
        raise ValueError("cut parent map requires one row per body, source surface, and cutting plane")
    if len(raw_rows) != len(parent_map):
        raise ValueError("cut parent map raw row serialization is incomplete")
    raw_body = raw_rows[0]["raw_descendants"]
    body_desc = [(row["dim"], row["tag"]) for row in raw_body]
    expected_parts = {int(tag) for tag in partition_volume_tags}
    body_tags = [tag for _dim, tag in body_desc]
    if (
        not body_desc
        or any(dim != 3 for dim, _tag in body_desc)
        or len(body_tags) != len(set(body_tags))
        or set(body_tags) != expected_parts
    ):
        raise ValueError(f"cut body raw parent map does not exactly match the two output volumes: {body_desc}")
    shared = {int(tag) for tag in shared_surface_tags}
    exterior = {int(tag) for tag in exterior_surface_tags}
    if not shared or not exterior or shared & exterior:
        raise ValueError("cut boundary classification has empty or overlapping interface/exterior sets")
    composed: dict[int, list[tuple[int, FaceWitnessInfo]]] = defaultdict(list)
    descendants_by_source: dict[int, set[int]] = {}
    raw_surface_rows: list[dict[str, Any]] = []
    for index, raw_row in enumerate(raw_rows[1:-1]):
        source_tag = int(source_surface_tags[index])
        info = source_info_by_surface_tag.get(source_tag)
        if info is None:
            raise ValueError(f"source surface {source_tag} has no exact witness identity")
        descendants = raw_row["raw_descendants"]
        dims = [row["dim"] for row in descendants]
        tags = [row["tag"] for row in descendants]
        if not descendants or any(dim != 2 for dim in dims):
            raise ValueError(
                f"source surface {source_tag} has lost/internal/non-surface raw cut descendants: {descendants}"
            )
        if len(tags) != len(set(tags)):
            raise ValueError(f"source surface {source_tag} has duplicate raw cut descendants: {descendants}")
        if set(tags) & shared:
            raise ValueError(
                f"interface plane surface has source-witness ancestry from input {source_tag}: {descendants}"
            )
        if not set(tags).issubset(exterior):
            raise ValueError(
                f"source surface {source_tag} has non-exterior/unmatched raw descendants: {descendants}"
            )
        descendants_by_source[source_tag] = set(tags)
        for tag in tags:
            composed[tag].append((source_tag, info))
        raw_surface_rows.append({
            "input_imprinted_exterior_surface_tag": source_tag,
            "source_face_id": str(info.source_face_id),
            "role": str(info.role),
            "raw_descendants": descendants,
        })

    plane_row = raw_rows[-1]["raw_descendants"]
    plane_dims = [row["dim"] for row in plane_row]
    plane_tags = [row["tag"] for row in plane_row]
    if not plane_row or any(dim != 2 for dim in plane_dims):
        raise ValueError(f"cut plane has missing or non-surface raw descendants: {plane_row}")
    if len(plane_tags) != len(set(plane_tags)):
        raise ValueError("cut plane raw parent map contains duplicate surfaces")
    plane_descendants = set(plane_tags)
    if not shared.issubset(plane_descendants):
        raise ValueError("cut plane parent map does not cover every interface surface")
    if shared & set(composed):
        raise ValueError("cut interface has source-face witness ancestry; it must have zero FID ancestry")
    if set(composed) != exterior:
        raise ValueError(
            "cut source-witness ancestry does not exactly cover exterior surfaces: "
            f"uncovered={sorted(exterior - set(composed))}, extra={sorted(set(composed) - exterior)}, "
            f"shared={sorted(shared)}, exterior={sorted(exterior)}, "
            f"raw_source_rows={raw_surface_rows}, raw_plane_row={plane_row}"
        )
    multiple = {tag: rows for tag, rows in composed.items() if len(rows) != 1}
    if multiple:
        raise ValueError(f"cut exterior surface has multiple witness parents: {multiple}")

    plane_remainders = sorted(plane_descendants - shared)
    all_surfaces = {int(tag) for dim, tag in gmsh.model.getEntities(2) if int(dim) == 2}
    expected_surfaces = shared | exterior | set(plane_remainders)
    if all_surfaces != expected_surfaces:
        raise ValueError(
            f"cut leaves non-boundary surfaces outside the plane remainder set: "
            f"unexpected={sorted(all_surfaces - expected_surfaces)}, "
            f"missing={sorted(expected_surfaces - all_surfaces)}"
        )
    plane_remainder_records = [
        {
            "surface_tag": tag,
            "area_m2": float(gmsh.model.occ.getMass(2, tag)),
            "bounds_m": [float(value) for value in gmsh.model.getBoundingBox(2, tag)],
            "disposition": "recorded as non-body plane-tool remainder before removal",
        }
        for tag in plane_remainders
    ]
    if plane_remainders:
        gmsh.model.occ.remove([(2, tag) for tag in plane_remainders], recursive=False)
        gmsh.model.occ.synchronize()
    remaining_surfaces = {int(tag) for dim, tag in gmsh.model.getEntities(2) if int(dim) == 2}
    if remaining_surfaces != shared | exterior:
        raise ValueError("removing plane remnants left missing or loose cut surfaces")

    pre_cut = {str(key): float(value) for key, value in imprint_report["source_face_area_by_fid_m2"].items()}
    if not pre_cut or not all(math.isfinite(area) and area > 0.0 for area in pre_cut.values()):
        raise ValueError("cut source-face imprint areas are empty or invalid")
    post_cut = {face_id: 0.0 for face_id in pre_cut}
    for tag, parents in composed.items():
        source_tag, info = parents[0]
        face_id = str(info.source_face_id)
        if face_id not in post_cut:
            raise ValueError(f"cut map contains an unknown source face ID {face_id}")
        descendant_area = float(gmsh.model.occ.getMass(2, int(tag)))
        if not math.isfinite(descendant_area) or descendant_area <= 0.0:
            raise ValueError(f"cut descendant surface {tag} has invalid area")
        post_cut[face_id] += descendant_area
    if set(post_cut) != set(pre_cut):
        raise ValueError("cut did not preserve the full pre-cut source-face identity set")
    area_rows: list[dict[str, Any]] = []
    for face_id in sorted(pre_cut):
        error = _relative_difference(pre_cut[face_id], post_cut[face_id])
        if error > area_relative_tolerance:
            raise ValueError(
                f"cut changed source face area beyond tolerance for {face_id}: "
                f"pre={pre_cut[face_id]}, post={post_cut[face_id]}, relative_error={error}"
            )
        area_rows.append({
            "source_face_id": face_id,
            "pre_cut_imprinted_exterior_area_m2": pre_cut[face_id],
            "post_cut_exterior_descendant_area_sum_m2": post_cut[face_id],
            "relative_area_error": error,
            "declared_relative_tolerance": area_relative_tolerance,
        })
    source_by_exterior = {
        str(tag): {
            "source_surface_tag": rows[0][0],
            "source_face_id": str(rows[0][1].source_face_id),
            "role": str(rows[0][1].role),
        }
        for tag, rows in sorted(composed.items())
    }
    return {
        "status": "VERIFIED_OCC_WITNESS_ANCESTRY",
        "raw_cut_parent_map_by_input": raw_rows,
        "raw_source_surface_parent_map_rows": raw_surface_rows,
        "raw_plane_parent_map": plane_row,
        "interface_surface_tags": sorted(shared),
        "exterior_surface_tags": sorted(exterior),
        "plane_remainder_surface_records_before_removal": plane_remainder_records,
        "source_face_area_conservation": area_rows,
        "source_by_exterior_surface": source_by_exterior,
        "source_descendants_by_surface_tag": {
            str(tag): sorted(descendants) for tag, descendants in sorted(descendants_by_source.items())
        },
        "interface_has_zero_source_face_ancestry": True,
        "every_exterior_surface_has_exactly_one_source_face": True,
    }
