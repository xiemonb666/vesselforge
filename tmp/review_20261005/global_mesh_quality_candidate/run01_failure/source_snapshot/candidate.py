"""Isolated source for one bounded global floor-mesh quality candidate.

Importing this module does not read files or generate a mesh.  The only
generation entry point is ``main --run``; it is intentionally not being invoked
while this source is awaiting root review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
REVIEW_ROOT = REPO_ROOT / "vesselforge" / "tmp" / "review_20261005" / "global_mesh_quality_candidate"
CONTRACT_PATH = HERE / "candidate_contract.json"
RUN02_DIR = REPO_ROOT / "vesselforge" / "tmp" / "review_20261004" / "surface_ornament_route" / "run02"
LOCAL_B_DIR = (
    REPO_ROOT
    / "vesselforge"
    / "tmp"
    / "review_20261005"
    / "ornament_resume"
    / "local_refinement_run"
    / "local_b_0p25mm"
)
LOCAL_B_CHECKS = LOCAL_B_DIR / "checks.json"
LOCAL_B_NPZ = LOCAL_B_DIR / "candidate_arrays.npz"
BASELINE_NPZ = RUN02_DIR / "fixture_arrays.npz"
OLD_REFINEMENT_SOURCE = (
    REPO_ROOT
    / "vesselforge"
    / "experiments"
    / "surface_ornament_refinement_20261005"
    / "refinement_prototype.py"
)
OLD_CASES = (
    REPO_ROOT
    / "vesselforge"
    / "experiments"
    / "surface_ornament_refinement_20261005"
    / "candidate_cases.json"
)

EXPECTED = {
    "baseline_sha256": "b44bb78176e690d8bc92ab2fc10f0803e142a0311acee8ff3944d4e324b9b974",
    "local_b_sha256": "8a2539dff0a05444951ecae6bd66ba2d849c753764dc635a4bacdf8382c6cfdf",
    "local_b_checks_sha256": "4e4c08b96bd6e7dd47a3285377979fc93fc3865a0bc1fcdd48d79397c23e14e8",
    "refinement_source_sha256": "5e946c205fb233e9354dfdde10d562597484ee38193e7930f93ce999f5840f74",
    "case_freeze_sha256": "ab89a0832366d0391b9539248cfbfab62e7ea770f3cf9b1499ee6b39b0b533c1",
}

GRID_SPACING_MM = 1.0
BOUNDARY_MARGIN_MM = 0.40
MAX_INTERIOR_VERTICES = 2500
MAX_OUTPUT_FACES = 45000
MAX_PATCH_RECORDS = 15000
MAX_PATCH_VERTICES = 60000
MAX_WALL_CLOCK_SECONDS = 120.0
AREA_EPS_MM2 = 1e-12
GEOMETRY_TOL_MM = 1e-9
LINEAGE_TOL_MM = 1e-9
COLOR_VERTEX_TOL = 1e-12
COLOR_FINITE_SAMPLE_TOL = 1e-12


class CandidateUnknown(RuntimeError):
    """A fixed budget or required pinned-input condition was not met."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {name: archive[name].copy() for name in archive.files}


def load_pinned_inputs() -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, Any], dict[str, Any]]:
    """Read the frozen run02 source and local-B candidate after exact SHA checks."""
    for path, expected in (
        (BASELINE_NPZ, EXPECTED["baseline_sha256"]),
        (LOCAL_B_NPZ, EXPECTED["local_b_sha256"]),
        (LOCAL_B_CHECKS, EXPECTED["local_b_checks_sha256"]),
        (OLD_REFINEMENT_SOURCE, EXPECTED["refinement_source_sha256"]),
        (OLD_CASES, EXPECTED["case_freeze_sha256"]),
    ):
        actual = sha256_file(path)
        if actual != expected:
            raise CandidateUnknown(f"pinned input SHA mismatch for {path.name}: {actual}")

    baseline = _load_npz(BASELINE_NPZ)
    local_b = _load_npz(LOCAL_B_NPZ)
    checks = json.loads(LOCAL_B_CHECKS.read_text(encoding="utf-8"))
    cases = json.loads(OLD_CASES.read_text(encoding="utf-8"))

    for name, expected in (
        ("baseline_fixture_arrays_sha256", EXPECTED["baseline_sha256"]),
        ("refinement_source_sha256", EXPECTED["refinement_source_sha256"]),
        ("case_freeze_sha256", EXPECTED["case_freeze_sha256"]),
    ):
        if str(np.asarray(local_b[name]).item()) != expected:
            raise CandidateUnknown(f"local-B embedded provenance mismatch at {name}")
    if int(np.asarray(local_b["original_vertex_count"]).item()) != len(baseline["vertices_rest_xyz_mm"]):
        raise CandidateUnknown("local-B original vertex count does not match frozen run02")
    if int(np.asarray(local_b["original_face_count"]).item()) != len(baseline["faces"]):
        raise CandidateUnknown("local-B original face count does not match frozen run02")
    if str(cases.get("freeze_id")) != "surface_ornament_refinement_20261005_source_review_v1":
        raise CandidateUnknown("unexpected frozen ornament case identifier")
    return baseline, local_b, checks, cases


