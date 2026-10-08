"""Independent saved-array checks for the quarantined two-cap experiment."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np


# Keep the saved-mesh continuous-field comparison at the frozen candidate tolerance.
COLOR_FINITE_SAMPLE_TOL = 1e-12
LINEAGE_TOL_MM = 1e-9
PATCH_AREA_TOL_MM2 = 1e-9
PATCH_OVERLAP_TOL_MM2 = 1e-10
MAX_PATCH_RECORDS = 15000
MAX_PATCH_VERTICES = 60000
MAX_PARENTS_PER_OUTPUT_FACE = 128
GLOBAL_FLOAT_ULPS = 64.0
SURFACE_SPECS = (
    ("bottom_exterior_z0", 0.0, 20.0, "outward_-z"),
    ("interior_floor_z2", 2.0, 17.0, "inward_+z"),
)


def _cross2(a: np.ndarray, b: np.ndarray) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def _area2(poly: np.ndarray) -> float:
    if len(poly) < 3:
        return 0.0
    return 0.5 * float(
        np.sum(poly[:, 0] * np.roll(poly[:, 1], -1) - poly[:, 1] * np.roll(poly[:, 0], -1))
    )


def _ccw(poly: np.ndarray) -> np.ndarray:
    arr = np.asarray(poly, dtype=np.float64)
    return arr if _area2(arr) >= 0.0 else arr[::-1].copy()


def _clip_convex(subject_xy: np.ndarray, clip_xy: np.ndarray) -> np.ndarray:
    """Independent convex polygon intersection used by the readback audit."""
    output = [np.asarray(point, dtype=np.float64) for point in _ccw(subject_xy)]
    clipper = _ccw(clip_xy)
    for edge_index in range(len(clipper)):
        if not output:
            return np.empty((0, 2), dtype=np.float64)
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
            start = end
            start_side = end_side
    if len(output) < 3:
        return np.empty((0, 2), dtype=np.float64)
    compact: list[np.ndarray] = []
    for point in output:
        if not compact or float(np.linalg.norm(point - compact[-1])) > 1e-11:
            compact.append(point)
    if len(compact) > 1 and float(np.linalg.norm(compact[0] - compact[-1])) <= 1e-11:
        compact.pop()
    result = np.asarray(compact, dtype=np.float64)
    return result if len(result) >= 3 and abs(_area2(result)) > 1e-12 else np.empty((0, 2), dtype=np.float64)


def _barycentric(point: np.ndarray, tri: np.ndarray) -> np.ndarray:
    a, b, c = np.asarray(tri, dtype=np.float64)
    v0, v1, v2 = b - a, c - a, np.asarray(point, dtype=np.float64) - a
    denominator = _cross2(v0, v1)
    if abs(denominator) <= 1e-15:
        raise ValueError("degenerate triangle in lineage readback")
    wb = _cross2(v2, v1) / denominator
    wc = _cross2(v0, v2) / denominator
    result = np.asarray((1.0 - wb - wc, wb, wc), dtype=np.float64)
    result[np.abs(result) < 5e-13] = 0.0
    result[np.abs(result - 1.0) < 5e-13] = 1.0
    return result


def _simplex_rows_pass(rows: np.ndarray, tolerance: float = 1e-12) -> bool:
    values = np.asarray(rows, dtype=np.float64)
    return bool(
        values.ndim == 2
        and values.shape[1] == 3
        and np.isfinite(values).all()
        and np.max(np.abs(values.sum(axis=1) - 1.0), initial=0.0) <= tolerance
        and values.min(initial=0.0) >= -tolerance
        and values.max(initial=0.0) <= 1.0 + tolerance
    )


def owner_lookup_two_parent_toy_regression() -> dict[str, Any]:
    """Exercise actual candidate owner lookup across adjacent parent triangles."""
    from candidate_owner_fix import CandidateUnknown, PlanarCap, _barycentric_xy_raw, _source_owner

    vertices = np.asarray(
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0),
         (1.0, 0.0, 0.0), (2.0, 0.0, 0.0), (1.0, 1.0, 0.0)),
        dtype=np.float64,
    )
    faces = np.asarray(((0, 1, 2), (3, 4, 5)), dtype=np.int64)
    baseline = {"vertices_rest_xyz_mm": vertices, "faces": faces}
    cap = PlanarCap(
        "toy_adjacent_parent_pair", 0.0, 2.0, "toy",
        np.asarray((0, 1), dtype=np.int64), 0,
        np.asarray((0, 1, 2, 3, 4, 5), dtype=np.int64),
        np.asarray(((0.0, 0.0), (2.0, 0.0), (1.0, 1.0)), dtype=np.float64),
    )

    inside_second_xy = np.asarray((1.5, 0.25), dtype=np.float64)
    first_raw = _barycentric_xy_raw(inside_second_xy, vertices[faces[0], :2])
    second_owner_id, second_bary = _source_owner(inside_second_xy, baseline, cap)
    outside_first_pass = bool(first_raw.min() < -1e-10 or first_raw.max() > 1.0 + 1e-10)
    second_parent_pass = bool(
        second_owner_id == 1
        and _simplex_rows_pass(second_bary[None, :])
        and np.allclose(second_bary @ vertices[faces[1], :2], inside_second_xy, rtol=0.0, atol=1e-12)
    )

    shared_boundary_xy = np.asarray((1.0, 0.5), dtype=np.float64)
    boundary_owner_id, boundary_bary = _source_owner(shared_boundary_xy, baseline, cap)
    shared_boundary_pass = bool(
        boundary_owner_id == 0
        and _simplex_rows_pass(boundary_bary[None, :])
        and np.count_nonzero(np.abs(boundary_bary) <= 1e-12) == 1
    )

    outside_rejected = False
    outside_error = None
    try:
        _source_owner(np.asarray((2.2, 1.0), dtype=np.float64), baseline, cap)
    except CandidateUnknown as exc:
        outside_rejected = True
        outside_error = str(exc)

    checks = {
        "first_parent_raw_coordinates_show_outside": outside_first_pass,
        "later_containing_parent_is_selected": second_parent_pass,
        "shared_boundary_uses_first_actual_parent": shared_boundary_pass,
        "point_outside_all_parents_fails_closed": outside_rejected,
    }
    if not all(checks.values()):
        raise ValueError(f"two-parent owner lookup regression failed: {checks}")
    return {
        "passed": True,
        "checks": checks,
        "first_parent_raw_barycentric_for_inside_second": first_raw.tolist(),
        "inside_second_parent_id": int(second_owner_id),
        "inside_second_barycentric": second_bary.tolist(),
        "shared_boundary_parent_id": int(boundary_owner_id),
        "shared_boundary_barycentric": boundary_bary.tolist(),
        "outside_all_rejection": outside_error,
    }


def _saved_face_source_ids(arrays: dict[str, np.ndarray]) -> np.ndarray:
    """Read schema-v2 lineage without treating it as a schema-v1 alias."""
    if "v2_legacy_single_parent_face_source_ids" in arrays:
        return np.asarray(arrays["v2_legacy_single_parent_face_source_ids"], dtype=np.int64)
    return np.asarray(arrays["source_face_ids"], dtype=np.int64)


def _saved_face_corner_barycentric(arrays: dict[str, np.ndarray]) -> np.ndarray:
    if "v2_legacy_single_parent_face_corner_barycentric_to_source" in arrays:
        return np.asarray(arrays["v2_legacy_single_parent_face_corner_barycentric_to_source"], dtype=np.float64)
    return np.asarray(arrays["face_corner_barycentric_to_source"], dtype=np.float64)


def _linear_rgb_to_srgb(linear: np.ndarray) -> np.ndarray:
    value = np.clip(np.asarray(linear, dtype=np.float64), 0.0, 1.0)
    return np.where(value <= 0.0031308, 12.92 * value, 1.055 * np.power(value, 1.0 / 2.4) - 0.055)


def _triangle_arrays(vertices: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    tri = np.asarray(vertices, dtype=np.float64)[np.asarray(faces, dtype=np.int64)]
    edge0 = tri[:, 1] - tri[:, 0]
    edge1 = tri[:, 2] - tri[:, 1]
    edge2 = tri[:, 0] - tri[:, 2]
    lengths = np.column_stack((np.linalg.norm(edge0, axis=1), np.linalg.norm(edge1, axis=1), np.linalg.norm(edge2, axis=1)))
    double_area = np.linalg.norm(np.cross(edge0, tri[:, 2] - tri[:, 0]), axis=1)
    area = 0.5 * double_area
    q = np.divide(4.0 * math.sqrt(3.0) * area, np.sum(lengths * lengths, axis=1),
                  out=np.zeros_like(area), where=np.sum(lengths * lengths, axis=1) > 0.0)
    aspect = np.divide(np.max(lengths, axis=1) ** 2, double_area,
                       out=np.full_like(area, np.inf), where=double_area > 0.0)
    return lengths, area, q, aspect


def summarize_triangle_quality(vertices: np.ndarray, faces: np.ndarray) -> dict[str, Any]:
    lengths, area, q, aspect = _triangle_arrays(vertices, faces)
    return {
        "face_count": int(len(faces)),
        "minimum_Q": float(np.min(q)) if len(q) else None,
        "minimum_altitude_mm": float(np.min(np.divide(2.0 * area, np.max(lengths, axis=1),
                                                         out=np.zeros_like(area), where=np.max(lengths, axis=1) > 0.0))) if len(area) else None,
        "maximum_aspect_longest_edge_over_minimum_altitude": float(np.max(aspect)) if len(aspect) else None,
        "maximum_edge_mm": float(np.max(lengths)) if len(lengths) else None,
        "zero_area_face_count": int(np.count_nonzero(area <= 1e-12)),
    }


def _topology(vertices: np.ndarray, faces: np.ndarray) -> dict[str, Any]:
    vertex_count = len(vertices)
    incidence: dict[tuple[int, int], list[tuple[int, int]]] = {}
    duplicate_keys: set[tuple[int, int, int]] = set()
    duplicate_count = 0
    repeated_count = 0
    for face_id, tri in enumerate(np.asarray(faces, dtype=np.int64)):
        if len(set(map(int, tri))) != 3:
            repeated_count += 1
            continue
        canonical = tuple(sorted(map(int, tri)))
        if canonical in duplicate_keys:
            duplicate_count += 1
        duplicate_keys.add(canonical)
        for a, b in ((int(tri[0]), int(tri[1])), (int(tri[1]), int(tri[2])), (int(tri[2]), int(tri[0]))):
            key = (a, b) if a < b else (b, a)
            incidence.setdefault(key, []).append((face_id, 1 if (a, b) == key else -1))
    boundary_count = sum(len(items) == 1 for items in incidence.values())
    non_two_count = sum(len(items) != 2 for items in incidence.values())
    winding_conflicts = sum(len(items) == 2 and items[0][1] == items[1][1] for items in incidence.values())
    used = np.unique(np.asarray(faces, dtype=np.int64))
    parent = {int(v): int(v) for v in used}

    def find(v: int) -> int:
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for tri in np.asarray(faces, dtype=np.int64):
        union(int(tri[0]), int(tri[1]))
        union(int(tri[1]), int(tri[2]))
    components = len({find(int(v)) for v in used}) if len(used) else 0
    xyz = np.asarray(vertices, dtype=np.float64)[np.asarray(faces, dtype=np.int64)]
    signed_volume = float(np.sum(np.einsum("ij,ij->i", xyz[:, 0], np.cross(xyz[:, 1], xyz[:, 2]))) / 6.0)
    _, area, _, _ = _triangle_arrays(vertices, faces)
    return {
        "vertex_count": int(vertex_count),
        "used_vertex_count": int(len(used)),
        "face_count": int(len(faces)),
        "unique_undirected_edge_count": int(len(incidence)),
        "boundary_edge_count": int(boundary_count),
        "non_two_incidence_edge_count": int(non_two_count),
        "inconsistent_winding_edge_count": int(winding_conflicts),
        "duplicate_face_count_unoriented": int(duplicate_count),
        "repeated_vertex_face_count": int(repeated_count),
        "zero_area_face_count_threshold_1e-12_mm2": int(np.count_nonzero(area <= 1e-12)),
        "connected_component_count": int(components),
        "euler_characteristic": int(len(used) - len(incidence) + len(faces)),
        "signed_volume_mm3": signed_volume,
        "positive_signed_volume": bool(signed_volume > 0.0),
    }


def _continuous_cylinder_field(theta: np.ndarray, z: np.ndarray, radius: float, field: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    theta = np.asarray(theta, dtype=np.float64)
    z = np.asarray(z, dtype=np.float64)
    repeat = int(field["repeat_count"])
    phase = np.remainder(repeat * theta / (2.0 * math.pi) + 0.5, 1.0) - 0.5
    arc = radius * (2.0 * math.pi / repeat) * phase
    dz = z - float(field["center_z_mm"])
    q = np.sqrt(
        (arc / float(field["circumferential_half_width_mm"])) ** 2
        + (dz / float(field["vertical_half_height_mm"])) ** 2
    )
    ramp = np.clip(1.0 - q, 0.0, 1.0)
    coverage = ramp * ramp * (3.0 - 2.0 * ramp)
    base = np.asarray(field["base_linear_rgb"], dtype=np.float64)
    pigment = np.asarray(field["pigment_linear_rgb"], dtype=np.float64)
    color = base + coverage[..., None] * (pigment - base)
    height = float(field["raised_height_mm"]) * coverage
    return height, color


def _outer_color_error(arrays: dict[str, np.ndarray], field: dict[str, Any]) -> dict[str, Any]:
    vertex_ids = np.asarray(arrays["outer_vertex_indices"], dtype=np.int64)
    theta = np.asarray(arrays["outer_theta_rad"], dtype=np.float64)
    z = np.asarray(arrays["outer_z_mm"], dtype=np.float64)
    colors = np.asarray(arrays["outer_color_linear_rgb"], dtype=np.float64)
    heights = np.asarray(arrays["outer_relief_height_mm"], dtype=np.float64)
    radius = float(np.asarray(arrays["outer_radius_mm"]).item())
    sample_height, sample_color = _continuous_cylinder_field(theta, z, radius, field)
    vertex_color_error = np.max(np.abs(sample_color - colors), axis=1)
    vertex_height_error = np.abs(sample_height - heights)
    color_by_vertex = {int(vertex): colors[i] for i, vertex in enumerate(vertex_ids)}
    height_by_vertex = {int(vertex): heights[i] for i, vertex in enumerate(vertex_ids)}
    theta_by_vertex = {int(vertex): theta[i] for i, vertex in enumerate(vertex_ids)}
    z_by_vertex = {int(vertex): z[i] for i, vertex in enumerate(vertex_ids)}
    source_set = set(np.asarray(arrays["outer_source_face_ids"], dtype=np.int64).tolist())
    source_ids = _saved_face_source_ids(arrays)
    faces = np.asarray(arrays["faces"], dtype=np.int64)
    mask = np.fromiter((int(sid) in source_set for sid in source_ids), dtype=bool, count=len(source_ids))
    outer_faces = faces[mask]
    samples = np.asarray((
        (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
        (0.5, 0.5, 0.0), (0.0, 0.5, 0.5), (0.5, 0.0, 0.5),
        (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0),
    ), dtype=np.float64)
    finite_color_errors: list[float] = []
    finite_height_errors: list[float] = []
    for tri in outer_faces:
        tri_theta = np.asarray([theta_by_vertex[int(v)] for v in tri], dtype=np.float64)
        # Shortest periodic chart around corner zero, matching the frozen source.
        tri_theta = tri_theta[0] + (tri_theta - tri_theta[0] + math.pi) % (2.0 * math.pi) - math.pi
        tri_z = np.asarray([z_by_vertex[int(v)] for v in tri], dtype=np.float64)
        tri_colors = np.asarray([color_by_vertex[int(v)] for v in tri], dtype=np.float64)
        tri_heights = np.asarray([height_by_vertex[int(v)] for v in tri], dtype=np.float64)
        sample_theta = samples @ tri_theta
        sample_z = samples @ tri_z
        expected_height, expected_color = _continuous_cylinder_field(sample_theta, sample_z, radius, field)
        interpolated_color = samples @ tri_colors
        interpolated_height = samples @ tri_heights
        finite_color_errors.extend(np.max(np.abs(expected_color - interpolated_color), axis=1).tolist())
        finite_height_errors.extend(np.abs(expected_height - interpolated_height).tolist())
    return {
        "outer_vertex_count": int(len(vertex_ids)),
        "outer_triangle_count": int(len(outer_faces)),
        "per_corner_color_max_abs_linear_rgb_error": float(np.max(vertex_color_error, initial=0.0)),
        "per_corner_relief_max_abs_error_mm": float(np.max(vertex_height_error, initial=0.0)),
        "finite_samples_per_outer_triangle": int(len(samples)),
        "finite_outer_sample_count": int(len(finite_color_errors)),
        "finite_outer_color_max_abs_linear_rgb_error": float(max(finite_color_errors, default=0.0)),
        "finite_outer_relief_max_abs_error_mm": float(max(finite_height_errors, default=0.0)),
    }


def _find_two_source_caps(baseline: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    rest = np.asarray(baseline["vertices_rest_xyz_mm"], dtype=np.float64)
    faces = np.asarray(baseline["faces"], dtype=np.int64)
    triangles = rest[faces]
    caps = []
    for surface_id, z, radius, orientation in SURFACE_SPECS:
        radii = np.linalg.norm(triangles[:, :, :2], axis=2)
        mask = (
            np.all(np.abs(triangles[:, :, 2] - z) <= 1e-12, axis=1)
            & np.all(radii <= radius + 1e-10, axis=1)
            & (np.count_nonzero(radii <= 1e-12, axis=1) == 1)
            & (np.count_nonzero(np.abs(radii - radius) <= 1e-9, axis=1) == 2)
        )
        source_ids = np.flatnonzero(mask).astype(np.int64)
        if len(source_ids) != 128:
            raise ValueError(f"actual baseline source lookup found {len(source_ids)} faces for {surface_id}")
        centers = np.unique(faces[source_ids][radii[source_ids] <= 1e-12])
        if len(centers) != 1:
            raise ValueError(f"actual baseline source lookup found no unique center for {surface_id}")
        center_id = int(centers[0])
        boundary = np.unique(faces[source_ids][faces[source_ids] != center_id])
        if len(boundary) != 128:
            raise ValueError(f"actual baseline source lookup found {len(boundary)} boundary vertices for {surface_id}")
        theta = np.arctan2(rest[boundary, 1], rest[boundary, 0])
        boundary = boundary[np.argsort(theta, kind="stable")]
        polygon = rest[boundary, :2].copy()
        if _area2(polygon) <= 0.0:
            raise ValueError(f"actual baseline source chart is not positively oriented for {surface_id}")
        caps.append({
            "surface_id": surface_id, "z": z, "radius": radius, "orientation": orientation,
            "source_ids": source_ids, "center_id": center_id, "boundary_ids": boundary, "polygon": polygon,
        })
    if np.intersect1d(caps[0]["source_ids"], caps[1]["source_ids"]).size:
        raise ValueError("the two actual baseline cap source fans overlap")
    return caps


def _check_saved_patch_csr(
    baseline: dict[str, np.ndarray], candidate: dict[str, np.ndarray], caps: list[dict[str, Any]], base_color: np.ndarray,
) -> dict[str, Any]:
    base_rest = np.asarray(baseline["vertices_rest_xyz_mm"], dtype=np.float64)
    base_faces = np.asarray(baseline["faces"], dtype=np.int64)
    rest = np.asarray(candidate["vertices_rest_xyz_mm"], dtype=np.float64)
    faces = np.asarray(candidate["faces"], dtype=np.int64)
    cap_face_ids = np.asarray(candidate["cap_output_face_ids"], dtype=np.int64)
    face_surface = np.asarray(candidate["cap_output_face_surface_index"], dtype=np.int64)
    face_offsets = np.asarray(candidate["cap_face_patch_offsets"], dtype=np.int64)
    patch_surface = np.asarray(candidate["cap_face_patch_surface_index"], dtype=np.int64)
    patch_sources = np.asarray(candidate["cap_face_patch_source_face_ids"], dtype=np.int64)
    patch_areas = np.asarray(candidate["cap_face_patch_area_mm2"], dtype=np.float64)
    vertex_offsets = np.asarray(candidate["cap_face_patch_vertex_offsets"], dtype=np.int64)
    patch_xy = np.asarray(candidate["cap_face_patch_vertices_xy_mm"], dtype=np.float64)
    bary_source = np.asarray(candidate["cap_face_patch_vertices_barycentric_to_source"], dtype=np.float64)
    bary_output = np.asarray(candidate["cap_face_patch_vertices_barycentric_to_output"], dtype=np.float64)
    colors_linear = np.asarray(candidate["cap_face_patch_vertices_color_linear_rgb"], dtype=np.float64)
    colors_srgb = np.asarray(candidate["cap_face_patch_vertices_color_srgb"], dtype=np.float64)
    if (len(face_offsets) != len(cap_face_ids) + 1 or len(vertex_offsets) != len(patch_sources) + 1
            or face_offsets[0] != 0 or face_offsets[-1] != len(patch_sources)
            or vertex_offsets[0] != 0 or vertex_offsets[-1] != len(patch_xy)
            or np.any(np.diff(face_offsets) < 0) or np.any(np.diff(vertex_offsets) < 0)):
        raise ValueError("cross-parent lineage CSR offsets are not complete monotone partitions")
    if (len(patch_sources) != len(patch_areas) or len(patch_xy) != len(bary_source)
            or len(patch_xy) != len(bary_output) or len(patch_xy) != len(colors_linear)
            or len(patch_xy) != len(colors_srgb)):
        raise ValueError("cross-parent lineage arrays have inconsistent lengths")
    if len(patch_sources) > MAX_PATCH_RECORDS or len(patch_xy) > MAX_PATCH_VERTICES:
        raise ValueError("cross-parent lineage exceeds its aggregate fixed budget")
    if not _simplex_rows_pass(bary_source) or not _simplex_rows_pass(bary_output):
        raise ValueError("cross-parent barycentric rows are not finite simplex values")
    max_source_residual = max_output_residual = max_area_residual = max_overlap = 0.0
    max_parents_per_face = 0
    for slot, output_face_id in enumerate(cap_face_ids):
        surface_index = int(face_surface[slot])
        cap = caps[surface_index]
        p0, p1 = int(face_offsets[slot]), int(face_offsets[slot + 1])
        if p1 <= p0:
            raise ValueError("remeshed cap output face has no parent-patch records")
        parent_count = p1 - p0
        max_parents_per_face = max(max_parents_per_face, parent_count)
        if parent_count > MAX_PARENTS_PER_OUTPUT_FACE:
            raise ValueError("one output cap face exceeds its complete 128-parent source fan")
        if np.any(patch_surface[p0:p1] != surface_index):
            raise ValueError("patch surface index differs from its output cap")
        if not set(patch_sources[p0:p1].tolist()).issubset(set(cap["source_ids"].tolist())):
            raise ValueError("one output face references a source from the other cap")
        output_triangle = faces[int(output_face_id)]
        output_xy = rest[output_triangle, :2]
        output_area = abs(_area2(output_xy))
        polygons = []
        covered_area = 0.0
        for patch_id in range(p0, p1):
            v0, v1 = int(vertex_offsets[patch_id]), int(vertex_offsets[patch_id + 1])
            polygon = patch_xy[v0:v1]
            if len(polygon) < 3:
                raise ValueError("saved parent patch polygon has fewer than three vertices")
            parent_id = int(patch_sources[patch_id])
            parent_xy = base_rest[base_faces[parent_id], :2]
            source_points = bary_source[v0:v1] @ parent_xy
            output_points = bary_output[v0:v1] @ output_xy
            source_error = float(np.max(np.linalg.norm(source_points - polygon, axis=1), initial=0.0))
            output_error = float(np.max(np.linalg.norm(output_points - polygon, axis=1), initial=0.0))
            max_source_residual = max(max_source_residual, source_error)
            max_output_residual = max(max_output_residual, output_error)
            if source_error > LINEAGE_TOL_MM or output_error > LINEAGE_TOL_MM:
                raise ValueError("saved barycentrics fail source/output chart reconstruction")
            area = abs(_area2(polygon))
            if abs(area - float(patch_areas[patch_id])) > max(PATCH_AREA_TOL_MM2, area * 1e-10):
                raise ValueError("saved patch area differs from its polygon area")
            polygons.append(polygon)
            covered_area += area
        area_error = abs(covered_area - output_area)
        max_area_residual = max(max_area_residual, area_error)
        if area_error > max(PATCH_AREA_TOL_MM2, output_area * 1e-10):
            raise ValueError("source patches do not cover an output face")
        for left in range(len(polygons)):
            for right in range(left + 1, len(polygons)):
                overlap = _clip_convex(polygons[left], polygons[right])
                overlap_area = abs(_area2(overlap)) if len(overlap) else 0.0
                max_overlap = max(max_overlap, overlap_area)
                if overlap_area > PATCH_OVERLAP_TOL_MM2:
                    raise ValueError("source patch polygons overlap with positive area")
        v0, v1 = int(vertex_offsets[p0]), int(vertex_offsets[p1])
        expected_linear = np.broadcast_to(base_color, (v1 - v0, 3))
        if not np.array_equal(colors_linear[v0:v1], expected_linear):
            raise ValueError("saved patch color differs from the frozen planar base field")
        if np.max(np.abs(colors_srgb[v0:v1] - _linear_rgb_to_srgb(expected_linear)), initial=0.0) > COLOR_FINITE_SAMPLE_TOL:
            raise ValueError("saved patch sRGB color differs from the frozen linear field conversion")
        face_status = int(np.asarray(candidate["face_lineage_status"])[int(output_face_id)])
        face_parent = int(np.asarray(candidate["v2_legacy_single_parent_face_source_ids"])[int(output_face_id)])
        face_bary = np.asarray(candidate["v2_legacy_single_parent_face_corner_barycentric_to_source"])[int(output_face_id)]
        is_single = parent_count == 1 and abs(float(patch_areas[p0]) - output_area) <= max(PATCH_AREA_TOL_MM2, output_area * 1e-10)
        if is_single and (face_status != 1 or face_parent != int(patch_sources[p0]) or not _simplex_rows_pass(face_bary)):
            raise ValueError("fully contained output face lacks valid v2 single-parent data")
        if not is_single and (face_status != 2 or face_parent != -1 or not np.isnan(face_bary).all()):
            raise ValueError("cross-parent face was represented as a legacy single parent")
    return {
        "patch_record_count": int(len(patch_sources)), "patch_polygon_vertex_count": int(len(patch_xy)),
        "maximum_parent_patches_per_output_face": int(max_parents_per_face),
        "source_chart_reconstruction_max_residual_mm": max_source_residual,
        "output_chart_reconstruction_max_residual_mm": max_output_residual,
        "patch_area_coverage_max_residual_mm2": max_area_residual,
        "patch_pairwise_overlap_max_area_mm2": max_overlap,
        "patch_cover_and_no_overlap_pass": True,
    }


def _new_vertex_lineage_report(
    baseline: dict[str, np.ndarray], local_b: dict[str, np.ndarray], candidate: dict[str, np.ndarray], caps: list[dict[str, Any]],
) -> dict[str, Any]:
    first_new = len(local_b["vertices_rest_xyz_mm"])
    rest = np.asarray(candidate["vertices_rest_xyz_mm"], dtype=np.float64)
    relief = np.asarray(candidate["vertices_relief_xyz_mm"], dtype=np.float64)
    parent_ids = np.asarray(candidate["vertex_lineage_source_face_id"], dtype=np.int64)
    bary = np.asarray(candidate["vertex_lineage_barycentric"], dtype=np.float64)
    new_ids = np.arange(first_new, len(rest), dtype=np.int64)
    if len(parent_ids) != len(rest) or bary.shape != (len(rest), 3) or not _simplex_rows_pass(bary[new_ids]):
        raise ValueError("new vertex lineage arrays are malformed")
    allowed = set(np.concatenate([cap["source_ids"] for cap in caps]).tolist())
    if not set(parent_ids[new_ids].tolist()).issubset(allowed):
        raise ValueError("new vertex parent source face is outside the actual two cap fans")
    base_rest = np.asarray(baseline["vertices_rest_xyz_mm"], dtype=np.float64)
    base_relief = np.asarray(baseline["vertices_relief_xyz_mm"], dtype=np.float64)
    base_faces = np.asarray(baseline["faces"], dtype=np.int64)
    max_rest_error = max_relief_error = 0.0
    for vertex_id in new_ids:
        corners = base_faces[int(parent_ids[vertex_id])]
        max_rest_error = max(max_rest_error, float(np.linalg.norm(bary[vertex_id] @ base_rest[corners] - rest[vertex_id])))
        max_relief_error = max(max_relief_error, float(np.linalg.norm(bary[vertex_id] @ base_relief[corners] - relief[vertex_id])))
    if max_rest_error > LINEAGE_TOL_MM or max_relief_error > LINEAGE_TOL_MM:
        raise ValueError("a new vertex fails independent rest/relief reconstruction")
    return {"new_vertex_count": int(len(new_ids)), "all_new_vertices_reconstructed": True,
            "rest_xyz_max_residual_mm": max_rest_error, "relief_xyz_max_residual_mm": max_relief_error}


def _interface_cycle_pass(rest: np.ndarray, boundary: np.ndarray, faces: np.ndarray, cap_faces: np.ndarray) -> bool:
    ordered = boundary[np.argsort(np.arctan2(rest[boundary, 1], rest[boundary, 0]), kind="stable")]
    counts: dict[tuple[int, int], int] = {}
    for tri in np.asarray(faces, dtype=np.int64)[np.asarray(cap_faces, dtype=np.int64)]:
        for a, b in ((int(tri[0]), int(tri[1])), (int(tri[1]), int(tri[2])), (int(tri[2]), int(tri[0]))):
            key = (a, b) if a < b else (b, a)
            counts[key] = counts.get(key, 0) + 1
    return all(counts.get((min(int(ordered[i]), int(ordered[(i + 1) % len(ordered)])),
                           max(int(ordered[i]), int(ordered[(i + 1) % len(ordered)]))), 0) == 1
               for i in range(len(ordered)))


def run_focused_checks(
    baseline: dict[str, np.ndarray], local_b: dict[str, np.ndarray], candidate: dict[str, np.ndarray],
    cases: dict[str, Any], local_b_checks: dict[str, Any],
) -> dict[str, Any]:
    """Read back the saved candidate, its two caps, and all v2 lineage arrays."""
    owner_lookup_regression = owner_lookup_two_parent_toy_regression()
    caps = _find_two_source_caps(baseline)
    before_rest = np.asarray(local_b["vertices_rest_xyz_mm"], dtype=np.float64)
    before_relief = np.asarray(local_b["vertices_relief_xyz_mm"], dtype=np.float64)
    before_faces = np.asarray(local_b["faces"], dtype=np.int64)
    before_source_ids = np.asarray(local_b["source_face_ids"], dtype=np.int64)
    after_rest = np.asarray(candidate["vertices_rest_xyz_mm"], dtype=np.float64)
    after_relief = np.asarray(candidate["vertices_relief_xyz_mm"], dtype=np.float64)
    after_faces = np.asarray(candidate["faces"], dtype=np.int64)
    after_source_ids = np.asarray(candidate["v2_legacy_single_parent_face_source_ids"], dtype=np.int64)
    after_bary = np.asarray(candidate["v2_legacy_single_parent_face_corner_barycentric_to_source"], dtype=np.float64)
    lineage_status = np.asarray(candidate["face_lineage_status"], dtype=np.uint8)
    cap_face_ids = np.asarray(candidate["cap_output_face_ids"], dtype=np.int64)
    cap_face_surface = np.asarray(candidate["cap_output_face_surface_index"], dtype=np.int64)
    expected_parents = np.concatenate([cap["source_ids"] for cap in caps])
    input_cap_mask = np.isin(before_source_ids, expected_parents)
    keep_ids = np.flatnonzero(~input_cap_mask)
    if np.count_nonzero(input_cap_mask) != 256:
        raise ValueError("local-B must contain exactly 256 source-identified cap faces")
    unchanged_connectivity = np.array_equal(after_faces[:len(keep_ids)], before_faces[keep_ids])
    unchanged_face_sources = np.array_equal(after_source_ids[:len(keep_ids)], before_source_ids[keep_ids])
    unchanged_face_bary = np.array_equal(after_bary[:len(keep_ids)], local_b["face_corner_barycentric_to_source"][keep_ids])

    schema_pass = bool(
        int(np.asarray(candidate["lineage_schema_version"]).item()) == 2
        and str(np.asarray(candidate["quarantine_status"]).item()) == "EXPERIMENT_ONLY_NOT_FOR_PRODUCTION"
        and str(np.asarray(candidate["two_cap_candidate_schema"]).item()) == "isolated_v2_global_two_planar_cap_patches"
        and str(np.asarray(candidate["legacy_reader_compatibility"]).item()).startswith("UNKNOWN;")
        and "source_face_ids" not in candidate and "face_corner_barycentric_to_source" not in candidate
        and np.count_nonzero(lineage_status == 2) > 0
    )
    if not schema_pass or not np.all((lineage_status == 1) | (lineage_status == 2)):
        raise ValueError("v2 quarantine or lineage-status contract failed")
    if (np.any(after_source_ids[lineage_status == 2] != -1)
            or not np.isnan(after_bary[lineage_status == 2]).all()
            or np.any(after_source_ids[lineage_status == 1] < 0)
            or not np.isfinite(after_bary[lineage_status == 1]).all()):
        raise ValueError("explicit v2 single-parent/multi-parent status is inconsistent with legacy-only arrays")

    surface_ids = np.asarray(candidate["cap_surface_ids"]).astype(str).tolist()
    if surface_ids != [cap["surface_id"] for cap in caps]:
        raise ValueError("physical surface IDs differ from the two actual baseline caps")
    if not np.array_equal(np.asarray(candidate["modified_baseline_cap_source_face_ids"]), expected_parents):
        raise ValueError("modified source-face identities are not exactly the two pinned cap fans")
    if (not np.array_equal(np.asarray(candidate["cap_parent_source_face_ids"]), expected_parents)
            or not np.array_equal(np.asarray(candidate["cap_parent_offsets"]), np.asarray([0, 128, 256]))):
        raise ValueError("cap parent CSR must retain both actual 128-face fans")

    output_face_offsets = np.asarray(candidate["cap_output_face_offsets"], dtype=np.int64)
    if (len(output_face_offsets) != 3 or output_face_offsets[0] != 0
            or output_face_offsets[-1] != len(cap_face_ids)
            or not np.array_equal(cap_face_ids, np.arange(len(keep_ids), len(after_faces), dtype=np.int64))):
        raise ValueError("cap output-face identity and offsets are malformed")
    if not np.array_equal(after_faces[:len(keep_ids)], before_faces[keep_ids]):
        raise ValueError("noncap face connectivity or order changed")
    if (not np.array_equal(after_source_ids[:len(keep_ids)], before_source_ids[keep_ids])
            or not np.array_equal(after_bary[:len(keep_ids)], local_b["face_corner_barycentric_to_source"][keep_ids])):
        raise ValueError("noncap v1 lineage values were not preserved under their explicit v2 names")
    if not np.array_equal(cap_face_surface, np.repeat(np.arange(2), np.diff(output_face_offsets))):
        raise ValueError("output cap faces do not match their physical surface ranges")
    expected_counts = np.asarray(candidate["candidate_cap_new_vertex_counts"], dtype=np.int64)
    if expected_counts.shape != (2,):
        raise ValueError("per-cap lattice vertex counts must have two entries")
    expected_face_counts = 2 * expected_counts + 128
    if not np.array_equal(np.asarray(candidate["candidate_cap_expected_face_counts"], dtype=np.int64), expected_face_counts):
        raise ValueError("candidate Euler face counts disagree with the preserved center/boundary and lattice vertices")
    if not np.array_equal(np.diff(output_face_offsets), expected_face_counts):
        raise ValueError("actual output cap face counts disagree with the disk Euler relation")

    # Every preexisting vertex/field array stays byte-for-byte stable.
    existing_rest_equal = np.array_equal(after_rest[:len(before_rest)], before_rest)
    existing_relief_equal = np.array_equal(after_relief[:len(before_relief)], before_relief)
    baseline_rest_equal = np.array_equal(after_rest[:len(baseline["vertices_rest_xyz_mm"])], baseline["vertices_rest_xyz_mm"])
    baseline_relief_equal = np.array_equal(after_relief[:len(baseline["vertices_relief_xyz_mm"])], baseline["vertices_relief_xyz_mm"])
    preserve_names = (
        "outer_vertex_indices", "outer_theta_rad", "outer_z_mm", "outer_color_linear_rgb",
        "outer_color_srgb_for_display", "outer_relief_height_mm", "outer_normals_analytic_displaced",
        "outer_source_face_ids", "outer_base_linear_rgb", "outer_base_srgb",
    )
    preserved_outer = {name: bool(np.array_equal(candidate[name], local_b[name])) for name in preserve_names}
    base_pattern = np.asarray(baseline["outer_color_linear_rgb"])
    saved_pattern = np.asarray(local_b["outer_base_linear_rgb"])
    baseline_table_identity = bool(
        saved_pattern.shape == base_pattern.shape and saved_pattern.dtype == base_pattern.dtype
        and np.array_equal(np.ascontiguousarray(saved_pattern).view(np.uint8),
                           np.ascontiguousarray(base_pattern).view(np.uint8))
    )

    saved_z = np.asarray(candidate["cap_plane_z_mm"], dtype=np.float64)
    saved_radius = np.asarray(candidate["cap_radius_mm"], dtype=np.float64)
    saved_orientation = np.asarray(candidate["cap_orientation"]).astype(str).tolist()
    if (not np.array_equal(saved_z, np.asarray([cap["z"] for cap in caps]))
            or not np.array_equal(saved_radius, np.asarray([cap["radius"] for cap in caps]))
            or saved_orientation != [cap["orientation"] for cap in caps]):
        raise ValueError("saved cap planes, radii, or material orientation differ from the frozen source geometry")
    boundary_saved = np.asarray(candidate["cap_boundary_vertex_ids_angle_sorted"], dtype=np.int64)
    if boundary_saved.shape != (2, 128):
        raise ValueError("candidate must preserve exactly two 128-vertex boundary cycles")
    interfaces_pass = True
    for i, cap in enumerate(caps):
        interfaces_pass = interfaces_pass and np.array_equal(boundary_saved[i], cap["boundary_ids"])
        interfaces_pass = interfaces_pass and _interface_cycle_pass(after_rest, cap["boundary_ids"], after_faces, cap_face_ids[cap_face_surface == i])

    chart_offsets = np.asarray(candidate["cap_chart_vertex_offsets"], dtype=np.int64)
    chart_ids = np.asarray(candidate["cap_chart_vertex_indices"], dtype=np.int64)
    chart_xy = np.asarray(candidate["cap_chart_xy_mm"], dtype=np.float64)
    chart_linear = np.asarray(candidate["cap_chart_vertex_color_linear_rgb"], dtype=np.float64)
    chart_srgb = np.asarray(candidate["cap_chart_vertex_color_srgb"], dtype=np.float64)
    base_linear = np.asarray(cases["field"]["base_linear_rgb"], dtype=np.float64)
    if (len(chart_offsets) != 3 or chart_offsets[0] != 0 or chart_offsets[-1] != len(chart_ids)
            or len(np.unique(chart_ids)) != len(chart_ids) or chart_xy.shape != (len(chart_ids), 2)
            or chart_linear.shape != (len(chart_ids), 3) or chart_srgb.shape != (len(chart_ids), 3)):
        raise ValueError("saved cap chart/color arrays have inconsistent shapes")
    chart_colors_pass = True
    for i, cap in enumerate(caps):
        v0, v1 = int(chart_offsets[i]), int(chart_offsets[i + 1])
        ids = chart_ids[v0:v1]
        cap_faces = after_faces[cap_face_ids[cap_face_surface == i]]
        expected_chart_ids = np.unique(np.r_[cap["center_id"], cap["boundary_ids"], cap_faces.ravel()])
        chart_colors_pass = chart_colors_pass and np.array_equal(ids, expected_chart_ids)
        chart_colors_pass = chart_colors_pass and np.array_equal(chart_xy[v0:v1], after_rest[ids, :2])
        chart_colors_pass = chart_colors_pass and bool(np.all(np.abs(after_rest[ids, 2] - cap["z"]) <= 1e-12))
        chart_colors_pass = chart_colors_pass and np.array_equal(chart_linear[v0:v1], np.broadcast_to(base_linear, (v1 - v0, 3)))
        chart_colors_pass = chart_colors_pass and bool(np.max(np.abs(chart_srgb[v0:v1] - _linear_rgb_to_srgb(chart_linear[v0:v1])), initial=0.0) <= COLOR_FINITE_SAMPLE_TOL)
    if not chart_colors_pass:
        raise ValueError("cap chart coordinates or sampled linear/sRGB colors fail independent readback")

    new_ids = np.arange(len(before_rest), len(after_rest), dtype=np.int64)
    if (len(new_ids) != int(expected_counts.sum()) or len(new_ids) > 2500
            or len(after_faces) != len(before_faces) - 256 + int(expected_face_counts.sum())
            or len(after_faces) > 45000):
        raise ValueError("aggregate two-cap vertex/face counts violate their fixed Euler budgets")
    if not np.array_equal(after_rest[new_ids], after_relief[new_ids]):
        raise ValueError("all new cap vertices must remain planar and unrelieved")
    for i, cap in enumerate(caps):
        ids = chart_ids[int(chart_offsets[i]):int(chart_offsets[i + 1])]
        added = ids[ids >= len(before_rest)]
        if len(added) != int(expected_counts[i]) or not np.all(np.abs(after_rest[added, 2] - cap["z"]) <= 1e-12):
            raise ValueError("per-cap added lattice points disagree with their pinned plane/count")
        for point in after_rest[added, :2]:
            for j, anchor in enumerate(cap["polygon"]):
                edge = cap["polygon"][(j + 1) % len(cap["polygon"])] - anchor
                if _cross2(edge, point - anchor) < -1e-8:
                    raise ValueError("a new cap lattice point lies outside the frozen boundary polygon")

    vertex_report = _new_vertex_lineage_report(baseline, local_b, candidate, caps)
    patch_report = _check_saved_patch_csr(baseline, candidate, caps, base_linear)
    stored_patch_counts_equal = bool(
        int(np.asarray(candidate["candidate_total_patch_record_count"]).item()) == patch_report["patch_record_count"]
        and int(np.asarray(candidate["candidate_total_patch_vertex_count"]).item()) == patch_report["patch_polygon_vertex_count"]
        and float(np.asarray(candidate["cap_patch_area_tolerance_mm2"]).item()) == PATCH_AREA_TOL_MM2
        and float(np.asarray(candidate["cap_patch_overlap_tolerance_mm2"]).item()) == PATCH_OVERLAP_TOL_MM2
    )
    cap_metrics = []
    for i, cap in enumerate(caps):
        metric = summarize_triangle_quality(after_relief, after_faces[cap_face_ids[cap_face_surface == i]])
        metric["surface_id"] = cap["surface_id"]
        cap_metrics.append(metric)
    cap_q_targets_pass = all(float(metric["minimum_Q"]) >= 0.35 for metric in cap_metrics)
    cap_ar_targets_pass = all(float(metric["maximum_aspect_longest_edge_over_minimum_altitude"]) <= 5.0 for metric in cap_metrics)

    noncap_before = summarize_triangle_quality(before_relief, before_faces[keep_ids])
    noncap_after_ids = np.flatnonzero(~np.isin(np.arange(len(after_faces)), cap_face_ids))
    noncap_after = summarize_triangle_quality(after_relief, after_faces[noncap_after_ids])
    noncap_metrics_unchanged = bool(
        noncap_before["face_count"] == noncap_after["face_count"]
        and noncap_before["minimum_Q"] == noncap_after["minimum_Q"]
        and noncap_before["maximum_aspect_longest_edge_over_minimum_altitude"]
            == noncap_after["maximum_aspect_longest_edge_over_minimum_altitude"]
    )
    global_before = summarize_triangle_quality(before_relief, before_faces)
    global_after = summarize_triangle_quality(after_relief, after_faces)
    q_before, q_after = float(global_before["minimum_Q"]), float(global_after["minimum_Q"])
    ar_before = float(global_before["maximum_aspect_longest_edge_over_minimum_altitude"])
    ar_after = float(global_after["maximum_aspect_longest_edge_over_minimum_altitude"])
    q_tol = GLOBAL_FLOAT_ULPS * np.finfo(np.float64).eps * max(1.0, abs(q_before), abs(q_after))
    ar_tol = GLOBAL_FLOAT_ULPS * np.finfo(np.float64).eps * max(1.0, abs(ar_before), abs(ar_after))
    q_gain, ar_gain = q_after - q_before, ar_before - ar_after
    global_q_pass = q_gain > q_tol
    global_ar_pass = ar_gain > ar_tol

    outer_after = _outer_color_error(candidate, cases["field"])
    outer_before = _outer_color_error(local_b, cases["field"])
    outer_color_delta = outer_after["finite_outer_color_max_abs_linear_rgb_error"] - outer_before["finite_outer_color_max_abs_linear_rgb_error"]
    outer_relief_delta = outer_after["finite_outer_relief_max_abs_error_mm"] - outer_before["finite_outer_relief_max_abs_error_mm"]
    outer_field_unchanged = bool(abs(outer_color_delta) <= COLOR_FINITE_SAMPLE_TOL and abs(outer_relief_delta) <= 1e-12)
    outer_corner_color_pass = outer_after["per_corner_color_max_abs_linear_rgb_error"] <= COLOR_FINITE_SAMPLE_TOL
    topology = _topology(after_relief, after_faces)
    topology_pass = bool(
        topology["boundary_edge_count"] == 0 and topology["non_two_incidence_edge_count"] == 0
        and topology["inconsistent_winding_edge_count"] == 0 and topology["duplicate_face_count_unoriented"] == 0
        and topology["repeated_vertex_face_count"] == 0 and topology["zero_area_face_count_threshold_1e-12_mm2"] == 0
        and topology["connected_component_count"] == 1 and topology["euler_characteristic"] == 2
        and topology["positive_signed_volume"]
    )
    checks = {
        "two_parent_owner_lookup_raw_signed_barycentric_regression": owner_lookup_regression["passed"],
        "schema_v2_quarantine_no_v1_aliases": schema_pass,
        "actual_two_cap_source_fans_and_physical_surface_ids": True,
        "noncap_connectivity_identity": unchanged_connectivity,
        "noncap_face_source_identity": unchanged_face_sources,
        "noncap_barycentric_identity": unchanged_face_bary,
        "all_preexisting_rest_relief_vertices_bitwise": existing_rest_equal and existing_relief_equal,
        "baseline_rest_relief_prefix_bitwise": baseline_rest_equal and baseline_relief_equal,
        "outer_surface_field_and_color_arrays_bitwise": all(preserved_outer.values()),
        "baseline_patterned_outer_color_table_bitwise": baseline_table_identity,
        "two_128_vertex_boundary_cycles_preserved": bool(interfaces_pass),
        "two_cap_chart_and_linear_srgb_samples_verified": bool(chart_colors_pass),
        "all_new_vertex_lineage_reconstructs": vertex_report["all_new_vertices_reconstructed"],
        "all_cross_parent_patches_cover_without_overlap": patch_report["patch_cover_and_no_overlap_pass"],
        "serialized_global_patch_counts_and_tolerances_match_readback": stored_patch_counts_equal,
        "outer_continuous_field_samples_unchanged": outer_field_unchanged,
        "outer_corner_color_matches_continuous_field": outer_corner_color_pass,
        "untouched_noncap_quality_unchanged": noncap_metrics_unchanged,
        "both_cap_minimum_Q_at_least_0p35": cap_q_targets_pass,
        "both_cap_aspect_at_most_5": cap_ar_targets_pass,
        "global_minimum_Q_improves_above_float_resolution": global_q_pass,
        "global_maximum_aspect_improves_above_float_resolution": global_ar_pass,
        "closed_oriented_sphere_topology": topology_pass,
        "fixed_total_vertex_and_face_budgets": len(new_ids) <= 2500 and len(after_faces) <= 45000,
        "fixed_aggregate_patch_budgets": patch_report["patch_record_count"] <= MAX_PATCH_RECORDS and patch_report["patch_polygon_vertex_count"] <= MAX_PATCH_VERTICES,
    }
    return {
        "candidate_id": "global_two_cap_mesh_candidate_owner_fix_20261005",
        "schema": "isolated_v2_global_two_planar_cap_patches",
        "quarantine_status": str(np.asarray(candidate["quarantine_status"]).item()),
        "legacy_reader_compatibility": str(np.asarray(candidate["legacy_reader_compatibility"]).item()),
        "interpretation": "geometric triangle quality only; no tetrahedral, solver, mechanical-h, fracture, or physical-match claim",
        "surface_ids": surface_ids,
        "input_counts": {"vertices": int(len(before_rest)), "faces": int(len(before_faces))},
        "candidate_counts": {"vertices": int(len(after_rest)), "faces": int(len(after_faces))},
        "cap_quality_relief": {metric["surface_id"]: metric for metric in cap_metrics},
        "input_global_quality_relief": global_before,
        "candidate_global_quality_relief": global_after,
        "untouched_noncap_input_quality_relief": noncap_before,
        "untouched_noncap_candidate_quality_relief": noncap_after,
        "robust_global_quality_gate": {
            "required_float64_ulps": GLOBAL_FLOAT_ULPS, "minimum_Q_gain": q_gain,
            "minimum_Q_resolution_tolerance": q_tol, "maximum_aspect_reduction": ar_gain,
            "maximum_aspect_resolution_tolerance": ar_tol,
        },
        "outer_field_candidate": outer_after, "outer_field_local_b": outer_before,
        "outer_field_sample_error_delta": {"linear_rgb": float(outer_color_delta), "relief_mm": float(outer_relief_delta)},
        "new_vertex_lineage": vertex_report, "cross_parent_lineage": patch_report, "topology": topology,
        "owner_lookup_two_parent_toy_regression": owner_lookup_regression,
        "focused_check_count": len(checks), "focused_check_pass_count": sum(bool(value) for value in checks.values()),
        "focused_checks_pass": all(checks.values()), "checks": checks,
        "recorded_local_b_checks_sha256": "4e4c08b96bd6e7dd47a3285377979fc93fc3865a0bc1fcdd48d79397c23e14e8",
        "local_b_recorded_run_status": local_b_checks.get("run_status", "UNKNOWN"),
    }


def render_saved_meshes(candidate: dict[str, np.ndarray], output_dir: Path, cases: dict[str, Any]) -> None:
    """Render actual saved output faces at equal physical scales."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    xyz = np.asarray(candidate["vertices_relief_xyz_mm"], dtype=np.float64)
    rest = np.asarray(candidate["vertices_rest_xyz_mm"], dtype=np.float64)
    faces = np.asarray(candidate["faces"], dtype=np.int64)
    base_srgb = _linear_rgb_to_srgb(np.asarray(cases["field"]["base_linear_rgb"], dtype=np.float64))
    face_colors = np.tile(np.r_[base_srgb, 1.0], (len(faces), 1))
    outer_vertex_ids = np.asarray(candidate["outer_vertex_indices"], dtype=np.int64)
    outer_colors = np.asarray(candidate["outer_color_srgb_for_display"], dtype=np.float64)
    color_by_vertex = {int(vertex): outer_colors[i] for i, vertex in enumerate(outer_vertex_ids)}
    outer_source_set = set(np.asarray(candidate["outer_source_face_ids"], dtype=np.int64).tolist())
    source_ids = _saved_face_source_ids(candidate)
    outer_mask = np.fromiter((int(source_id) in outer_source_set for source_id in source_ids), dtype=bool, count=len(source_ids))
    for face_id in np.flatnonzero(outer_mask):
        face_colors[face_id, :3] = np.mean([color_by_vertex[int(vertex)] for vertex in faces[face_id]], axis=0)

    figure = plt.figure(figsize=(10.5, 8.0), constrained_layout=True)
    axis = figure.add_subplot(111, projection="3d")
    axis.add_collection3d(Poly3DCollection(
        xyz[faces], facecolors=face_colors, edgecolors=(0.12, 0.10, 0.08, 0.16), linewidths=0.035,
    ))
    lower, upper = xyz.min(axis=0), xyz.max(axis=0)
    center = 0.5 * (lower + upper)
    half_span = 0.5 * max(float(np.max(upper - lower)), 1.0)
    axis.set_xlim(center[0] - half_span, center[0] + half_span)
    axis.set_ylim(center[1] - half_span, center[1] + half_span)
    axis.set_zlim(center[2] - half_span, center[2] + half_span)
    axis.set_box_aspect((1.0, 1.0, 1.0))
    axis.set_xlabel("X (mm)")
    axis.set_ylabel("Y (mm)")
    axis.set_zlabel("Z (mm)")
    axis.set_title("Saved actual geometry with both cap remeshes | triangles only")
    figure.savefig(Path(output_dir) / "global_equal_aspect_actual_mesh.png", dpi=170)
    plt.close(figure)

    cap_face_ids = np.asarray(candidate["cap_output_face_ids"], dtype=np.int64)
    cap_face_surface = np.asarray(candidate["cap_output_face_surface_index"], dtype=np.int64)
    figure, axes = plt.subplots(1, 2, figsize=(11.0, 5.5), constrained_layout=True)
    for surface_index, axis in enumerate(axes):
        surface_id, z, radius, _ = SURFACE_SPECS[surface_index]
        actual_face_ids = cap_face_ids[cap_face_surface == surface_index]
        polygons = rest[faces[actual_face_ids], :2]
        axis.add_collection(PolyCollection(
            polygons, facecolors=base_srgb, edgecolors=(0.12, 0.10, 0.08, 0.34), linewidths=0.18,
        ))
        axis.set_xlim(-radius - 0.75, radius + 0.75)
        axis.set_ylim(-radius - 0.75, radius + 0.75)
        axis.set_aspect("equal", adjustable="box")
        axis.set_xlabel("X (mm)")
        axis.set_ylabel("Y (mm)")
        axis.set_title(f"{surface_id} | z={z:g} mm | R={radius:g} mm")
        axis.grid(alpha=0.15)
    figure.suptitle("Saved two-cap charts | equal XY scale | geometric quality only")
    figure.savefig(Path(output_dir) / "two_caps_equal_aspect_actual_mesh.png", dpi=170)
    plt.close(figure)

