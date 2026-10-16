"""Fail-closed binding of canonical STEP wall stations to their parent surface mesh.

This is stage 1 only. It binds frozen wall-reference stations to triangles from the exact
canonical STEP B-rep face recorded for each station. It does not map fragments, measure material
intervals, or claim global wall quality or physical qualification.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version as package_version
from numbers import Real
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import cadquery as cq
import numpy as np
import OCP
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.BRepLProp import BRepLProp_SLProps
from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_OUT, TopAbs_REVERSED
from OCP.gp import gp_Pnt2d

from .brep_identity import (
    BREP_FACE_BOUNDS_POLICY_ID,
    brep_bounds_mm,
    brep_face_bounds_policy_record,
    validate_brep_face_bounds_policy,
)
from .schema import (
    AssetValidationError,
    load_manifest,
    package_file,
    sha256_file,
    validate_asset,
)
from .semantics import classify_canonical_faces
from .wall_reference import validate_wall_reference

__all__ = [
    "CAD_NUMERIC_TOLERANCE_MM",
    "BindingPolicy",
    "bind_station_to_parent_mesh",
    "build_wall_mesh_binding",
    "parent_mesh_content_sha256",
]

WALL_MESH_BINDING_SCHEMA = "vf.wall-mesh-binding.v1"
WALL_MESH_CONTENT_SCHEMA = "vf.parent-mesh-content.v1"
WELD_RULE = "geometry.mesh_shape:min(1e-5_mm,linear_deflection_mm*1e-4)/v1"
# The B-rep face classifier and surface-property calls use 1e-7 in semantics.py. This is a
# predeclared numeric evaluation tolerance, not a fitted allowance for a failed station.
CAD_NUMERIC_TOLERANCE_MM = 1.0e-7
CAD_NUMERIC_ANGLE_TOLERANCE_RAD = 1.0e-7
NORMAL_ANGLE_POLICY_ID = "vf.wall-mesh-binding.normal-angle/2x-deflection-5deg-floor-15deg-cap/v1"
_EPS = np.finfo(np.float64).eps


@dataclass(frozen=True)
class BindingPolicy:
    """Explicit source-derived input tolerances and local acceptance thresholds."""

    target_linear_deflection_mm: float
    target_angular_deflection_rad: float
    weld_tolerance_mm: float
    cad_numeric_tolerance_mm: float = CAD_NUMERIC_TOLERANCE_MM
    cad_numeric_angle_tolerance_rad: float = CAD_NUMERIC_ANGLE_TOLERANCE_RAD

    def __post_init__(self) -> None:
        numeric_fields = (
            "target_linear_deflection_mm",
            "target_angular_deflection_rad",
            "weld_tolerance_mm",
            "cad_numeric_tolerance_mm",
            "cad_numeric_angle_tolerance_rad",
        )
        for name in numeric_fields:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError(f"{name} must be a non-boolean real number")
            try:
                valid = math.isfinite(float(value)) and float(value) > 0.0
            except (OverflowError, TypeError, ValueError):
                valid = False
            if not valid:
                raise ValueError(f"{name} must be finite and positive")
        for name in ("target_angular_deflection_rad", "cad_numeric_angle_tolerance_rad"):
            if float(getattr(self, name)) >= math.pi:
                raise ValueError(f"{name} must be less than pi radians")
        if (not math.isfinite(self.linear_projection_limit_mm)
                or not math.isfinite(self.normal_angle_limit_rad)
                or not math.isfinite(self.tie_tolerance_mm)
                or not math.isfinite(self.ambiguity_tolerance_mm)):
            raise ValueError("binding policy derived thresholds must be finite")

    @property
    def linear_projection_limit_mm(self) -> float:
        return (self.target_linear_deflection_mm + 2.0 * self.weld_tolerance_mm
                + self.cad_numeric_tolerance_mm)

    @property
    def normal_angle_limit_rad(self) -> float:
        return min(math.radians(15.0), max(math.radians(5.0),
                                           2.0 * self.target_angular_deflection_rad))

    @property
    def tie_tolerance_mm(self) -> float:
        return max(2.0 * self.weld_tolerance_mm,
                   2.0 * self.cad_numeric_tolerance_mm, 1.0e-9)

    @property
    def ambiguity_tolerance_mm(self) -> float:
        # A different source face within the whole local projection uncertainty is ambiguous.
        return max(self.tie_tolerance_mm, self.linear_projection_limit_mm)

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_linear_deflection_mm": float(self.target_linear_deflection_mm),
            "target_angular_deflection_rad": float(self.target_angular_deflection_rad),
            "weld_tolerance_mm": float(self.weld_tolerance_mm),
            "weld_tolerance_rule": WELD_RULE,
            "cad_numeric_tolerance_mm": float(self.cad_numeric_tolerance_mm),
            "cad_numeric_angle_tolerance_rad": float(self.cad_numeric_angle_tolerance_rad),
            "linear_projection_limit_mm": float(self.linear_projection_limit_mm),
            "normal_angle_limit_rad": float(self.normal_angle_limit_rad),
            "normal_angle_policy_id": NORMAL_ANGLE_POLICY_ID,
            "normal_angle_policy_basis": (
                "min(15 degrees, max(5 degrees, 2 * source angular deflection))"
            ),
            "normal_angle_limit_semantics": (
                "predeclared local acceptance threshold derived from source angular deflection; "
                "each station's measured normal_angle_error_rad is reported separately; "
                "this threshold is not a measured error or global error bound"
            ),
            "tie_tolerance_mm": float(self.tie_tolerance_mm),
            "ambiguity_tolerance_mm": float(self.ambiguity_tolerance_mm),
        }


def parent_mesh_content_sha256(
    vertices_mm: np.ndarray,
    faces: np.ndarray,
    face_source_brep_index: np.ndarray,
    *,
    units: str = "mm",
    frame: str = "right_handed_z_up",
) -> str:
    """Hash canonical little-endian arrays plus their indexing/coordinate contract.

    Input storage dtypes may vary; identity uses float64 vertices and signed int64 indices so
    triangle identity is stable across int32/int64 NPZ storage. Triangle order and winding remain
    significant. This hash is separate from every file-byte hash and the STEP SHA.
    """
    vertices = np.asarray(vertices_mm)
    triangles = np.asarray(faces)
    source_faces = np.asarray(face_source_brep_index)
    if units != "mm" or frame != "right_handed_z_up":
        raise ValueError("parent mesh content hash requires mm/right_handed_z_up")
    if (vertices.ndim != 2 or vertices.shape[1:] != (3,) or vertices.dtype.kind != "f"
            or len(vertices) < 4 or not np.isfinite(vertices).all()):
        raise ValueError("vertices_mm must be finite floating N×3")
    if (triangles.ndim != 2 or triangles.shape[1:] != (3,) or triangles.dtype.kind not in "iu"
            or len(triangles) < 1):
        raise ValueError("faces must be nonempty integer F×3")
    if int(triangles.min()) < 0 or int(triangles.max()) >= len(vertices):
        raise ValueError("faces contain an out-of-range vertex index")
    if (source_faces.ndim != 1 or source_faces.shape != (len(triangles),)
            or source_faces.dtype.kind not in "iu" or int(source_faces.min()) < 0):
        raise ValueError("face_source_brep_index must have one nonnegative integer per triangle")

    canonical_arrays = (
        ("vertices_mm", np.ascontiguousarray(vertices, dtype="<f8")),
        ("faces", np.ascontiguousarray(triangles, dtype="<i8")),
        ("face_source_brep_index", np.ascontiguousarray(source_faces, dtype="<i8")),
    )
    header = {
        "schema": WALL_MESH_CONTENT_SCHEMA,
        "units": units,
        "frame": frame,
        "arrays": [{"name": name, "dtype": array.dtype.str,
                    "shape": [int(size) for size in array.shape]}
                   for name, array in canonical_arrays],
    }
    digest = hashlib.sha256()
    digest.update(json.dumps(header, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8"))
    digest.update(b"\0")
    for _name, array in canonical_arrays:
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _unknown_station(station_id: str, reason: str, **details: Any) -> dict[str, Any]:
    return {"station_id": station_id, "status": "UNKNOWN", "reason": reason, **details}


def _unknown_record(reason: str, *, errors: list[str] | None = None,
                    hashes: Mapping[str, str] | None = None) -> dict[str, Any]:
    return {
        "schema": WALL_MESH_BINDING_SCHEMA,
        "status": "UNKNOWN",
        "reason": reason,
        "errors": sorted(set(errors or [reason])),
        "input_file_sha256": dict(hashes or {}),
        "coverage": {"stations_requested": 0, "stations_bound": 0,
                     "station_mapping_fraction": None,
                     "coverage_semantics": "finite wall-reference station mapping fraction; not area coverage"},
        "qualification": {
            "mesh_binding_status": "UNKNOWN",
            "fragment_mapping_status": "UNAVAILABLE",
            "stage_2_fragment_lineage_status": "UNIMPLEMENTED",
            "global_minimum_wall_status": "NOT_ESTABLISHED",
            "global_wall_status": "UNVERIFIED",
            "physics_status": "NOT_ASSESSED",
            "physical_qualification_status": "UNKNOWN",
            "global_minimum_wall_claim": False,
            "physics_claim": False,
        },
        "stations": [],
    }


def _validate_mesh_arrays(vertices: np.ndarray, faces: np.ndarray,
                          source_faces: np.ndarray, canonical_face_count: int
                          ) -> str | None:
    if (vertices.ndim != 2 or vertices.shape[1:] != (3,) or vertices.dtype.kind != "f"
            or len(vertices) < 4 or not np.isfinite(vertices).all()):
        return "SURFACE_VERTICES_INVALID"
    if (faces.ndim != 2 or faces.shape[1:] != (3,) or faces.dtype.kind not in "iu"
            or len(faces) < 4):
        return "SURFACE_TRIANGLES_INVALID"
    if int(faces.min()) < 0 or int(faces.max()) >= len(vertices):
        return "SURFACE_VERTEX_INDEX_OUT_OF_RANGE"
    if (source_faces.ndim != 1 or source_faces.shape != (len(faces),)
            or source_faces.dtype.kind not in "iu"):
        return "TRIANGLE_LINEAGE_LENGTH_OR_DTYPE_INVALID"
    if (canonical_face_count < 1 or int(source_faces.min()) < 0
            or int(source_faces.max()) >= canonical_face_count):
        return "TRIANGLE_LINEAGE_FACE_INDEX_OUT_OF_RANGE"
    tri = np.asarray(vertices, dtype=np.float64)[np.asarray(faces, dtype=np.int64)]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area2 = np.linalg.norm(cross, axis=1)
    if not np.isfinite(area2).all() or np.any(area2 <= np.finfo(np.float64).tiny):
        return "SURFACE_HAS_DEGENERATE_TRIANGLE"
    return None


def _closest_points_on_triangles(point: np.ndarray, triangles: np.ndarray
                                 ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized exact closest points on closed triangles; returns point, bary, distance, normal."""
    a = triangles[:, 0, :]
    b = triangles[:, 1, :]
    c = triangles[:, 2, :]
    ab = b - a
    ac = c - a
    ap = point[None, :] - a
    d00 = np.einsum("ij,ij->i", ab, ab)
    d01 = np.einsum("ij,ij->i", ab, ac)
    d11 = np.einsum("ij,ij->i", ac, ac)
    d20 = np.einsum("ij,ij->i", ap, ab)
    d21 = np.einsum("ij,ij->i", ap, ac)
    denom = d00 * d11 - d01 * d01
    valid = np.isfinite(denom) & (denom > np.finfo(np.float64).tiny)
    beta = np.zeros(len(triangles), dtype=np.float64)
    gamma = np.zeros(len(triangles), dtype=np.float64)
    beta[valid] = (d11[valid] * d20[valid] - d01[valid] * d21[valid]) / denom[valid]
    gamma[valid] = (d00[valid] * d21[valid] - d01[valid] * d20[valid]) / denom[valid]
    alpha = 1.0 - beta - gamma
    inside = valid & (alpha >= -1e-12) & (beta >= -1e-12) & (gamma >= -1e-12)
    plane_bary = np.column_stack((alpha, beta, gamma))
    if np.any(inside):
        plane_bary[inside] = np.maximum(plane_bary[inside], 0.0)
        plane_bary[inside] /= plane_bary[inside].sum(axis=1, keepdims=True)
    plane_points = np.einsum("ij,ijk->ik", plane_bary, triangles)
    plane_d2 = np.einsum("ij,ij->i", plane_points - point[None, :],
                         plane_points - point[None, :])
    plane_d2[~inside] = np.inf

    edge_candidates: list[tuple[np.ndarray, np.ndarray]] = []
    for start, end, bary_start, bary_end in (
        (a, b, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        (b, c, (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        (c, a, (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
    ):
        edge = end - start
        edge_len2 = np.einsum("ij,ij->i", edge, edge)
        usable = np.isfinite(edge_len2) & (edge_len2 > np.finfo(np.float64).tiny)
        t = np.zeros(len(triangles), dtype=np.float64)
        delta = point[None, :] - start
        t[usable] = (np.einsum("ij,ij->i", delta, edge)[usable] / edge_len2[usable])
        t = np.clip(t, 0.0, 1.0)
        cp = start + t[:, None] * edge
        bary = (1.0 - t[:, None]) * np.asarray(bary_start)[None, :] \
            + t[:, None] * np.asarray(bary_end)[None, :]
        d2 = np.einsum("ij,ij->i", cp - point[None, :], cp - point[None, :])
        d2[~usable] = np.inf
        edge_candidates.append((d2, bary))

    all_d2 = np.stack([plane_d2, *(entry[0] for entry in edge_candidates)], axis=1)
    choices = np.argmin(all_d2, axis=1)
    best_bary = plane_bary.copy()
    for edge_index, (_d2, edge_bary) in enumerate(edge_candidates, start=1):
        use = choices == edge_index
        best_bary[use] = edge_bary[use]
    closest = np.einsum("ij,ijk->ik", best_bary, triangles)
    distances = np.sqrt(np.maximum(all_d2[np.arange(len(triangles)), choices], 0.0))
    crosses = np.cross(ab, ac)
    norms = np.linalg.norm(crosses, axis=1)
    normals = np.zeros_like(crosses)
    good_normal = np.isfinite(norms) & (norms > np.finfo(np.float64).tiny)
    normals[good_normal] = crosses[good_normal] / norms[good_normal, None]
    return closest, best_bary, distances, normals


def _angle_rad(a: np.ndarray, b: np.ndarray) -> float:
    a_norm = float(np.linalg.norm(a))
    b_norm = float(np.linalg.norm(b))
    if not math.isfinite(a_norm) or not math.isfinite(b_norm) or a_norm <= 0 or b_norm <= 0:
        return float("inf")
    dot = float(np.dot(a / a_norm, b / b_norm))
    if not math.isfinite(dot):
        return float("inf")
    return float(math.acos(float(np.clip(dot, -1.0, 1.0))))


def bind_station_to_parent_mesh(
    station: Mapping[str, Any],
    vertices_mm: np.ndarray,
    faces: np.ndarray,
    face_source_brep_index: np.ndarray,
    *,
    canonical_face_count: int,
    policy: BindingPolicy,
) -> dict[str, Any]:
    """Bind one already rechecked STEP station to its exact source-face triangles.

    `trimmed_uv_state`, `step_point_mm`, and `outward_from_material` are outputs of a fresh
    canonical STEP B-rep evaluation, not values inferred from mesh normals.
    """
    station_id = str(station.get("station_id", ""))
    if not station_id:
        return _unknown_station("", "STATION_ID_MISSING")
    if station.get("trimmed_uv_state") != "IN":
        return _unknown_station(station_id, "TRIMMED_UV_NOT_IN",
                                trimmed_uv_state=station.get("trimmed_uv_state"))
    face_index = station.get("source_wall_face_index_zero_based")
    role = station.get("wall_role")
    if (isinstance(face_index, bool) or not isinstance(face_index, int)
            or not 0 <= face_index < canonical_face_count):
        return _unknown_station(station_id, "SOURCE_BREP_FACE_INDEX_INVALID")
    if role not in {"outer", "inner"}:
        return _unknown_station(station_id, "WALL_ROLE_INVALID")
    try:
        point = np.asarray(station.get("step_point_mm"), dtype=np.float64)
        outward = np.asarray(station.get("outward_from_material"), dtype=np.float64)
        recorded_point = np.asarray(station.get("recorded_point_mm"), dtype=np.float64)
        recorded_normal = np.asarray(station.get("recorded_outward_normal"), dtype=np.float64)
    except (TypeError, ValueError):
        return _unknown_station(station_id, "STATION_VECTOR_INVALID")
    if any(value.shape != (3,) or not np.isfinite(value).all()
           for value in (point, outward, recorded_point, recorded_normal)):
        return _unknown_station(station_id, "STATION_VECTOR_INVALID")
    outward_norm = float(np.linalg.norm(outward))
    if not math.isfinite(outward_norm) or abs(outward_norm - 1.0) > 1e-5:
        return _unknown_station(station_id, "RECOMPUTED_NORMAL_NOT_UNIT_LENGTH")
    reprojected_step_point_error = float(np.linalg.norm(point - recorded_point))
    rechecked_normal_error = _angle_rad(outward, recorded_normal)
    if reprojected_step_point_error > policy.cad_numeric_tolerance_mm:
        return _unknown_station(station_id, "STEP_POINT_RECHECK_MISMATCH",
                                step_point_recheck_error_mm=reprojected_step_point_error)
    if rechecked_normal_error > policy.cad_numeric_angle_tolerance_rad:
        return _unknown_station(station_id, "STEP_NORMAL_RECHECK_MISMATCH",
                                step_normal_recheck_error_rad=rechecked_normal_error)

    vertices = np.asarray(vertices_mm)
    triangles = np.asarray(faces)
    source_faces = np.asarray(face_source_brep_index)
    mesh_error = _validate_mesh_arrays(vertices, triangles, source_faces, canonical_face_count)
    if mesh_error:
        return _unknown_station(station_id, mesh_error)
    target_ids = np.flatnonzero(source_faces.astype(np.int64, copy=False) == face_index)
    if not len(target_ids):
        return _unknown_station(station_id, "NO_TRIANGLES_FOR_SOURCE_BREP_FACE")

    all_triangles = np.asarray(vertices, dtype=np.float64)[np.asarray(triangles, dtype=np.int64)]
    target_points, target_bary, target_dist, target_normals = _closest_points_on_triangles(
        point, all_triangles[target_ids])
    if not np.isfinite(target_dist).all():
        return _unknown_station(station_id, "TARGET_FACE_TRIANGLE_PROJECTION_INVALID")
    best_distance = float(target_dist.min())
    tied_local = np.flatnonzero(np.abs(target_dist - best_distance) <= policy.tie_tolerance_mm)
    if not len(tied_local):
        return _unknown_station(station_id, "TARGET_FACE_PROJECTION_UNRESOLVED")
    chosen_local = int(tied_local[0])
    chosen_id = int(target_ids[chosen_local])
    chosen_point = target_points[chosen_local]
    chosen_normal = target_normals[chosen_local]
    tied_ids = [int(target_ids[int(index)]) for index in tied_local]
    for local_index in tied_local:
        local_index = int(local_index)
        if float(np.linalg.norm(target_points[local_index] - chosen_point)) > policy.tie_tolerance_mm:
            return _unknown_station(station_id, "SAME_FACE_TIE_POINTS_DISAGREE",
                                    tied_parent_triangle_indices=tied_ids)
        angle = _angle_rad(outward, target_normals[local_index])
        if angle > policy.normal_angle_limit_rad:
            return _unknown_station(station_id, "SAME_FACE_TIE_NORMAL_DISAGREEMENT",
                                    tied_parent_triangle_indices=tied_ids,
                                    tied_normal_angle_error_rad=angle)

    # A triangle on any distinct B-rep face is only an ambiguity probe. It is never a fallback.
    other_ids = np.flatnonzero(source_faces.astype(np.int64, copy=False) != face_index)
    nearest_other_distance: float | None = None
    nearest_other_face: int | None = None
    if len(other_ids):
        other_points, _other_bary, other_dist, _other_normals = _closest_points_on_triangles(
            point, all_triangles[other_ids])
        if not np.isfinite(other_dist).all():
            return _unknown_station(station_id, "OTHER_FACE_AMBIGUITY_PROBE_INVALID")
        other_local = int(np.argmin(other_dist))
        nearest_other_distance = float(other_dist[other_local])
        nearest_other_face = int(source_faces[int(other_ids[other_local])])
        distance_delta = nearest_other_distance - best_distance
        if (nearest_other_distance <= policy.linear_projection_limit_mm
                and abs(distance_delta) <= policy.ambiguity_tolerance_mm):
            return _unknown_station(
                station_id, "AMBIGUOUS_FACE_LINEAGE",
                target_projection_distance_mm=best_distance,
                nearest_other_face_index=nearest_other_face,
                nearest_other_face_distance_mm=nearest_other_distance,
                cross_face_distance_delta_mm=distance_delta,
            )
        if distance_delta < -policy.ambiguity_tolerance_mm:
            return _unknown_station(
                station_id, "DIFFERENT_FACE_CLEARLY_NEARER_THAN_DECLARED_FACE",
                target_projection_distance_mm=best_distance,
                nearest_other_face_index=nearest_other_face,
                nearest_other_face_distance_mm=nearest_other_distance,
            )

    projection_error = float(np.linalg.norm(chosen_point - point))
    if not math.isfinite(projection_error) or projection_error > policy.linear_projection_limit_mm:
        return _unknown_station(station_id, "STATION_PROJECTION_ERROR_EXCEEDS_LIMIT",
                                target_projection_distance_mm=best_distance,
                                station_projection_error_mm=projection_error,
                                linear_projection_limit_mm=policy.linear_projection_limit_mm)
    normal_angle_error = _angle_rad(outward, chosen_normal)
    if not math.isfinite(normal_angle_error) or normal_angle_error > policy.normal_angle_limit_rad:
        return _unknown_station(station_id, "MESH_NORMAL_MISMATCH",
                                normal_angle_error_rad=normal_angle_error,
                                normal_angle_limit_rad=policy.normal_angle_limit_rad)

    barycentric = np.asarray(target_bary[chosen_local], dtype=np.float64)
    if (not np.isfinite(barycentric).all() or np.any(barycentric < -1e-12)
            or np.any(barycentric > 1.0 + 1e-12)
            or abs(float(barycentric.sum()) - 1.0) > 1e-12):
        return _unknown_station(station_id, "BARYCENTRIC_COORDINATES_INVALID")
    barycentric = np.clip(barycentric, 0.0, 1.0)
    barycentric /= float(barycentric.sum())
    mesh_station = barycentric @ np.asarray(vertices, dtype=np.float64)[
        np.asarray(triangles, dtype=np.int64)[chosen_id]]
    return {
        "station_id": station_id,
        "status": "BOUND",
        "source_wall_face_index_zero_based": int(face_index),
        "wall_role": str(role),
        "trimmed_uv_state": "IN",
        "u": float(station["u"]),
        "v": float(station["v"]),
        "step_point_mm": [float(value) for value in point],
        "outward_from_material": [float(value) for value in outward / outward_norm],
        "step_point_recheck_error_mm": reprojected_step_point_error,
        "step_normal_recheck_error_rad": rechecked_normal_error,
        "parent_triangle_index": chosen_id,
        "same_face_tie_triangle_indices": sorted(tied_ids),
        "parent_triangle_barycentric": [float(value) for value in barycentric],
        "mesh_station_point_mm": [float(value) for value in mesh_station],
        "station_projection_error_mm": projection_error,
        "normal_angle_error_rad": normal_angle_error,
        "nearest_other_face_index": nearest_other_face,
        "nearest_other_face_distance_mm": nearest_other_distance,
    }


def _aggregate_bound_stations(
    stations: list[Mapping[str, Any]],
    vertices_mm: np.ndarray,
    faces: np.ndarray,
    face_source_brep_index: np.ndarray,
    *,
    canonical_face_count: int,
    parent_mesh_content_hash: str,
    policy: BindingPolicy,
) -> dict[str, Any]:
    """Aggregate internally resolved station rows; this does not authenticate external inputs.

    Only the validated `build_wall_mesh_binding` path may use the aggregate status as part of a
    source-bound report. A caller-provided `BOUND` row is not evidence that any source or mesh was
    checked.
    """
    rows: list[dict[str, Any]] = []
    for station in stations:
        # The high-level reader can pass through a terminal CAD-recheck or projection row. This
        # keeps the first, more specific UNKNOWN reason rather than trying to bind it again.
        if station.get("status") in {"BOUND", "UNKNOWN"}:
            rows.append(dict(station))
        else:
            rows.append(bind_station_to_parent_mesh(
                station, vertices_mm, faces, face_source_brep_index,
                canonical_face_count=canonical_face_count, policy=policy))
    requested = len(rows)
    bound = sum(row.get("status") == "BOUND" for row in rows)
    full = requested > 0 and bound == requested
    return {
        "schema": WALL_MESH_BINDING_SCHEMA,
        "status": "PASS_MOTHER_STATION_BINDING" if full else "UNKNOWN",
        "reason": None if full else "NOT_ALL_WALL_REFERENCE_STATIONS_BOUND",
        "parent_mesh_content_sha256": str(parent_mesh_content_hash),
        "tolerances": policy.as_dict(),
        "aggregation_scope": "internal_station_status_aggregation_only_not_external_source_authentication",
        "coverage": {
            "stations_requested": int(requested),
            "stations_bound": int(bound),
            "station_mapping_fraction": float(bound / requested) if requested else None,
            "coverage_semantics": "finite wall-reference station mapping fraction; not area coverage",
        },
        "qualification": {
            "mesh_binding_status": "PASS_MOTHER_STATION_BINDING" if full else "UNKNOWN",
            "fragment_mapping_status": "UNAVAILABLE",
            "stage_2_fragment_lineage_status": "UNIMPLEMENTED",
            "global_minimum_wall_status": "NOT_ESTABLISHED",
            "global_wall_status": "UNVERIFIED",
            "physics_status": "NOT_ASSESSED",
            "physical_qualification_status": "UNKNOWN",
            "global_minimum_wall_claim": False,
            "physics_claim": False,
        },
        "stations": rows,
    }


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}_JSON_INVALID:{type(exc).__name__}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label}_JSON_NOT_OBJECT")
    return data


def _canonical_json_equal(left: Any, right: Any) -> bool:
    try:
        return json.dumps(left, sort_keys=True, separators=(",", ":"), allow_nan=False) == json.dumps(
            right, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return False


def _verify_package_file_hash(manifest: Mapping[str, Any], relative: str, path: Path) -> str:
    actual = sha256_file(path)
    entry = (manifest.get("files") or {}).get(relative)
    if not isinstance(entry, Mapping):
        raise ValueError(f"FILE_NOT_HASHED_IN_MANIFEST:{relative}")
    if entry.get("sha256") != actual or entry.get("bytes") != path.stat().st_size:
        raise ValueError(f"FILE_HASH_MISMATCH:{relative}")
    return actual


def _read_npz_pair(surface_path: Path, lineage_path: Path
                   ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    try:
        with np.load(surface_path, allow_pickle=False) as surface:
            vertices = np.array(surface["vertices_mm"], copy=True)
            faces = np.array(surface["faces"], copy=True)
        with np.load(lineage_path, allow_pickle=False) as lineage:
            source_faces = np.array(lineage["face_source_brep_index"], copy=True)
    except (OSError, ValueError, KeyError) as exc:
        raise ValueError(f"SURFACE_OR_LINEAGE_NPZ_INVALID:{type(exc).__name__}") from exc
    return vertices, faces, source_faces


def _runtime_backend() -> dict[str, str | None]:
    try:
        ocp_distribution_version: str | None = package_version("cadquery-ocp")
    except PackageNotFoundError:
        ocp_distribution_version = None
    return {
        "cadquery_version": str(cq.__version__),
        "ocp_module_version": str(getattr(OCP, "__version__", "")) or None,
        "ocp_distribution_version": ocp_distribution_version,
    }


def _require_matching_backend(semantics: Mapping[str, Any]) -> None:
    recorded = semantics.get("backend")
    if not isinstance(recorded, Mapping):
        raise ValueError("SEMANTICS_BACKEND_VERSION_MISSING")
    actual = _runtime_backend()
    if any(not isinstance(recorded.get(name), str) or recorded.get(name) != actual.get(name)
           for name in actual):
        raise ValueError("CADQUERY_OCP_VERSION_MISMATCH")


def _match_recomputed_semantics(stored: Mapping[str, Any], fresh: Mapping[str, Any],
                                expected_step_sha256: str) -> None:
    scalar_keys = ("schema", "status", "classifier", "canonical_step_sha256",
                   "canonical_step_face_count")
    if any(stored.get(key) != fresh.get(key) for key in scalar_keys):
        raise ValueError("REIMPORTED_FACE_SEMANTICS_IDENTITY_MISMATCH")
    if stored.get("canonical_step_sha256") != expected_step_sha256:
        raise ValueError("SEMANTICS_STEP_SHA256_MISMATCH")
    stored_faces = stored.get("faces")
    fresh_faces = fresh.get("faces")
    if not isinstance(stored_faces, list) or not isinstance(fresh_faces, list) \
            or len(stored_faces) != len(fresh_faces):
        raise ValueError("REIMPORTED_FACE_COUNT_MISMATCH")
    identity_fields = ("face_index_zero_based", "status", "region_code", "region_name",
                       "surface_type", "classification_basis", "classification_evidence",
                       "canonical_step_sha256")
    for index, (old, new) in enumerate(zip(stored_faces, fresh_faces)):
        if not isinstance(old, Mapping) or not isinstance(new, Mapping):
            raise ValueError(f"REIMPORTED_FACE_ROW_INVALID:{index}")
        if any(not _canonical_json_equal(old.get(key), new.get(key)) for key in identity_fields):
            raise ValueError(f"REIMPORTED_FACE_ORDER_OR_SEMANTICS_MISMATCH:{index}")


def _wall_reference_source_semantics_projection(
    face_semantics: Mapping[str, Any],
) -> dict[str, Any]:
    """Project full VF face semantics into wall_reference.py's exact compact v1 field shape."""
    faces = face_semantics.get("faces")
    face_count = face_semantics.get("canonical_step_face_count")
    if (not isinstance(faces, list) or isinstance(face_count, bool)
            or not isinstance(face_count, int) or face_count != len(faces)):
        raise ValueError("WALL_REFERENCE_EXPECTED_SEMANTICS_INVENTORY_INVALID")
    wall_roles = {"body_outer": "outer", "body_inner": "inner"}
    inventory: list[dict[str, Any]] = []
    for expected_index, row in enumerate(faces):
        if not isinstance(row, Mapping):
            raise ValueError(f"WALL_REFERENCE_EXPECTED_SEMANTICS_FACE_INVALID:{expected_index}")
        index = row.get("face_index_zero_based")
        if isinstance(index, bool) or not isinstance(index, int) or index != expected_index:
            raise ValueError(f"WALL_REFERENCE_EXPECTED_SEMANTICS_FACE_ORDER_INVALID:{expected_index}")
        role = wall_roles.get(row.get("region_name"))
        if role is not None:
            inventory.append({
                "source_wall_face_index_zero_based": index,
                "wall_role": role,
            })
    return {
        "schema": face_semantics.get("schema"),
        "status": face_semantics.get("status"),
        "classifier": face_semantics.get("classifier"),
        "canonical_step_sha256": face_semantics.get("canonical_step_sha256"),
        "canonical_step_face_count": face_count,
        "wall_face_inventory": inventory,
    }


def _validate_wall_reference_source_semantics(
    compact_source_semantics: Any,
    full_face_semantics: Mapping[str, Any],
) -> None:
    """Require exact equality with the compact source_semantics emitted by wall_reference v1."""
    expected = _wall_reference_source_semantics_projection(full_face_semantics)
    if not _canonical_json_equal(compact_source_semantics, expected):
        raise ValueError("WALL_REFERENCE_SEMANTICS_FILE_MISMATCH")


def _check_face_inventory(
    shape: cq.Shape,
    inventory: Any,
    tolerance_mm: float,
    bounds_policy: Any,
) -> None:
    validate_brep_face_bounds_policy(bounds_policy)
    if not isinstance(inventory, list) or len(inventory) != len(shape.Faces()):
        raise ValueError("CANONICAL_BREP_FACE_INVENTORY_MISMATCH")
    for index, (face, recorded) in enumerate(zip(shape.Faces(), inventory)):
        if not isinstance(recorded, Mapping) or recorded.get("index_zero_based") != index:
            raise ValueError(f"CANONICAL_BREP_FACE_INDEX_MISMATCH:{index}")
        if recorded.get("geom_type") != face.geomType():
            raise ValueError(f"CANONICAL_BREP_FACE_TYPE_MISMATCH:{index}")
        center = np.asarray(face.Center().toTuple(), dtype=np.float64)
        bbox = np.asarray(brep_bounds_mm(face), dtype=np.float64)
        try:
            recorded_center = np.asarray(recorded.get("center_mm"), dtype=np.float64)
            recorded_bbox = np.asarray(recorded.get("bbox_mm"), dtype=np.float64)
            recorded_area = float(recorded.get("area_mm2"))
        except (TypeError, ValueError):
            raise ValueError(f"CANONICAL_BREP_FACE_INVENTORY_VALUE_INVALID:{index}")
        if (recorded_center.shape != (3,) or recorded_bbox.shape != (6,)
                or not np.isfinite(recorded_center).all() or not np.isfinite(recorded_bbox).all()
                or not math.isfinite(recorded_area)):
            raise ValueError(f"CANONICAL_BREP_FACE_INVENTORY_VALUE_INVALID:{index}")
        if float(np.max(np.abs(center - recorded_center))) > tolerance_mm:
            raise ValueError(f"CANONICAL_BREP_FACE_CENTER_MISMATCH:{index}")
        if float(np.max(np.abs(bbox - recorded_bbox))) > tolerance_mm:
            raise ValueError(f"CANONICAL_BREP_FACE_BOUNDS_MISMATCH:{index}")
        area_tol = tolerance_mm * max(1.0, math.sqrt(abs(recorded_area)))
        if abs(float(face.Area()) - recorded_area) > area_tol:
            raise ValueError(f"CANONICAL_BREP_FACE_AREA_MISMATCH:{index}")


def _load_binding_policy(manifest: Mapping[str, Any], report: Mapping[str, Any]
                         ) -> BindingPolicy:
    provenance = manifest.get("provenance")
    spec = provenance.get("spec") if isinstance(provenance, Mapping) else None
    if not isinstance(spec, Mapping):
        raise ValueError("TESSELLATION_SPEC_MISSING")
    parameters = spec.get("parameters")
    tessellation = spec.get("tessellation")
    if not isinstance(parameters, Mapping) or not isinstance(tessellation, Mapping):
        raise ValueError("TESSELLATION_SPEC_MISSING")
    raw = (
        parameters.get("tessellation_linear_mm"),
        parameters.get("tessellation_angular_rad"),
        tessellation.get("linear_chord_deflection_mm"),
        tessellation.get("angular_tolerance_rad"),
        report.get("tessellation_chord_deflection_target_mm"),
        report.get("tessellation_angular_tolerance_rad"),
    )
    values: list[float] = []
    for index, value in enumerate(raw):
        name = (
            "spec_parameter_linear", "spec_parameter_angular",
            "spec_tessellation_linear", "spec_tessellation_angular",
            "geometry_report_linear", "geometry_report_angular",
        )[index]
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"TESSELLATION_DEFLECTION_SOURCE_INVALID:{name}:NON_REAL_OR_BOOLEAN")
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"TESSELLATION_DEFLECTION_SOURCE_INVALID:{name}") from exc
        if not math.isfinite(numeric) or numeric <= 0.0:
            raise ValueError(f"TESSELLATION_DEFLECTION_SOURCE_INVALID:{name}")
        if "angular" in name and numeric >= math.pi:
            raise ValueError(f"TESSELLATION_DEFLECTION_SOURCE_INVALID:{name}:ANGLE_NOT_BELOW_PI")
        values.append(numeric)
    linear_a, angular_a, linear_b, angular_b, linear_c, angular_c = values
    if not (math.isclose(linear_a, linear_b, rel_tol=0.0, abs_tol=1e-12)
            and math.isclose(linear_a, linear_c, rel_tol=0.0, abs_tol=1e-12)
            and math.isclose(angular_a, angular_b, rel_tol=0.0, abs_tol=1e-12)
            and math.isclose(angular_a, angular_c, rel_tol=0.0, abs_tol=1e-12)):
        raise ValueError("TESSELLATION_DEFLECTION_SOURCE_MISMATCH")
    weld_tolerance = min(1.0e-5, linear_a * 1.0e-4)
    return BindingPolicy(
        target_linear_deflection_mm=linear_a,
        target_angular_deflection_rad=angular_a,
        weld_tolerance_mm=weld_tolerance,
    )


def _reevaluate_station_on_step_face(
    face: cq.Face,
    station: Mapping[str, Any],
    face_index: int,
    policy: BindingPolicy,
) -> dict[str, Any]:
    station_id = str(station.get("station_id", ""))
    evidence = station.get("source_classification_evidence")
    sample = evidence.get("interior_sample") if isinstance(evidence, Mapping) else None
    if not isinstance(sample, Mapping):
        return _unknown_station(station_id, "WALL_REFERENCE_UV_SAMPLE_MISSING")
    try:
        u = float(sample["u"])
        v = float(sample["v"])
        frozen_point = np.asarray(station.get("position_mm"), dtype=np.float64)
        frozen_normal = np.asarray(station.get("outward_from_material"), dtype=np.float64)
    except (KeyError, TypeError, ValueError, OverflowError):
        return _unknown_station(station_id, "WALL_REFERENCE_STATION_VECTOR_INVALID")
    if (not math.isfinite(u) or not math.isfinite(v) or frozen_point.shape != (3,)
            or frozen_normal.shape != (3,) or not np.isfinite(frozen_point).all()
            or not np.isfinite(frozen_normal).all()):
        return _unknown_station(station_id, "WALL_REFERENCE_STATION_VECTOR_INVALID")

    classifier = BRepClass_FaceClassifier(
        face.wrapped, gp_Pnt2d(u, v), float(policy.cad_numeric_tolerance_mm))
    state = classifier.State()
    if state != TopAbs_IN:
        state_name = (
            "IN" if state == TopAbs_IN else
            "ON" if state == TopAbs_ON else
            "OUT" if state == TopAbs_OUT else
            str(state)
        )
        return _unknown_station(station_id, "TRIMMED_UV_NOT_IN",
                                trimmed_uv_state=state_name,
                                source_wall_face_index_zero_based=int(face_index))

    adaptor = BRepAdaptor_Surface(face.wrapped, True)
    properties = BRepLProp_SLProps(adaptor, u, v, 1,
                                   float(policy.cad_numeric_angle_tolerance_rad))
    if not properties.IsNormalDefined():
        return _unknown_station(station_id, "STEP_FACE_NORMAL_UNDEFINED")
    point = adaptor.Value(u, v)
    normal = properties.Normal()
    if face.wrapped.Orientation() == TopAbs_REVERSED:
        normal.Reverse()
    point_mm = np.asarray([point.X(), point.Y(), point.Z()], dtype=np.float64)
    normal_vec = np.asarray([normal.X(), normal.Y(), normal.Z()], dtype=np.float64)
    point_error = float(np.linalg.norm(point_mm - frozen_point))
    normal_error = _angle_rad(normal_vec, frozen_normal)
    if (not math.isfinite(point_error) or point_error > policy.cad_numeric_tolerance_mm
            or not math.isfinite(normal_error)
            or normal_error > policy.cad_numeric_angle_tolerance_rad):
        return _unknown_station(station_id, "STEP_STATION_RECHECK_MISMATCH",
                                step_point_recheck_error_mm=point_error,
                                step_normal_recheck_error_rad=normal_error,
                                source_wall_face_index_zero_based=int(face_index))
    return {
        "station_id": station_id,
        "source_wall_face_index_zero_based": int(face_index),
        "wall_role": station.get("wall_role"),
        "u": u,
        "v": v,
        "trimmed_uv_state": "IN",
        "step_point_mm": point_mm.tolist(),
        "outward_from_material": (normal_vec / np.linalg.norm(normal_vec)).tolist(),
        "recorded_point_mm": frozen_point.tolist(),
        "recorded_outward_normal": frozen_normal.tolist(),
    }


def _open_wall_reference(path: Path, expected_step_hash: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("WALL_REFERENCE_FILE_MISSING_OR_SYMLINK")
    record = _read_json(path, "WALL_REFERENCE")
    validation = validate_wall_reference(record, expected_source_geometry_sha256=expected_step_hash)
    if validation.get("status") != "VALID":
        raise ValueError("WALL_REFERENCE_INVALID:" + ",".join(validation.get("errors") or []))
    return record, validation


def _binding_from_loaded_inputs(
    *,
    manifest: Mapping[str, Any],
    asset_root: Path,
    wall_reference_path: Path,
    canonical_shape: cq.Shape,
    file_hashes: Mapping[str, str],
) -> dict[str, Any]:
    """Finish a binding with one already imported canonical STEP shape (internal/test runner)."""
    semantics_path = manifest["provenance"]["spec"]["face_semantics_report"]
    report_path = manifest["validation"]["report"]
    lineage_path = manifest["provenance"]["spec"]["mesh_lineage_npz"]
    surface_path = manifest["geometry"]["surface_npz"]
    semantics = _read_json(package_file(asset_root, semantics_path), "FACE_SEMANTICS")
    geometry_report = _read_json(package_file(asset_root, report_path), "GEOMETRY_REPORT")
    wall_reference = _read_json(wall_reference_path, "WALL_REFERENCE")
    step_hash = file_hashes["canonical_step_file_sha256"]
    if semantics.get("status") != "PASS" or semantics.get("canonical_step_sha256") != step_hash:
        raise ValueError("FACE_SEMANTICS_NOT_PASS_OR_STEP_MISMATCH")
    _validate_wall_reference_source_semantics(wall_reference.get("source_semantics"), semantics)
    wall_validation = validate_wall_reference(
        wall_reference, expected_source_geometry_sha256=step_hash)
    if wall_validation.get("status") != "VALID":
        raise ValueError("WALL_REFERENCE_INVALID:" + ",".join(wall_validation.get("errors") or []))
    _require_matching_backend(semantics)

    params = manifest["provenance"]["spec"].get("parameters")
    if not isinstance(params, Mapping):
        raise ValueError("CANONICAL_SPEC_PARAMETERS_MISSING")
    policy = _load_binding_policy(manifest, geometry_report)
    canonical_face_count = len(canonical_shape.Faces())
    sem_face_count = semantics.get("canonical_step_face_count")
    if canonical_face_count < 1 or sem_face_count != canonical_face_count:
        raise ValueError("REIMPORTED_CANONICAL_FACE_COUNT_MISMATCH")
    if not bool(canonical_shape.isValid()) or len(canonical_shape.Solids()) != 1:
        raise ValueError("REIMPORTED_CANONICAL_STEP_SHAPE_INVALID")
    _check_face_inventory(
        canonical_shape,
        manifest["provenance"]["spec"].get("brep_face_inventory"),
        policy.cad_numeric_tolerance_mm,
        manifest["provenance"]["spec"].get("brep_face_bounds_policy"),
    )

    spec = SimpleNamespace(**dict(params))
    fresh_semantics = classify_canonical_faces(canonical_shape, spec, step_hash)
    if fresh_semantics.get("status") != "PASS":
        raise ValueError("REIMPORTED_CANONICAL_SEMANTICS_UNKNOWN")
    _match_recomputed_semantics(semantics, fresh_semantics, step_hash)

    with np.load(package_file(asset_root, surface_path), allow_pickle=False) as archive:
        vertices = np.array(archive["vertices_mm"], copy=True)
        faces = np.array(archive["faces"], copy=True)
    with np.load(package_file(asset_root, lineage_path), allow_pickle=False) as archive:
        source_faces = np.array(archive["face_source_brep_index"], copy=True)
    mesh_error = _validate_mesh_arrays(vertices, faces, source_faces, canonical_face_count)
    if mesh_error:
        raise ValueError(mesh_error)
    content_hash = parent_mesh_content_sha256(vertices, faces, source_faces)

    bound_stations: list[dict[str, Any]] = []
    canonical_faces = canonical_shape.Faces()
    for station in wall_reference["stations"]:
        face_index = station["source_wall_face_index_zero_based"]
        semantic_row = semantics["faces"][face_index]
        expected_region = "body_outer" if station["wall_role"] == "outer" else "body_inner"
        if semantic_row.get("region_name") != expected_region:
            bound_stations.append(_unknown_station(
                str(station.get("station_id", "")), "WALL_ROLE_SEMANTIC_FACE_MISMATCH",
                source_wall_face_index_zero_based=int(face_index),
                expected_region=expected_region,
                actual_region=semantic_row.get("region_name"),
            ))
            continue
        rechecked = _reevaluate_station_on_step_face(
            canonical_faces[face_index], station, int(face_index), policy)
        if rechecked.get("status") == "UNKNOWN":
            bound_stations.append(rechecked)
            continue
        bound_stations.append(bind_station_to_parent_mesh(
            rechecked, vertices, faces, source_faces,
            canonical_face_count=canonical_face_count, policy=policy))

    record = _aggregate_bound_stations(
        bound_stations, vertices, faces, source_faces,
        canonical_face_count=canonical_face_count,
        parent_mesh_content_hash=content_hash,
        policy=policy,
    )
    # The aggregator consumes terminal binding rows; preserve original station
    # diagnostics rather than interpreting its synthetic rows as already rechecked coordinates.
    record["stations"] = bound_stations
    record["input_file_sha256"] = dict(file_hashes)
    record["brep_face_bounds_policy"] = brep_face_bounds_policy_record()
    record["brep_face_bounds_policy_id"] = BREP_FACE_BOUNDS_POLICY_ID
    record["canonical_step_face_count"] = int(canonical_face_count)
    record["parent_vertex_count"] = int(len(vertices))
    record["parent_triangle_count"] = int(len(faces))
    record["frame"] = "right_handed_z_up"
    record["units"] = {"length": "mm", "direction": "dimensionless"}
    record["canonical_step_backend"] = _runtime_backend()
    record["wall_reference_validation"] = wall_validation
    record["source_scope"] = wall_reference.get("source_scope")
    record["coverage"]["stations_requested"] = int(len(wall_reference["stations"]))
    record["coverage"]["stations_bound"] = sum(
        row.get("status") == "BOUND" for row in bound_stations)
    requested = record["coverage"]["stations_requested"]
    record["coverage"]["station_mapping_fraction"] = (
        float(record["coverage"]["stations_bound"] / requested) if requested else None)
    full = requested > 0 and record["coverage"]["stations_bound"] == requested
    record["status"] = "PASS_MOTHER_STATION_BINDING" if full else "UNKNOWN"
    record["reason"] = None if full else "NOT_ALL_WALL_REFERENCE_STATIONS_BOUND"
    record["qualification"]["mesh_binding_status"] = record["status"]
    return record


def build_wall_mesh_binding(
    asset_root: str | Path,
    wall_reference_path: str | Path,
) -> dict[str, Any]:
    """Read a forge.asset.v1 package and bind its frozen wall stations to its parent surface.

    All file hashes are independently recomputed and returned. Any missing, stale, ambiguous or
    inconsistent input yields structured UNKNOWN; no mesh repair, face fallback or tolerance fit
    is attempted. The function is read-only and does not write into the asset package.
    """
    hashes: dict[str, str] = {}
    root = Path(asset_root)
    try:
        root = root.resolve(strict=True)
        if not root.is_dir():
            return _unknown_record("ASSET_ROOT_NOT_DIRECTORY")
        validation = validate_asset(root)
        if validation.get("contract_status") != "PASS" or validation.get("geometry_status") != "PASS":
            return _unknown_record("ASSET_VALIDATION_NOT_PASS")
        manifest = load_manifest(root)
        provenance_spec = manifest["provenance"]["spec"]
        validate_brep_face_bounds_policy(provenance_spec.get("brep_face_bounds_policy"))
        paths = {
            "canonical_step_file_sha256": manifest["geometry"]["solid_step"],
            "face_semantics_file_sha256": provenance_spec["face_semantics_report"],
            "parent_surface_file_sha256": manifest["geometry"]["surface_npz"],
            "parent_lineage_file_sha256": provenance_spec["mesh_lineage_npz"],
        }
        package_paths: dict[str, Path] = {}
        for key, relative in paths.items():
            if not isinstance(relative, str):
                raise ValueError(f"PACKAGE_PATH_INVALID:{key}")
            package_path = package_file(root, relative)
            package_paths[key] = package_path
            hashes[key] = _verify_package_file_hash(manifest, relative, package_path)
        reference_path = Path(wall_reference_path)
        if not reference_path.is_absolute():
            reference_path = root / reference_path
        if reference_path.is_symlink():
            raise ValueError("WALL_REFERENCE_FILE_MISSING_OR_SYMLINK")
        reference_path = reference_path.resolve(strict=True)
        if not reference_path.is_file():
            raise ValueError("WALL_REFERENCE_FILE_MISSING_OR_SYMLINK")
        hashes["wall_reference_file_sha256"] = sha256_file(reference_path)
        wall_record, wall_validation = _open_wall_reference(
            reference_path, hashes["canonical_step_file_sha256"])
        del wall_validation
        del wall_record

        # Re-import the exact STEP bytes once; face index namespace is version- and inventory-bound.
        canonical = cq.importers.importStep(str(package_paths["canonical_step_file_sha256"])).val()
        # Run the shared binding body with the same canonical import used for face-index checks.
        record = _binding_from_loaded_inputs(
            manifest=manifest, asset_root=root, wall_reference_path=reference_path,
            canonical_shape=canonical, file_hashes=hashes)
        if record.get("status") != "PASS_MOTHER_STATION_BINDING":
            return record
        return record
    except (AssetValidationError, OSError, KeyError, TypeError, ValueError, OverflowError) as exc:
        reason = str(exc) or type(exc).__name__
        return _unknown_record(reason, hashes=hashes)
