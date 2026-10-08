from __future__ import annotations
import hashlib, json, math
from pathlib import Path
import numpy as np

ROOT = Path(r'C:\Users\xiemo\Desktop\ShardForge')
OUT = ROOT / 'vesselforge/tmp/review_20261005/ornament_independent_review'
RUN = ROOT / 'vesselforge/tmp/review_20261005/ornament_resume/local_refinement_run'
BASE_PATH = ROOT / 'vesselforge/tmp/review_20261004/surface_ornament_route/run02/fixture_arrays.npz'
SOURCE_PATH = ROOT / 'vesselforge/experiments/surface_ornament_refinement_20261005/refinement_prototype.py'
EXPECTED_BASE_SHA = 'b44bb78176e690d8bc92ab2fc10f0803e142a0311acee8ff3944d4e324b9b974'


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def wrapped_delta(a: np.ndarray | float, b: np.ndarray | float) -> np.ndarray | float:
    return (np.asarray(a) - np.asarray(b) + math.pi) % (2.0 * math.pi) - math.pi


def stats(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=np.float64)
    return {
        'count': int(x.size),
        'finite': bool(np.isfinite(x).all()),
        'max_mm_or_value': float(np.max(x)) if x.size else None,
        'p95_mm_or_value': float(np.percentile(x, 95)) if x.size else None,
        'p99_mm_or_value': float(np.percentile(x, 99)) if x.size else None,
        'rms_mm_or_value': float(np.sqrt(np.mean(x * x))) if x.size else None,
    }


def tri_metrics(points: np.ndarray) -> dict[str, np.ndarray]:
    e01 = points[:, 1] - points[:, 0]
    e12 = points[:, 2] - points[:, 1]
    e20 = points[:, 0] - points[:, 2]
    edges = np.stack([np.linalg.norm(e01, axis=1), np.linalg.norm(e12, axis=1), np.linalg.norm(e20, axis=1)], axis=1)
    area = 0.5 * np.linalg.norm(np.cross(e01, points[:, 2] - points[:, 0]), axis=1)
    longest = edges.max(axis=1)
    min_altitude = 2.0 * area / np.maximum(longest, 1e-300)
    quality = 4.0 * math.sqrt(3.0) * area / np.maximum(np.sum(edges * edges, axis=1), 1e-300)
    aspect = longest / np.maximum(min_altitude, 1e-300)
    return {'edges': edges, 'area': area, 'longest': longest, 'min_altitude': min_altitude, 'quality': quality, 'aspect': aspect}


def chart_tri_metrics(theta_tri: np.ndarray, z_tri: np.ndarray, radius: float) -> dict[str, np.ndarray]:
    # Unwrap each triangle around its first source corner; seam branch choices then cancel modulo 2pi.
    d1 = wrapped_delta(theta_tri[:, 1], theta_tri[:, 0])
    d2 = wrapped_delta(theta_tri[:, 2], theta_tri[:, 0])
    points = np.empty((len(theta_tri), 3, 2), dtype=np.float64)
    points[:, 0, :] = np.column_stack([np.zeros(len(theta_tri)), z_tri[:, 0]])
    points[:, 1, :] = np.column_stack([radius * d1, z_tri[:, 1]])
    points[:, 2, :] = np.column_stack([radius * d2, z_tri[:, 2]])
    e01 = points[:, 1] - points[:, 0]
    e12 = points[:, 2] - points[:, 1]
    e20 = points[:, 0] - points[:, 2]
    edges = np.stack([np.linalg.norm(e01, axis=1), np.linalg.norm(e12, axis=1), np.linalg.norm(e20, axis=1)], axis=1)
    e02 = points[:, 2] - points[:, 0]
    area = 0.5 * np.abs(e01[:, 0] * e02[:, 1] - e01[:, 1] * e02[:, 0])
    longest = edges.max(axis=1)
    min_altitude = 2.0 * area / np.maximum(longest, 1e-300)
    quality = 4.0 * math.sqrt(3.0) * area / np.maximum(np.sum(edges * edges, axis=1), 1e-300)
    aspect = longest / np.maximum(min_altitude, 1e-300)
    return {'edges': edges, 'area': area, 'longest': longest, 'min_altitude': min_altitude, 'quality': quality, 'aspect': aspect}