def _cross2(a: np.ndarray, b: np.ndarray) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def _signed_area(poly: np.ndarray) -> float:
    if len(poly) < 3:
        return 0.0
    return 0.5 * float(
        np.sum(poly[:, 0] * np.roll(poly[:, 1], -1) - poly[:, 1] * np.roll(poly[:, 0], -1))
    )


def _ccw(poly: np.ndarray) -> np.ndarray:
    return poly if _signed_area(poly) >= 0.0 else poly[::-1].copy()


def _inside_convex_polygon(point: np.ndarray, polygon_ccw: np.ndarray, margin_mm: float) -> bool:
    for index in range(len(polygon_ccw)):
        a = polygon_ccw[index]
        edge = polygon_ccw[(index + 1) % len(polygon_ccw)] - a
        distance_numerator = _cross2(edge, point - a)
        distance = distance_numerator / float(np.linalg.norm(edge))
        if distance < margin_mm - 1e-12:
            return False
    return True


def _triangular_lattice_inside(polygon_xy: np.ndarray) -> np.ndarray:
    """Return stable row-major lattice points strictly inside a fixed margin."""
    polygon = _ccw(np.asarray(polygon_xy, dtype=np.float64))
    spacing = GRID_SPACING_MM
    row_height = spacing * math.sqrt(3.0) / 2.0
    lower = polygon.min(axis=0)
    upper = polygon.max(axis=0)
    first_row = int(math.ceil(lower[1] / row_height))
    last_row = int(math.floor(upper[1] / row_height))
    points: list[tuple[float, float]] = []
    for row in range(first_row, last_row + 1):
        y = row * row_height
        offset = 0.5 * spacing if row % 2 else 0.0
        first_column = int(math.ceil((lower[0] - offset) / spacing))
        last_column = int(math.floor((upper[0] - offset) / spacing))
        for column in range(first_column, last_column + 1):
            point = np.asarray((column * spacing + offset, y), dtype=np.float64)
            if float(np.linalg.norm(point)) <= 1e-10:
                continue  # retain the exact frozen center vertex instead
            if _inside_convex_polygon(point, polygon, BOUNDARY_MARGIN_MM):
                points.append((float(point[0]), float(point[1])))
                if len(points) > MAX_INTERIOR_VERTICES:
                    raise CandidateUnknown("interior lattice exceeded its fixed vertex budget")
    if not points:
        raise CandidateUnknown("bounded lattice produced no interior vertices")
    return np.asarray(points, dtype=np.float64)


def _barycentric_xy(point: np.ndarray, triangle_xy: np.ndarray) -> np.ndarray:
    a, b, c = np.asarray(triangle_xy, dtype=np.float64)
    v0 = b - a
    v1 = c - a
    v2 = np.asarray(point, dtype=np.float64) - a
    denominator = _cross2(v0, v1)
    if abs(denominator) <= 1e-15:
        raise CandidateUnknown("degenerate source or output triangle in lineage calculation")
    weight_b = _cross2(v2, v1) / denominator
    weight_c = _cross2(v0, v2) / denominator
    return np.asarray((1.0 - weight_b - weight_c, weight_b, weight_c), dtype=np.float64)


def _clean_barycentric(weights: np.ndarray) -> np.ndarray:
    result = np.asarray(weights, dtype=np.float64).copy()
    result[np.abs(result) < 5e-13] = 0.0
    result[np.abs(result - 1.0) < 5e-13] = 1.0
    if result.min() < -1e-10 or result.max() > 1.0 + 1e-10:
        raise CandidateUnknown("source/output barycentric coordinate escaped its simplex")
    result = np.clip(result, 0.0, 1.0)
    total = float(result.sum())
    if total <= 0.0:
        raise CandidateUnknown("empty barycentric simplex")
    return result / total


