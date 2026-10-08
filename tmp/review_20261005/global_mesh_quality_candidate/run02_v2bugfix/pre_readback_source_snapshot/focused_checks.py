"""Focused readback checks for the isolated global floor-mesh candidate.

These checks are source only until the parent agent approves the one bounded
generation run.  They intentionally audit the actual saved candidate arrays.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np


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


def _floor_patch_checks(
    baseline: dict[str, np.ndarray],
    candidate: dict[str, np.ndarray],
    field: dict[str, Any],
) -> dict[str, Any]:
    base_rest = np.asarray(baseline["vertices_rest_xyz_mm"], dtype=np.float64)
    base_faces = np.asarray(baseline["faces"], dtype=np.int64)
    candidate_rest = np.asarray(candidate["vertices_rest_xyz_mm"], dtype=np.float64)
    candidate_faces = np.asarray(candidate["faces"], dtype=np.int64)
    floor_faces = np.asarray(candidate["floor_output_face_ids"], dtype=np.int64)
    floor_sources = set(_source_floor_ids(baseline).tolist())
    declared_floor_sources = set(
        np.asarray(candidate["modified_baseline_floor_source_face_ids"], dtype=np.int64).tolist()
    )
    floor_source_declaration_equal = declared_floor_sources == floor_sources
    face_offsets = np.asarray(candidate["floor_face_patch_offsets"], dtype=np.int64)
    patch_sources = np.asarray(candidate["floor_face_patch_source_face_ids"], dtype=np.int64)
    patch_areas = np.asarray(candidate["floor_face_patch_area_mm2"], dtype=np.float64)
    vertex_offsets = np.asarray(candidate["floor_face_patch_vertex_offsets"], dtype=np.int64)
    patch_xy = np.asarray(candidate["floor_face_patch_vertices_xy_mm"], dtype=np.float64)
    patch_source_bary = np.asarray(candidate["floor_face_patch_vertices_barycentric_to_source"], dtype=np.float64)
    patch_output_bary = np.asarray(candidate["floor_face_patch_vertices_barycentric_to_output"], dtype=np.float64)
    patch_color = np.asarray(candidate["floor_face_patch_vertices_color_linear_rgb"], dtype=np.float64)
    patch_color_srgb = np.asarray(candidate["floor_face_patch_vertices_color_srgb"], dtype=np.float64)
    candidate_source_ids = _saved_face_source_ids(candidate)
    candidate_face_bary = _saved_face_corner_barycentric(candidate)
    lineage_status = np.asarray(candidate["face_lineage_status"], dtype=np.uint8)
    if len(face_offsets) != len(floor_faces) + 1 or len(face_offsets) == 0:
        raise ValueError("floor patch face CSR offsets have the wrong shape")
    if len(vertex_offsets) != len(patch_sources) + 1:
        raise ValueError("floor patch vertex CSR offsets have the wrong shape")
    if (face_offsets[0] != 0 or face_offsets[-1] != len(patch_sources)
            or np.any(np.diff(face_offsets) < 0)):
        raise ValueError("floor patch face CSR offsets are not a complete monotone partition")
    if (vertex_offsets[0] != 0 or vertex_offsets[-1] != len(patch_xy)
            or np.any(np.diff(vertex_offsets) < 0)):
        raise ValueError("floor patch vertex CSR offsets are not a complete monotone partition")
    if (len(np.unique(floor_faces)) != len(floor_faces)
            or np.any(floor_faces < 0) or np.any(floor_faces >= len(candidate_faces))):
        raise ValueError("floor output face IDs must be unique valid face indices")
    if (len(patch_areas) != len(patch_sources)
            or len(patch_xy) != len(patch_source_bary)
            or len(patch_xy) != len(patch_output_bary)
            or len(patch_xy) != len(patch_color)
            or len(patch_xy) != len(patch_color_srgb)):
        raise ValueError("floor patch data columns have inconsistent lengths")

    color_base = np.asarray(field["base_linear_rgb"], dtype=np.float64)
    source_recon_max = 0.0
    output_recon_max = 0.0
    color_max = 0.0
    color_srgb_max = 0.0
    floor_corner_srgb_error = 0.0
    coverage_max = 0.0
    overlap_max = 0.0
    patch_area_total = 0.0
    single_parent_count = 0
    multi_parent_count = 0
    per_output_face_patch_records_max = 0
    source_simplex_ok = True
    output_simplex_ok = True
    color_corner_errors: list[float] = []
    floor_chart_ids = np.asarray(candidate["floor_chart_vertex_indices"], dtype=np.int64)
    floor_chart_xy = np.asarray(candidate["floor_chart_xy_mm"], dtype=np.float64)
    floor_chart_colors = np.asarray(candidate["floor_vertex_color_linear_rgb"], dtype=np.float64)
    floor_chart_colors_srgb = np.asarray(candidate["floor_vertex_color_srgb"], dtype=np.float64)
    chart_color_by_vertex = {int(v): floor_chart_colors[i] for i, v in enumerate(floor_chart_ids)}
    chart_color_srgb_by_vertex = {int(v): floor_chart_colors_srgb[i] for i, v in enumerate(floor_chart_ids)}
    expected_floor_srgb = _linear_rgb_to_srgb(color_base)
    if (floor_chart_xy.shape != (len(floor_chart_ids), 2)
            or floor_chart_colors.shape != (len(floor_chart_ids), 3)
            or floor_chart_colors_srgb.shape != (len(floor_chart_ids), 3)):
        raise ValueError("floor chart/color arrays have inconsistent shape")
    for face_id in floor_faces:
        tri_ids = candidate_faces[int(face_id)]
        tri_xy = candidate_rest[tri_ids, :2]
        tri_area = abs(_area2(tri_xy))
        for vertex_id in tri_ids:
            if int(vertex_id) not in chart_color_by_vertex:
                raise ValueError("floor face corner is missing its sampled floor color")
            source_color = chart_color_by_vertex[int(vertex_id)]
            expected = color_base
            color_corner_errors.append(float(np.max(np.abs(source_color - expected))))
        for vertex_id in tri_ids:
            actual_srgb = chart_color_srgb_by_vertex[int(vertex_id)]
            floor_corner_srgb_error = max(
                floor_corner_srgb_error,
                float(np.max(np.abs(actual_srgb - expected_floor_srgb))),
            )
        start_patch, end_patch = int(face_offsets[np.flatnonzero(floor_faces == face_id)[0]]), int(face_offsets[np.flatnonzero(floor_faces == face_id)[0] + 1])
        if end_patch <= start_patch:
            raise ValueError("floor output face has no source patches")
        face_patch_record_count = end_patch - start_patch
        per_output_face_patch_records_max = max(per_output_face_patch_records_max, face_patch_record_count)
        if face_patch_record_count > len(floor_sources):
            raise ValueError("one floor output face exceeds the complete frozen source fan")
        local_polygons: list[np.ndarray] = []
        local_area_sum = 0.0
        for patch_id in range(start_patch, end_patch):
            source_id = int(patch_sources[patch_id])
            if source_id not in floor_sources:
                raise ValueError("floor source patch points outside the original bottom fan")
            area = float(patch_areas[patch_id])
            if not math.isfinite(area) or area <= 0.0:
                raise ValueError("floor source patch has nonpositive area")
            patch_area_total += area
            local_area_sum += area
            v0, v1 = int(vertex_offsets[patch_id]), int(vertex_offsets[patch_id + 1])
            poly = patch_xy[v0:v1]
            src_bary = patch_source_bary[v0:v1]
            out_bary = patch_output_bary[v0:v1]
            patch_colors = patch_color[v0:v1]
            if len(poly) < 3 or not _simplex_rows_pass(src_bary) or not _simplex_rows_pass(out_bary):
                raise ValueError("floor patch vertex barycentric rows are not simplex values")
            source_tri_xy = base_rest[base_faces[source_id], :2]
            source_recon = src_bary @ source_tri_xy
            output_recon = out_bary @ tri_xy
            source_recon_max = max(source_recon_max, float(np.max(np.linalg.norm(source_recon - poly, axis=1))))
            output_recon_max = max(output_recon_max, float(np.max(np.linalg.norm(output_recon - poly, axis=1))))
            source_simplex_ok = source_simplex_ok and _simplex_rows_pass(src_bary)
            output_simplex_ok = output_simplex_ok and _simplex_rows_pass(out_bary)
            color_max = max(color_max, float(np.max(np.abs(patch_colors - color_base[None, :]), initial=0.0)))
            color_srgb_max = max(
                color_srgb_max,
                float(np.max(np.abs(patch_color_srgb[v0:v1] - _linear_rgb_to_srgb(patch_colors)), initial=0.0)),
            )
            local_polygons.append(poly)
            computed_area = abs(_area2(poly))
            if abs(computed_area - area) > max(1e-9, area * 1e-10):
                raise ValueError("stored source-patch area disagrees with its polygon")
        coverage_error = abs(local_area_sum - tri_area)
        coverage_max = max(coverage_max, coverage_error)
        if coverage_error > max(1e-9, tri_area * 1e-10):
            raise ValueError("source patches do not cover their output face area")
        for left in range(len(local_polygons)):
            for right in range(left + 1, len(local_polygons)):
                overlap = _clip_convex(local_polygons[left], local_polygons[right])
                overlap_area = abs(_area2(overlap)) if len(overlap) else 0.0
                overlap_max = max(overlap_max, overlap_area)
                if overlap_area > 1e-10:
                    raise ValueError("source patches overlap with positive area")
        local_sources = patch_sources[start_patch:end_patch]
        unique_sources = np.unique(local_sources)
        if len(unique_sources) != len(local_sources):
            raise ValueError("one floor output face repeats a source parent patch")
        if len(unique_sources) == 1 and abs(local_area_sum - tri_area) <= max(1e-9, tri_area * 1e-10):
            single_parent_count += 1
            if int(candidate_source_ids[int(face_id)]) != int(unique_sources[0]) or int(lineage_status[int(face_id)]) != 1:
                raise ValueError("single-parent floor face did not retain a valid legacy source row")
            bary_rows = candidate_face_bary[int(face_id)]
            if not _simplex_rows_pass(bary_rows):
                raise ValueError("single-parent floor legacy barycentric row is invalid")
            reconstructed = bary_rows @ base_rest[base_faces[int(unique_sources[0])], :]
            actual_xyz = candidate_rest[tri_ids]
            if float(np.max(np.linalg.norm(reconstructed - actual_xyz, axis=1))) > 1e-9:
                raise ValueError("single-parent legacy face corner does not reconstruct its source location")
        else:
            multi_parent_count += 1
            if int(candidate_source_ids[int(face_id)]) != -1 or int(lineage_status[int(face_id)]) != 2:
                raise ValueError("multi-parent floor face is missing its explicit legacy sentinel")
            if np.isfinite(candidate_face_bary[int(face_id)]).any():
                raise ValueError("multi-parent floor face legacy barycentrics must be unreadable NaNs")
    floor_corner_error = max(color_corner_errors, default=0.0)
    return {
        "floor_output_face_count": int(len(floor_faces)),
        "floor_patch_count": int(len(patch_sources)),
        "floor_patch_vertex_count": int(len(patch_xy)),
        "frozen_floor_source_face_count": int(len(floor_sources)),
        "floor_source_declaration_matches_frozen_fan": bool(floor_source_declaration_equal),
        "per_output_face_patch_record_cap": int(len(floor_sources)),
        "per_output_face_patch_records_max": int(per_output_face_patch_records_max),
        "per_output_face_patch_cap_pass": bool(per_output_face_patch_records_max <= len(floor_sources)),
        "single_parent_floor_face_count": int(single_parent_count),
        "multi_parent_floor_face_count": int(multi_parent_count),
        "source_barycentric_simplex_pass": bool(source_simplex_ok),
        "output_barycentric_simplex_pass": bool(output_simplex_ok),
        "source_chart_reconstruction_max_residual_mm": float(source_recon_max),
        "output_chart_reconstruction_max_residual_mm": float(output_recon_max),
        "patch_area_coverage_max_residual_mm2": float(coverage_max),
        "patch_pairwise_overlap_max_area_mm2": float(overlap_max),
        "patch_area_total_mm2": float(patch_area_total),
        "floor_vertex_color_max_abs_linear_rgb_error": float(floor_corner_error),
        "floor_vertex_color_max_abs_srgb_error": float(floor_corner_srgb_error),
        "patch_vertex_color_max_abs_linear_rgb_error": float(color_max),
        "patch_vertex_color_max_abs_srgb_error": float(color_srgb_max),
    }


def _baseline_floor_face_mask(local_b: dict[str, np.ndarray], floor_source_ids: np.ndarray) -> np.ndarray:
    source_ids = np.asarray(local_b["source_face_ids"], dtype=np.int64)
    return np.isin(source_ids, np.asarray(floor_source_ids, dtype=np.int64))


def _source_floor_ids(baseline: dict[str, np.ndarray]) -> np.ndarray:
    rest = np.asarray(baseline["vertices_rest_xyz_mm"], dtype=np.float64)
    faces = np.asarray(baseline["faces"], dtype=np.int64)
    tri = rest[faces]
    zmask = np.all(np.abs(tri[:, :, 2]) <= 1e-12, axis=1)
    radius = float(np.asarray(baseline["outer_radius_mm"]).item())
    rmask = np.all(np.linalg.norm(tri[:, :, :2], axis=2) <= radius + 1e-10, axis=1)
    return np.flatnonzero(zmask & rmask).astype(np.int64)


def _new_vertex_lineage_checks(
    baseline: dict[str, np.ndarray],
    local_b: dict[str, np.ndarray],
    candidate: dict[str, np.ndarray],
) -> dict[str, Any]:
    """Independently reconstruct every vertex appended by this candidate."""
    start = len(np.asarray(local_b["vertices_rest_xyz_mm"]))
    candidate_rest = np.asarray(candidate["vertices_rest_xyz_mm"], dtype=np.float64)
    new_ids = np.arange(start, len(candidate_rest), dtype=np.int64)
    source_ids = np.asarray(candidate["vertex_lineage_source_face_id"], dtype=np.int64)[new_ids]
    bary = np.asarray(candidate["vertex_lineage_barycentric"], dtype=np.float64)[new_ids]
    baseline_faces = np.asarray(baseline["faces"], dtype=np.int64)
    baseline_rest = np.asarray(baseline["vertices_rest_xyz_mm"], dtype=np.float64)
    allowed_floor_sources = set(_source_floor_ids(baseline).tolist())
    source_ids_valid = bool(all(int(source_id) in allowed_floor_sources for source_id in source_ids))
    simplex_pass = _simplex_rows_pass(bary)
    if len(source_ids) and source_ids_valid and simplex_pass:
        source_triangles = baseline_rest[baseline_faces[source_ids]]
        reconstructed = np.einsum("ij,ijk->ik", bary, source_triangles)
        residuals = np.linalg.norm(reconstructed - candidate_rest[new_ids], axis=1)
        maximum_residual = float(np.max(residuals, initial=0.0))
    else:
        maximum_residual = None
    return {
        "new_vertex_count": int(len(new_ids)),
        "source_ids_valid_bottom_fan_only": source_ids_valid,
        "barycentric_simplex_pass": bool(simplex_pass),
        "source_triangle_reconstruction_max_residual_mm": maximum_residual,
        "all_new_vertices_reconstructed": bool(
            len(new_ids) > 0 and source_ids_valid and simplex_pass
            and maximum_residual is not None and maximum_residual <= 1e-9
        ),
    }


def _interface_cycle_pass(rest: np.ndarray, boundary_ids: np.ndarray, faces: np.ndarray, floor_face_ids: np.ndarray) -> bool:
    theta = np.arctan2(rest[boundary_ids, 1], rest[boundary_ids, 0])
    ordered = boundary_ids[np.argsort(theta, kind="stable")]
    floor_edges: dict[tuple[int, int], int] = {}
    for tri in np.asarray(faces, dtype=np.int64)[np.asarray(floor_face_ids, dtype=np.int64)]:
        for a, b in ((int(tri[0]), int(tri[1])), (int(tri[1]), int(tri[2])), (int(tri[2]), int(tri[0]))):
            key = (a, b) if a < b else (b, a)
            floor_edges[key] = floor_edges.get(key, 0) + 1
    return all(
        floor_edges.get((min(int(ordered[i]), int(ordered[(i + 1) % len(ordered)])),
                         max(int(ordered[i]), int(ordered[(i + 1) % len(ordered)]))), 0) == 1
        for i in range(len(ordered))
    )


def run_focused_checks(
    baseline: dict[str, np.ndarray],
    local_b: dict[str, np.ndarray],
    candidate: dict[str, np.ndarray],
    cases: dict[str, Any],
    local_b_checks: dict[str, Any],
) -> dict[str, Any]:
    """Audit saved arrays, lineage patches, colors, topology, and actual Q/aspect."""
    floor_source_ids = _source_floor_ids(baseline)
    if len(floor_source_ids) != 128:
        raise ValueError("readback did not find the frozen 128-face bottom source fan")
    base_rest = np.asarray(baseline["vertices_rest_xyz_mm"], dtype=np.float64)
    base_faces = np.asarray(baseline["faces"], dtype=np.int64)
    center_ids = np.flatnonzero(
        (np.abs(base_rest[:, 2]) <= 1e-12)
        & (np.linalg.norm(base_rest[:, :2], axis=1) <= 1e-12)
    )
    if len(center_ids) != 1:
        raise ValueError("readback did not find one frozen bottom center vertex")
    boundary_ids = np.unique(base_faces[floor_source_ids][base_faces[floor_source_ids] != int(center_ids[0])])
    if len(boundary_ids) != 128:
        raise ValueError("readback did not find the frozen 128-vertex floor boundary")
    before_rest = np.asarray(local_b["vertices_rest_xyz_mm"], dtype=np.float64)
    before_relief = np.asarray(local_b["vertices_relief_xyz_mm"], dtype=np.float64)
    after_rest = np.asarray(candidate["vertices_rest_xyz_mm"], dtype=np.float64)
    after_relief = np.asarray(candidate["vertices_relief_xyz_mm"], dtype=np.float64)
    before_faces = np.asarray(local_b["faces"], dtype=np.int64)
    after_faces = np.asarray(candidate["faces"], dtype=np.int64)
    before_sources = np.asarray(local_b["source_face_ids"], dtype=np.int64)
    after_sources = _saved_face_source_ids(candidate)
    floor_face_ids = np.asarray(candidate["floor_output_face_ids"], dtype=np.int64)
    floor_metrics_before = summarize_triangle_quality(before_relief, before_faces[_baseline_floor_face_mask(local_b, floor_source_ids)])
    floor_metrics_after = summarize_triangle_quality(after_relief, after_faces[floor_face_ids])
    global_metrics_before = summarize_triangle_quality(before_relief, before_faces)
    global_metrics_after = summarize_triangle_quality(after_relief, after_faces)
    nonfloor_mask_after = np.ones(len(after_faces), dtype=bool)
    nonfloor_mask_after[floor_face_ids] = False
    nonfloor_metrics_after = summarize_triangle_quality(after_relief, after_faces[nonfloor_mask_after])

    original_vertex_prefix_rest_equal = bool(np.array_equal(after_rest[:len(before_rest)], before_rest))
    original_vertex_prefix_relief_equal = bool(np.array_equal(after_relief[:len(before_relief)], before_relief))
    baseline_prefix_rest_equal = bool(np.array_equal(after_rest[:len(baseline["vertices_rest_xyz_mm"])], baseline["vertices_rest_xyz_mm"]))
    baseline_prefix_relief_equal = bool(np.array_equal(after_relief[:len(baseline["vertices_relief_xyz_mm"])], baseline["vertices_relief_xyz_mm"]))
    preserved_fields = (
        "outer_vertex_indices", "outer_theta_rad", "outer_z_mm", "outer_color_linear_rgb",
        "outer_color_srgb_for_display", "outer_relief_height_mm", "outer_normals_analytic_displaced",
        "outer_base_linear_rgb", "outer_base_srgb", "outer_source_face_ids",
    )
    preserved_array_equal = {name: bool(np.array_equal(candidate[name], local_b[name])) for name in preserved_fields}
    nonfloor_ids_before = np.flatnonzero(~_baseline_floor_face_mask(local_b, floor_source_ids))
    nonfloor_ids_after = np.flatnonzero(np.ones(len(after_faces), dtype=bool))
    nonfloor_ids_after = nonfloor_ids_after[~np.isin(nonfloor_ids_after, floor_face_ids)]
    nonfloor_face_connectivity_equal = bool(np.array_equal(after_faces[nonfloor_ids_after], before_faces[nonfloor_ids_before]))
    nonfloor_source_ids_equal = bool(np.array_equal(after_sources[nonfloor_ids_after], before_sources[nonfloor_ids_before]))
    after_face_bary = _saved_face_corner_barycentric(candidate)
    nonfloor_face_bary_equal = bool(np.array_equal(
        after_face_bary[nonfloor_ids_after],
        np.asarray(local_b["face_corner_barycentric_to_source"])[nonfloor_ids_before],
    ))

    input_floor_mask = _baseline_floor_face_mask(local_b, floor_source_ids)
    input_floor_xyz = before_relief[before_faces[input_floor_mask]]
    output_floor_xyz = after_relief[after_faces[floor_face_ids]]
    input_area = float(np.sum(np.linalg.norm(np.cross(input_floor_xyz[:, 1] - input_floor_xyz[:, 0], input_floor_xyz[:, 2] - input_floor_xyz[:, 0]), axis=1) / 2.0))
    output_area = float(np.sum(np.linalg.norm(np.cross(output_floor_xyz[:, 1] - output_floor_xyz[:, 0], output_floor_xyz[:, 2] - output_floor_xyz[:, 0]), axis=1) / 2.0))
    floor_area_error = abs(input_area - output_area)
    floor_chart_ids = np.asarray(candidate["floor_chart_vertex_indices"], dtype=np.int64)
    floor_chart = np.asarray(candidate["floor_chart_xy_mm"], dtype=np.float64)
    floor_chart_coordinate_match = bool(
        floor_chart.shape == (len(floor_chart_ids), 2)
        and np.array_equal(after_rest[floor_chart_ids, :2], floor_chart)
        and np.all(np.abs(after_rest[floor_chart_ids, 2]) <= 1e-12)
    )
    polygon = after_rest[boundary_ids, :2]
    polygon_theta = np.arctan2(polygon[:, 1], polygon[:, 0])
    polygon = polygon[np.argsort(polygon_theta, kind="stable")]
    # Every floor vertex must be inside/on the exact polygon, and new points
    # must remain on the unchanged physical z=0 surface.
    new_start = len(before_rest)
    new_floor_ids = np.arange(new_start, len(after_rest), dtype=np.int64)
    new_floor_geometry_pass = bool(
        np.all(np.abs(after_rest[new_floor_ids, 2]) <= 1e-12)
        and np.array_equal(after_rest[new_floor_ids], after_relief[new_floor_ids])
        and np.all(np.abs(after_rest[new_floor_ids, 0] ** 2 + after_rest[new_floor_ids, 1] ** 2 - 400.0) > 1e-8)
    )
    inside_polygon_pass = bool(len(floor_chart_ids) > len(boundary_ids) + 1 and floor_chart.shape[1] == 2)
    if not inside_polygon_pass:
        raise ValueError("floor chart omitted remesh vertices")
    for point in floor_chart:
        for i in range(len(polygon)):
            edge = polygon[(i + 1) % len(polygon)] - polygon[i]
            if _cross2(edge, point - polygon[i]) < -1e-8:
                inside_polygon_pass = False
                break
        if not inside_polygon_pass:
            break
    floor_area_match = floor_area_error <= 1e-8
    interface_pass = _interface_cycle_pass(after_rest, boundary_ids, after_faces, floor_face_ids)
    patch_report = _floor_patch_checks(baseline, candidate, cases["field"])
    new_vertex_lineage = _new_vertex_lineage_checks(baseline, local_b, candidate)

    outer_after = _outer_color_error(candidate, cases["field"])
    outer_before = _outer_color_error(local_b, cases["field"])
    outer_finite_color_error_delta = (
        outer_after["finite_outer_color_max_abs_linear_rgb_error"]
        - outer_before["finite_outer_color_max_abs_linear_rgb_error"]
    )
    outer_finite_relief_error_delta_mm = (
        outer_after["finite_outer_relief_max_abs_error_mm"]
        - outer_before["finite_outer_relief_max_abs_error_mm"]
    )
    outer_finite_color_error_unchanged = abs(outer_finite_color_error_delta) <= COLOR_FINITE_SAMPLE_TOL
    outer_finite_relief_error_unchanged = abs(outer_finite_relief_error_delta_mm) <= 1e-12
    outer_face_geometry_equal = bool(
        np.array_equal(after_faces[nonfloor_ids_after][np.isin(after_sources[nonfloor_ids_after], candidate["outer_source_face_ids"])],
                       before_faces[nonfloor_ids_before][np.isin(before_sources[nonfloor_ids_before], local_b["outer_source_face_ids"])])
    )

    topology = _topology(after_relief, after_faces)
    before_quality_q = float(global_metrics_before["minimum_Q"])
    after_quality_q = float(global_metrics_after["minimum_Q"])
    before_quality_ar = float(global_metrics_before["maximum_aspect_longest_edge_over_minimum_altitude"])
    after_quality_ar = float(global_metrics_after["maximum_aspect_longest_edge_over_minimum_altitude"])
    floor_quality_q_improved = float(floor_metrics_after["minimum_Q"]) > float(floor_metrics_before["minimum_Q"])
    floor_quality_ar_improved = float(floor_metrics_after["maximum_aspect_longest_edge_over_minimum_altitude"]) < float(floor_metrics_before["maximum_aspect_longest_edge_over_minimum_altitude"])
    global_quality_q_improved = after_quality_q > before_quality_q
    global_quality_ar_improved = after_quality_ar < before_quality_ar
    targets = {
        "floor_minimum_Q_at_least": 0.35,
        "floor_maximum_aspect_at_most": 5.0,
    }
    target_q_pass = float(floor_metrics_after["minimum_Q"]) >= targets["floor_minimum_Q_at_least"]
    target_ar_pass = float(floor_metrics_after["maximum_aspect_longest_edge_over_minimum_altitude"]) <= targets["floor_maximum_aspect_at_most"]
    legacy_v2_alias_pass = bool(
        int(np.asarray(candidate["lineage_schema_version"]).item()) == 2
        and str(np.asarray(candidate["quarantine_status"]).item()) == "EXPERIMENT_ONLY_NOT_FOR_PRODUCTION"
        and str(np.asarray(candidate["legacy_reader_compatibility"]).item()).startswith("UNKNOWN;")
        and "source_face_ids" not in candidate
        and "face_corner_barycentric_to_source" not in candidate
        and "v2_legacy_single_parent_face_source_ids" in candidate
        and "v2_legacy_single_parent_face_corner_barycentric_to_source" in candidate
        and np.count_nonzero(np.asarray(candidate["face_lineage_status"]) == 2) > 0
    )
    patch_lineage_pass = bool(
        patch_report["floor_source_declaration_matches_frozen_fan"]
        and patch_report["source_barycentric_simplex_pass"]
        and patch_report["output_barycentric_simplex_pass"]
        and patch_report["source_chart_reconstruction_max_residual_mm"] <= 1e-9
        and patch_report["output_chart_reconstruction_max_residual_mm"] <= 1e-9
        and patch_report["patch_area_coverage_max_residual_mm2"] <= 1e-9
        and patch_report["patch_pairwise_overlap_max_area_mm2"] <= 1e-10
        and patch_report["per_output_face_patch_cap_pass"]
        and patch_report["floor_vertex_color_max_abs_linear_rgb_error"] <= 1e-12
        and patch_report["floor_vertex_color_max_abs_srgb_error"] <= 1e-12
        and patch_report["patch_vertex_color_max_abs_linear_rgb_error"] <= 1e-12
        and patch_report["patch_vertex_color_max_abs_srgb_error"] <= 1e-12
    )
    floor_color_vertex_match = bool(
        patch_report["floor_vertex_color_max_abs_linear_rgb_error"] <= 1e-12
        and patch_report["floor_vertex_color_max_abs_srgb_error"] <= 1e-12
    )
    outer_color_corner_match = bool(outer_after["per_corner_color_max_abs_linear_rgb_error"] <= 1e-12)
    outer_finite_field_match = bool(outer_finite_color_error_unchanged and outer_finite_relief_error_unchanged)
    topology_pass = bool(
        topology["boundary_edge_count"] == 0
        and topology["non_two_incidence_edge_count"] == 0
        and topology["inconsistent_winding_edge_count"] == 0
        and topology["duplicate_face_count_unoriented"] == 0
        and topology["repeated_vertex_face_count"] == 0
        and topology["zero_area_face_count_threshold_1e-12_mm2"] == 0
        and topology["connected_component_count"] == 1
        and topology["euler_characteristic"] == 2
        and topology["positive_signed_volume"]
    )
    checks = {
        "candidate_id": "global_mesh_quality_candidate_20261005",
        "schema": "isolated_global_mesh_quality_candidate_v2_multi_parent_floor_patches",
        "quarantine_status": str(np.asarray(candidate["quarantine_status"]).item()),
        "legacy_reader_compatibility": str(np.asarray(candidate["legacy_reader_compatibility"]).item()),
        "interpretation": "actual displaced geometric triangle metrics only; no tetrahedron quality, mechanics, fracture h, material calibration, or fragment match claim",
        "source_surface_id": str(np.asarray(candidate["floor_surface_id"]).item()),
        "input_counts": {"vertices": int(len(before_rest)), "faces": int(len(before_faces))},
        "candidate_counts": {"vertices": int(len(after_rest)), "faces": int(len(after_faces))},
        "floor_polygon_area_input_mm2": input_area,
        "floor_polygon_area_candidate_mm2": output_area,
        "floor_polygon_area_abs_difference_mm2": floor_area_error,
        "input_global_quality": global_metrics_before,
        "candidate_global_quality": global_metrics_after,
        "input_floor_quality": floor_metrics_before,
        "candidate_floor_quality": floor_metrics_after,
        "candidate_nonfloor_quality": nonfloor_metrics_after,
        "outer_field_samples_candidate": outer_after,
        "outer_field_samples_input_local_b": outer_before,
        "outer_finite_sample_error_difference_from_input": {
            "linear_rgb_max_abs_error_delta": float(outer_finite_color_error_delta),
            "relief_max_abs_error_delta_mm": float(outer_finite_relief_error_delta_mm),
            "color_error_unchanged_pass": bool(outer_finite_color_error_unchanged),
            "relief_error_unchanged_pass": bool(outer_finite_relief_error_unchanged),
        },
        "floor_patch_lineage": patch_report,
        "new_vertex_lineage": new_vertex_lineage,
        "topology": topology,
        "preservation": {
            "local_b_vertex_rest_prefix_equal": original_vertex_prefix_rest_equal,
            "local_b_vertex_relief_prefix_equal": original_vertex_prefix_relief_equal,
            "run02_baseline_rest_prefix_equal": baseline_prefix_rest_equal,
            "run02_baseline_relief_prefix_equal": baseline_prefix_relief_equal,
            "preserved_outer_arrays_equal": preserved_array_equal,
            "all_preserved_outer_arrays_equal": bool(all(preserved_array_equal.values())),
            "all_nonfloor_faces_connectivity_equal": nonfloor_face_connectivity_equal,
            "all_nonfloor_face_source_ids_equal": nonfloor_source_ids_equal,
            "all_nonfloor_face_barycentric_rows_equal": nonfloor_face_bary_equal,
            "outer_face_connectivity_equal": outer_face_geometry_equal,
            "new_floor_vertices_remain_planar_and_unrelieved": new_floor_geometry_pass,
            "floor_chart_matches_saved_vertex_coordinates": floor_chart_coordinate_match,
            "floor_chart_points_inside_same_polygon": bool(inside_polygon_pass),
            "floor_boundary_interface_cycle_preserved": bool(interface_pass),
            "floor_polygon_area_preserved": bool(floor_area_match),
            "schema_v2_quarantine_and_legacy_alias_pass": legacy_v2_alias_pass,
        },
        "review_targets": {
            **targets,
            "floor_Q_improved_over_input": bool(floor_quality_q_improved),
            "floor_aspect_improved_over_input": bool(floor_quality_ar_improved),
            "global_minimum_Q_improved_over_input": bool(global_quality_q_improved),
            "global_maximum_aspect_improved_over_input": bool(global_quality_ar_improved),
            "floor_Q_target_pass": bool(target_q_pass),
            "floor_aspect_target_pass": bool(target_ar_pass),
        },
    }
    required = [
        original_vertex_prefix_rest_equal,
        original_vertex_prefix_relief_equal,
        baseline_prefix_rest_equal,
        baseline_prefix_relief_equal,
        all(preserved_array_equal.values()),
        nonfloor_face_connectivity_equal,
        nonfloor_source_ids_equal,
        nonfloor_face_bary_equal,
        outer_face_geometry_equal,
        new_floor_geometry_pass,
        floor_chart_coordinate_match,
        inside_polygon_pass,
        interface_pass,
        floor_area_match,
        legacy_v2_alias_pass,
        patch_lineage_pass,
        new_vertex_lineage["all_new_vertices_reconstructed"],
        floor_color_vertex_match,
        outer_color_corner_match,
        outer_finite_field_match,
        topology_pass,
        floor_quality_q_improved,
        floor_quality_ar_improved,
        global_quality_q_improved,
        global_quality_ar_improved,
        target_q_pass,
        target_ar_pass,
        len(after_faces) <= 45000,
        len(after_rest) - len(before_rest) <= 2500,
    ]
    checks["focused_checks_pass"] = bool(all(required))
    checks["focused_check_count"] = int(len(required))
    checks["focused_check_pass_count"] = int(sum(bool(item) for item in required))
    checks["recorded_local_b_checks_sha256"] = "4e4c08b96bd6e7dd47a3285377979fc93fc3865a0bc1fcdd48d79397c23e14e8"
    checks["local_b_recorded_run_gate"] = local_b_checks.get("run_status", "UNKNOWN")
    return checks


def render_saved_meshes(candidate: dict[str, np.ndarray], output_dir: Path, cases: dict[str, Any]) -> None:
    """Render flat saved coordinates with physical equal-axis scaling."""
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    xyz = np.asarray(candidate["vertices_relief_xyz_mm"], dtype=np.float64)
    rest = np.asarray(candidate["vertices_rest_xyz_mm"], dtype=np.float64)
    faces = np.asarray(candidate["faces"], dtype=np.int64)
    source_ids = _saved_face_source_ids(candidate)
    outer_sources = set(np.asarray(candidate["outer_source_face_ids"], dtype=np.int64).tolist())
    outer_vertex_ids = np.asarray(candidate["outer_vertex_indices"], dtype=np.int64)
    outer_colors = np.asarray(candidate["outer_color_srgb_for_display"], dtype=np.float64)
    color_by_vertex = {int(vertex): outer_colors[index] for index, vertex in enumerate(outer_vertex_ids)}
    base_srgb = np.asarray(candidate["outer_base_srgb"], dtype=np.float64)[0]
    face_colors = np.tile(np.r_[base_srgb, 1.0], (len(faces), 1))
    outer_mask = np.fromiter((int(sid) in outer_sources for sid in source_ids), dtype=bool, count=len(source_ids))
    for face_id in np.flatnonzero(outer_mask):
        face_colors[face_id, :3] = np.mean([color_by_vertex[int(v)] for v in faces[face_id]], axis=0)

    figure = plt.figure(figsize=(10.2, 8.0), constrained_layout=True)
    axis = figure.add_subplot(111, projection="3d")
    collection = Poly3DCollection(
        xyz[faces], facecolors=face_colors, edgecolors=(0.15, 0.12, 0.09, 0.16), linewidths=0.045
    )
    axis.add_collection3d(collection)
    lower = xyz.min(axis=0)
    upper = xyz.max(axis=0)
    span = np.maximum(upper - lower, 1e-9)
    padding = np.maximum(span * 0.035, 0.2)
    axis.set_xlim(lower[0] - padding[0], upper[0] + padding[0])
    axis.set_ylim(lower[1] - padding[1], upper[1] + padding[1])
    axis.set_zlim(lower[2] - padding[2], upper[2] + padding[2])
    axis.set_box_aspect(span + 2.0 * padding)
    axis.set_proj_type("ortho")
    axis.view_init(elev=21, azim=34)
    axis.set_xlabel("x (mm)")
    axis.set_ylabel("y (mm)")
    axis.set_zlabel("z (mm)")
    axis.set_title("Saved displaced mesh | flat triangles | equal physical axis units")
    figure.suptitle("Analytic R20 H24 wall3 floor2 fixture | triangle quality is geometric only")
    figure.savefig(output_dir / "global_equal_aspect_actual_mesh.png", dpi=170)
    plt.close(figure)

    floor_ids = np.asarray(candidate["floor_output_face_ids"], dtype=np.int64)
    floor_polygons = rest[faces[floor_ids], :2]
    floor_xy = rest[np.asarray(candidate["floor_chart_vertex_indices"], dtype=np.int64), :2]
    floor_lo = floor_xy.min(axis=0)
    floor_hi = floor_xy.max(axis=0)
    floor_span = np.maximum(floor_hi - floor_lo, 1e-9)
    floor_pad = 0.05 * floor_span
    fig, ax = plt.subplots(figsize=(8.2, 8.2), constrained_layout=True)
    collection2d = PolyCollection(
        floor_polygons,
        facecolors=np.tile(base_srgb[None, :], (len(floor_polygons), 1)),
        edgecolors=(0.16, 0.13, 0.10, 0.8),
        linewidths=0.16,
    )
    ax.add_collection(collection2d)
    ax.set_xlim(floor_lo[0] - floor_pad[0], floor_hi[0] + floor_pad[0])
    ax.set_ylim(floor_lo[1] - floor_pad[1], floor_hi[1] + floor_pad[1])
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_title("Saved bottom exterior z=0 triangles | exact polygon boundary | equal aspect")
    fig.savefig(output_dir / "floor_equal_aspect_actual_mesh.png", dpi=190)
    plt.close(fig)
