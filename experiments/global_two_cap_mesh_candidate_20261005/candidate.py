"""Quarantined source for the two-planar-cap global mesh candidate.

Importing this module is inert. Mesh generation is available only through the
explicit ``--run`` entry point after root review. The output is schema-v2 and
does not expose the unsafe schema-v1 source-face aliases.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
REVIEW_ROOT = REPO_ROOT / "vesselforge" / "tmp" / "review_20261005" / "global_two_cap_mesh_candidate"
RUN_DIR = REVIEW_ROOT / "run01_two_cap"
BASELINE_NPZ = REPO_ROOT / "vesselforge" / "tmp" / "review_20261004" / "surface_ornament_route" / "run02" / "fixture_arrays.npz"
LOCAL_B_DIR = REPO_ROOT / "vesselforge" / "tmp" / "review_20261005" / "ornament_resume" / "local_refinement_run" / "local_b_0p25mm"
LOCAL_B_NPZ = LOCAL_B_DIR / "candidate_arrays.npz"
LOCAL_B_CHECKS = LOCAL_B_DIR / "checks.json"
REFINEMENT_SOURCE = REPO_ROOT / "vesselforge" / "experiments" / "surface_ornament_refinement_20261005" / "refinement_prototype.py"
CASE_FREEZE = REPO_ROOT / "vesselforge" / "experiments" / "surface_ornament_refinement_20261005" / "candidate_cases.json"
PREWRITE_AUDIT = REVIEW_ROOT / "prewrite_budget_audit.json"

EXPECTED_SHA256 = {
    "baseline_npz": "b44bb78176e690d8bc92ab2fc10f0803e142a0311acee8ff3944d4e324b9b974",
    "local_b_npz": "8a2539dff0a05444951ecae6bd66ba2d849c753764dc635a4bacdf8382c6cfdf",
    "local_b_checks": "4e4c08b96bd6e7dd47a3285377979fc93fc3865a0bc1fcdd48d79397c23e14e8",
    "refinement_source": "5e946c205fb233e9354dfdde10d562597484ee38193e7930f93ce999f5840f74",
    "case_freeze": "ab89a0832366d0391b9539248cfbfab62e7ea770f3cf9b1499ee6b39b0b533c1",
}
EXPECTED_PREWRITE_AUDIT_SHA256 = "9aa9464977a3d551585182ab2b355b09f4b2f7db8843b9056fe0baf5cba9a5c1"

GRID_SPACING_MM = 1.0
BOUNDARY_MARGIN_MM = 0.40
MAX_NEW_VERTICES = 2500
MAX_OUTPUT_FACES = 45000
MAX_PATCH_RECORDS = 15000
MAX_PATCH_VERTICES = 60000
MAX_PARENTS_PER_OUTPUT_FACE = 128
MAX_WALL_CLOCK_SECONDS = 120.0
AREA_EPS_MM2 = 1e-12
CAP_FACE_AREA_TOLERANCE_MM2 = 1e-9
PATCH_OVERLAP_TOLERANCE_MM2 = 1e-10
LINEAGE_TOLERANCE_MM = 1e-9
COLOR_TOLERANCE = 1e-12
GLOBAL_FLOAT_ULPS = 64.0


class CandidateUnknown(RuntimeError):
    """A frozen input, provenance, geometry, or budget condition failed."""


@dataclass(frozen=True)
class PlanarCap:
    surface_id: str
    plane_z_mm: float
    radius_mm: float
    orientation: str
    source_face_ids: np.ndarray
    center_vertex_id: int
    boundary_vertex_ids: np.ndarray
    polygon_xy_mm: np.ndarray


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {name: archive[name].copy() for name in archive.files}


def _input_paths() -> dict[str, Path]:
    return {
        "baseline_npz": BASELINE_NPZ,
        "local_b_npz": LOCAL_B_NPZ,
        "local_b_checks": LOCAL_B_CHECKS,
        "refinement_source": REFINEMENT_SOURCE,
        "case_freeze": CASE_FREEZE,
    }


def load_pinned_inputs() -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, Any], dict[str, Any]]:
    """Read the immutable fixture/local-B input set after exact SHA checks."""
    actual = {name: sha256_file(path) for name, path in _input_paths().items()}
    if actual != EXPECTED_SHA256:
        mismatches = {name: (EXPECTED_SHA256[name], actual[name]) for name in actual if actual[name] != EXPECTED_SHA256[name]}
        raise CandidateUnknown(f"pinned input SHA mismatch: {mismatches}")
    baseline = _load_npz(BASELINE_NPZ)
    local_b = _load_npz(LOCAL_B_NPZ)
    old_checks = json.loads(LOCAL_B_CHECKS.read_text(encoding="utf-8"))
    cases = json.loads(CASE_FREEZE.read_text(encoding="utf-8"))
    for field_name, key in (
        ("baseline_fixture_arrays_sha256", "baseline_npz"),
        ("refinement_source_sha256", "refinement_source"),
        ("case_freeze_sha256", "case_freeze"),
    ):
        if str(np.asarray(local_b[field_name]).item()) != EXPECTED_SHA256[key]:
            raise CandidateUnknown(f"local-B embedded provenance mismatch at {field_name}")
    if len(local_b["vertices_rest_xyz_mm"]) <= len(baseline["vertices_rest_xyz_mm"]):
        raise CandidateUnknown("local-B no longer contains its frozen baseline prefix plus refinement vertices")
    if int(np.asarray(local_b["original_vertex_count"]).item()) != len(baseline["vertices_rest_xyz_mm"]):
        raise CandidateUnknown("local-B original vertex count differs from the pinned baseline")
    if int(np.asarray(local_b["original_face_count"]).item()) != len(baseline["faces"]):
        raise CandidateUnknown("local-B original face count differs from the pinned baseline")
    if str(cases.get("freeze_id")) != "surface_ornament_refinement_20261005_source_review_v1":
        raise CandidateUnknown("unexpected frozen fixture case identifier")
    if not PREWRITE_AUDIT.is_file():
        raise CandidateUnknown("required independent prewrite noncap audit is missing")
    if sha256_file(PREWRITE_AUDIT) != EXPECTED_PREWRITE_AUDIT_SHA256:
        raise CandidateUnknown("independent prewrite audit hash differs from source freeze")
    audit = json.loads(PREWRITE_AUDIT.read_text(encoding="utf-8"))
    if audit.get("status") != "PREWRITE_AUDIT_PASS" or not audit["data"]["no_candidate_geometry_or_triangulation_computed"]:
        raise CandidateUnknown("independent prewrite audit does not prove a valid no-mesh budget preflight")
    return baseline, local_b, cases, old_checks


def _cross2(a: np.ndarray, b: np.ndarray) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def _signed_area(poly: np.ndarray) -> float:
    if len(poly) < 3:
        return 0.0
    return 0.5 * float(np.sum(poly[:, 0] * np.roll(poly[:, 1], -1) - poly[:, 1] * np.roll(poly[:, 0], -1)))


def _ccw(poly: np.ndarray) -> np.ndarray:
    arr = np.asarray(poly, dtype=np.float64)
    return arr if _signed_area(arr) >= 0.0 else arr[::-1].copy()


def _inside_convex_polygon(point: np.ndarray, polygon_ccw: np.ndarray, margin_mm: float) -> bool:
    for index, a in enumerate(polygon_ccw):
        edge = polygon_ccw[(index + 1) % len(polygon_ccw)] - a
        distance = _cross2(edge, point - a) / float(np.linalg.norm(edge))
        if distance < margin_mm - 1e-12:
            return False
    return True


def _triangular_lattice_inside(polygon_xy: np.ndarray) -> np.ndarray:
    """Stable row-major 1 mm triangular lattice inside the frozen 0.4 mm margin."""
    polygon = _ccw(np.asarray(polygon_xy, dtype=np.float64))
    row_height = GRID_SPACING_MM * math.sqrt(3.0) / 2.0
    lower, upper = polygon.min(axis=0), polygon.max(axis=0)
    points: list[tuple[float, float]] = []
    for row in range(int(math.ceil(lower[1] / row_height)), int(math.floor(upper[1] / row_height)) + 1):
        y = row * row_height
        offset = 0.5 * GRID_SPACING_MM if row % 2 else 0.0
        first_col = int(math.ceil((lower[0] - offset) / GRID_SPACING_MM))
        last_col = int(math.floor((upper[0] - offset) / GRID_SPACING_MM))
        for col in range(first_col, last_col + 1):
            point = np.asarray((col * GRID_SPACING_MM + offset, y), dtype=np.float64)
            if float(np.linalg.norm(point)) <= 1e-10:
                continue  # retain the exact frozen center vertex
            if _inside_convex_polygon(point, polygon, BOUNDARY_MARGIN_MM):
                points.append((float(point[0]), float(point[1])))
                if len(points) > MAX_NEW_VERTICES:
                    raise CandidateUnknown("one cap lattice exceeded the fixed aggregate vertex budget")
    if not points:
        raise CandidateUnknown("fixed triangular lattice produced no interior vertices")
    return np.asarray(points, dtype=np.float64)


def _barycentric_xy(point: np.ndarray, triangle_xy: np.ndarray) -> np.ndarray:
    a, b, c = np.asarray(triangle_xy, dtype=np.float64)
    v0, v1, v2 = b - a, c - a, np.asarray(point, dtype=np.float64) - a
    denominator = _cross2(v0, v1)
    if abs(denominator) <= 1e-15:
        raise CandidateUnknown("degenerate triangle in planar lineage calculation")
    weight_b = _cross2(v2, v1) / denominator
    weight_c = _cross2(v0, v2) / denominator
    result = np.asarray((1.0 - weight_b - weight_c, weight_b, weight_c), dtype=np.float64)
    result[np.abs(result) < 5e-13] = 0.0
    result[np.abs(result - 1.0) < 5e-13] = 1.0
    if result.min() < -1e-10 or result.max() > 1.0 + 1e-10:
        raise CandidateUnknown("barycentric coordinates escaped their source simplex")
    result = np.clip(result, 0.0, 1.0)
    return result / float(result.sum())


def _clip_convex(subject_xy: np.ndarray, clip_xy: np.ndarray) -> np.ndarray:
    """Sutherland-Hodgman convex polygon intersection in one cap's XY chart."""
    output = [np.asarray(p, dtype=np.float64) for p in _ccw(subject_xy)]
    clipper = _ccw(np.asarray(clip_xy, dtype=np.float64))
    for edge_index in range(len(clipper)):
        if not output:
            break
        clip_a = clipper[edge_index]
        clip_edge = clipper[(edge_index + 1) % len(clipper)] - clip_a
        previous = output
        output = []
        start = previous[-1]
        start_side = _cross2(clip_edge, start - clip_a)
        for end in previous:
            end_side = _cross2(clip_edge, end - clip_a)
            start_inside = start_side >= -1e-12
            end_inside = end_side >= -1e-12
            if end_inside:
                if not start_inside and abs(start_side - end_side) > 1e-18:
                    output.append(start + (start_side / (start_side - end_side)) * (end - start))
                output.append(end)
            elif start_inside and abs(start_side - end_side) > 1e-18:
                output.append(start + (start_side / (start_side - end_side)) * (end - start))
            start, start_side = end, end_side
    if len(output) < 3:
        return np.empty((0, 2), dtype=np.float64)
    compact: list[np.ndarray] = []
    for point in output:
        if not compact or float(np.linalg.norm(point - compact[-1])) > 1e-11:
            compact.append(point)
    if len(compact) > 1 and float(np.linalg.norm(compact[0] - compact[-1])) <= 1e-11:
        compact.pop()
    if len(compact) < 3:
        return np.empty((0, 2), dtype=np.float64)
    result = np.asarray(compact, dtype=np.float64)
    return result if abs(_signed_area(result)) > AREA_EPS_MM2 else np.empty((0, 2), dtype=np.float64)