def _floor_source_faces(baseline: dict[str, np.ndarray]) -> tuple[np.ndarray, int, np.ndarray]:
    rest = np.asarray(baseline["vertices_rest_xyz_mm"], dtype=np.float64)
    faces = np.asarray(baseline["faces"], dtype=np.int64)
    radius = float(np.asarray(baseline["outer_radius_mm"]).item())
    z0 = 0.0
    tri_xyz = rest[faces]
    z_mask = np.all(np.abs(tri_xyz[:, :, 2] - z0) <= 1e-12, axis=1)
    radial = np.linalg.norm(tri_xyz[:, :, :2], axis=2)
    in_radius = np.all(radial <= radius + 1e-10, axis=1)
    fan = np.flatnonzero(z_mask & in_radius)
    center_candidates = np.flatnonzero(
        (np.abs(rest[:, 2] - z0) <= 1e-12)
        & (np.linalg.norm(rest[:, :2], axis=1) <= 1e-12)
    )
    if len(fan) != 128 or len(center_candidates) != 1:
        raise CandidateUnknown(f"expected the pinned 128-face bottom fan; got {len(fan)} faces")
    center_id = int(center_candidates[0])
    boundary = np.unique(faces[fan][faces[fan] != center_id])
    if len(boundary) != 128:
        raise CandidateUnknown(f"expected 128 bottom interface vertices; got {len(boundary)}")
    boundary_radius = np.linalg.norm(rest[boundary, :2], axis=1)
    if not np.allclose(boundary_radius, radius, rtol=0.0, atol=1e-9):
        raise CandidateUnknown("bottom interface does not match the frozen outer-radius polygon")
    theta = np.arctan2(rest[boundary, 1], rest[boundary, 0])
    boundary = boundary[np.argsort(theta, kind="stable")]
    polygon = _ccw(rest[boundary, :2])
    if _signed_area(polygon) <= 0.0:
        raise CandidateUnknown("bottom interface polygon has invalid orientation")
    return fan.astype(np.int64), center_id, boundary.astype(np.int64)


def _clip_convex(subject_xy: np.ndarray, clip_xy: np.ndarray) -> np.ndarray:
    """Sutherland-Hodgman intersection for two small convex XY polygons."""
    output = [np.asarray(p, dtype=np.float64) for p in _ccw(subject_xy)]
    clipper = _ccw(np.asarray(clip_xy, dtype=np.float64))
    for edge_index in range(len(clipper)):
        if not output:
            break
        clip_a = clipper[edge_index]
        clip_edge = clipper[(edge_index + 1) % len(clipper)] - clip_a
        input_points = output
        output = []
        start = input_points[-1]
        start_side = _cross2(clip_edge, start - clip_a)
        for end in input_points:
            end_side = _cross2(clip_edge, end - clip_a)
            start_inside = start_side >= -1e-12
            end_inside = end_side >= -1e-12
            if end_inside:
                if not start_inside:
                    denominator = start_side - end_side
                    if abs(denominator) > 1e-18:
                        t = start_side / denominator
                        output.append(start + t * (end - start))
                output.append(end)
            elif start_inside:
                denominator = start_side - end_side
                if abs(denominator) > 1e-18:
                    t = start_side / denominator
                    output.append(start + t * (end - start))
            start = end
            start_side = end_side
    if len(output) < 3:
        return np.empty((0, 2), dtype=np.float64)
    polygon = np.asarray(output, dtype=np.float64)
    compact: list[np.ndarray] = []
    for point in polygon:
        if not compact or float(np.linalg.norm(point - compact[-1])) > 1e-11:
            compact.append(point)
    if len(compact) > 1 and float(np.linalg.norm(compact[0] - compact[-1])) <= 1e-11:
        compact.pop()
    if len(compact) < 3:
        return np.empty((0, 2), dtype=np.float64)
    result = np.asarray(compact, dtype=np.float64)
    return result if abs(_signed_area(result)) > AREA_EPS_MM2 else np.empty((0, 2), dtype=np.float64)


def _source_owner(point_xy: np.ndarray, baseline: dict[str, np.ndarray], floor_source_ids: np.ndarray) -> tuple[int, np.ndarray]:
    base_rest = np.asarray(baseline["vertices_rest_xyz_mm"], dtype=np.float64)
    base_faces = np.asarray(baseline["faces"], dtype=np.int64)
    for source_id in np.sort(np.asarray(floor_source_ids, dtype=np.int64)):
        tri_ids = base_faces[int(source_id)]
        tri_xy = base_rest[tri_ids, :2]
        bary = _barycentric_xy(point_xy, tri_xy)
        if bary.min() >= -1e-10 and bary.max() <= 1.0 + 1e-10:
            return int(source_id), _clean_barycentric(bary)
    raise CandidateUnknown(f"no frozen bottom source face owns XY point {point_xy.tolist()}")