def summarize_metric_group(indices: np.ndarray, face_ids: np.ndarray, faces: np.ndarray, values: dict[str, np.ndarray], label: str) -> dict:
    if indices.size == 0:
        return {'triangle_count': 0, 'status': 'NO_TRIANGLES'}
    q_idx = int(indices[np.argmin(values['quality'][indices])])
    alt_idx = int(indices[np.argmin(values['min_altitude'][indices])])
    ar_idx = int(indices[np.argmax(values['aspect'][indices])])
    def row(idx: int) -> dict:
        return {
            'candidate_face_index': idx,
            'source_face_id': int(face_ids[idx]),
            'candidate_vertex_indices': [int(v) for v in faces[idx]],
            'edge_lengths_mm': [float(v) for v in values['edges'][idx]],
            'area_mm2': float(values['area'][idx]),
            'minimum_altitude_mm': float(values['min_altitude'][idx]),
            'quality_Q': float(values['quality'][idx]),
            'aspect_longest_edge_over_min_altitude': float(values['aspect'][idx]),
        }
    return {
        'triangle_count': int(indices.size),
        'quality_Q_min': float(values['quality'][q_idx]),
        'worst_quality_triangle': row(q_idx),
        'minimum_altitude_mm': float(values['min_altitude'][alt_idx]),
        'worst_altitude_triangle': row(alt_idx),
        'aspect_longest_edge_over_min_altitude_max': float(values['aspect'][ar_idx]),
        'worst_aspect_triangle': row(ar_idx),
    }