def _clean_barycentric(weights: np.ndarray) -> np.ndarray:
    result = np.asarray(weights, dtype=np.float64).copy()
    result[np.abs(result) < 5e-13] = 0.0
    result[np.abs(result - 1.0) < 5e-13] = 1.0
    if result.min() < -1e-10 or result.max() > 1.0 + 1e-10:
        raise CandidateUnknown("barycentric coordinates escaped their simplex")
    result = np.clip(result, 0.0, 1.0)
    total = float(result.sum())
    if total <= 0.0:
        raise CandidateUnknown("empty barycentric simplex")
    return result / total


def _find_caps(baseline: dict[str, np.ndarray]) -> list[PlanarCap]:
    rest = np.asarray(baseline["vertices_rest_xyz_mm"], dtype=np.float64)
    faces = np.asarray(baseline["faces"], dtype=np.int64)
    outer_radius = float(np.asarray(baseline["outer_radius_mm"]).item())
    inner_radius = float(np.asarray(baseline["inner_radius_mm"]).item())
    inner_floor_z = float(np.asarray(baseline["floor_mm"]).item())
    if (outer_radius, inner_radius, inner_floor_z) != (20.0, 17.0, 2.0):
        raise CandidateUnknown("fixture radii/floor do not match the pinned R20/R17/z2 case")
    caps: list[PlanarCap] = []
    for surface_id, z, radius, orientation in (
        ("bottom_exterior_z0", 0.0, outer_radius, "outward_-z"),
        ("interior_floor_z2", inner_floor_z, inner_radius, "inward_+z"),
    ):
        tri = rest[faces]
        radii = np.linalg.norm(tri[:, :, :2], axis=2)
        center_count = np.count_nonzero(radii <= 1e-12, axis=1)
        boundary_count = np.count_nonzero(np.abs(radii - radius) <= 1e-9, axis=1)
        mask = (
            np.all(np.abs(tri[:, :, 2] - z) <= 1e-12, axis=1)
            & np.all(radii <= radius + 1e-10, axis=1)
            & (center_count == 1)
            & (boundary_count == 2)
        )
        source_ids = np.flatnonzero(mask).astype(np.int64)
        if len(source_ids) != 128:
            raise CandidateUnknown(f"{surface_id}: expected exactly 128 pinned source faces; got {len(source_ids)}")
        center_candidates = np.unique(faces[source_ids][radii[source_ids] <= 1e-12])
        if len(center_candidates) != 1:
            raise CandidateUnknown(f"{surface_id}: expected one pinned source center")
        center_id = int(center_candidates[0])
        boundary_ids = np.unique(faces[source_ids][faces[source_ids] != center_id])
        if len(boundary_ids) != 128:
            raise CandidateUnknown(f"{surface_id}: expected an unchanged 128-vertex interface")
        if not np.allclose(np.linalg.norm(rest[boundary_ids, :2], axis=1), radius, rtol=0.0, atol=1e-9):
            raise CandidateUnknown(f"{surface_id}: interface is not the pinned regular-radius polygon")
        theta = np.arctan2(rest[boundary_ids, 1], rest[boundary_ids, 0])
        boundary_ids = boundary_ids[np.argsort(theta, kind="stable")]
        polygon = rest[boundary_ids, :2].copy()
        if _signed_area(polygon) <= 0.0:
            raise CandidateUnknown(f"{surface_id}: invalid planar chart boundary orientation")
        original_xy = rest[faces[int(source_ids[0])], :2]
        sign = _signed_area(original_xy)
        if (orientation == "outward_-z" and sign >= 0.0) or (orientation == "inward_+z" and sign <= 0.0):
            raise CandidateUnknown(f"{surface_id}: actual source winding disagrees with its physical orientation")
        caps.append(PlanarCap(surface_id, z, radius, orientation, source_ids, center_id, boundary_ids, polygon))
    if np.intersect1d(caps[0].source_face_ids, caps[1].source_face_ids).size:
        raise CandidateUnknown("the two planar cap source-face identity sets overlap")
    return caps


