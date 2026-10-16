"""Exact semantic face names for STEP files and their Gmsh OCC import.

This module deliberately avoids assigning meaning from imported face order or
spatial proximity.  The caller supplies source-face IDs and roles already tied
to native ``TopoDS_Face`` objects.  The complete native solid is transferred
once, and OCP's transfer map resolves each exact face to its STEP entity. Gmsh
bindings are recovered only from imported entity names on the volume boundary.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import hashlib
import math
import re
from pathlib import Path
from typing import Any


SOURCE_FACE_METADATA_SCHEMA = "vesselforge.step_source_face_metadata.v1"
NATIVE_FACE_WITNESS_SCHEMA = "vesselforge.native_face_witness_manifest.v1"
_NAME_PATTERN = re.compile(
    r"^VF_FACE_(?P<face_id>[A-Za-z0-9][A-Za-z0-9.-]*)__"
    r"(?P<role>[A-Za-z][A-Za-z0-9_]*)$"
)
_FACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*$")
_ROLE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def sha256_file(path: str | Path) -> str:
    """Return the SHA-256 digest of a file without loading it all at once."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def face_entity_name(source_face_id: str, role: str) -> str:
    """Build a STEP/Gmsh-safe name without lossy escaping."""
    face_id = str(source_face_id)
    face_role = str(role)
    if not _FACE_ID_PATTERN.fullmatch(face_id):
        raise ValueError("source_face_id must use letters, digits, dot, or hyphen")
    if not _ROLE_PATTERN.fullmatch(face_role):
        raise ValueError("role must begin with a letter and use letters, digits, or underscore")
    return f"VF_FACE_{face_id}__{face_role}"


def parse_face_entity_name(entity_name: str) -> tuple[str, str] | None:
    """Parse a semantic STEP face name from a Gmsh entity name.

    Gmsh prepends a display namespace such as ``Shapes/``.  Only the final
    component is interpreted; arbitrary names return ``None``.
    """
    if not isinstance(entity_name, str):
        return None
    tail = entity_name.rsplit("/", 1)[-1]
    match = _NAME_PATTERN.fullmatch(tail)
    if not match:
        return None
    return match.group("face_id"), match.group("role")