def load_case(case_id: str, base: dict[str, np.ndarray]) -> dict:
    npz_path = RUN / case_id / 'candidate_arrays.npz'
    checks_path = RUN / case_id / 'checks.json'
    with np.load(npz_path, allow_pickle=False) as d:
        c = {key: d[key].copy() for key in d.files}
    checks = json.loads(checks_path.read_text(encoding='utf-8-sig'))

    b_rest = np.asarray(base['vertices_rest_xyz_mm'], dtype=np.float64)
    b_faces = np.asarray(base['faces'], dtype=np.int64)
    b_outer = np.asarray(base['outer_side_vertex_indices'], dtype=np.int64)
    b_inner = np.asarray(base['inner_side_vertex_indices'], dtype=np.int64)
    b_theta_outer = np.asarray(base['outer_side_theta_rad'], dtype=np.float64)
    b_z_outer = np.asarray(base['outer_side_z_mm'], dtype=np.float64)
    b_inner_radius = float(base['inner_radius_mm'])
    b_outer_radius = float(base['outer_radius_mm'])

    rest = np.asarray(c['vertices_rest_xyz_mm'], dtype=np.float64)
    relief_xyz = np.asarray(c['vertices_relief_xyz_mm'], dtype=np.float64)
    faces = np.asarray(c['faces'], dtype=np.int64)
    face_ids = np.asarray(c['source_face_ids'], dtype=np.int64)
    corner_bary = np.asarray(c['face_corner_barycentric_to_source'], dtype=np.float64)
    vline_face = np.asarray(c['vertex_lineage_source_face_id'], dtype=np.int64)
    vline_bary = np.asarray(c['vertex_lineage_barycentric'], dtype=np.float64)
    original_vertex_count = int(c['original_vertex_count'])
    original_face_count = int(c['original_face_count'])
    outer_idx = np.asarray(c['outer_vertex_indices'], dtype=np.int64)
    outer_theta = np.asarray(c['outer_theta_rad'], dtype=np.float64)
    outer_z = np.asarray(c['outer_z_mm'], dtype=np.float64)
    outer_h = np.asarray(c['outer_relief_height_mm'], dtype=np.float64)
    outer_src = np.asarray(c['outer_source_face_ids'], dtype=np.int64)

    # Confirm scalar and source face relationships before reconstruction.
    stored_base_hash = str(np.asarray(c['baseline_fixture_arrays_sha256']).item())
    source_count_ok = len(b_rest) == original_vertex_count and len(b_faces) == original_face_count
    outer_map = np.full(len(rest), -1, dtype=np.int64)
    outer_map[outer_idx] = np.arange(len(outer_idx), dtype=np.int64)
    outer_src_set = set(map(int, outer_src))
    b_outer_set, b_inner_set = set(map(int, b_outer)), set(map(int, b_inner))
    source_kind = np.empty(len(b_faces), dtype='<U5')
    for fi, tri in enumerate(b_faces):
        vv = set(map(int, tri))
        if vv.issubset(b_outer_set):
            source_kind[fi] = 'outer'
        elif vv.issubset(b_inner_set):
            source_kind[fi] = 'inner'
        else:
            source_kind[fi] = 'base'
    expected_outer_source = set(np.flatnonzero(source_kind == 'outer').tolist())

    # Base surface charts by vertex. Outer chart values are authoritative arrays; inner theta/z derive from exact cylinder coordinates.
    base_outer_theta_by_v = np.full(len(b_rest), np.nan, dtype=np.float64)
    base_outer_z_by_v = np.full(len(b_rest), np.nan, dtype=np.float64)
    base_outer_theta_by_v[b_outer] = b_theta_outer
    base_outer_z_by_v[b_outer] = b_z_outer
    cand_outer_theta_by_v = np.full(len(rest), np.nan, dtype=np.float64)
    cand_outer_z_by_v = np.full(len(rest), np.nan, dtype=np.float64)
    cand_outer_h_by_v = np.full(len(rest), np.nan, dtype=np.float64)
    cand_outer_theta_by_v[outer_idx] = outer_theta
    cand_outer_z_by_v[outer_idx] = outer_z
    cand_outer_h_by_v[outer_idx] = outer_h

    # Reconstruct one target chart/space point from parent face barycentrics; compare using the correct surface parameterization.
    def residual_for(src_id: int, bary: np.ndarray, cand_vertex: int) -> tuple[str, float, bool]:
        tri = b_faces[src_id].astype(np.int64)
        kind = str(source_kind[src_id])
        if kind == 'outer':
            source_theta = base_outer_theta_by_v[tri]
            source_z = base_outer_z_by_v[tri]
            if not np.isfinite(source_theta).all() or not np.isfinite(source_z).all() or outer_map[cand_vertex] < 0:
                return kind, float('nan'), False
            unwrapped = source_theta[0] + wrapped_delta(source_theta, source_theta[0])
            expected_theta = float(np.dot(bary, unwrapped))
            expected_z = float(np.dot(bary, source_z))
            actual_theta = float(cand_outer_theta_by_v[cand_vertex])
            actual_z = float(cand_outer_z_by_v[cand_vertex])
            dtheta = float(wrapped_delta(actual_theta, expected_theta))
            return kind, math.hypot(b_outer_radius * dtheta, actual_z - expected_z), True
        if kind == 'inner':
            source_xyz = b_rest[tri]
            source_theta = np.arctan2(source_xyz[:, 1], source_xyz[:, 0])
            source_z = source_xyz[:, 2]
            unwrapped = source_theta[0] + wrapped_delta(source_theta, source_theta[0])
            expected_theta = float(np.dot(bary, unwrapped))
            expected_z = float(np.dot(bary, source_z))
            xyz = rest[cand_vertex]
            actual_theta = math.atan2(float(xyz[1]), float(xyz[0]))
            dtheta = float(wrapped_delta(actual_theta, expected_theta))
            return kind, math.hypot(b_inner_radius * dtheta, float(xyz[2] - expected_z)), True
        expected_xyz = np.dot(bary, b_rest[tri])
        residual = float(np.linalg.norm(rest[cand_vertex] - expected_xyz))
        return kind, residual, True

    source_id_range_ok = bool(face_ids.min() >= 0 and face_ids.max() < len(b_faces))
    source_outer_set_ok = set(map(int, outer_src)) == expected_outer_source
    face_residuals: dict[str, list[float]] = {'outer': [], 'inner': [], 'base': []}
    face_bad = 0
    bary_sums = np.sum(corner_bary, axis=2)
    face_bary_simplex = bool(np.isfinite(corner_bary).all() and corner_bary.min() >= -1e-12 and corner_bary.max() <= 1.0 + 1e-12 and np.max(np.abs(bary_sums - 1.0)) <= 1e-12)
    face_corner_count_by_kind = {'outer': 0, 'inner': 0, 'base': 0}
    for fi, tri in enumerate(faces):
        src_id = int(face_ids[fi])
        for corner, cand_vertex in enumerate(tri):
            kind, residual, ok = residual_for(src_id, corner_bary[fi, corner], int(cand_vertex))
            face_corner_count_by_kind[kind] += 1
            if not ok or not math.isfinite(residual):
                face_bad += 1
            else:
                face_residuals[kind].append(residual)

    new_vertex_indices = np.arange(original_vertex_count, len(rest), dtype=np.int64)
    vertex_residuals: dict[str, list[float]] = {'outer': [], 'inner': [], 'base': []}
    vertex_bad = 0
    vertex_id_range_ok = bool(np.all((vline_face[new_vertex_indices] >= 0) & (vline_face[new_vertex_indices] < len(b_faces))))
    vertex_bary_sums = vline_bary[new_vertex_indices].sum(axis=1)
    vertex_bary_simplex = bool(vline_bary[new_vertex_indices].size == 0 or (np.isfinite(vline_bary[new_vertex_indices]).all() and vline_bary[new_vertex_indices].min() >= -1e-12 and vline_bary[new_vertex_indices].max() <= 1.0 + 1e-12 and np.max(np.abs(vertex_bary_sums - 1.0)) <= 1e-12))
    vertex_kind_counts = {'outer': 0, 'inner': 0, 'base': 0}
    for vi in new_vertex_indices:
        src_id = int(vline_face[vi])
        kind, residual, ok = residual_for(src_id, vline_bary[vi], int(vi))
        vertex_kind_counts[kind] += 1
        if not ok or not math.isfinite(residual):
            vertex_bad += 1
        else:
            vertex_residuals[kind].append(residual)

    # Exact preservation checks for the original prefix and baseline colors.
    original_rest_equal = bool(np.array_equal(rest[:original_vertex_count], b_rest))
    original_relief_equal = bool(np.array_equal(relief_xyz[:original_vertex_count], np.asarray(base['vertices_relief_xyz_mm'], dtype=np.float64)))
    original_baseline_outer_h_equal = bool(np.array_equal(outer_h[outer_map[b_outer]], np.asarray(base['outer_relief_height_mm'], dtype=np.float64)))
    outer_base_linear_equal = bool(np.array_equal(np.asarray(c['outer_base_linear_rgb']), np.asarray(base['outer_color_linear_rgb'])))
    outer_base_srgb_equal = bool(np.array_equal(np.asarray(c['outer_base_srgb']), np.asarray(base['outer_color_srgb_for_display'])))
    original_outer_color_linear_equal = bool(np.array_equal(np.asarray(c['outer_color_linear_rgb'])[outer_map[b_outer]], np.asarray(base['outer_color_linear_rgb'])))
    original_outer_color_srgb_equal = bool(np.array_equal(np.asarray(c['outer_color_srgb_for_display'])[outer_map[b_outer]], np.asarray(base['outer_color_srgb_for_display'])))
    original_outer_color_linear_diff = np.abs(np.asarray(c['outer_color_linear_rgb'])[outer_map[b_outer]] - np.asarray(base['outer_color_linear_rgb']))
    original_outer_color_srgb_diff = np.abs(np.asarray(c['outer_color_srgb_for_display'])[outer_map[b_outer]] - np.asarray(base['outer_color_srgb_for_display']))

    # Triangle group partition from exact saved h nodal values; charted cylinders use geodesic arc-length coordinates.
    tri_3d = tri_metrics(relief_xyz[faces])
    face_kind = source_kind[face_ids]
    group_masks = {name: np.zeros(len(faces), dtype=bool) for name in ['body', 'support', 'transition', 'inner', 'base']}
    face_outer_local = outer_map[faces]
    outer_face = face_kind == 'outer'
    if not np.isin(face_outer_local[outer_face], np.arange(len(outer_idx))).all():
        raise ValueError('outer source face has a candidate corner without saved outer chart data')
    outer_h_tri = cand_outer_h_by_v[faces[outer_face]]
    if not np.isfinite(outer_h_tri).all():
        raise ValueError('outer source faces lack finite saved relief heights')
    h_positive = outer_h_tri > 0.0
    group_masks['body'][outer_face] = ~np.any(h_positive, axis=1)
    group_masks['support'][outer_face] = np.all(h_positive, axis=1)
    group_masks['transition'][outer_face] = np.any(h_positive, axis=1) & ~np.all(h_positive, axis=1)
    group_masks['inner'] = face_kind == 'inner'
    group_masks['base'] = face_kind == 'base'
    partition_ok = bool(np.all(sum(mask.astype(np.int8) for mask in group_masks.values()) == 1))

    all_chart = {}
    theta_by_v = np.full(len(rest), np.nan, dtype=np.float64)
    z_by_v = np.full(len(rest), np.nan, dtype=np.float64)
    theta_by_v[outer_idx] = outer_theta
    z_by_v[outer_idx] = outer_z
    # Derive the inner cylindrical chart directly from original/candidate rest XYZ; no faces there add vertices.
    # All baseline inner vertices are preserved in the original prefix; newly sampled vertices belong to the outer side.
    theta_by_v[b_inner] = np.arctan2(rest[b_inner, 1], rest[b_inner, 0])
    z_by_v[b_inner] = rest[b_inner, 2]
    for side_name, mask_name, radius in [('outer', 'outer', b_outer_radius), ('inner', 'inner', b_inner_radius)]:
        fmask = face_kind == side_name
        idx = np.flatnonzero(fmask)
        theta_tri = theta_by_v[faces[idx]]
        z_tri = z_by_v[faces[idx]]
        if not np.isfinite(theta_tri).all() or not np.isfinite(z_tri).all():
            raise ValueError(f'missing chart coordinate for {side_name} cylinder face')
        all_chart[side_name] = (idx, chart_tri_metrics(theta_tri, z_tri, radius))

    grouped_results = {}
    for group_name, mask in group_masks.items():
        indices = np.flatnonzero(mask)
        grouped_results[group_name] = {
            '3d_displaced_chord_geometry': summarize_metric_group(indices, face_ids, faces, tri_3d, group_name),
        }
    overall_indices = np.arange(len(faces), dtype=np.int64)
    grouped_results['all'] = {'3d_displaced_chord_geometry': summarize_metric_group(overall_indices, face_ids, faces, tri_3d, 'all')}
    for side_name, (side_indices, chart_values) in all_chart.items():
        chart_full = {}
        for metric_name, local_values in chart_values.items():
            full_values = np.full((len(faces),) + local_values.shape[1:], np.nan, dtype=np.float64)
            full_values[side_indices] = local_values
            chart_full[metric_name] = full_values
        side_group = ['body', 'support', 'transition'] if side_name == 'outer' else ['inner']
        for group_name in side_group:
            local_mask = group_masks[group_name][side_indices]
            idx = side_indices[local_mask]
            grouped_results[group_name]['intrinsic_cylinder_chart'] = summarize_metric_group(idx, face_ids, faces, chart_full, group_name)
        if side_name == 'outer':
            grouped_results['outer_all'] = {'intrinsic_cylinder_chart': summarize_metric_group(side_indices, face_ids, faces, chart_full, side_name)}
        else:
            grouped_results['inner']['intrinsic_cylinder_chart_all_side_faces'] = summarize_metric_group(side_indices, face_ids, faces, chart_full, side_name)

    # Keep source and candidate positions for every reported worst face so the high-aspect base fan can be located.
    for group_data in grouped_results.values():
        for metric_data in group_data.values():
            if not isinstance(metric_data, dict) or 'triangle_count' not in metric_data or not metric_data['triangle_count']:
                continue
            for row_key in ['worst_quality_triangle', 'worst_altitude_triangle', 'worst_aspect_triangle']:
                row = metric_data[row_key]
                face_index = int(row['candidate_face_index'])
                source_face = int(row['source_face_id'])
                vertex_ids = faces[face_index]
                row['candidate_vertex_coordinates_rest_xyz_mm'] = rest[vertex_ids].tolist()
                row['candidate_vertex_coordinates_relief_xyz_mm'] = relief_xyz[vertex_ids].tolist()
                row['baseline_source_vertex_indices'] = [int(v) for v in b_faces[source_face]]
                row['baseline_source_vertex_coordinates_rest_xyz_mm'] = b_rest[b_faces[source_face]].tolist()

    # Compare independently recomputed topology/lineage counts with the saved record.
    recorded_topo = checks['checks']['topology']
    report = {
        'case_id': case_id,
        'candidate_sha256': sha256(npz_path),
        'checks_sha256': sha256(checks_path),
        'candidate_baseline_hash_matches_verified_file_sha256': stored_base_hash == EXPECTED_BASE_SHA,
        'original_counts_match_baseline': source_count_ok,
        'outer_source_face_ids_exactly_match_baseline_outer_side_faces': source_outer_set_ok,
        'source_ids_in_baseline_face_range': source_id_range_ok,
        'face_corner_barycentric_simplex_pass': face_bary_simplex,
        'face_corner_lineage_reconstruction': {
            'method': 'source face + saved barycentric weights; outer/inner cylinders compared in locally unwrapped (R*theta,z) chart using periodic angle difference; planar/base faces compared in rest XYZ',
            'reconstructed_corner_count': int(sum(map(len, face_residuals.values()))),
            'unreconstructed_corner_count': int(face_bad),
            'corner_count_by_source_type': face_corner_count_by_kind,
            'residual_mm_by_source_type': {kind: stats(np.asarray(values)) for kind, values in face_residuals.items()},
            'all_corners_reconstructed': face_bad == 0 and sum(map(len, face_residuals.values())) == faces.size,
        },
        'new_vertex_lineage_reconstruction': {
            'new_vertex_count': int(len(new_vertex_indices)),
            'source_face_ids_valid': vertex_id_range_ok,
            'barycentric_simplex_pass': vertex_bary_simplex,
            'max_barycentric_sum_error': float(np.max(np.abs(vertex_bary_sums - 1.0))) if vertex_bary_sums.size else 0.0,
            'reconstructed_vertex_count': int(sum(map(len, vertex_residuals.values()))),
            'unreconstructed_vertex_count': int(vertex_bad),
            'source_type_counts': vertex_kind_counts,
            'residual_mm_by_source_type': {kind: stats(np.asarray(values)) for kind, values in vertex_residuals.items()},
            'all_new_vertices_reconstructed': vertex_bad == 0 and sum(map(len, vertex_residuals.values())) == len(new_vertex_indices),
        },
        'original_prefix_and_color_exactness': {
            'baseline_rest_vertices_array_equal': original_rest_equal,
            'baseline_relief_vertices_array_equal': original_relief_equal,
            'baseline_outer_relief_heights_array_equal_by_vertex_id': original_baseline_outer_h_equal,
            'outer_base_linear_rgb_array_equal': outer_base_linear_equal,
            'outer_base_srgb_array_equal': outer_base_srgb_equal,
            'outer_colors_on_original_vertex_ids_linear_rgb_array_equal': original_outer_color_linear_equal,
            'outer_colors_on_original_vertex_ids_srgb_array_equal': original_outer_color_srgb_equal,
            'outer_colors_on_original_vertex_ids_linear_rgb_max_abs_difference': float(original_outer_color_linear_diff.max()),
            'outer_colors_on_original_vertex_ids_linear_rgb_exact_rows': int(np.all(original_outer_color_linear_diff == 0.0, axis=1).sum()),
            'outer_colors_on_original_vertex_ids_srgb_max_abs_difference': float(original_outer_color_srgb_diff.max()),
            'outer_colors_on_original_vertex_ids_srgb_exact_rows': int(np.all(original_outer_color_srgb_diff == 0.0, axis=1).sum()),
            'recorded_baseline_field_and_color_gate_pass': bool(checks['checks']['baseline_field_and_color_gate_pass']),
            'recorded_baseline_linear_rgb_max_difference': float(checks['checks']['baseline_linear_rgb_max_difference']),
        },
        'triangle_quality_definitions': {
            'quality_Q': '4*sqrt(3)*area/sum(edge_length^2), equilateral = 1',
            'minimum_altitude': '2*area/longest_edge',
            'aspect_ratio': 'longest_edge/minimum_altitude, equilateral = sqrt(4/3) ~1.155',
            '3d_geometry': 'candidate relief vertex coordinates and straight triangle chords; geometric mesh descriptor, not a mechanics or fracture measure',
            'cylinder_chart': 'intrinsic local chart metric with shortest periodic angular deltas and arc length radius*delta_theta, combined with z',
        },
        'triangle_group_definitions': {
            'body': 'outer source face with all three saved outer relief heights exactly zero',
            'support': 'outer source face with all three saved outer relief heights strictly positive',
            'transition': 'outer source face with both zero and positive saved outer relief heights at its corners',
            'inner': 'source face whose three baseline vertices are all in baseline inner_side_vertex_indices',
            'base': 'remaining non-outer and non-inner source faces, including planar rims/floor/caps',
            'outer_classification_complete': True,
            'groups_form_exact_partition': partition_ok,
        },
        'triangle_quality_by_group': grouped_results,
        'recorded_check_reconciliation': {
            'recorded_lineage_reconstruction_pass': checks['checks']['lineage_reconstruction_pass'],
            'recorded_face_chart_max_residual_mm': checks['checks']['face_lineage_chart_max_residual_mm'],
            'recorded_new_vertex_chart_max_residual_mm': checks['checks']['new_vertex_lineage_chart_max_residual_mm'],
            'recorded_baseline_field_and_color_gate_pass': checks['checks']['baseline_field_and_color_gate_pass'],
            'recorded_baseline_linear_rgb_max_difference': checks['checks']['baseline_linear_rgb_max_difference'],
            'prototype_baseline_color_tolerance': 1e-12,
            'prototype_lineage_chart_tolerance_mm': 1e-9,
            'recorded_topology_counts': recorded_topo,
            'finite_geometry_recorded_max_error_mm': checks['checks']['geometry_and_resolution']['geometry_error_mm']['all_probes']['max'],
            'finite_geometry_reference_residual_independently_recomputed': False,
            'finite_geometry_reference_residual_status': 'UNKNOWN_IN_THIS_SUPPLEMENT; baseline/source lineage is now verified, but the prototype analytic field evaluator and its exact geometric probe construction were not re-executed or independently reimplemented',
            'normal_angle_recorded_max_degrees': checks['checks']['geometry_and_resolution']['normal_angle_error_degrees']['all_probes']['max'],
        },
    }
    return report