def _source_owner(point_xy: np.ndarray, baseline: dict[str, np.ndarray], cap: PlanarCap) -> tuple[int, np.ndarray]:
    rest = np.asarray(baseline["vertices_rest_xyz_mm"], dtype=np.float64)
    faces = np.asarray(baseline["faces"], dtype=np.int64)
    for source_id in cap.source_face_ids:  # ascending source identity, deterministic on a shared edge
        tri = rest[faces[int(source_id)], :2]
        bary = _barycentric_xy(point_xy, tri)
        if bary.min() >= -1e-10 and bary.max() <= 1.0 + 1e-10:
            return int(source_id), _clean_barycentric(bary)
    raise CandidateUnknown(f"no pinned {cap.surface_id} parent owns lattice point {point_xy.tolist()}")


def _orient_triangle(triangle: np.ndarray, point_by_vertex: dict[int, np.ndarray], desired_sign: float) -> np.ndarray:
    result = np.asarray(triangle, dtype=np.int64).copy()
    signed = _cross2(
        point_by_vertex[int(result[1])] - point_by_vertex[int(result[0])],
        point_by_vertex[int(result[2])] - point_by_vertex[int(result[0])],
    )
    if abs(signed) <= 1e-13:
        raise CandidateUnknown("Delaunay emitted a zero-area cap triangle")
    if signed * desired_sign < 0.0:
        result[[1, 2]] = result[[2, 1]]
    return result


def _linear_rgb_to_srgb(linear: np.ndarray) -> np.ndarray:
    value = np.clip(np.asarray(linear, dtype=np.float64), 0.0, 1.0)
    return np.where(value <= 0.0031308, 12.92 * value, 1.055 * np.power(value, 1.0 / 2.4) - 0.055)


