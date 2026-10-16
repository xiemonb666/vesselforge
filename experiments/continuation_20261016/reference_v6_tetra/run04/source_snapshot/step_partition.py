"""Generic, SI-scale tetrahedral mesh generation from one canonical STEP solid.

The adapter imports the STEP with Gmsh's OpenCascade unit conversion set to
metres, then uses a planar OCC fragment to create two conformal volume regions.
It does not infer a vessel shape or use analytical sphere containment checks.
The caller owns Gmsh initialization and supplies explicit resource limits.

Optional face metadata must bind each source face ID to an imported OCC surface
tag.  That exact entity binding is then propagated through OCC's fragment parent
map.  Metadata without such a binding is retained as unbound evidence and yields
unknown exterior face IDs and roles; no coordinate or nearest-face matching is
attempted.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Any, Mapping

import numpy as np

from .face_witness import (
    FaceWitnessInfo,
    imprint_native_face_witnesses,
    load_native_face_witness_manifest,
    validate_cut_witness_parent_map,
)
from .tetra_audit import audit_tetra_mesh


_OUTWARD_FACE_CORNERS = ((1, 2, 3), (0, 3, 2), (0, 1, 3), (0, 2, 1))
_MAX_RELATIVE_GEOMETRY_ERROR = 0.01


@dataclass(frozen=True)
class ResourceCaps:
    """Explicit limits for reading the STEP and constructing its tetra mesh.

    The mesh forecast uses the configured conservative cell-volume multiplier,
    then adds a boundary-refinement allowance for any requested local sizes.
    The peak-memory value is a forecast based on ``bytes_per_forecast_tetra``;
    it is not an operating-system memory measurement.
    """

    max_step_bytes: int
    max_tetrahedra: int
    max_memory_bytes: int
    max_source_faces: int = 5000
    tetrahedra_per_volume_cell: float = 50.0
    boundary_refinement_factor: float = 8.0
    bytes_per_forecast_tetra: int = 16_384

    def validate(self) -> None:
        integer_values = {
            "max_step_bytes": self.max_step_bytes,
            "max_tetrahedra": self.max_tetrahedra,
            "max_memory_bytes": self.max_memory_bytes,
            "max_source_faces": self.max_source_faces,
            "bytes_per_forecast_tetra": self.bytes_per_forecast_tetra,
        }
        if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in integer_values.values()):
            raise ValueError("all integer resource caps must be positive integers")
        if (not np.isfinite(self.tetrahedra_per_volume_cell)
                or self.tetrahedra_per_volume_cell <= 0
                or not np.isfinite(self.boundary_refinement_factor)
                or self.boundary_refinement_factor < 0):
            raise ValueError("resource forecast factors must be finite and nonnegative")


class ResourceCapError(RuntimeError):
    """A preflight resource forecast exceeds a caller-supplied limit."""

    def __init__(self, message: str, forecast: Mapping[str, Any]):
        super().__init__(message)
        self.forecast = dict(forecast)


@dataclass(frozen=True)
class _FaceInfo:
    source_face_id: str
    role: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _step_length_unit(path: Path) -> str:
    """Read common STEP length-unit declarations without changing geometry."""
    text = path.read_text(encoding="ascii", errors="ignore").upper()
    unit_pattern = re.compile(
        r"LENGTH_UNIT\s*\(\s*\)\s*NAMED_UNIT\s*\([^)]*\)\s*"
        r"SI_UNIT\s*\(\s*(\.[A-Z]+\.|\$)\s*,\s*\.METRE\.\s*\)",
        re.DOTALL,
    )
    match = unit_pattern.search(text)
    if match:
        prefix = match.group(1)
        names = {
            ".NANO.": "nm",
            ".MICRO.": "um",
            ".MILLI.": "mm",
            ".CENTI.": "cm",
            "$": "m",
            ".KILO.": "km",
        }
        if prefix not in names:
            raise ValueError(f"unsupported STEP SI length-unit prefix {prefix}")
        return names[prefix]

    conversion = re.search(r"CONVERSION_BASED_UNIT\s*\(\s*'([^']+)'", text)
    if conversion:
        unit_name = conversion.group(1).strip().upper()
        if unit_name in {"INCH", "FOOT", "YARD", "MILE", "MIL", "THOU"}:
            return unit_name.lower()
        raise ValueError(f"unsupported STEP conversion-based length unit {unit_name!r}")
    raise ValueError("STEP file has no recognized declared length unit; refusing an unverified scale")


def _load_source_face_metadata(
    metadata: str | Path | Mapping[str, Any] | None,
) -> tuple[dict[int, _FaceInfo], dict[str, Any]]:
    """Load exact imported-tag bindings, or record why ancestry is unavailable.

    Exact input format::

        {
          "schema": "vesselforge.step_source_face_metadata.v1",
          "mapping_status": "EXACT",
          "mapping_basis": "...",
          "faces": [
            {"imported_surface_tag": 1, "source_face_id": "face-A", "role": "rim"}
          ]
        }

    The tag is the Gmsh OCC surface tag returned by importing this exact STEP.
    Existing ``vf.native_meridian_face_lineage.v1`` files do not contain that
    binding and are intentionally reported as unbound.
    """
    if metadata is None:
        return {}, {"status": "NOT_PROVIDED", "metadata_sha256": None, "unbound_face_records": 0}

    metadata_path: Path | None = None
    if isinstance(metadata, (str, Path)):
        metadata_path = Path(metadata).resolve(strict=True)
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata_hash = _sha256(metadata_path)
        metadata_name = metadata_path.name
    elif isinstance(metadata, Mapping):
        raw = dict(metadata)
        metadata_hash = None
        metadata_name = None
    else:
        raise TypeError("source_face_metadata must be a JSON path, mapping, or None")
    if not isinstance(raw, dict):
        raise ValueError("source face metadata must contain a JSON object")

    if raw.get("schema") != "vesselforge.step_source_face_metadata.v1":
        faces = raw.get("faces")
        unbound_count = len(faces) if isinstance(faces, (dict, list)) else 0
        return {}, {
            "status": "PRESENT_BUT_UNBOUND",
            "metadata_sha256": metadata_hash,
            "metadata_name": metadata_name,
            "metadata_schema": raw.get("schema"),
            "unbound_face_records": unbound_count,
            "reason": "metadata has no exact imported_surface_tag to source_face_id binding",
        }

    if raw.get("mapping_status") != "EXACT" or not str(raw.get("mapping_basis", "")).strip():
        raise ValueError("source face bindings require mapping_status='EXACT' and a mapping_basis")
    rows = raw.get("faces")
    if not isinstance(rows, list) or not rows:
        raise ValueError("exact source face metadata must contain a nonempty faces list")
    by_tag: dict[int, _FaceInfo] = {}
    seen_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("each source face metadata row must be an object")
        tag = row.get("imported_surface_tag")
        face_id = row.get("source_face_id")
        role = row.get("role", "unknown")
        if isinstance(tag, bool) or not isinstance(tag, int) or tag <= 0:
            raise ValueError("imported_surface_tag must be a positive integer")
        if tag in by_tag:
            raise ValueError(f"duplicate imported surface tag in source metadata: {tag}")
        if face_id is None or not str(face_id).strip():
            raise ValueError("source_face_id must be a nonempty identifier")
        face_id_text = str(face_id)
        if face_id_text in seen_ids:
            raise ValueError(f"duplicate source_face_id in source metadata: {face_id_text}")
        role_text = str(role).strip()
        if not role_text:
            raise ValueError("source face role must be nonempty")
        seen_ids.add(face_id_text)
        by_tag[tag] = _FaceInfo(face_id_text, role_text)
    return by_tag, {
        "status": "EXACT_INPUT_BINDINGS",
        "metadata_sha256": metadata_hash,
        "metadata_name": metadata_name,
        "metadata_schema": raw.get("schema"),
        "mapping_basis": str(raw["mapping_basis"]),
        "unbound_face_records": 0,
    }


def _resource_forecast(
    *,
    source_volume_m3: float,
    mesh_size_m: float,
    source_surface_areas_m2: Mapping[int, float],
    interface_area_m2: float,
    source_face_info: Mapping[int, _FaceInfo],
    boundary_size_by_source_face_m: Mapping[str, float],
    boundary_size_by_role_m: Mapping[str, float],
    interface_size_m: float | None,
    caps: ResourceCaps,
) -> dict[str, Any]:
    """Conservative preflight estimate, separated for pure unit testing."""
    caps.validate()
    if not np.isfinite(source_volume_m3) or source_volume_m3 <= 0:
        raise ValueError("source volume must be finite and positive")
    if not np.isfinite(mesh_size_m) or mesh_size_m <= 0:
        raise ValueError("mesh_size_m must be finite and positive")
    if not np.isfinite(interface_area_m2) or interface_area_m2 <= 0:
        raise ValueError("interface area must be finite and positive")
    if interface_size_m is not None and (not np.isfinite(interface_size_m) or interface_size_m <= 0):
        raise ValueError("interface_size_m must be finite and positive")

    unknown_ids = set(boundary_size_by_source_face_m) - {
        info.source_face_id for info in source_face_info.values()
    }
    unknown_roles = set(boundary_size_by_role_m) - {info.role for info in source_face_info.values()}
    if unknown_ids:
        raise ValueError(f"local sizes refer to source face IDs without exact metadata: {sorted(unknown_ids)}")
    if unknown_roles:
        raise ValueError(f"local sizes refer to roles without exact metadata: {sorted(unknown_roles)}")
    for mapping_name, mapping in (
        ("boundary_size_by_source_face_m", boundary_size_by_source_face_m),
        ("boundary_size_by_role_m", boundary_size_by_role_m),
    ):
        if any(not np.isfinite(value) or value <= 0 for value in mapping.values()):
            raise ValueError(f"{mapping_name} values must be finite and positive")

    base_forecast = caps.tetrahedra_per_volume_cell * source_volume_m3 / mesh_size_m**3
    refinement_allowance = 0.0
    surface_sizes: dict[str, float] = {}
    for tag, area in source_surface_areas_m2.items():
        if not np.isfinite(area) or area <= 0:
            raise ValueError(f"source surface {tag} has invalid area")
        info = source_face_info.get(tag)
        size = mesh_size_m
        if info is not None:
            size = boundary_size_by_source_face_m.get(
                info.source_face_id,
                boundary_size_by_role_m.get(info.role, mesh_size_m),
            )
        surface_sizes[str(tag)] = float(size)
        if size < mesh_size_m:
            refinement_allowance += caps.boundary_refinement_factor * area * (size**-2 - mesh_size_m**-2)
    interface_target = interface_size_m if interface_size_m is not None else mesh_size_m
    if interface_target < mesh_size_m:
        refinement_allowance += (
            caps.boundary_refinement_factor
            * interface_area_m2
            * (interface_target**-2 - mesh_size_m**-2)
        )
    estimated_tetrahedra = math.ceil(base_forecast + refinement_allowance)
    estimated_peak_bytes = estimated_tetrahedra * caps.bytes_per_forecast_tetra
    return {
        "forecast_method": (
            f"{caps.tetrahedra_per_volume_cell:g}*CAD_volume/global_size^3 plus "
            f"{caps.boundary_refinement_factor:g}*area*(local_size^-2-global_size^-2) refinement allowance"
        ),
        "estimated_tetrahedra": int(estimated_tetrahedra),
        "estimated_peak_memory_bytes": int(estimated_peak_bytes),
        "base_volume_forecast_tetrahedra": float(base_forecast),
        "boundary_refinement_allowance_tetrahedra": float(refinement_allowance),
        "bytes_per_forecast_tetra": caps.bytes_per_forecast_tetra,
        "mesh_size_m": float(mesh_size_m),
        "interface_size_m": float(interface_target),
        "boundary_mesh_size_by_imported_surface_tag_m": surface_sizes,
        "caps": {
            "max_step_bytes": caps.max_step_bytes,
            "max_tetrahedra": caps.max_tetrahedra,
            "max_memory_bytes": caps.max_memory_bytes,
            "max_source_faces": caps.max_source_faces,
            "tetrahedra_per_volume_cell": caps.tetrahedra_per_volume_cell,
            "boundary_refinement_factor": caps.boundary_refinement_factor,
            "bytes_per_forecast_tetra": caps.bytes_per_forecast_tetra,
        },
        "within_caps": (
            estimated_tetrahedra <= caps.max_tetrahedra
            and estimated_peak_bytes <= caps.max_memory_bytes
        ),
    }


def _positive_oriented_tetrahedra(nodes_m: Any, tets: Any) -> tuple[np.ndarray, np.ndarray]:
    """Validate connectivity, orient every T4 positively, and return cell volumes."""
    xyz = np.asarray(nodes_m, dtype=np.float64)
    cells = np.asarray(tets)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or not len(xyz) or not np.isfinite(xyz).all():
        raise ValueError("nodes_m must be a nonempty finite (N, 3) array")
    if cells.ndim != 2 or cells.shape[1] != 4 or not len(cells) or not np.issubdtype(cells.dtype, np.integer):
        raise ValueError("tets must be a nonempty integer (T, 4) array")
    cells = cells.astype(np.int64, copy=True)
    if np.any(cells < 0) or np.any(cells >= len(xyz)):
        raise ValueError("tetrahedron connectivity references a missing node")
    if np.any(np.apply_along_axis(lambda row: len(set(row.tolist())), 1, cells) != 4):
        raise ValueError("tetrahedron contains repeated node indices")
    points = xyz[cells]
    determinant = np.einsum(
        "ij,ij->i",
        points[:, 1] - points[:, 0],
        np.cross(points[:, 2] - points[:, 0], points[:, 3] - points[:, 0]),
    )
    if not np.isfinite(determinant).all() or np.any(determinant == 0.0):
        raise ValueError("tetrahedra must have finite nonzero signed volume")
    negative = determinant < 0
    cells[negative, 2], cells[negative, 3] = cells[negative, 3].copy(), cells[negative, 2].copy()
    volumes = np.abs(determinant) / 6.0
    return cells, volumes


def _tetra_face_records(
    tets: np.ndarray, partition: np.ndarray
) -> tuple[dict[tuple[int, int, int], list[tuple[int, tuple[int, int, int], int]]],
           list[tuple[int, tuple[int, int, int]]],
           list[tuple[int, int, tuple[int, int, int]]]]:
    """Return all incidences, outward exterior faces, and cross-partition faces."""
    cells = np.asarray(tets, dtype=np.int64)
    groups = np.asarray(partition)
    if cells.ndim != 2 or cells.shape[1] != 4 or groups.shape != (len(cells),):
        raise ValueError("partition must contain one label per (T, 4) tetrahedron")
    records: dict[tuple[int, int, int], list[tuple[int, tuple[int, int, int], int]]] = defaultdict(list)
    for cell_index, row in enumerate(cells):
        for corners in _OUTWARD_FACE_CORNERS:
            oriented = tuple(int(row[index]) for index in corners)
            records[tuple(sorted(oriented))].append((cell_index, oriented, int(groups[cell_index])))
    overused = [key for key, parents in records.items() if len(parents) > 2]
    if overused:
        raise ValueError(f"tetra mesh has {len(overused)} faces with more than two parents")
    exterior = []
    interfaces = []
    for key, parents in records.items():
        if len(parents) == 1:
            exterior.append((parents[0][0], parents[0][1]))
        elif parents[0][2] != parents[1][2]:
            interfaces.append((parents[0][0], parents[1][0], parents[0][1]))
    return records, exterior, interfaces


def _fragment_descendant_ancestry(
    source_surface_tags: list[int],
    parent_map: list[Any],
    exterior_surface_tags: set[int],
    face_info_by_import_tag: Mapping[int, _FaceInfo],
) -> tuple[dict[int, set[int]], dict[int, list[tuple[int, _FaceInfo]]]]:
    """Propagate only explicit source-face identities through the OCC parent map."""
    if len(parent_map) < len(source_surface_tags) + 1:
        raise ValueError("OCC parent map is missing one or more source surfaces")
    descendants_by_source: dict[int, set[int]] = {}
    ancestry_by_descendant: dict[int, list[tuple[int, _FaceInfo]]] = defaultdict(list)
    for source_index, source_tag in enumerate(source_surface_tags):
        descendants = {
            int(tag) for dim, tag in parent_map[source_index + 1]
            if dim == 2 and int(tag) in exterior_surface_tags
        }
        descendants_by_source[source_tag] = descendants
        info = face_info_by_import_tag.get(source_tag)
        if info is not None:
            for descendant in descendants:
                ancestry_by_descendant[descendant].append((source_tag, info))
    return descendants_by_source, dict(ancestry_by_descendant)


def _surface_triangles(gmsh: Any, surface_tags: list[int], node_index: Mapping[int, int]) -> dict[tuple[int, int, int], int]:
    """Get Tri3 keys and their CAD surface tags, rejecting non-linear surfaces."""
    result: dict[tuple[int, int, int], int] = {}
    for surface_tag in surface_tags:
        kinds, _element_tags, connectivities = gmsh.model.mesh.getElements(2, surface_tag)
        for kind, connectivity in zip(kinds, connectivities, strict=True):
            if kind != 2:
                raise ValueError(f"expected Tri3 boundary elements, got Gmsh element type {kind}")
            for row in np.asarray(connectivity, dtype=np.int64).reshape(-1, 3):
                local = tuple(int(node_index[int(tag)]) for tag in row)
                key = tuple(sorted(local))
                if key in result:
                    raise ValueError("a surface Tri3 belongs to more than one CAD surface entity")
                result[key] = int(surface_tag)
    return result


def _rejected_mesh_diagnostics(
    gmsh: Any,
    *,
    nodes_m: np.ndarray,
    tets: np.ndarray,
    cell_volume_m3: np.ndarray,
    partition: np.ndarray,
    original_node_tags: np.ndarray,
    original_cell_tags: np.ndarray,
    parts: list[int],
    node_index: Mapping[int, int],
    shared_surfaces: list[int],
    exterior_surfaces: list[int],
    descendant_ancestry: Mapping[int, list[tuple[int, _FaceInfo]]],
    witness_imprint_report: Mapping[str, Any] | None,
    witness_cut_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Collect bounded mesh/ancestry arrays for an explicitly rejected mesh.

    This bundle is attached only to the existing CAD-volume gate exception. It
    never writes to the accepted partition output path and carries no pass
    status or simulation qualification.
    """
    if len(tets) > 100_000 or len(nodes_m) > np.iinfo(np.int32).max:
        raise ValueError("rejected-mesh diagnostics exceed the fixed mesh bounds")
    _face_records, exterior_faces, cross_partition_faces = _tetra_face_records(tets, partition)
    interface_triangle_map = _surface_triangles(gmsh, shared_surfaces, node_index)
    exterior_triangle_map = _surface_triangles(gmsh, exterior_surfaces, node_index)

    interface_triangles: list[tuple[int, int, int]] = []
    interface_parents: list[tuple[int, int]] = []
    interface_parent_partition: list[tuple[int, int]] = []
    interface_surface_tags: list[int] = []
    for first, second, face in cross_partition_faces:
        key = tuple(sorted(face))
        interface_triangles.append(tuple(face))
        interface_parents.append((first, second))
        interface_parent_partition.append((int(partition[first]), int(partition[second])))
        interface_surface_tags.append(int(interface_triangle_map.get(key, 0)))

    exterior_triangles: list[tuple[int, int, int]] = []
    exterior_surface_tags: list[int] = []
    exterior_source_face_ids: list[str] = []
    exterior_roles: list[str] = []
    exterior_ancestry_exact: list[bool] = []
    exterior_ancestry_counts: list[int] = []
    for _cell, face in exterior_faces:
        key = tuple(sorted(face))
        surface_tag = int(exterior_triangle_map.get(key, 0))
        ancestry = descendant_ancestry.get(surface_tag, []) if surface_tag else []
        exterior_triangles.append(tuple(face))
        exterior_surface_tags.append(surface_tag)
        exterior_ancestry_counts.append(len(ancestry))
        if len(ancestry) == 1:
            _source_tag, info = ancestry[0]
            exterior_source_face_ids.append(info.source_face_id)
            exterior_roles.append(info.role)
            exterior_ancestry_exact.append(True)
        else:
            exterior_source_face_ids.append("")
            exterior_roles.append("unknown")
            exterior_ancestry_exact.append(False)

    return {
        "diagnostic_status": "FAILED_GEOMETRY_NOT_FOR_SIMULATION",
        "nodes_m": np.asarray(nodes_m, dtype=np.float64),
        "tets": np.asarray(tets, dtype=np.int32),
        "original_node_tags": np.asarray(original_node_tags, dtype=np.int64),
        "original_cell_tags": np.asarray(original_cell_tags, dtype=np.int64),
        "partition": np.asarray(partition, dtype=np.int32),
        "volume_m3": np.asarray(cell_volume_m3, dtype=np.float64),
        "interface_triangles": np.asarray(interface_triangles, dtype=np.int32).reshape(-1, 3),
        "interface_parents": np.asarray(interface_parents, dtype=np.int32).reshape(-1, 2),
        "interface_parent_partition": np.asarray(interface_parent_partition, dtype=np.int8).reshape(-1, 2),
        "interface_surface_tags": np.asarray(interface_surface_tags, dtype=np.int32),
        "exterior_triangles": np.asarray(exterior_triangles, dtype=np.int32).reshape(-1, 3),
        "exterior_surface_tags": np.asarray(exterior_surface_tags, dtype=np.int32),
        "exterior_source_face_ids": np.asarray(exterior_source_face_ids, dtype=str),
        "exterior_roles": np.asarray(exterior_roles, dtype=str),
        "exterior_ancestry_exact": np.asarray(exterior_ancestry_exact, dtype=np.bool_),
        "exterior_ancestry_counts": np.asarray(exterior_ancestry_counts, dtype=np.int16),
        "partition_entity_tags": np.asarray(parts, dtype=np.int32),
        "witness_imprint_report": dict(witness_imprint_report or {}),
        "witness_cut_report": dict(witness_cut_report or {}),
    }