def _sample_floor_color(point_xy: np.ndarray, base_linear_rgb: np.ndarray) -> np.ndarray:
    """The frozen planar bottom field is constant base linear RGB at z=0."""
    if np.asarray(point_xy, dtype=np.float64).shape != (2,):
        raise CandidateUnknown("floor color sample requires one XY point")
    return np.asarray(base_linear_rgb, dtype=np.float64).copy()


def _linear_rgb_to_srgb(linear: np.ndarray) -> np.ndarray:
    value = np.clip(np.asarray(linear, dtype=np.float64), 0.0, 1.0)
    return np.where(value <= 0.0031308, 12.92 * value, 1.055 * np.power(value, 1.0 / 2.4) - 0.055)


def _orient_triangle(triangle: np.ndarray, xy_by_candidate_id: dict[int, np.ndarray], desired_sign: float) -> np.ndarray:
    result = np.asarray(triangle, dtype=np.int64).copy()
    signed = _cross2(xy_by_candidate_id[int(result[1])] - xy_by_candidate_id[int(result[0])],
                     xy_by_candidate_id[int(result[2])] - xy_by_candidate_id[int(result[0])])
    if abs(signed) <= 1e-13:
        raise CandidateUnknown("Delaunay emitted a zero-area floor triangle")
    if signed * desired_sign < 0.0:
        result[[1, 2]] = result[[2, 1]]
    return result