def residual_summary_text(values_by_kind: dict[str, dict]) -> str:
    parts = []
    for kind, item in values_by_kind.items():
        if item['count']:
            parts.append(f"{kind} {item['max_mm_or_value']:.3e} mm (n={item['count']:,})")
        else:
            parts.append(f"{kind} none (n=0)")
    return '; '.join(parts)

# Verify the frozen baseline file hash before opening the NPZ.
actual_baseline_sha = sha256(BASE_PATH)
if actual_baseline_sha.lower() != EXPECTED_BASE_SHA:
    raise SystemExit(f'baseline SHA mismatch; expected {EXPECTED_BASE_SHA}, found {actual_baseline_sha}')
with np.load(BASE_PATH, allow_pickle=False) as loaded_base:
    baseline = {key: loaded_base[key].copy() for key in loaded_base.files}

cases = [load_case('local_a_0p50mm', baseline), load_case('local_b_0p25mm', baseline)]

input_paths = [BASE_PATH, SOURCE_PATH]
for cid in ['local_a_0p50mm', 'local_b_0p25mm']:
    input_paths.extend([RUN / cid / 'candidate_arrays.npz', RUN / cid / 'checks.json'])
input_paths.append(RUN / 'run_receipt.json')
input_hashes = {str(path.relative_to(ROOT)): {'sha256': sha256(path), 'bytes': path.stat().st_size} for path in input_paths}
(OUT / 'supplement_input_sha256.json').write_text(json.dumps(input_hashes, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

receipt = {
    'status': 'READ_ONLY_SUPPLEMENT_COMPLETE',
    'baseline_file': str(BASE_PATH.relative_to(ROOT)),
    'expected_baseline_sha256': EXPECTED_BASE_SHA,
    'actual_baseline_sha256': actual_baseline_sha,
    'baseline_hash_verified_before_npz_load': True,
    'cases': [c['case_id'] for c in cases],
    'candidate_sha256': {c['case_id']: c['candidate_sha256'] for c in cases},
    'checks_sha256': {c['case_id']: c['checks_sha256'] for c in cases},
    'generated_outputs': ['supplement_report.md', 'supplement_metrics.json', 'supplement_receipt.json', 'supplement_input_sha256.json', 'supplement_artifacts_sha256.json', 'lineage_geometry_supplement.py'],
    'production_source_or_candidate_modified': False,
    'generation_or_cad_run': False,
}
(OUT / 'supplement_receipt.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
(OUT / 'supplement_metrics.json').write_text(json.dumps({'verified_baseline': {'path': str(BASE_PATH.relative_to(ROOT)), 'sha256': actual_baseline_sha, 'arrays': {k: {'shape': list(v.shape), 'dtype': str(v.dtype)} for k, v in baseline.items()}}, 'cases': cases}, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

lines = [
    '# Ornament lineage and whole-mesh quality supplement',
    '',
    f"Frozen baseline SHA-256 was verified before opening its NPZ: `{actual_baseline_sha}`. This equals the authorized hash `{EXPECTED_BASE_SHA}`.",
    '',
    'This supplement reads the frozen baseline fixture, the saved candidate NPZs, and their recorded checks. It uses NumPy calculations only. It does not run the refinement generator or CAD and does not modify production or candidate artifacts.',
    '',
    '## Lineage reconstruction method',
    '',
    'For every candidate face corner, the stored `source_face_ids` selects a baseline triangle and the corresponding row in `face_corner_barycentric_to_source` supplies its barycentric weights. New vertices use `vertex_lineage_source_face_id` and `vertex_lineage_barycentric` the same way. Outer and inner cylinder residuals are computed in each baseline triangle’s locally unwrapped cylindrical chart: unwrap its three source angles around corner zero, interpolate `(theta,z)` with the barycentric weights, compare the candidate angle using the shortest periodic delta, and convert angular residual to millimeters using the appropriate radius. This avoids treating a curved cylinder point as a straight 3D chord interpolation. Remaining planar base/rim faces are reconstructed in rest XYZ.',
    '',
    '## Preservation and lineage results',
    '',
]
for case in cases:
    prefix = case['original_prefix_and_color_exactness']
    lines.extend([
        f"### {case['case_id']}", '',
        f"Original baseline rest and relief vertices are array-equal: `{prefix['baseline_rest_vertices_array_equal']}` / `{prefix['baseline_relief_vertices_array_equal']}`; original outer relief heights are array-equal by vertex ID: `{prefix['baseline_outer_relief_heights_array_equal_by_vertex_id']}`. The frozen `outer_base_linear_rgb` and `outer_base_srgb` arrays are bitwise equal to baseline: `{prefix['outer_base_linear_rgb_array_equal']}` / `{prefix['outer_base_srgb_array_equal']}`. Expanded `outer_color_*` samples mapped to the original outer vertex IDs are NON_BITWISE_EQUAL: maximum absolute differences are {prefix['outer_colors_on_original_vertex_ids_linear_rgb_max_abs_difference']:.3e} linear RGB and {prefix['outer_colors_on_original_vertex_ids_srgb_max_abs_difference']:.3e} sRGB; {prefix['outer_colors_on_original_vertex_ids_linear_rgb_exact_rows']}/3200 linear rows and {prefix['outer_colors_on_original_vertex_ids_srgb_exact_rows']}/3200 sRGB rows are bitwise exact. The recorded linear difference {prefix['recorded_baseline_linear_rgb_max_difference']:.3e} is within the prototype's `BASELINE_COLOR_TOL=1e-12`, and its field/color gate is `{prefix['recorded_baseline_field_and_color_gate_pass']}`. This supports tolerance-level numerical preservation, not byte-for-byte equality of expanded field samples.",
        '',
        f"Face-corner lineage reconstructed {case['face_corner_lineage_reconstruction']['reconstructed_corner_count']:,}/{case['face_corner_lineage_reconstruction']['reconstructed_corner_count'] + case['face_corner_lineage_reconstruction']['unreconstructed_corner_count']:,} corners; all reconstructed: `{case['face_corner_lineage_reconstruction']['all_corners_reconstructed']}`. Maximum residuals by source type: " + residual_summary_text(case['face_corner_lineage_reconstruction']['residual_mm_by_source_type']) + '.',
        '',
        f"New vertex lineage reconstructed {case['new_vertex_lineage_reconstruction']['reconstructed_vertex_count']:,}/{case['new_vertex_lineage_reconstruction']['new_vertex_count']:,} vertices; all reconstructed: `{case['new_vertex_lineage_reconstruction']['all_new_vertices_reconstructed']}`. Maximum residuals by source type: " + residual_summary_text(case['new_vertex_lineage_reconstruction']['residual_mm_by_source_type']) + '.',
        '',
        f"Source IDs, outer parent-face set, face-corner barycentric simplices, and new-vertex barycentric simplices all pass: `{case['source_ids_in_baseline_face_range']}`, `{case['outer_source_face_ids_exactly_match_baseline_outer_side_faces']}`, `{case['face_corner_barycentric_simplex_pass']}`, `{case['new_vertex_lineage_reconstruction']['barycentric_simplex_pass']}`.",
        '',
    ])
    all_geo = case['triangle_quality_by_group']['all']['3d_displaced_chord_geometry']
    q_worst = all_geo['worst_quality_triangle']
    alt_worst = all_geo['worst_altitude_triangle']
    ar_worst = all_geo['worst_aspect_triangle']
    support_geo = case['triangle_quality_by_group']['support']['3d_displaced_chord_geometry']
    transition_geo = case['triangle_quality_by_group']['transition']['3d_displaced_chord_geometry']
    body_geo = case['triangle_quality_by_group']['body']['3d_displaced_chord_geometry']
    lines.extend([
        f"The full-mesh minimum 3D Q and maximum aspect both occur in the planar base fan, source face {q_worst['source_face_id']}: edges {', '.join(f'{v:.6f}' for v in q_worst['edge_lengths_mm'])} mm, Q={q_worst['quality_Q']:.4f}, minimum altitude={q_worst['minimum_altitude_mm']:.6f} mm, aspect={q_worst['aspect_longest_edge_over_min_altitude']:.4f}. This is the radial floor fan from the center vertex to adjacent rim vertices. The full-mesh minimum altitude instead occurs in source face {alt_worst['source_face_id']} at {alt_worst['minimum_altitude_mm']:.6f} mm. Relief support/transition minimum Qs are {support_geo['quality_Q_min']:.4f}/{transition_geo['quality_Q_min']:.4f}, while the unornamented outer body reaches maximum aspect {body_geo['aspect_longest_edge_over_min_altitude_max']:.4f}.",
        '',
        '| region | triangles | min Q | min altitude (mm) | max aspect | Q source | altitude source | aspect source |',
        '|---|---:|---:|---:|---:|---:|---:|---:|',
    ])
    for name in ['all', 'body', 'support', 'transition', 'inner', 'base']:
        block = case['triangle_quality_by_group'][name]['3d_displaced_chord_geometry']
        if block.get('triangle_count', 0) == 0:
            lines.append(f"| {name} | 0 | — | — | — | — | — | — |")
        else:
            lines.append(f"| {name} | {block['triangle_count']:,} | {block['quality_Q_min']:.4f} | {block['minimum_altitude_mm']:.6f} | {block['aspect_longest_edge_over_min_altitude_max']:.4f} | {block['worst_quality_triangle']['source_face_id']} | {block['worst_altitude_triangle']['source_face_id']} | {block['worst_aspect_triangle']['source_face_id']} |")
    lines.extend(['', 'Cylinder groups also have intrinsic chart metrics in `supplement_metrics.json`; 3D values above measure saved relief-mesh chords. Neither metric measures fracture mechanics or validates a physical `h`.', ''])

lines.extend([
    '## Interpretation and limits',
    '',
    'The fan-like view alone did not establish triangle severity. The full-mesh metrics now show that minimum Q=0.0849 and maximum aspect=20.38 are in a planar base radial fan triangle with 20 mm radial edges, a 0.982 mm rim chord, and 0.981 mm minimum altitude. It is high-aspect, but not zero-area; without an owner threshold it cannot be called a pass/fail defect. Relief support and transition triangles have minimum Q about 0.841 and maximum aspect about 2.117 in these runs. The finer candidate’s unornamented outer body reaches aspect about 8.0. These are triangle-shape descriptors; a 20 mm fan chord or triangle quality is not a mechanical relief height `h` or a fracture criterion.',
    '',
    'The recorded finite geometry probe errors remain recorded checks, not independently reproduced analytic-field residuals in this supplement. Reconstructing the saved mesh lineage against the baseline does not by itself reproduce the prototype’s analytic field sampling or certify a global geometry error. Those analytic residuals remain unknown here. The 20 mm radius cylinder and its chord triangle metrics are a synthetic fixture; they do not establish mechanics, material response, real-fragment correspondence, or calibrated relief.',
    '',
    'See `supplement_metrics.json` for full residual distributions, worst-face vertex IDs and edge lengths, chart metrics by region, and the baseline schema. Input hashes and a completion receipt are saved alongside this report.',
    '',
])
(OUT / 'supplement_report.md').write_text('\n'.join(lines), encoding='utf-8')
artifact_names = [
    'supplement_report.md', 'supplement_metrics.json', 'supplement_receipt.json',
    'supplement_input_sha256.json', 'lineage_geometry_supplement.py',
]
artifact_manifest = {name: {'sha256': sha256(OUT / name), 'bytes': (OUT / name).stat().st_size} for name in artifact_names}
(OUT / 'supplement_artifacts_sha256.json').write_text(json.dumps(artifact_manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print(json.dumps(receipt, ensure_ascii=False))