def _relative_error(actual: float, expected: float) -> float:
    return abs(actual - expected) / expected


def partition_step_at_x(
    gmsh: Any,
    canonical_step_path: str | Path,
    source_step_sha256: str,
    output_dir: str | Path,
    *,
    resource_caps: ResourceCaps,
    plane_x_m: float = 0.0,
    expected_volume_m3: float | None = None,
    expected_meridian_section_area_m2: float | None = None,
    mesh_size_m: float = 0.003,
    interface_size_m: float | None = None,
    mesh_size_from_curvature: bool = False,
    boundary_size_by_source_face_m: Mapping[str, float] | None = None,
    boundary_size_by_role_m: Mapping[str, float] | None = None,
    source_face_metadata: str | Path | Mapping[str, Any] | None = None,
    native_face_witness_manifest: str | Path | Mapping[str, Any] | None = None,
    expected_witness_source_step_sha256: str | None = None,
    expected_witness_source_face_lineage_sha256: str | None = None,
    cad_partition_volume_relative_tolerance: float = 1e-7,
    model_name: str = "vesselforge_generic_step_partition",
) -> dict[str, Any]:
    """Partition and mesh one imported STEP solid at ``x=plane_x_m``.

    All coordinates, lengths and volumes are SI.  ``expected_meridian_section_area_m2``
    is the area on the positive-radius side of an independent meridian section;
    for a central symmetry plane the complete cut area is twice that value.
    Local boundary sizes require exact source-face ancestry. This can come from
    imported-tag metadata, or from native-face STEP witnesses imprinted onto
    the exact canonical STEP body. The output directory must not already exist.
    """
    started = time.monotonic()
    caps = resource_caps
    caps.validate()
    if not np.isfinite(plane_x_m):
        raise ValueError("plane_x_m must be finite")
    if not np.isfinite(mesh_size_m) or mesh_size_m <= 0:
        raise ValueError("mesh_size_m must be finite and positive")
    if interface_size_m is not None and (not np.isfinite(interface_size_m) or interface_size_m <= 0):
        raise ValueError("interface_size_m must be finite and positive")
    if (
        not np.isfinite(cad_partition_volume_relative_tolerance)
        or cad_partition_volume_relative_tolerance <= 0
        or cad_partition_volume_relative_tolerance > 1e-6
    ):
        raise ValueError("cad_partition_volume_relative_tolerance must be finite, positive, and <= 1e-6")
    if source_face_metadata is not None and native_face_witness_manifest is not None:
        raise ValueError("source_face_metadata and native_face_witness_manifest are mutually exclusive")
    for name, value in (
        ("expected_volume_m3", expected_volume_m3),
        ("expected_meridian_section_area_m2", expected_meridian_section_area_m2),
    ):
        if value is not None and (not np.isfinite(value) or value <= 0):
            raise ValueError(f"{name} must be finite and positive")
    target = Path(output_dir).expanduser().absolute()
    if target.exists():
        raise FileExistsError(f"output already exists: {target}")
    step = Path(canonical_step_path).expanduser().resolve(strict=True)
    if step.suffix.lower() not in {".step", ".stp"}:
        raise ValueError("canonical source must have a .step or .stp extension")
    if step.stat().st_size > caps.max_step_bytes:
        forecast = {"step_bytes": step.stat().st_size, "max_step_bytes": caps.max_step_bytes, "within_caps": False}
        raise ResourceCapError("STEP byte count exceeds the caller's preflight cap", forecast)
    actual_hash = _sha256(step)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(source_step_sha256)):
        raise ValueError("source_step_sha256 must be a 64-character SHA-256 hex digest")
    if actual_hash.lower() != str(source_step_sha256).lower():
        raise ValueError(f"canonical STEP SHA-256 mismatch: expected={source_step_sha256} actual={actual_hash}")
    source_unit = _step_length_unit(step)
    witness_manifest: dict[str, Any] | None = None
    witness_manifest_report: dict[str, Any] | None = None
    if native_face_witness_manifest is not None:
        witness_manifest, witness_manifest_report = load_native_face_witness_manifest(
            native_face_witness_manifest,
            canonical_step_path=step,
            expected_upstream_source_step_sha256=expected_witness_source_step_sha256,
            expected_source_face_lineage_sha256=expected_witness_source_face_lineage_sha256,
            max_source_faces=caps.max_source_faces,
        )
        face_info_by_import_tag: dict[int, _FaceInfo] = {}
        metadata_report = {
            **witness_manifest_report,
            "status": "VERIFIED_OCC_WITNESS_ANCESTRY",
            "source_face_identity_scope": (
                "conditional CAD ancestry within declared OCC tolerances; not literal TopoDS identity across STEP"
            ),
        }
    else:
        face_info_by_import_tag, metadata_report = _load_source_face_metadata(source_face_metadata)
    boundary_size_by_source_face_m = dict(boundary_size_by_source_face_m or {})
    boundary_size_by_role_m = dict(boundary_size_by_role_m or {})

    # Gmsh's OCC importer needs to see the source declaration and target unit
    # before reading the STEP. No post-import dilation/scaling is performed.
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.option.setNumber("General.NumThreads", 1)
    gmsh.clear()
    gmsh.model.add(model_name)
    gmsh.option.setString("Geometry.OCCTargetUnit", "M")
    imported = gmsh.model.occ.importShapes(str(step), highestDimOnly=True)
    gmsh.model.occ.synchronize()
    imported_volumes = sorted({tag for dim, tag in imported if dim == 3})
    if len(imported_volumes) != 1:
        raise ValueError(f"canonical STEP must import as exactly one solid volume; got {len(imported_volumes)}")
    source_volume_tag = imported_volumes[0]
    source_surface_tags = sorted({
        abs(tag)
        for dim, tag in gmsh.model.getBoundary([(3, source_volume_tag)], oriented=False, recursive=False)
        if dim == 2
    })
    if not source_surface_tags:
        raise ValueError("imported solid has no boundary faces")
    if len(source_surface_tags) > caps.max_source_faces:
        forecast = {
            "source_face_count": len(source_surface_tags),
            "max_source_faces": caps.max_source_faces,
            "within_caps": False,
        }
        raise ResourceCapError("imported STEP face count exceeds the caller's cap", forecast)
    unknown_metadata_tags = set(face_info_by_import_tag) - set(source_surface_tags)
    if unknown_metadata_tags:
        raise ValueError(f"face metadata refers to non-boundary imported surface tags: {sorted(unknown_metadata_tags)}")
    if (
        (boundary_size_by_source_face_m or boundary_size_by_role_m)
        and not face_info_by_import_tag
        and witness_manifest is None
    ):
        raise ValueError("boundary sizing by source face or role requires exact imported-tag metadata")
    source_surface_areas = {
        tag: float(gmsh.model.occ.getMass(2, tag))
        for tag in source_surface_tags
    }
    if not all(np.isfinite(area) and area > 0 for area in source_surface_areas.values()):
        raise ValueError("imported STEP contains a source surface with nonpositive or nonfinite area")
    source_volume_m3 = float(gmsh.model.occ.getMass(3, source_volume_tag))
    if not np.isfinite(source_volume_m3) or source_volume_m3 <= 0:
        raise ValueError("imported STEP solid has nonpositive or nonfinite CAD volume")
    if expected_volume_m3 is not None:
        expected_error = _relative_error(source_volume_m3, expected_volume_m3)
        if expected_error > _MAX_RELATIVE_GEOMETRY_ERROR:
            raise ValueError(
                f"imported STEP volume differs from independent expected volume by more than 1%: {expected_error:.3%}"
            )

    witness_imprint_report: dict[str, Any] | None = None
    witness_cut_report: dict[str, Any] | None = None
    witness_source_area_by_fid_m2: dict[str, float] | None = None
    if witness_manifest is not None:
        witness_imprint_report = imprint_native_face_witnesses(
            gmsh,
            source_volume_tag,
            witness_manifest,
            canonical_body_step_sha256=actual_hash,
        )
        source_volume_tag = int(witness_imprint_report["output_volume_tag"])
        source_surface_tags = [int(tag) for tag in witness_imprint_report["exterior_surface_tags"]]
        if len(source_surface_tags) > caps.max_source_faces:
            forecast = {
                "source_face_count": len(source_surface_tags),
                "max_source_faces": caps.max_source_faces,
                "within_caps": False,
            }
            raise ResourceCapError("witness-imprinted source face count exceeds the caller's cap", forecast)
        face_info_by_import_tag = {
            int(tag): _FaceInfo(str(row["source_face_id"]), str(row["role"]))
            for tag, row in witness_imprint_report["source_info_by_surface_tag"].items()
        }
        source_surface_areas = {
            int(tag): float(area)
            for tag, area in witness_imprint_report["source_area_by_surface_tag_m2"].items()
        }
        source_volume_m3 = float(witness_imprint_report["output_body_volume_m3"])
        witness_source_area_by_fid_m2 = {
            str(face_id): float(area)
            for face_id, area in witness_imprint_report["source_face_area_by_fid_m2"].items()
        }
        metadata_report = {
            **metadata_report,
            "witness_imprint": witness_imprint_report,
        }

    # Use the imported bounding box to build a finite cutting sheet with margin.
    bounds = np.asarray(gmsh.model.getBoundingBox(3, source_volume_tag), dtype=np.float64)
    if bounds.shape != (6,) or not np.isfinite(bounds).all():
        raise ValueError("OpenCascade returned invalid source bounds")
    xmin, ymin, zmin, xmax, ymax, zmax = map(float, bounds)
    span = max(xmax - xmin, ymax - ymin, zmax - zmin)
    if not np.isfinite(span) or span <= 0:
        raise ValueError("imported STEP has a degenerate bounding box")
    padding = max(0.05 * span, 2.0 * mesh_size_m)
    y0, y1 = ymin - padding, ymax + padding
    z0, z1 = zmin - padding, zmax + padding
    plane_points = [
        gmsh.model.occ.addPoint(plane_x_m, y0, z0),
        gmsh.model.occ.addPoint(plane_x_m, y1, z0),
        gmsh.model.occ.addPoint(plane_x_m, y1, z1),
        gmsh.model.occ.addPoint(plane_x_m, y0, z1),
    ]
    plane_lines = [
        gmsh.model.occ.addLine(plane_points[i], plane_points[(i + 1) % 4])
        for i in range(4)
    ]
    plane_loop = gmsh.model.occ.addCurveLoop(plane_lines)
    plane_surface = (2, gmsh.model.occ.addPlaneSurface([plane_loop]))

    # Include every original boundary face as an OCC boolean object. The parent
    # map then gives exact descendant surfaces for each imported face entity.
    original_faces = [(2, tag) for tag in source_surface_tags]
    _, parent_map = gmsh.model.occ.fragment(
        [(3, source_volume_tag), *original_faces], [plane_surface],
        removeObject=True, removeTool=True,
    )
    gmsh.model.occ.synchronize()
    if len(parent_map) != 1 + len(original_faces) + 1:
        raise ValueError("OCC fragment returned an incomplete source ancestry map")
    parts = sorted({tag for dim, tag in parent_map[0] if dim == 3})
    if len(parts) != 2:
        raise ValueError(f"partition must create exactly two geometry volumes, got {len(parts)}")
    # A stable label order keeps left/right partition IDs predictable.
    parts.sort(key=lambda tag: (
        float(gmsh.model.occ.getCenterOfMass(3, tag)[0]),
        float(gmsh.model.occ.getCenterOfMass(3, tag)[1]),
        float(gmsh.model.occ.getCenterOfMass(3, tag)[2]),
        int(tag),
    ))
    boundary_sets = [
        {abs(tag) for dim, tag in gmsh.model.getBoundary([(3, part)], oriented=False, recursive=False) if dim == 2}
        for part in parts
    ]
    shared_surfaces = sorted(boundary_sets[0] & boundary_sets[1])
    if not shared_surfaces:
        raise ValueError("the two OCC volumes do not share a conformal surface")
    exterior_surfaces = sorted((boundary_sets[0] | boundary_sets[1]) - set(shared_surfaces))
    if not exterior_surfaces:
        raise ValueError("partition produced no exterior boundary surfaces")
    part_volumes = [float(gmsh.model.occ.getMass(3, part)) for part in parts]
    if not all(np.isfinite(value) and value > 0 for value in part_volumes):
        raise ValueError("partition contains a nonpositive or nonfinite CAD volume")
    shared_area_m2 = float(sum(gmsh.model.occ.getMass(2, face) for face in shared_surfaces))
    area_floor = max(1e-16, span * span * 1e-12)
    if not np.isfinite(shared_area_m2) or shared_area_m2 <= area_floor:
        raise ValueError("shared OCC interface area is zero or degenerate")
    partition_volume_error = abs(sum(part_volumes) - source_volume_m3) / source_volume_m3
    if partition_volume_error > cad_partition_volume_relative_tolerance:
        raise ValueError(f"OCC partition does not conserve source volume: relative error={partition_volume_error:.3g}")
    expected_interface_area_m2 = (
        2.0 * expected_meridian_section_area_m2
        if expected_meridian_section_area_m2 is not None
        else None
    )
    if expected_interface_area_m2 is not None:
        section_error = _relative_error(shared_area_m2, expected_interface_area_m2)
        if section_error > _MAX_RELATIVE_GEOMETRY_ERROR:
            raise ValueError(
                "OCC symmetry-plane area differs from twice the independent meridian section area "
                f"by more than 1%: {section_error:.3%}"
            )

    if witness_manifest is not None:
        witness_cut_report = validate_cut_witness_parent_map(
            gmsh,
            parent_map=parent_map,
            source_surface_tags=source_surface_tags,
            source_info_by_surface_tag={
                int(tag): info for tag, info in face_info_by_import_tag.items()
            },
            partition_volume_tags=parts,
            shared_surface_tags=shared_surfaces,
            exterior_surface_tags=exterior_surfaces,
            imprint_report=witness_imprint_report or {},
        )
        source_descendants_by_tag = {
            int(tag): {int(value) for value in descendants}
            for tag, descendants in witness_cut_report["source_descendants_by_surface_tag"].items()
        }
        descendant_ancestry = {
            int(tag): [
                (
                    int(row["source_surface_tag"]),
                    _FaceInfo(str(row["source_face_id"]), str(row["role"])),
                )
            ]
            for tag, row in witness_cut_report["source_by_exterior_surface"].items()
        }

    used_surfaces = set(boundary_sets[0]) | set(boundary_sets[1])
    orphan_surfaces = [
        (2, tag) for dim, tag in gmsh.model.getEntities(2) if tag not in used_surfaces
    ]
    if orphan_surfaces:
        gmsh.model.occ.remove(orphan_surfaces, recursive=True)
        gmsh.model.occ.synchronize()

    if witness_manifest is None:
        source_descendants_by_tag, descendant_ancestry = _fragment_descendant_ancestry(
            source_surface_tags,
            parent_map,
            set(exterior_surfaces),
            face_info_by_import_tag,
        )

    # Refuse local mesh controls whose IDs/roles have no exact CAD ancestry.
    source_size_by_tag: dict[int, float] = {}
    for source_tag, info in face_info_by_import_tag.items():
        source_size_by_tag[source_tag] = boundary_size_by_source_face_m.get(
            info.source_face_id,
            boundary_size_by_role_m.get(info.role, mesh_size_m),
        )
    unknown_size_ids = set(boundary_size_by_source_face_m) - {
        info.source_face_id for info in face_info_by_import_tag.values()
    }
    unknown_size_roles = set(boundary_size_by_role_m) - {
        info.role for info in face_info_by_import_tag.values()
    }
    if unknown_size_ids or unknown_size_roles:
        raise ValueError("local size mapping contains an unknown source face ID or role")
    forecast = _resource_forecast(
        source_volume_m3=source_volume_m3,
        mesh_size_m=mesh_size_m,
        source_surface_areas_m2=source_surface_areas,
        interface_area_m2=shared_area_m2,
        source_face_info=face_info_by_import_tag,
        boundary_size_by_source_face_m=boundary_size_by_source_face_m,
        boundary_size_by_role_m=boundary_size_by_role_m,
        interface_size_m=interface_size_m,
        caps=caps,
    )
    step_bytes = step.stat().st_size
    forecast.update({"step_bytes": step_bytes, "source_face_count": len(source_surface_tags)})
    curvature_allowance_factor = 1.5 if mesh_size_from_curvature else 1.0
    if curvature_allowance_factor > 1.0:
        forecast["estimated_tetrahedra"] = math.ceil(
            forecast["estimated_tetrahedra"] * curvature_allowance_factor
        )
        forecast["estimated_peak_memory_bytes"] = (
            forecast["estimated_tetrahedra"] * caps.bytes_per_forecast_tetra
        )
    forecast["curvature_allowance_factor"] = curvature_allowance_factor
    forecast["within_caps"] = (
        forecast["estimated_tetrahedra"] <= caps.max_tetrahedra
        and forecast["estimated_peak_memory_bytes"] <= caps.max_memory_bytes
    )
    if not forecast["within_caps"]:
        raise ResourceCapError(
            "conservative tetrahedron or memory forecast exceeds caller-supplied resource caps",
            forecast,
        )

    gmsh.model.addPhysicalGroup(3, parts, 1)
    gmsh.model.setPhysicalName(3, 1, "partitioned_body")
    gmsh.model.addPhysicalGroup(2, shared_surfaces, 2)
    gmsh.model.setPhysicalName(2, 2, "cut_interface")
    gmsh.model.addPhysicalGroup(2, exterior_surfaces, 3)
    gmsh.model.setPhysicalName(2, 3, "source_exterior")

    gmsh.option.setNumber("Mesh.MeshSizeMin", min(
        [mesh_size_m, interface_size_m or mesh_size_m, *source_size_by_tag.values()]
    ))
    gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_size_m)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", int(bool(mesh_size_from_curvature)))
    gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 1)
    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 1)
    gmsh.option.setNumber("Mesh.ElementOrder", 1)
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
    gmsh.option.setNumber("Mesh.Binary", 0)

    # Local face sizes are implemented by distance fields over OCC descendant
    # surfaces; global size remains the field's far-field value.
    local_fields: list[int] = []
    grouped_descendants: dict[float, set[int]] = defaultdict(set)
    for source_tag, descendants in source_descendants_by_tag.items():
        size = source_size_by_tag.get(source_tag, mesh_size_m)
        if size < mesh_size_m:
            grouped_descendants[size].update(descendants)
    if interface_size_m is not None and interface_size_m < mesh_size_m:
        grouped_descendants[interface_size_m].update(shared_surfaces)
    for size, surface_tags in sorted(grouped_descendants.items()):
        if not surface_tags:
            continue
        distance_field = gmsh.model.mesh.field.add("Distance")
        gmsh.model.mesh.field.setNumbers(distance_field, "SurfacesList", sorted(surface_tags))
        gmsh.model.mesh.field.setNumber(distance_field, "Sampling", 100)
        threshold_field = gmsh.model.mesh.field.add("Threshold")
        gmsh.model.mesh.field.setNumber(threshold_field, "InField", distance_field)
        gmsh.model.mesh.field.setNumber(threshold_field, "SizeMin", size)
        gmsh.model.mesh.field.setNumber(threshold_field, "SizeMax", mesh_size_m)
        gmsh.model.mesh.field.setNumber(threshold_field, "DistMin", 0.0)
        gmsh.model.mesh.field.setNumber(threshold_field, "DistMax", 3.0 * mesh_size_m)
        local_fields.append(threshold_field)
    if local_fields:
        minimum_field = gmsh.model.mesh.field.add("Min")
        gmsh.model.mesh.field.setNumbers(minimum_field, "FieldsList", local_fields)
        gmsh.model.mesh.field.setAsBackgroundMesh(minimum_field)

    gmsh.model.mesh.generate(3)
    node_tags_raw, coordinates, _ = gmsh.model.mesh.getNodes()
    original_node_tags = np.asarray(node_tags_raw, dtype=np.int64)
    nodes_m = np.asarray(coordinates, dtype=np.float64).reshape(-1, 3)
    if len(nodes_m) > np.iinfo(np.int32).max:
        raise ResourceCapError("node count exceeds int32 output connectivity", {**forecast, "node_count": len(nodes_m)})
    node_index = {int(tag): index for index, tag in enumerate(original_node_tags)}
    all_tets: list[np.ndarray] = []
    original_cell_tags: list[int] = []
    partition_labels: list[int] = []
    for label, part in enumerate(parts):
        kinds, element_tags, connectivities = gmsh.model.mesh.getElements(3, part)
        for kind, cell_tags, connectivity in zip(kinds, element_tags, connectivities, strict=True):
            if kind != 4:
                raise ValueError(f"expected linear T4 elements only, got Gmsh element type {kind}")
            rows = np.asarray(connectivity, dtype=np.int64).reshape(-1, 4)
            local = np.asarray(
                [[node_index[int(tag)] for tag in row] for row in rows], dtype=np.int64
            )
            all_tets.append(local)
            original_cell_tags.extend(map(int, cell_tags))
            partition_labels.extend([label] * len(local))
    if not all_tets:
        raise ValueError("Gmsh generated no tetrahedral cells")
    tets_raw = np.concatenate(all_tets, axis=0)
    tets, cell_volume_m3 = _positive_oriented_tetrahedra(nodes_m, tets_raw)
    partition = np.asarray(partition_labels, dtype=np.int32)
    original_cell_tags_array = np.asarray(original_cell_tags, dtype=np.int64)
    if len(tets) != len(original_cell_tags_array) or len(tets) != len(partition):
        raise ValueError("element tags, owners, and T4 connectivity counts disagree")
    if len(tets) > caps.max_tetrahedra:
        raise ResourceCapError(
            f"generated tetrahedron count {len(tets)} exceeds cap {caps.max_tetrahedra}",
            {**forecast, "actual_tetrahedra": len(tets), "within_caps": False},
        )
    mesh_volume_m3 = float(cell_volume_m3.sum())
    cad_mesh_volume_error = _relative_error(mesh_volume_m3, source_volume_m3)
    if cad_mesh_volume_error > _MAX_RELATIVE_GEOMETRY_ERROR:
        error = ValueError(
            "tetrahedral volume differs from imported CAD volume by more than 1%: "
            f"{cad_mesh_volume_error:.3%} (tetrahedra={len(tets)}, mesh_volume_m3={mesh_volume_m3:.12g}, "
            f"cad_volume_m3={source_volume_m3:.12g}, cad_partition_volumes_m3={part_volumes}, "
            f"forecast={forecast['estimated_tetrahedra']})"
        )
        try:
            error.mesh_diagnostics = _rejected_mesh_diagnostics(
                gmsh,
                nodes_m=nodes_m,
                tets=tets,
                cell_volume_m3=cell_volume_m3,
                partition=partition,
                original_node_tags=original_node_tags,
                original_cell_tags=original_cell_tags_array,
                parts=parts,
                node_index=node_index,
                shared_surfaces=shared_surfaces,
                exterior_surfaces=exterior_surfaces,
                descendant_ancestry=descendant_ancestry,
                witness_imprint_report=witness_imprint_report,
                witness_cut_report=witness_cut_report,
            )
            error.mesh_diagnostics.update({
                "source_volume_m3": float(source_volume_m3),
                "mesh_volume_m3": float(mesh_volume_m3),
                "cad_mesh_volume_relative_error": float(cad_mesh_volume_error),
                "resource_forecast": dict(forecast),
            })
        except Exception as diagnostics_error:
            error.mesh_diagnostics_error = f"{type(diagnostics_error).__name__}: {diagnostics_error}"
        raise error

    face_records, exterior_faces, cross_partition_faces = _tetra_face_records(tets, partition)
    interface_triangle_map = _surface_triangles(gmsh, shared_surfaces, node_index)
    exterior_triangle_map = _surface_triangles(gmsh, exterior_surfaces, node_index)
    exterior_keys_from_tets = {tuple(sorted(face)) for _cell, face in exterior_faces}
    interface_keys_from_tets = {tuple(sorted(face)) for _a, _b, face in cross_partition_faces}
    if set(exterior_triangle_map) != exterior_keys_from_tets:
        missing = len(exterior_keys_from_tets - set(exterior_triangle_map))
        extra = len(set(exterior_triangle_map) - exterior_keys_from_tets)
        raise ValueError(f"CAD exterior Tri3 do not match one-parent tetra faces (missing={missing}, extra={extra})")
    if set(interface_triangle_map) != interface_keys_from_tets:
        missing = len(interface_keys_from_tets - set(interface_triangle_map))
        extra = len(set(interface_triangle_map) - interface_keys_from_tets)
        raise ValueError(f"CAD interface Tri3 do not match cross-partition faces (missing={missing}, extra={extra})")

    interface_triangles: list[tuple[int, int, int]] = []
    interface_parents: list[tuple[int, int]] = []
    interface_parent_partitions: list[tuple[int, int]] = []
    for key, face_surface_tag in sorted(interface_triangle_map.items()):
        parents = face_records[key]
        if len(parents) != 2 or parents[0][2] == parents[1][2]:
            raise ValueError("interface triangle does not have exactly two distinct partition parents")
        interface_triangles.append(tuple(sorted(key)))
        interface_parents.append((parents[0][0], parents[1][0]))
        interface_parent_partitions.append((parents[0][2], parents[1][2]))
    if not interface_triangles:
        raise ValueError("mesh contains no interface triangles")

    exterior_triangles: list[tuple[int, int, int]] = []
    exterior_surface_tag_by_key: dict[tuple[int, int, int], int] = {}
    for _cell, outward_face in exterior_faces:
        key = tuple(sorted(outward_face))
        exterior_triangles.append(outward_face)
        exterior_surface_tag_by_key[key] = exterior_triangle_map[key]
    boundary_source_face_ids: list[str] = []
    boundary_roles: list[str] = []
    boundary_ancestry_exact: list[bool] = []
    ancestry_counts = {"exact": 0, "unknown": 0, "ambiguous": 0}
    for outward_face in exterior_triangles:
        surface_tag = exterior_surface_tag_by_key[tuple(sorted(outward_face))]
        ancestors = descendant_ancestry.get(surface_tag, [])
        # Dedupe a single source face propagated through possible OCC aliases.
        unique = {(source_tag, info.source_face_id, info.role) for source_tag, info in ancestors}
        if len(unique) == 1:
            _tag, face_id, role = next(iter(unique))
            boundary_source_face_ids.append(face_id)
            boundary_roles.append(role)
            boundary_ancestry_exact.append(True)
            ancestry_counts["exact"] += 1
        elif len(unique) > 1:
            boundary_source_face_ids.append("")
            boundary_roles.append("unknown")
            boundary_ancestry_exact.append(False)
            ancestry_counts["ambiguous"] += 1
        else:
            boundary_source_face_ids.append("")
            boundary_roles.append("unknown")
            boundary_ancestry_exact.append(False)
            ancestry_counts["unknown"] += 1
    if witness_manifest is not None and (
        ancestry_counts["unknown"] != 0 or ancestry_counts["ambiguous"] != 0
    ):
        raise ValueError(
            "VERIFIED_OCC_WITNESS_ANCESTRY requires every exterior triangle to have one known source face and role"
        )

    tri_xyz = nodes_m[np.asarray(interface_triangles, dtype=np.int64)]
    interface_tri_area_m2 = 0.5 * np.linalg.norm(
        np.cross(tri_xyz[:, 1] - tri_xyz[:, 0], tri_xyz[:, 2] - tri_xyz[:, 0]), axis=1
    )
    if not np.isfinite(interface_tri_area_m2).all() or np.any(interface_tri_area_m2 <= 0):
        raise ValueError("interface contains degenerate or nonfinite Tri3 elements")
    triangular_interface_area_m2 = float(interface_tri_area_m2.sum())
    interface_mesh_area_error = _relative_error(triangular_interface_area_m2, shared_area_m2)
    if interface_mesh_area_error > _MAX_RELATIVE_GEOMETRY_ERROR:
        raise ValueError(
            f"linear Tri3 interface area differs from OCC interface by more than 1%: {interface_mesh_area_error:.3%}"
        )

    audit = audit_tetra_mesh(
        nodes_m,
        tets,
        partition,
        np.asarray(interface_triangles, dtype=np.int64),
        np.asarray(interface_parents, dtype=np.int64),
        stored_volume_m3=cell_volume_m3,
        interface_plane_x_m=float(plane_x_m),
        expected_volume_m3=source_volume_m3,
        expected_interface_area_m2=shared_area_m2,
        analytic_relative_tolerance=_MAX_RELATIVE_GEOMETRY_ERROR,
    )

    if witness_manifest is not None:
        metadata_report = {
            **metadata_report,
            "cut_witness_ancestry": witness_cut_report,
            "propagation_method": (
                "native STEP face witnesses imprinted onto the exact canonical STEP solid, "
                "then OCC parent maps composed through the cut"
            ),
            "spatial_or_nearest_face_matching_used": False,
            "exterior_triangle_counts": ancestry_counts,
            "all_exterior_triangles_have_exact_source_face_ancestry": True,
            "identity_scope": (
                "VERIFIED_OCC_WITNESS_ANCESTRY within declared CAD-kernel tolerances; "
                "not literal TopoDS identity across STEP or exact metrology"
            ),
        }

    import importlib.metadata
    import platform

    try:
        ocp_version: str | None = importlib.metadata.version("cadquery-ocp")
    except importlib.metadata.PackageNotFoundError:
        ocp_version = None
    execution_environment = {
        "python_version": platform.python_version(),
        "gmsh_python_module_version": str(getattr(gmsh, "__version__", "unknown")),
        "opencascade_ocp_version": ocp_version,
    }

    ancestry_propagation_method = (
        "native STEP face witnesses imprinted onto the exact canonical STEP solid, "
        "then OCC parent maps composed through the cut"
        if witness_manifest is not None
        else "OCC fragment parent map from imported source surface entities to exterior descendants"
    )
    result: dict[str, Any] = {
        "schema": "vesselforge.generic_step_tetra_partition.v1",
        "status": "GEOMETRY_DIAGNOSTIC_ONLY",
        "source_step": str(step),
        "source_step_sha256": actual_hash,
        "source_step_bytes": step_bytes,
        "source_step_declared_length_unit": source_unit,
        "step_unit_conversion": "Geometry.OCCTargetUnit=M set before import; no post-import scaling",
        "units": "SI",
        "plane_x_m": float(plane_x_m),
        "global_mesh_size_m": float(mesh_size_m),
        "interface_size_m": float(interface_size_m) if interface_size_m is not None else None,
        "mesh_size_from_curvature": bool(mesh_size_from_curvature),
        "cad_partition_volume_relative_tolerance": float(cad_partition_volume_relative_tolerance),
        "execution_environment": execution_environment,
        "boundary_size_by_source_face_m": boundary_size_by_source_face_m,
        "boundary_size_by_role_m": boundary_size_by_role_m,
        "resource_forecast": forecast,
        "counts": {
            "source_faces": len(source_surface_tags),
            "source_volumes": 1,
            "partition_volumes": len(parts),
            "nodes": len(nodes_m),
            "tetrahedra": len(tets),
            "interface_triangles": len(interface_triangles),
            "exterior_triangles": len(exterior_triangles),
        },
        "source_face_ancestry": {
            **metadata_report,
            "propagation_method": ancestry_propagation_method,
            "spatial_or_nearest_face_matching_used": False,
            "exterior_triangle_counts": ancestry_counts,
            "all_exterior_triangles_have_exact_source_face_ancestry": ancestry_counts["unknown"] == 0 and ancestry_counts["ambiguous"] == 0,
        },
        "cad": {
            "source_volume_m3": source_volume_m3,
            "partition_volume_m3": part_volumes,
            "partition_volume_conservation_relative_error": partition_volume_error,
            "partition_volume_conservation_relative_tolerance": float(cad_partition_volume_relative_tolerance),
            "shared_surface_tags": shared_surfaces,
            "shared_area_m2": shared_area_m2,
            "expected_volume_m3": expected_volume_m3,
            "expected_volume_relative_error": (
                _relative_error(source_volume_m3, expected_volume_m3)
                if expected_volume_m3 is not None else None
            ),
            "expected_meridian_section_area_m2": expected_meridian_section_area_m2,
            "expected_complete_cut_area_m2": expected_interface_area_m2,
            "shared_area_vs_independent_section_relative_error": (
                _relative_error(shared_area_m2, expected_interface_area_m2)
                if expected_interface_area_m2 is not None else None
            ),
        },
        "mesh": {
            "tetrahedral_volume_m3": mesh_volume_m3,
            "cad_mesh_volume_relative_error": cad_mesh_volume_error,
            "triangular_interface_area_m2": triangular_interface_area_m2,
            "occ_mesh_interface_area_relative_error": interface_mesh_area_error,
            "partition_volume_entity_tags": [int(value) for value in parts],
            "partition_label_to_entity_tag": {str(i): int(tag) for i, tag in enumerate(parts)},
            "audit": audit,
        },
        "elapsed_s": time.monotonic() - started,
        "qualification": {
            "real_world_geometry_review": "NOT_ESTABLISHED_BY_MESHING",
            "physical_material_validity": "NOT_ASSESSED",
            "fracture_or_fragment_result": "NOT_CREATED",
            "solver_qualification": "NOT_ESTABLISHED",
        },
    }

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"output already exists: {target}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.option.setNumber("Mesh.Binary", 0)
        gmsh.write(str(temporary / "mesh.msh"))
        msh_head = (temporary / "mesh.msh").read_text(encoding="ascii", errors="strict")[:64]
        if not msh_head.startswith("$MeshFormat\n2.2 0 8"):
            raise ValueError("Gmsh did not write an ASCII MSH 2.2 file")
        np.savez_compressed(
            temporary / "mesh.npz",
            nodes_m=nodes_m,
            tets=tets.astype(np.int32),
            original_node_tags=original_node_tags,
            original_cell_tags=original_cell_tags_array,
            source_partition_volume=partition,
            volume_m3=cell_volume_m3,
            interface_triangles=np.asarray(interface_triangles, dtype=np.int32),
            interface_parents=np.asarray(interface_parents, dtype=np.int32),
            interface_parent_partition=np.asarray(interface_parent_partitions, dtype=np.int8),
            exterior_triangles=np.asarray(exterior_triangles, dtype=np.int32),
            exterior_surface_tags=np.asarray(
                [exterior_surface_tag_by_key[tuple(sorted(face))] for face in exterior_triangles],
                dtype=np.int32,
            ),
            exterior_source_face_ids=np.asarray(boundary_source_face_ids, dtype=str),
            exterior_roles=np.asarray(boundary_roles, dtype=str),
            exterior_ancestry_exact=np.asarray(boundary_ancestry_exact, dtype=np.bool_),
            partition_entity_tags=np.asarray(parts, dtype=np.int32),
        )
        result["files"] = {
            filename: {
                "sha256": _sha256(temporary / filename),
                "bytes": (temporary / filename).stat().st_size,
            }
            for filename in ("mesh.msh", "mesh.npz")
        }
        (temporary / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    finally:
        gmsh.clear()
    return result