def build_candidate(
    baseline: dict[str, np.ndarray],
    local_b: dict[str, np.ndarray],
    cases: dict[str, Any],
    started_clock: float,
) -> dict[str, np.ndarray]:
    """Replace only the bottom fan with a deterministic clipped-patch mesh."""
    try:
        from scipy.spatial import Delaunay
    except Exception as exc:  # pragma: no cover - depends on selected runtime
        raise CandidateUnknown(f"SciPy Delaunay is unavailable: {exc}") from exc

    base_rest = np.asarray(baseline["vertices_rest_xyz_mm"], dtype=np.float64)
    base_faces = np.asarray(baseline["faces"], dtype=np.int64)
    input_rest = np.asarray(local_b["vertices_rest_xyz_mm"], dtype=np.float64)
    input_relief = np.asarray(local_b["vertices_relief_xyz_mm"], dtype=np.float64)
    input_faces = np.asarray(local_b["faces"], dtype=np.int64)
    input_sources = np.asarray(local_b["source_face_ids"], dtype=np.int64)
    floor_source_ids, center_id, boundary_ids = _floor_source_faces(baseline)
    floor_input_mask = np.isin(input_sources, floor_source_ids)
    floor_input_ids = np.flatnonzero(floor_input_mask)
    if len(floor_input_ids) != len(floor_source_ids):
        raise CandidateUnknown("local-B bottom fan child faces are not a one-to-one frozen baseline match")
    for source_id in floor_source_ids:
        if int(np.count_nonzero(input_sources[floor_input_ids] == int(source_id))) != 1:
            raise CandidateUnknown("local-B floor contains an unexpected source-face multiplicity")

    polygon = _ccw(input_rest[boundary_ids, :2])
    interior_xy = _triangular_lattice_inside(polygon)
    if len(interior_xy) > MAX_INTERIOR_VERTICES:
        raise CandidateUnknown("interior vertex count exceeds frozen budget")

    input_vertex_count = len(input_rest)
    new_vertex_ids = np.arange(input_vertex_count, input_vertex_count + len(interior_xy), dtype=np.int64)
    center_xy = input_rest[center_id, :2].copy()
    boundary_xy = input_rest[boundary_ids, :2].copy()
    point_xy = np.vstack((center_xy[None, :], boundary_xy, interior_xy))
    point_candidate_ids = np.concatenate((
        np.asarray((center_id,), dtype=np.int64),
        boundary_ids.astype(np.int64),
        new_vertex_ids,
    ))
    if len(np.unique(point_candidate_ids)) != len(point_candidate_ids):
        raise CandidateUnknown("Delaunay point mapping contains a duplicate candidate vertex")
    triangulation = Delaunay(point_xy, qhull_options="Qbb Qc Qz Q12")
    simplices = np.asarray(triangulation.simplices, dtype=np.int64)
    if simplices.ndim != 2 or simplices.shape[1] != 3 or simplices.max() >= len(point_candidate_ids):
        raise CandidateUnknown("Delaunay returned an invalid bounded simplex array")

    original_floor_tri = base_rest[base_faces[int(floor_source_ids[0])], :2]
    desired_sign = math.copysign(1.0, _signed_area(original_floor_tri))
    xy_by_candidate_id = {
        int(candidate_id): point_xy[index]
        for index, candidate_id in enumerate(point_candidate_ids)
    }
    new_floor_faces = [
        _orient_triangle(point_candidate_ids[simplex], xy_by_candidate_id, desired_sign)
        for simplex in simplices
    ]
    new_floor_faces.sort(key=lambda tri: tuple(sorted(int(v) for v in tri)))
    new_floor_faces_array = np.asarray(new_floor_faces, dtype=np.int64)
    if len(new_floor_faces_array) + len(input_faces) - len(floor_input_ids) > MAX_OUTPUT_FACES:
        raise CandidateUnknown("candidate face count exceeds frozen output budget")

    source_ids_for_new_vertices: list[int] = []
    bary_for_new_vertices: list[np.ndarray] = []
    for point_xy_value in interior_xy:
        owner, bary = _source_owner(point_xy_value, baseline, floor_source_ids)
        source_ids_for_new_vertices.append(owner)
        bary_for_new_vertices.append(bary)

    new_rest = np.column_stack((interior_xy, np.zeros(len(interior_xy), dtype=np.float64)))
    if not np.allclose(new_rest[:, :2], interior_xy, rtol=0.0, atol=0.0):
        raise CandidateUnknown("new floor rest coordinates changed during assembly")
    new_relief = new_rest.copy()
    all_rest = np.vstack((input_rest, new_rest))
    all_relief = np.vstack((input_relief, new_relief))

    keep_faces = np.flatnonzero(~floor_input_mask)
    output_faces = np.vstack((input_faces[keep_faces], new_floor_faces_array)).astype(np.int64)
    output_sources = np.concatenate((input_sources[keep_faces], np.full(len(new_floor_faces_array), -1, dtype=np.int64)))
    input_face_bary = np.asarray(local_b["face_corner_barycentric_to_source"], dtype=np.float64)
    output_face_bary = np.concatenate((
        input_face_bary[keep_faces],
        np.full((len(new_floor_faces_array), 3, 3), np.nan, dtype=np.float64),
    ), axis=0)
    lineage_status = np.concatenate((
        np.ones(len(keep_faces), dtype=np.uint8),
        np.full(len(new_floor_faces_array), 2, dtype=np.uint8),
    ))

    floor_output_start = len(keep_faces)
    floor_output_face_ids = np.arange(floor_output_start, len(output_faces), dtype=np.int64)
    base_linear = np.asarray(cases["field"]["base_linear_rgb"], dtype=np.float64)
    if base_linear.shape != (3,) or not np.isfinite(base_linear).all():
        raise CandidateUnknown("frozen base linear-RGB field is malformed")
    input_base_colors = np.asarray(local_b["outer_base_linear_rgb"], dtype=np.float64)
    if input_base_colors.ndim != 2 or input_base_colors.shape[1] != 3:
        raise CandidateUnknown("local-B base color provenance is malformed")
    if not np.allclose(input_base_colors, base_linear[None, :], rtol=0.0, atol=COLOR_VERTEX_TOL):
        raise CandidateUnknown("local-B base colors disagree with the frozen continuous field")

    floor_patch_face_offsets = [0]
    floor_patch_source_ids: list[int] = []
    floor_patch_areas: list[float] = []
    floor_patch_vertex_offsets = [0]
    floor_patch_vertices_xy: list[np.ndarray] = []
    floor_patch_bary_source: list[np.ndarray] = []
    floor_patch_bary_output: list[np.ndarray] = []
    floor_patch_colors_linear: list[np.ndarray] = []
    floor_single_parent_bary: list[np.ndarray] = []
    floor_single_parent_ids: list[int] = []
    floor_single_parent_status: list[int] = []
    parent_polygons = {
        int(source_id): _ccw(base_rest[base_faces[int(source_id)], :2])
        for source_id in floor_source_ids
    }
    parent_triangles = {
        int(source_id): base_faces[int(source_id)]
        for source_id in floor_source_ids
    }
    patch_count = 0
    patch_vertex_count = 0

    for out_local, candidate_tri in enumerate(new_floor_faces_array):
        if (out_local & 127) == 0 and time.perf_counter() - started_clock > MAX_WALL_CLOCK_SECONDS:
            raise CandidateUnknown("candidate exceeded its fixed wall-clock budget during patch clipping")
        tri_xy = all_rest[candidate_tri, :2]
        tri_area = abs(_signed_area(tri_xy))
        subject = _ccw(tri_xy)
        patches: list[tuple[int, np.ndarray, float]] = []
        for source_id in floor_source_ids:
            sid = int(source_id)
            intersection = _clip_convex(subject, parent_polygons[sid])
            if len(intersection) == 0:
                continue
            intersection_area = abs(_signed_area(intersection))
            if intersection_area <= AREA_EPS_MM2:
                continue
            patches.append((sid, intersection, intersection_area))
        if not patches:
            raise CandidateUnknown("remeshed floor face has no baseline source patch")
        patches.sort(key=lambda item: item[0])
        # A child face around the retained center can cross many narrow radial
        # fan sectors. Bound this bookkeeping list by the complete frozen
        # parent fan; the global patch-record budget remains the tighter run
        # budget when appropriate.
        if len(patches) > len(floor_source_ids):
            raise CandidateUnknown("one remeshed floor face exceeds the complete frozen source fan")
        if patch_count + len(patches) > MAX_PATCH_RECORDS:
            raise CandidateUnknown("floor source-patch count exceeds its fixed budget")
        total_covered = sum(item[2] for item in patches)
        if abs(total_covered - tri_area) > max(1e-9, tri_area * 1e-10):
            raise CandidateUnknown("baseline patches do not cover one output floor face")
        for left in range(len(patches)):
            for right in range(left + 1, len(patches)):
                overlap = _clip_convex(patches[left][1], patches[right][1])
                overlap_area = abs(_signed_area(overlap)) if len(overlap) else 0.0
                if overlap_area > 1e-10:
                    raise CandidateUnknown("source patches overlap with positive area")

        if len(patches) == 1 and abs(patches[0][2] - tri_area) <= max(1e-9, tri_area * 1e-10):
            parent_id = patches[0][0]
            src_tri_xy = base_rest[parent_triangles[parent_id], :2]
            corner_bary = np.asarray([_clean_barycentric(_barycentric_xy(p, src_tri_xy)) for p in tri_xy])
            floor_single_parent_ids.append(parent_id)
            floor_single_parent_bary.append(corner_bary)
            floor_single_parent_status.append(1)
        else:
            floor_single_parent_ids.append(-1)
            floor_single_parent_bary.append(np.full((3, 3), np.nan, dtype=np.float64))
            floor_single_parent_status.append(2)

        for source_id, polygon_xy, area in patches:
            src_tri_xy = base_rest[parent_triangles[source_id], :2]
            source_bary_rows = []
            output_bary_rows = []
            color_rows = []
            for patch_xy in polygon_xy:
                source_bary_rows.append(_clean_barycentric(_barycentric_xy(patch_xy, src_tri_xy)))
                output_bary_rows.append(_clean_barycentric(_barycentric_xy(patch_xy, tri_xy)))
                color_rows.append(_sample_floor_color(patch_xy, base_linear))
            floor_patch_source_ids.append(source_id)
            floor_patch_areas.append(float(area))
            floor_patch_vertices_xy.extend(polygon_xy)
            floor_patch_bary_source.extend(source_bary_rows)
            floor_patch_bary_output.extend(output_bary_rows)
            floor_patch_colors_linear.extend(color_rows)
            patch_vertex_count += len(polygon_xy)
            if patch_vertex_count > MAX_PATCH_VERTICES:
                raise CandidateUnknown("floor patch vertex count exceeds its fixed budget")
            floor_patch_vertex_offsets.append(patch_vertex_count)
            patch_count += 1
        floor_patch_face_offsets.append(patch_count)

    # Populate explicitly named schema-v2 legacy-single-parent arrays only
    # where one old source triangle covers the full output face. Cross-source
    # faces receive a sentinel/NaNs here and complete patch records below.
    output_sources[floor_output_face_ids] = np.asarray(floor_single_parent_ids, dtype=np.int64)
    output_face_bary[floor_output_face_ids] = np.asarray(floor_single_parent_bary, dtype=np.float64)
    lineage_status[floor_output_face_ids] = np.asarray(floor_single_parent_status, dtype=np.uint8)

    result = {name: np.asarray(value).copy() for name, value in local_b.items()}
    result["vertices_rest_xyz_mm"] = all_rest
    result["vertices_relief_xyz_mm"] = all_relief
    result["faces"] = output_faces
    # Do not serialize ambiguous lineage under the schema-v1 standard names:
    # legacy consumers then fail closed with KeyError instead of indexing -1.
    result.pop("source_face_ids", None)
    result.pop("face_corner_barycentric_to_source", None)
    result["v2_legacy_single_parent_face_source_ids"] = output_sources
    result["v2_legacy_single_parent_face_corner_barycentric_to_source"] = output_face_bary
    result["face_lineage_status"] = lineage_status
    result["vertex_lineage_source_face_id"] = np.concatenate((
        np.asarray(local_b["vertex_lineage_source_face_id"], dtype=np.int64),
        np.asarray(source_ids_for_new_vertices, dtype=np.int64),
    ))
    result["vertex_lineage_barycentric"] = np.vstack((
        np.asarray(local_b["vertex_lineage_barycentric"], dtype=np.float64),
        np.asarray(bary_for_new_vertices, dtype=np.float64),
    ))

    floor_vertex_ids = np.unique(np.concatenate((
        np.asarray((center_id,), dtype=np.int64), boundary_ids, new_vertex_ids,
    )))
    floor_chart_xy = all_rest[floor_vertex_ids, :2].copy()
    floor_color_linear = np.asarray([_sample_floor_color(point, base_linear) for point in floor_chart_xy])
    result.update({
        "lineage_schema_version": np.asarray(2, dtype=np.int32),
        "quarantine_status": np.asarray("EXPERIMENT_ONLY_NOT_FOR_PRODUCTION"),
        "legacy_reader_compatibility": np.asarray(
            "UNKNOWN; standard schema-v1 source_face_ids and face_corner_barycentric_to_source keys are omitted"
        ),
        "v2_face_lineage_status_codes": np.asarray("1=single_parent_valid;2=multi_parent_patch_required"),
        "floor_surface_id": np.asarray("bottom_exterior_z0"),
        "floor_chart_name": np.asarray("world_XY_mm_at_z0"),
        "floor_chart_vertex_indices": floor_vertex_ids.astype(np.int64),
        "floor_chart_xy_mm": floor_chart_xy,
        "floor_vertex_color_linear_rgb": floor_color_linear,
        "floor_vertex_color_srgb": _linear_rgb_to_srgb(floor_color_linear),
        "floor_output_face_ids": floor_output_face_ids,
        "floor_face_patch_offsets": np.asarray(floor_patch_face_offsets, dtype=np.int64),
        "floor_face_patch_source_face_ids": np.asarray(floor_patch_source_ids, dtype=np.int64),
        "floor_face_patch_area_mm2": np.asarray(floor_patch_areas, dtype=np.float64),
        "floor_face_patch_vertex_offsets": np.asarray(floor_patch_vertex_offsets, dtype=np.int64),
        "floor_face_patch_vertices_xy_mm": np.asarray(floor_patch_vertices_xy, dtype=np.float64).reshape(-1, 2),
        "floor_face_patch_vertices_barycentric_to_source": np.asarray(floor_patch_bary_source, dtype=np.float64).reshape(-1, 3),
        "floor_face_patch_vertices_barycentric_to_output": np.asarray(floor_patch_bary_output, dtype=np.float64).reshape(-1, 3),
        "floor_face_patch_vertices_color_linear_rgb": np.asarray(floor_patch_colors_linear, dtype=np.float64).reshape(-1, 3),
        "floor_face_patch_vertices_color_srgb": _linear_rgb_to_srgb(
            np.asarray(floor_patch_colors_linear, dtype=np.float64).reshape(-1, 3)
        ),
        "floor_patch_area_tolerance_mm2": np.asarray(1e-9, dtype=np.float64),
        "floor_patch_overlap_tolerance_mm2": np.asarray(1e-10, dtype=np.float64),
        "modified_baseline_floor_source_face_ids": floor_source_ids.astype(np.int64),
        "modified_region_physical_surface_id": np.asarray("bottom_exterior_z0"),
        "candidate_grid_spacing_mm": np.asarray(GRID_SPACING_MM, dtype=np.float64),
        "candidate_boundary_margin_mm": np.asarray(BOUNDARY_MARGIN_MM, dtype=np.float64),
    })
    if len(output_faces) > MAX_OUTPUT_FACES:
        raise CandidateUnknown("final candidate face count exceeds its fixed budget")
    if time.perf_counter() - started_clock > MAX_WALL_CLOCK_SECONDS:
        raise CandidateUnknown("candidate exceeded its fixed wall-clock budget")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="generate the one approved candidate and its bounded review outputs")
    args = parser.parse_args()
    if not args.run:
        print("SOURCE_ONLY_AWAITING_ROOT_REVIEW; no input files read and no outputs generated. Use --run only after root approval.")
        return 0

    from focused_checks import run_focused_checks, summarize_triangle_quality

    output_dir = REVIEW_ROOT.resolve()
    authorized_review_root = (REPO_ROOT / "vesselforge" / "tmp" / "review_20261005").resolve()
    if authorized_review_root not in output_dir.parents:
        raise CandidateUnknown("output path escaped the authorized review directory")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise CandidateUnknown(f"refusing to reuse non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    start_iso = datetime.now(timezone.utc).isoformat()
    started_clock = time.perf_counter()
    receipt: dict[str, Any] = {
        "candidate_id": "global_mesh_quality_candidate_20261005",
        "status": "RUNNING",
        "started_at_utc": start_iso,
        "input_sha256": EXPECTED,
        "generation_invoked": True,
        "candidate_count": 1,
    }
    try:
        baseline, local_b, old_checks, cases = load_pinned_inputs()
        candidate = build_candidate(baseline, local_b, cases, started_clock)
        npz_path = output_dir / "candidate_arrays.npz"
        np.savez_compressed(npz_path, **candidate)
        saved_candidate = _load_npz(npz_path)
        checks = run_focused_checks(baseline, local_b, saved_candidate, cases, old_checks)
        checks_path = output_dir / "checks.json"
        checks_path.write_text(json.dumps(checks, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
        baseline_quality = summarize_triangle_quality(
            np.asarray(local_b["vertices_relief_xyz_mm"], dtype=np.float64),
            np.asarray(local_b["faces"], dtype=np.int64),
        )
        candidate_quality = summarize_triangle_quality(
            np.asarray(saved_candidate["vertices_relief_xyz_mm"], dtype=np.float64),
            np.asarray(saved_candidate["faces"], dtype=np.int64),
        )
        from focused_checks import render_saved_meshes
        render_saved_meshes(saved_candidate, output_dir, cases)
        manifest = {
            "candidate_id": "global_mesh_quality_candidate_20261005",
            "input_sha256": EXPECTED,
            "source_sha256": sha256_file(Path(__file__).resolve()),
            "candidate_arrays_sha256": sha256_file(npz_path),
            "checks_sha256": sha256_file(checks_path),
            "baseline_quality": baseline_quality,
            "candidate_quality": candidate_quality,
            "pngs": {
                "global_equal_aspect_actual_mesh.png": sha256_file(output_dir / "global_equal_aspect_actual_mesh.png"),
                "floor_equal_aspect_actual_mesh.png": sha256_file(output_dir / "floor_equal_aspect_actual_mesh.png"),
            },
            "schema": "isolated_global_mesh_quality_candidate_v2_multi_parent_floor_patches",
            "quarantine_status": "EXPERIMENT_ONLY_NOT_FOR_PRODUCTION",
            "legacy_reader_compatibility": "UNKNOWN; standard schema-v1 source-face keys are omitted",
            "candidate_language": "analytic fixture geometry only; no tetrahedral, solver, mechanics, fracture, or fragment-match claim",
        }
        (output_dir / "candidate_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8"
        )
        receipt.update({
            "status": "CANDIDATE_CHECK_PASS" if checks["focused_checks_pass"] else "CANDIDATE_CHECK_FAIL",
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": time.perf_counter() - started_clock,
            "candidate_arrays_sha256": sha256_file(npz_path),
            "candidate_faces": int(len(saved_candidate["faces"])),
            "candidate_vertices": int(len(saved_candidate["vertices_rest_xyz_mm"])),
            "focused_checks_pass": bool(checks["focused_checks_pass"]),
        })
    except Exception as exc:
        receipt.update({
            "status": "UNKNOWN_OR_FAIL",
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": time.perf_counter() - started_clock,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "automatic_retry": False,
        })
        (output_dir / "run_receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8"
        )
        return 2
    (output_dir / "run_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8"
    )
    return 0 if receipt["status"] == "CANDIDATE_CHECK_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