def normalize_face_rows(face_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Validate and normalize exact native source-face IDs and roles."""
    normalized: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for row in face_rows:
        if not isinstance(row, Mapping):
            raise ValueError("each face row must be a mapping")
        if "source_face_id" not in row or "role" not in row:
            raise ValueError("each face row requires source_face_id and role")
        face_id = str(row["source_face_id"])
        role = str(row["role"])
        face_entity_name(face_id, role)
        if face_id in seen_ids:
            raise ValueError(f"duplicate source_face_id {face_id!r}")
        seen_ids.add(face_id)
        normalized.append({"source_face_id": face_id, "role": role})
    if not normalized:
        raise ValueError("at least one source face is required")
    return normalized


def export_named_step_faces(
    native_shape: Any,
    face_rows: Sequence[Mapping[str, Any]],
    output_step: str | Path,
) -> dict[str, Any]:
    """Write one closed solid and name each exact native face in its STEP body.

    ``native_shape.Faces()[i]`` must be the exact native topology whose
    lineage produced ``face_rows[i]``. The body is transferred first, then
    ``STEPConstruct.FindEntity_s`` resolves each face through OCP's own
    transfer map. Export fails if a source face cannot resolve uniquely or if
    the written STEP does not round-trip as the same single closed solid.
    """
    from OCP.BRep import BRep_Tool
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.Bnd import Bnd_Box
    from OCP.GProp import GProp_GProps
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPConstruct import STEPConstruct
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
    from OCP.TCollection import TCollection_HAsciiString
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    def explore(shape: Any, shape_type: Any) -> list[Any]:
        explorer = TopExp_Explorer(shape, shape_type)
        found: list[Any] = []
        while explorer.More():
            found.append(explorer.Current())
            explorer.Next()
        return found

    def metrics(solid: Any) -> dict[str, Any]:
        volume_props = GProp_GProps()
        BRepGProp.VolumeProperties_s(solid, volume_props, True, False, False)
        volume = float(volume_props.Mass())
        if not (volume > 0.0):
            raise ValueError("native or round-tripped solid has nonpositive volume")
        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(solid, box, False, False)
        xmin, ymin, zmin, xmax, ymax, zmax = map(float, box.Get())
        return {"volume": volume, "bounds": [xmin, ymin, zmin, xmax, ymax, zmax]}

    def require_single_closed_solid(shape: Any, faces: Sequence[Any], *, label: str) -> Any:
        solids = explore(shape, TopAbs_SOLID)
        if len(solids) != 1:
            raise ValueError(f"{label} must contain exactly one solid; found {len(solids)}")
        solid = solids[0]
        if not BRepCheck_Analyzer(solid).IsValid():
            raise ValueError(f"{label} is not a valid OpenCascade solid")
        shells = explore(solid, TopAbs_SHELL)
        if not shells or not all(BRep_Tool.IsClosed_s(shell) for shell in shells):
            raise ValueError(f"{label} contains an open or missing solid shell")
        solid_faces = explore(solid, TopAbs_FACE)
        if len(solid_faces) != len(faces):
            raise ValueError(
                f"{label} face set does not match the supplied native face lineage: "
                f"solid_faces={len(solid_faces)}, lineage_faces={len(faces)}"
            )
        for index, face in enumerate(faces):
            wrapped = getattr(face, "wrapped", face)
            if sum(bool(wrapped.IsSame(candidate)) for candidate in solid_faces) != 1:
                raise ValueError(
                    f"{label} face lineage entry {index} is not one unique face of its solid"
                )
            if any(
                wrapped.IsSame(getattr(other, "wrapped", other))
                for other in faces[:index]
            ):
                raise ValueError(f"{label} native face list contains duplicate topology")
        return solid

    rows = normalize_face_rows(face_rows)
    faces = list(native_shape.Faces())
    if len(faces) != len(rows):
        raise ValueError(
            f"native face count {len(faces)} does not match exact lineage rows {len(rows)}"
        )
    native_solid = require_single_closed_solid(
        native_shape.wrapped, faces, label="native shape"
    )
    native_metrics = metrics(native_solid)
    output = Path(output_step).expanduser().absolute()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite named STEP: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    writer = STEPControl_Writer()
    if writer.Transfer(native_shape.wrapped, STEPControl_AsIs) != IFSelect_RetDone:
        raise RuntimeError("STEP transfer failed for the complete native solid")
    finder_process = writer.WS().TransferWriter().FinderProcess()
    transfer_rows: list[dict[str, Any]] = []
    for face, row in zip(faces, rows, strict=True):
        step_face = STEPConstruct.FindEntity_s(
            finder_process, getattr(face, "wrapped", face)
        )
        if step_face is None or not step_face.IsKind("StepShape_AdvancedFace"):
            raise ValueError(
                f"OCP transfer map did not resolve source face {row['source_face_id']!r} "
                "to one STEP ADVANCED_FACE"
            )
        name = face_entity_name(row["source_face_id"], row["role"])
        step_face.SetName(TCollection_HAsciiString(name))
        transfer_rows.append({**row, "step_entity_name": name})

    model = writer.Model()
    advanced_faces = [
        model.Value(index)
        for index in range(1, model.NbEntities() + 1)
        if model.Value(index).IsKind("StepShape_AdvancedFace")
    ]
    if len(advanced_faces) != len(rows):
        raise ValueError(
            "the STEP model must contain exactly one ADVANCED_FACE per source face: "
            f"advanced_faces={len(advanced_faces)}, expected={len(rows)}"
        )
    observed_names = [entity.Name().String().ToCString() for entity in advanced_faces]
    expected_names = {row["step_entity_name"] for row in transfer_rows}
    for name in expected_names:
        if observed_names.count(name) != 1:
            raise ValueError(
                f"named STEP model must contain one exact AdvancedFace named {name!r}; "
                f"found {observed_names.count(name)}"
            )

    if writer.Write(str(output)) != IFSelect_RetDone or not output.is_file():
        raise RuntimeError(f"OCP could not write named STEP file {output}")

    reader = STEPControl_Reader()
    if reader.ReadFile(str(output)) != IFSelect_RetDone:
        raise RuntimeError(f"OCP could not read the generated named STEP file {output}")
    if int(reader.NbRootsForTransfer()) != 1:
        raise ValueError(
            "named STEP must have exactly one transfer root; "
            f"found {reader.NbRootsForTransfer()}"
        )
    if int(reader.TransferRoots()) != 1:
        raise ValueError("OCP could not transfer the one named STEP root")
    round_trip_shape = reader.OneShape()
    round_trip_faces = explore(round_trip_shape, TopAbs_FACE)
    round_trip_solid = require_single_closed_solid(
        round_trip_shape, round_trip_faces, label="round-tripped STEP"
    )
    round_trip_metrics = metrics(round_trip_solid)
    volume_error = abs(round_trip_metrics["volume"] - native_metrics["volume"]) / native_metrics["volume"]
    bounds_error = max(
        abs(source - imported)
        for source, imported in zip(
            native_metrics["bounds"], round_trip_metrics["bounds"], strict=True
        )
    )
    bounds_scale = max(1.0, *(abs(value) for value in native_metrics["bounds"]))
    if volume_error > 1e-9 or bounds_error > 1e-8 * bounds_scale:
        raise ValueError(
            "named STEP round-trip changed the native solid: "
            f"relative_volume_error={volume_error:.12g}, bounds_error={bounds_error:.12g}"
        )

    return {
        "step_path": str(output),
        "step_sha256": sha256_file(output),
        "step_bytes": output.stat().st_size,
        "named_face_count": len(rows),
        "named_advanced_face_entity_count": len(advanced_faces),
        "source_face_entity_lookup": "STEPConstruct.FindEntity_s on the complete-solid transfer map",
        "source_face_entity_bindings": transfer_rows,
        "complete_solid_transferred_once_before_face_name_assignment": True,
        "face_names_applied_to_exact_solid_boundary_entities": True,
        "round_trip": {
            "transfer_roots": 1,
            "solid_count": 1,
            "valid_closed_solid": True,
            "advanced_face_count": len(advanced_faces),
            "source_volume": native_metrics["volume"],
            "round_trip_volume": round_trip_metrics["volume"],
            "relative_volume_error": volume_error,
            "source_bounds": native_metrics["bounds"],
            "round_trip_bounds": round_trip_metrics["bounds"],
            "maximum_bounds_error": bounds_error,
        },
    }


def export_native_face_witnesses(
    native_shape: Any,
    face_rows: Sequence[Mapping[str, Any]],
    witness_directory: str | Path,
    *,
    source_step_sha256: str,
    lineage_sha256: str,
    native_body_step_sha256: str,
) -> dict[str, Any]:
    """Export one STEP surface witness for each exact child face of one solid.

    Each witness is transferred from the original in-memory ``TopoDS_Face``.
    The function verifies that each face is a unique member of the one valid,
    closed native solid before writing. The returned manifest records each
    witness file's hash and source-face semantic row; downstream code must
    still prove correspondence through an OCC boolean parent map.
    """
    from OCP.BRep import BRep_Tool
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.GProp import GProp_GProps
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
    from OCP.TCollection import TCollection_HAsciiString
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(source_step_sha256)):
        raise ValueError("source_step_sha256 must be a 64-character SHA-256 digest")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(lineage_sha256)):
        raise ValueError("lineage_sha256 must be a 64-character SHA-256 digest")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(native_body_step_sha256)):
        raise ValueError("native_body_step_sha256 must be a 64-character SHA-256 digest")
    rows = normalize_face_rows(face_rows)
    faces = list(native_shape.Faces())
    if len(faces) != len(rows):
        raise ValueError(
            f"native face count {len(faces)} does not match exact lineage rows {len(rows)}"
        )

    def explore(shape: Any, shape_type: Any) -> list[Any]:
        explorer = TopExp_Explorer(shape, shape_type)
        result = []
        while explorer.More():
            result.append(explorer.Current())
            explorer.Next()
        return result

    solids = explore(native_shape.wrapped, TopAbs_SOLID)
    if len(solids) != 1:
        raise ValueError(f"native shape must contain exactly one solid; found {len(solids)}")
    solid = solids[0]
    if not BRepCheck_Analyzer(solid).IsValid():
        raise ValueError("native shape is not a valid OpenCascade solid")
    shells = explore(solid, TopAbs_SHELL)
    if not shells or not all(BRep_Tool.IsClosed_s(shell) for shell in shells):
        raise ValueError("native shape contains an open or missing solid shell")
    solid_faces = explore(solid, TopAbs_FACE)
    if len(solid_faces) != len(faces):
        raise ValueError(
            "native solid face count does not match the exact source-face lineage: "
            f"solid_faces={len(solid_faces)}, lineage_faces={len(faces)}"
        )
    for index, face in enumerate(faces):
        wrapped = getattr(face, "wrapped", face)
        if sum(bool(wrapped.IsSame(candidate)) for candidate in solid_faces) != 1:
            raise ValueError(f"source face row {index} is not one unique face of the native solid")
        if any(
            wrapped.IsSame(getattr(other, "wrapped", other))
            for other in faces[:index]
        ):
            raise ValueError("native shape face list contains duplicate topology")

    directory = Path(witness_directory).expanduser().absolute()
    directory.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, Any]] = []
    for face, row in zip(faces, rows, strict=True):
        wrapped = getattr(face, "wrapped", face)
        native_area_props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(wrapped, native_area_props)
        native_area = float(native_area_props.Mass())
        if not math.isfinite(native_area) or not (native_area > 0.0):
            raise ValueError(f"native face witness {row['source_face_id']!r} has nonpositive area")
        name = face_entity_name(row["source_face_id"], row["role"])
        output = directory / f"{row['source_face_id']}.step"
        writer = STEPControl_Writer()
        if writer.Transfer(wrapped, STEPControl_AsIs) != IFSelect_RetDone:
            raise RuntimeError(f"STEP transfer failed for witness face {row['source_face_id']!r}")
        model = writer.Model()
        advanced_faces = [
            model.Value(i)
            for i in range(1, model.NbEntities() + 1)
            if model.Value(i).IsKind("StepShape_AdvancedFace")
        ]
        if len(advanced_faces) != 1:
            raise ValueError(
                f"face witness must contain one ADVANCED_FACE; found {len(advanced_faces)}"
            )
        # A standalone face transfer is represented by a shell-based surface
        # root, so FindEntity_s(face) resolves the root rather than the
        # AdvancedFace. Because the writer received exactly this one native
        # TopoDS_Face and the STEP model contains exactly one AdvancedFace,
        # the unique model face is its exact transfer result.
        advanced_faces[0].SetName(TCollection_HAsciiString(name))
        if writer.Write(str(output)) != IFSelect_RetDone or not output.is_file():
            raise RuntimeError(f"OCP could not write face witness STEP {output}")
        if name not in output.read_text(encoding="ascii", errors="strict"):
            raise ValueError(f"face witness {output.name} lost its exact STEP entity name")

        reader = STEPControl_Reader()
        if reader.ReadFile(str(output)) != IFSelect_RetDone:
            raise RuntimeError(f"OCP could not read back face witness {output}")
        if int(reader.NbRootsForTransfer()) != 1 or int(reader.TransferRoots()) != 1:
            raise ValueError(f"face witness {output.name} must contain one transfer root")
        round_trip = reader.OneShape()
        round_trip_faces = explore(round_trip, TopAbs_FACE)
        if len(round_trip_faces) != 1 or explore(round_trip, TopAbs_SOLID):
            raise ValueError(f"face witness {output.name} is not exactly one open surface")
        round_trip_area_props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(round_trip_faces[0], round_trip_area_props)
        round_trip_area = float(round_trip_area_props.Mass())
        if not math.isfinite(round_trip_area) or not (round_trip_area > 0.0):
            raise ValueError(f"round-tripped face witness {output.name} has nonpositive area")
        round_trip_area_error = abs(round_trip_area - native_area) / native_area
        records.append({
            **row,
            "step_entity_name": name,
            "witness_path": str(output),
            "witness_sha256": sha256_file(output),
            "witness_bytes": output.stat().st_size,
            "native_face_child_verified": True,
            "native_face_area_mm2": native_area,
            "step_round_trip_face_area_mm2": round_trip_area,
            "step_round_trip_relative_area_error": round_trip_area_error,
            "witness_face_entity_count": 1,
            "witness_solid_count": 0,
        })
    return {
        "schema": NATIVE_FACE_WITNESS_SCHEMA,
        "mapping_status": "EXACT_NATIVE_FACE_WITNESSES",
        "source_step_sha256": str(source_step_sha256).lower(),
        "source_face_lineage_sha256": str(lineage_sha256).lower(),
        "native_body_step_sha256": str(native_body_step_sha256).lower(),
        "native_solid_face_count": len(faces),
        "witness_count": len(records),
        "witnesses": records,
    }


def exact_gmsh_boundary_bindings(
    gmsh: Any,
    volume_tag: int,
    expected_face_rows: Iterable[Mapping[str, Any]],
    *,
    step_path: str | Path,
    upstream_step_sha256: str,
    lineage_sha256: str,
    labels_option_enabled: bool,
) -> dict[str, Any]:
    """Bind boundary surface tags only through exact imported STEP entity names."""
    if not labels_option_enabled:
        raise ValueError("Geometry.OCCImportLabels must be enabled before STEP import")
    step = Path(step_path).expanduser().resolve(strict=True)
    actual_hash = sha256_file(step)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(upstream_step_sha256)):
        raise ValueError("upstream_step_sha256 must be a 64-character SHA-256 digest")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(lineage_sha256)):
        raise ValueError("lineage_sha256 must be a 64-character SHA-256 digest")

    expected_rows = normalize_face_rows(expected_face_rows)
    expected_by_id = {row["source_face_id"]: row["role"] for row in expected_rows}
    boundary_pairs = [
        (int(dim), abs(int(tag)))
        for dim, tag in gmsh.model.getBoundary(
            [(3, int(volume_tag))], oriented=False, recursive=False
        )
        if int(dim) == 2
    ]
    if not boundary_pairs:
        raise ValueError("imported solid has no boundary surface entities")
    model_volumes = [
        int(tag) for dim, tag in gmsh.model.getEntities(3) if int(dim) == 3
    ]
    if model_volumes != [int(volume_tag)]:
        raise ValueError(
            "Gmsh model must contain exactly the supplied single imported volume; "
            f"volumes={model_volumes}, supplied={int(volume_tag)}"
        )
    if len({tag for _, tag in boundary_pairs}) != len(boundary_pairs):
        raise ValueError("imported solid boundary contains duplicate surface tags")
    all_surface_tags = {
        int(tag) for dim, tag in gmsh.model.getEntities(2) if int(dim) == 2
    }
    boundary_surface_tags = {tag for _, tag in boundary_pairs}
    if all_surface_tags != boundary_surface_tags:
        raise ValueError(
            "Gmsh import contains loose or duplicate surfaces outside the one solid boundary: "
            f"boundary={sorted(boundary_surface_tags)}, all_surfaces={sorted(all_surface_tags)}"
        )

    bound_rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    unexpected: list[dict[str, Any]] = []
    for _, tag in boundary_pairs:
        entity_name = str(gmsh.model.getEntityName(2, tag))
        parsed = parse_face_entity_name(entity_name)
        if parsed is None:
            unexpected.append({"imported_surface_tag": tag, "entity_name": entity_name})
            continue
        face_id, role = parsed
        if face_id not in expected_by_id:
            unexpected.append({"imported_surface_tag": tag, "entity_name": entity_name})
            continue
        if expected_by_id[face_id] != role:
            raise ValueError(
                f"entity name role mismatch for source face {face_id!r}: "
                f"expected={expected_by_id[face_id]!r} imported={role!r}"
            )
        if face_id in seen_ids:
            raise ValueError(f"source face {face_id!r} labels multiple volume-boundary entities")
        if entity_name in seen_names:
            raise ValueError(f"duplicate imported STEP face name {entity_name!r}")
        seen_ids.add(face_id)
        seen_names.add(entity_name)
        bound_rows.append({
            "imported_surface_tag": tag,
            "source_face_id": face_id,
            "role": role,
            "step_entity_name": entity_name,
        })

    missing = sorted(set(expected_by_id) - seen_ids)
    if missing or unexpected or len(bound_rows) != len(expected_rows):
        raise ValueError(
            "Gmsh STEP labels do not provide unique complete boundary coverage: "
            f"missing={missing}, unexpected={unexpected}, "
            f"expected={len(expected_rows)}, bound={len(bound_rows)}"
        )
    bound_rows.sort(key=lambda row: row["source_face_id"])
    return {
        "schema": SOURCE_FACE_METADATA_SCHEMA,
        "mapping_status": "EXACT",
        "mapping_basis": (
            "STEPControl_Writer complete-solid transfer; STEPConstruct.FindEntity_s "
            "native TopoDS_Face lookup; semantic ADVANCED_FACE names; Gmsh OCC "
            "entity names on the imported volume boundary; no import-order or spatial matching"
        ),
        "source_step_sha256": actual_hash,
        "upstream_canonical_step_sha256": str(upstream_step_sha256).lower(),
        "source_face_lineage_sha256": str(lineage_sha256).lower(),
        "imported_surface_count": len(bound_rows),
        "faces": bound_rows,
    }


def validate_exact_binding_metadata(
    metadata: Mapping[str, Any],
    *,
    imported_step_path: str | Path,
    expected_upstream_step_sha256: str,
) -> None:
    """Check generated bindings against both the labeled and upstream STEP hashes."""
    if metadata.get("schema") != SOURCE_FACE_METADATA_SCHEMA:
        raise ValueError("unsupported exact source-face metadata schema")
    if metadata.get("mapping_status") != "EXACT":
        raise ValueError("source face metadata is not marked EXACT")
    actual_imported_hash = sha256_file(imported_step_path)
    if str(metadata.get("source_step_sha256", "")).lower() != actual_imported_hash.lower():
        raise ValueError("source face metadata hash does not match the STEP being imported")
    if str(metadata.get("upstream_canonical_step_sha256", "")).lower() != str(
        expected_upstream_step_sha256
    ).lower():
        raise ValueError("source face metadata does not match the declared upstream STEP hash")
    faces = normalize_face_rows(metadata.get("faces", []))
    if len(faces) != int(metadata.get("imported_surface_count", -1)):
        raise ValueError("source face metadata count is inconsistent")