def _base_cap_color(point_xy: np.ndarray, base_linear_rgb: np.ndarray) -> np.ndarray:
    """Sample the frozen unornamented base field at either planar cap chart point."""
    if np.asarray(point_xy).shape != (2,):
        raise CandidateUnknown("planar cap color sample must be an XY point")
    return np.asarray(base_linear_rgb, dtype=np.float64).copy()


def _triangulate_cap(
    baseline: dict[str, np.ndarray], local_b: dict[str, np.ndarray], cap: PlanarCap,
    interior_xy: np.ndarray, first_new_vertex_id: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    try:
        from scipy.spatial import Delaunay
    except Exception as exc:  # pragma: no cover - runtime dependent
        raise CandidateUnknown(f"SciPy Delaunay is unavailable: {exc}") from exc
    center_xy = np.asarray(local_b["vertices_rest_xyz_mm"], dtype=np.float64)[cap.center_vertex_id, :2]
    boundary_xy = np.asarray(local_b["vertices_rest_xyz_mm"], dtype=np.float64)[cap.boundary_vertex_ids, :2]
    point_xy = np.vstack((center_xy[None, :], boundary_xy, interior_xy))
    new_ids = np.arange(first_new_vertex_id, first_new_vertex_id + len(interior_xy), dtype=np.int64)
    point_vertex_ids = np.concatenate((np.asarray([cap.center_vertex_id], dtype=np.int64), cap.boundary_vertex_ids, new_ids))
    if len(np.unique(point_vertex_ids)) != len(point_vertex_ids):
        raise CandidateUnknown(f"{cap.surface_id}: duplicate vertex ID in cap chart")
    if len(np.unique(point_xy, axis=0)) != len(point_xy):
        raise CandidateUnknown(f"{cap.surface_id}: duplicate planar point in Delaunay input")
    triangulation = Delaunay(point_xy, qhull_options="Qbb Qc Qz Q12")
    simplices = np.asarray(triangulation.simplices, dtype=np.int64)
    if simplices.ndim != 2 or simplices.shape[1] != 3 or simplices.max(initial=-1) >= len(point_vertex_ids):
        raise CandidateUnknown(f"{cap.surface_id}: Delaunay returned malformed simplices")
    source_faces = np.asarray(baseline["faces"], dtype=np.int64)
    source_rest = np.asarray(baseline["vertices_rest_xyz_mm"], dtype=np.float64)
    desired_sign = math.copysign(1.0, _signed_area(source_rest[source_faces[int(cap.source_face_ids[0])], :2]))
    point_by_vertex = {int(vertex): point_xy[i] for i, vertex in enumerate(point_vertex_ids)}
    oriented = [_orient_triangle(point_vertex_ids[simplex], point_by_vertex, desired_sign) for simplex in simplices]
    oriented.sort(key=lambda tri: tuple(sorted(int(v) for v in tri)))
    output_faces = np.asarray(oriented, dtype=np.int64)
    euler_expected = 2 * len(interior_xy) + len(cap.boundary_vertex_ids)
    if len(output_faces) != euler_expected:
        raise CandidateUnknown(f"{cap.surface_id}: triangulation face count {len(output_faces)} violates disk Euler count {euler_expected}")
    vertex_source_ids: list[int] = []
    vertex_bary: list[np.ndarray] = []
    for point in interior_xy:
        parent, bary = _source_owner(point, baseline, cap)
        vertex_source_ids.append(parent)
        vertex_bary.append(bary)
    return output_faces, new_ids, np.asarray(vertex_source_ids, dtype=np.int64), np.asarray(vertex_bary, dtype=np.float64)


def build_candidate(
    baseline: dict[str, np.ndarray], local_b: dict[str, np.ndarray], cases: dict[str, Any], started_clock: float,
) -> dict[str, np.ndarray]:
    """Replace only the two pinned planar disk fans; retain all other arrays/faces."""
    base_rest = np.asarray(baseline["vertices_rest_xyz_mm"], dtype=np.float64)
    base_faces = np.asarray(baseline["faces"], dtype=np.int64)
    base_relief = np.asarray(baseline["vertices_relief_xyz_mm"], dtype=np.float64)
    input_rest = np.asarray(local_b["vertices_rest_xyz_mm"], dtype=np.float64)
    input_relief = np.asarray(local_b["vertices_relief_xyz_mm"], dtype=np.float64)
    input_faces = np.asarray(local_b["faces"], dtype=np.int64)
    input_sources = np.asarray(local_b["source_face_ids"], dtype=np.int64)
    if not np.array_equal(input_rest[:len(base_rest)], base_rest):
        raise CandidateUnknown("local-B rest vertices do not preserve the exact run02 baseline prefix")
    if len(input_faces) != len(input_sources):
        raise CandidateUnknown("local-B face/source identity arrays have inconsistent lengths")
    caps = _find_caps(baseline)
    all_cap_sources = np.concatenate([cap.source_face_ids for cap in caps])
    cap_input_mask = np.isin(input_sources, all_cap_sources)
    cap_input_face_ids = np.flatnonzero(cap_input_mask)
    if len(cap_input_face_ids) != 256:
        raise CandidateUnknown(f"expected exactly 256 local-B source-identified cap faces; got {len(cap_input_face_ids)}")
    for cap in caps:
        cap_child_ids: list[int] = []
        for source_id in cap.source_face_ids:
            matches = np.flatnonzero(input_sources == int(source_id))
            if len(matches) != 1:
                raise CandidateUnknown(f"{cap.surface_id}: source face {int(source_id)} is not one-to-one in local-B")
            child_id = int(matches[0])
            if not np.array_equal(np.sort(input_faces[child_id]), np.sort(base_faces[int(source_id)])):
                raise CandidateUnknown(f"{cap.surface_id}: local-B child does not map to its actual baseline parent")
            cap_child_ids.append(child_id)
        if len(cap_child_ids) != 128:
            raise CandidateUnknown(f"{cap.surface_id}: local-B child face count changed")

    base_linear_rgb = np.asarray(cases["field"]["base_linear_rgb"], dtype=np.float64)
    if base_linear_rgb.shape != (3,) or not np.isfinite(base_linear_rgb).all():
        raise CandidateUnknown("frozen base linear-RGB sample is malformed")
    local_base_table = np.asarray(local_b["outer_base_linear_rgb"])
    frozen_baseline_table = np.asarray(baseline["outer_color_linear_rgb"])
    if (local_base_table.shape != frozen_baseline_table.shape
            or local_base_table.dtype != frozen_baseline_table.dtype
            or not np.array_equal(np.ascontiguousarray(local_base_table).view(np.uint8),
                                  np.ascontiguousarray(frozen_baseline_table).view(np.uint8))):
        raise CandidateUnknown("preserved patterned baseline outer color table differs bitwise from the pinned input")

    interior_by_cap = [_triangular_lattice_inside(cap.polygon_xy_mm) for cap in caps]
    if [len(points) for points in interior_by_cap] != [1392, 1002]:
        raise CandidateUnknown("the fixed lattice counts no longer match the independently frozen prewrite audit")
    total_new_vertices = sum(len(points) for points in interior_by_cap)
    if total_new_vertices > MAX_NEW_VERTICES:
        raise CandidateUnknown("aggregate two-cap interior vertex count exceeds its fixed budget")
    euler_faces = [2 * len(points) + len(cap.boundary_vertex_ids) for cap, points in zip(caps, interior_by_cap)]
    predicted_output_faces = len(input_faces) - len(cap_input_face_ids) + sum(euler_faces)
    if predicted_output_faces != 41876:
        raise CandidateUnknown("the fixed Euler face count no longer matches the independently frozen prewrite audit")
    if predicted_output_faces > MAX_OUTPUT_FACES:
        raise CandidateUnknown("aggregate two-cap Euler face count exceeds its fixed budget")

    new_face_lists: list[np.ndarray] = []
    new_vertex_ids_by_cap: list[np.ndarray] = []
    vertex_source_by_cap: list[np.ndarray] = []
    vertex_bary_by_cap: list[np.ndarray] = []
    next_vertex = len(input_rest)
    for cap, points in zip(caps, interior_by_cap):
        if time.perf_counter() - started_clock > MAX_WALL_CLOCK_SECONDS:
            raise CandidateUnknown("two-cap generation exceeded its fixed wall-clock budget")
        new_faces, new_ids, owner_ids, owner_bary = _triangulate_cap(
            baseline, local_b, cap, points, next_vertex,
        )
        new_face_lists.append(new_faces)
        new_vertex_ids_by_cap.append(new_ids)
        vertex_source_by_cap.append(owner_ids)
        vertex_bary_by_cap.append(owner_bary)
        next_vertex += len(new_ids)

    new_xyz_parts: list[np.ndarray] = []
    for cap, points in zip(caps, interior_by_cap):
        new_xyz_parts.append(np.column_stack((points, np.full(len(points), cap.plane_z_mm, dtype=np.float64))))
    new_rest = np.vstack(new_xyz_parts)
    if len(new_rest) != total_new_vertices:
        raise CandidateUnknown("aggregate two-cap vertex assembly count changed")
    all_rest = np.vstack((input_rest, new_rest))
    all_relief = np.vstack((input_relief, new_rest.copy()))

    keep_face_ids = np.flatnonzero(~cap_input_mask)
    output_faces = np.vstack([input_faces[keep_face_ids], *new_face_lists]).astype(np.int64)
    if len(output_faces) != predicted_output_faces or len(output_faces) > MAX_OUTPUT_FACES:
        raise CandidateUnknown("two-cap assembled face count violates its preflight or global budget")
    input_bary = np.asarray(local_b["face_corner_barycentric_to_source"], dtype=np.float64)
    legacy_source_ids = np.concatenate((input_sources[keep_face_ids], np.full(len(output_faces) - len(keep_face_ids), -1, dtype=np.int64)))
    legacy_corner_bary = np.concatenate((
        input_bary[keep_face_ids],
        np.full((len(output_faces) - len(keep_face_ids), 3, 3), np.nan, dtype=np.float64),
    ), axis=0)
    lineage_status = np.concatenate((
        np.ones(len(keep_face_ids), dtype=np.uint8),
        np.full(len(output_faces) - len(keep_face_ids), 2, dtype=np.uint8),
    ))

    cap_output_face_ids: list[int] = []
    cap_output_face_surface_index: list[int] = []
    cap_output_face_offsets = [0]
    cap_parent_offsets = [0]
    cap_parent_sources: list[int] = []
    cap_center_ids: list[int] = []
    cap_boundary_ids: list[np.ndarray] = []
    cap_chart_vertex_offsets = [0]
    cap_chart_vertex_ids: list[int] = []
    cap_chart_colors: list[np.ndarray] = []
    cap_chart_names: list[str] = []
    cap_face_patch_offsets = [0]
    cap_patch_surface_index: list[int] = []
    cap_patch_source_ids: list[int] = []
    cap_patch_areas: list[float] = []
    cap_patch_vertex_offsets = [0]
    cap_patch_xy: list[np.ndarray] = []
    cap_patch_bary_source: list[np.ndarray] = []
    cap_patch_bary_output: list[np.ndarray] = []
    cap_patch_colors: list[np.ndarray] = []
    global_patch_records = 0
    global_patch_vertices = 0
    next_output_face = len(keep_face_ids)
    base_polygons = {
        int(source_id): _ccw(base_rest[base_faces[int(source_id)], :2])
        for source_id in all_cap_sources
    }

    for cap_index, (cap, points, cap_faces, new_vertex_ids) in enumerate(
        zip(caps, interior_by_cap, new_face_lists, new_vertex_ids_by_cap)
    ):
        if time.perf_counter() - started_clock > MAX_WALL_CLOCK_SECONDS:
            raise CandidateUnknown("two-cap clipping exceeded its fixed wall-clock budget")
        cap_output_face_ids.extend(range(next_output_face, next_output_face + len(cap_faces)))
        cap_output_face_surface_index.extend([cap_index] * len(cap_faces))
        cap_output_face_offsets.append(len(cap_output_face_ids))
        cap_parent_sources.extend(int(i) for i in cap.source_face_ids)
        cap_parent_offsets.append(len(cap_parent_sources))
        cap_center_ids.append(cap.center_vertex_id)
        cap_boundary_ids.append(cap.boundary_vertex_ids.copy())
        chart_ids = np.unique(np.concatenate((
            np.asarray([cap.center_vertex_id], dtype=np.int64), cap.boundary_vertex_ids, new_vertex_ids,
        )))
        cap_chart_vertex_ids.extend(int(i) for i in chart_ids)
        cap_chart_vertex_offsets.append(len(cap_chart_vertex_ids))
        cap_chart_names.append(f"world_XY_mm_at_z{cap.plane_z_mm:g}")
        cap_chart_colors.extend(_base_cap_color(all_rest[vertex_id, :2], base_linear_rgb) for vertex_id in chart_ids)

        parent_triangles = {int(sid): base_faces[int(sid)] for sid in cap.source_face_ids}
        for local_face_id, candidate_tri in enumerate(cap_faces):
            if (local_face_id & 127) == 0 and time.perf_counter() - started_clock > MAX_WALL_CLOCK_SECONDS:
                raise CandidateUnknown("two-cap lineage clipping exceeded its fixed wall-clock budget")
            output_face_id = next_output_face + local_face_id
            tri_xy = all_rest[candidate_tri, :2]
            triangle_area = abs(_signed_area(tri_xy))
            if triangle_area <= AREA_EPS_MM2:
                raise CandidateUnknown(f"{cap.surface_id}: output triangle has zero chart area")
            subject = _ccw(tri_xy)
            patches: list[tuple[int, np.ndarray, float]] = []
            for source_id in cap.source_face_ids:
                sid = int(source_id)
                intersection = _clip_convex(subject, base_polygons[sid])
                if len(intersection) == 0:
                    continue
                area = abs(_signed_area(intersection))
                if area > AREA_EPS_MM2:
                    patches.append((sid, intersection, area))
            patches.sort(key=lambda item: item[0])
            if not patches:
                raise CandidateUnknown(f"{cap.surface_id}: output face has no source patch")
            if len(patches) > MAX_PARENTS_PER_OUTPUT_FACE:
                raise CandidateUnknown(f"{cap.surface_id}: face exceeds the complete 128-parent fan bound")
            if global_patch_records + len(patches) > MAX_PATCH_RECORDS:
                raise CandidateUnknown("aggregate two-cap cross-parent patch records exceed the fixed 15,000 cap")
            covered_area = sum(item[2] for item in patches)
            if abs(covered_area - triangle_area) > max(CAP_FACE_AREA_TOLERANCE_MM2, triangle_area * 1e-10):
                raise CandidateUnknown(f"{cap.surface_id}: source patches do not cover one output face")
            for left in range(len(patches)):
                for right in range(left + 1, len(patches)):
                    overlap = _clip_convex(patches[left][1], patches[right][1])
                    overlap_area = abs(_signed_area(overlap)) if len(overlap) else 0.0
                    if overlap_area > PATCH_OVERLAP_TOLERANCE_MM2:
                        raise CandidateUnknown(f"{cap.surface_id}: source patches overlap with positive area")

            if len(patches) == 1 and abs(patches[0][2] - triangle_area) <= max(CAP_FACE_AREA_TOLERANCE_MM2, triangle_area * 1e-10):
                parent_id = patches[0][0]
                source_xy = base_rest[parent_triangles[parent_id], :2]
                legacy_source_ids[output_face_id] = parent_id
                legacy_corner_bary[output_face_id] = np.asarray(
                    [_clean_barycentric(_barycentric_xy(point, source_xy)) for point in tri_xy]
                )
                lineage_status[output_face_id] = 1
            for source_id, patch_polygon, area in patches:
                source_xy = base_rest[parent_triangles[source_id], :2]
                source_bary = np.asarray([_clean_barycentric(_barycentric_xy(point, source_xy)) for point in patch_polygon])
                output_bary = np.asarray([_clean_barycentric(_barycentric_xy(point, tri_xy)) for point in patch_polygon])
                patch_colors = np.asarray([_base_cap_color(point, base_linear_rgb) for point in patch_polygon])
                cap_patch_surface_index.append(cap_index)
                cap_patch_source_ids.append(source_id)
                cap_patch_areas.append(float(area))
                cap_patch_xy.extend(patch_polygon)
                cap_patch_bary_source.extend(source_bary)
                cap_patch_bary_output.extend(output_bary)
                cap_patch_colors.extend(patch_colors)
                global_patch_vertices += len(patch_polygon)
                global_patch_records += 1
                if global_patch_vertices > MAX_PATCH_VERTICES:
                    raise CandidateUnknown("aggregate two-cap patch-polygon vertices exceed the fixed 60,000 cap")
                cap_patch_vertex_offsets.append(global_patch_vertices)
            cap_face_patch_offsets.append(global_patch_records)
        next_output_face += len(cap_faces)

    vertex_source_ids = np.concatenate((
        np.asarray(local_b["vertex_lineage_source_face_id"], dtype=np.int64),
        *vertex_source_by_cap,
    ))
    vertex_bary = np.vstack((
        np.asarray(local_b["vertex_lineage_barycentric"], dtype=np.float64),
        *vertex_bary_by_cap,
    ))
    result = {name: np.asarray(value).copy() for name, value in local_b.items()}
    result["vertices_rest_xyz_mm"] = all_rest
    result["vertices_relief_xyz_mm"] = all_relief
    result["faces"] = output_faces
    result.pop("source_face_ids", None)
    result.pop("face_corner_barycentric_to_source", None)
    result["v2_legacy_single_parent_face_source_ids"] = legacy_source_ids
    result["v2_legacy_single_parent_face_corner_barycentric_to_source"] = legacy_corner_bary
    result["face_lineage_status"] = lineage_status
    result["vertex_lineage_source_face_id"] = vertex_source_ids
    result["vertex_lineage_barycentric"] = vertex_bary

    result.update({
        "lineage_schema_version": np.asarray(2, dtype=np.int32),
        "quarantine_status": np.asarray("EXPERIMENT_ONLY_NOT_FOR_PRODUCTION"),
        "legacy_reader_compatibility": np.asarray(
            "UNKNOWN; standard schema-v1 source_face_ids and face_corner_barycentric_to_source keys are omitted"
        ),
        "v2_face_lineage_status_codes": np.asarray("1=single_parent_valid;2=multi_parent_patch_required"),
        "two_cap_candidate_schema": np.asarray("isolated_v2_global_two_planar_cap_patches"),
        "cap_surface_ids": np.asarray([cap.surface_id for cap in caps]),
        "cap_chart_names": np.asarray(cap_chart_names),
        "cap_plane_z_mm": np.asarray([cap.plane_z_mm for cap in caps], dtype=np.float64),
        "cap_radius_mm": np.asarray([cap.radius_mm for cap in caps], dtype=np.float64),
        "cap_orientation": np.asarray([cap.orientation for cap in caps]),
        "cap_center_vertex_ids": np.asarray(cap_center_ids, dtype=np.int64),
        "cap_boundary_vertex_ids_angle_sorted": np.asarray(cap_boundary_ids, dtype=np.int64),
        "cap_parent_offsets": np.asarray(cap_parent_offsets, dtype=np.int64),
        "cap_parent_source_face_ids": np.asarray(cap_parent_sources, dtype=np.int64),
        "cap_output_face_offsets": np.asarray(cap_output_face_offsets, dtype=np.int64),
        "cap_output_face_ids": np.asarray(cap_output_face_ids, dtype=np.int64),
        "cap_output_face_surface_index": np.asarray(cap_output_face_surface_index, dtype=np.uint8),
        "cap_chart_vertex_offsets": np.asarray(cap_chart_vertex_offsets, dtype=np.int64),
        "cap_chart_vertex_indices": np.asarray(cap_chart_vertex_ids, dtype=np.int64),
        "cap_chart_xy_mm": all_rest[np.asarray(cap_chart_vertex_ids, dtype=np.int64), :2].copy(),
        "cap_chart_vertex_color_linear_rgb": np.asarray(cap_chart_colors, dtype=np.float64).reshape(-1, 3),
        "cap_chart_vertex_color_srgb": _linear_rgb_to_srgb(np.asarray(cap_chart_colors, dtype=np.float64).reshape(-1, 3)),
        "cap_face_patch_offsets": np.asarray(cap_face_patch_offsets, dtype=np.int64),
        "cap_face_patch_surface_index": np.asarray(cap_patch_surface_index, dtype=np.uint8),
        "cap_face_patch_source_face_ids": np.asarray(cap_patch_source_ids, dtype=np.int64),
        "cap_face_patch_area_mm2": np.asarray(cap_patch_areas, dtype=np.float64),
        "cap_face_patch_vertex_offsets": np.asarray(cap_patch_vertex_offsets, dtype=np.int64),
        "cap_face_patch_vertices_xy_mm": np.asarray(cap_patch_xy, dtype=np.float64).reshape(-1, 2),
        "cap_face_patch_vertices_barycentric_to_source": np.asarray(cap_patch_bary_source, dtype=np.float64).reshape(-1, 3),
        "cap_face_patch_vertices_barycentric_to_output": np.asarray(cap_patch_bary_output, dtype=np.float64).reshape(-1, 3),
        "cap_face_patch_vertices_color_linear_rgb": np.asarray(cap_patch_colors, dtype=np.float64).reshape(-1, 3),
        "cap_face_patch_vertices_color_srgb": _linear_rgb_to_srgb(
            np.asarray(cap_patch_colors, dtype=np.float64).reshape(-1, 3)
        ),
        "cap_patch_area_tolerance_mm2": np.asarray(CAP_FACE_AREA_TOLERANCE_MM2, dtype=np.float64),
        "cap_patch_overlap_tolerance_mm2": np.asarray(PATCH_OVERLAP_TOLERANCE_MM2, dtype=np.float64),
        "modified_baseline_cap_source_face_ids": all_cap_sources.astype(np.int64),
        "modified_region_physical_surface_ids": np.asarray([cap.surface_id for cap in caps]),
        "candidate_grid_spacing_mm": np.asarray(GRID_SPACING_MM, dtype=np.float64),
        "candidate_boundary_margin_mm": np.asarray(BOUNDARY_MARGIN_MM, dtype=np.float64),
        "candidate_cap_new_vertex_counts": np.asarray([len(points) for points in interior_by_cap], dtype=np.int64),
        "candidate_cap_expected_face_counts": np.asarray(euler_faces, dtype=np.int64),
        "candidate_total_patch_record_count": np.asarray(global_patch_records, dtype=np.int64),
        "candidate_total_patch_vertex_count": np.asarray(global_patch_vertices, dtype=np.int64),
    })
    if len(all_rest) - len(input_rest) != total_new_vertices or total_new_vertices > MAX_NEW_VERTICES:
        raise CandidateUnknown("aggregate two-cap vertex budget is exceeded")
    if len(output_faces) > MAX_OUTPUT_FACES:
        raise CandidateUnknown("aggregate two-cap face budget is exceeded")
    if global_patch_records > MAX_PATCH_RECORDS or global_patch_vertices > MAX_PATCH_VERTICES:
        raise CandidateUnknown("aggregate two-cap cross-parent lineage budget is exceeded")
    if time.perf_counter() - started_clock > MAX_WALL_CLOCK_SECONDS:
        raise CandidateUnknown("two-cap candidate exceeded its fixed 120-second wall-clock budget")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="run one root-approved bounded candidate")
    args = parser.parse_args()
    if not args.run:
        print("SOURCE_ONLY_AWAITING_ROOT_REVIEW; no input files read and no mesh generated. --run requires root approval.")
        return 0
    from focused_checks import render_saved_meshes, run_focused_checks, summarize_triangle_quality

    authorized_review_root = (REPO_ROOT / "vesselforge" / "tmp" / "review_20261005").resolve()
    output_dir = RUN_DIR.resolve()
    if authorized_review_root not in output_dir.parents:
        raise CandidateUnknown("output path escaped the authorized two-cap review directory")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise CandidateUnknown(f"refusing to reuse a nonempty review directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    start_iso = datetime.now(timezone.utc).isoformat()
    started_clock = time.perf_counter()
    input_hash_before = {name: sha256_file(path) for name, path in _input_paths().items()}
    receipt: dict[str, Any] = {
        "candidate_id": "global_two_cap_mesh_candidate_20261005",
        "status": "RUNNING",
        "started_at_utc": start_iso,
        "actual_argv": sys.argv,
        "input_sha256_before": input_hash_before,
        "source_sha256": sha256_file(Path(__file__).resolve()),
        "prewrite_audit_sha256": sha256_file(PREWRITE_AUDIT),
        "generation_invoked": True,
        "candidate_count": 1,
        "automatic_retry": False,
    }
    try:
        baseline, local_b, cases, local_b_checks = load_pinned_inputs()
        candidate = build_candidate(baseline, local_b, cases, started_clock)
        npz_path = output_dir / "candidate_arrays.npz"
        np.savez_compressed(npz_path, **candidate)
        saved_candidate = _load_npz(npz_path)
        check_started = time.perf_counter()
        checks = run_focused_checks(baseline, local_b, saved_candidate, cases, local_b_checks)
        if time.perf_counter() - check_started > MAX_WALL_CLOCK_SECONDS:
            raise CandidateUnknown("saved-NPZ focused readback exceeded its fixed 120-second budget")
        checks_path = output_dir / "checks.json"
        checks_path.write_text(json.dumps(checks, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
        before_quality = summarize_triangle_quality(
            np.asarray(local_b["vertices_relief_xyz_mm"], dtype=np.float64),
            np.asarray(local_b["faces"], dtype=np.int64),
        )
        after_quality = summarize_triangle_quality(
            np.asarray(saved_candidate["vertices_relief_xyz_mm"], dtype=np.float64),
            np.asarray(saved_candidate["faces"], dtype=np.int64),
        )
        render_started = time.perf_counter()
        render_saved_meshes(saved_candidate, output_dir, cases)
        if time.perf_counter() - render_started > MAX_WALL_CLOCK_SECONDS:
            raise CandidateUnknown("actual-geometry PNG preparation exceeded its fixed 120-second budget")
        manifest = {
            "candidate_id": "global_two_cap_mesh_candidate_20261005",
            "schema": "isolated_v2_global_two_planar_cap_patches",
            "quarantine_status": "EXPERIMENT_ONLY_NOT_FOR_PRODUCTION",
            "legacy_reader_compatibility": "UNKNOWN; standard schema-v1 aliases omitted; legacy consumer compatibility is unverified",
            "source_sha256": sha256_file(Path(__file__).resolve()),
            "focused_checks_sha256": sha256_file(HERE / "focused_checks.py"),
            "prewrite_audit_sha256": sha256_file(PREWRITE_AUDIT),
            "input_sha256": EXPECTED_SHA256,
            "candidate_arrays_sha256": sha256_file(npz_path),
            "checks_sha256": sha256_file(checks_path),
            "input_global_quality_relief": before_quality,
            "candidate_global_quality_relief": after_quality,
            "png_sha256": {
                "global_equal_aspect_actual_mesh.png": sha256_file(output_dir / "global_equal_aspect_actual_mesh.png"),
                "two_caps_equal_aspect_actual_mesh.png": sha256_file(output_dir / "two_caps_equal_aspect_actual_mesh.png"),
            },
            "candidate_language": "geometric triangle quality only; no tetrahedral, mechanical h, solver, fracture, physical-match, or production-compatibility claim",
        }
        (output_dir / "candidate_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
        input_hash_after = {name: sha256_file(path) for name, path in _input_paths().items()}
        if input_hash_after != input_hash_before:
            raise CandidateUnknown("one or more pinned inputs changed during the candidate run")
        receipt.update({
            "status": "CANDIDATE_CHECK_PASS" if checks["focused_checks_pass"] else "CANDIDATE_CHECK_FAIL",
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": time.perf_counter() - started_clock,
            "input_sha256_after": input_hash_after,
            "candidate_arrays_sha256": sha256_file(npz_path),
            "candidate_vertices": int(len(saved_candidate["vertices_rest_xyz_mm"])),
            "candidate_faces": int(len(saved_candidate["faces"])),
            "candidate_patch_records": int(np.asarray(saved_candidate["candidate_total_patch_record_count"]).item()),
            "candidate_patch_vertices": int(np.asarray(saved_candidate["candidate_total_patch_vertex_count"]).item()),
            "focused_checks_pass": bool(checks["focused_checks_pass"]),
        })
    except Exception as exc:
        receipt.update({
            "status": "UNKNOWN_OR_FAIL",
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": time.perf_counter() - started_clock,
            "input_sha256_after": {name: sha256_file(path) for name, path in _input_paths().items()},
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
        (output_dir / "run_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
        return 2
    (output_dir / "run_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    return 0 if receipt["status"] == "CANDIDATE_CHECK_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
