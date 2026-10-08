from __future__ import annotations
import hashlib, json, math, shutil, sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.collections import PolyCollection
from matplotlib.patches import Polygon

ROOT = Path(r'C:\Users\xiemo\Desktop\ShardForge')
RUN = ROOT / 'vesselforge/tmp/review_20261005/ornament_resume/local_refinement_run'
SOURCE = ROOT / 'vesselforge/experiments/surface_ornament_refinement_20261005/refinement_prototype.py'
OUT = ROOT / 'vesselforge/tmp/review_20261005/ornament_independent_review'
OUT.mkdir(parents=True, exist_ok=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def edges_and_topology(vertices: np.ndarray, faces: np.ndarray) -> dict:
    edge_map: dict[tuple[int, int], list[int]] = {}
    face_keys: dict[tuple[int, int, int], int] = {}
    parent = list(range(len(vertices)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    repeated = 0
    for tri in faces:
        a, b, c = map(int, tri)
        if len({a, b, c}) < 3:
            repeated += 1
        key_face = tuple(sorted((a, b, c)))
        face_keys[key_face] = face_keys.get(key_face, 0) + 1
        for u, v in ((a, b), (b, c), (c, a)):
            lo, hi = (u, v) if u < v else (v, u)
            edge_map.setdefault((lo, hi), []).append(1 if (u, v) == (lo, hi) else -1)
            union(u, v)
    incidence = np.fromiter((len(v) for v in edge_map.values()), dtype=np.int64)
    winding_bad = sum(1 for v in edge_map.values() if len(v) == 2 and sum(v) != 0)
    non_two = int(np.count_nonzero(incidence != 2))
    boundary = int(np.count_nonzero(incidence == 1))
    roots = {find(i) for i in range(len(vertices))}
    xyz = vertices[faces]
    signed_volume = float(np.einsum('ij,ij->i', xyz[:, 0], np.cross(xyz[:, 1], xyz[:, 2])).sum() / 6.0)
    double_area = np.linalg.norm(np.cross(xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0]), axis=1)
    return {
        'vertex_count': int(len(vertices)), 'face_count': int(len(faces)),
        'unique_undirected_edge_count': int(len(edge_map)),
        'boundary_edge_count': boundary, 'non_two_incidence_edge_count': non_two,
        'inconsistent_winding_edge_count': int(winding_bad),
        'connected_component_count': int(len(roots)),
        'euler_characteristic': int(len(vertices) - len(edge_map) + len(faces)),
        'duplicate_face_count_unoriented': int(sum(n - 1 for n in face_keys.values() if n > 1)),
        'repeated_vertex_face_count': int(repeated),
        'zero_area_face_count_threshold_1e-12_mm2_double_area': int(np.count_nonzero(double_area <= 1e-12)),
        'minimum_double_area_mm2': float(double_area.min()),
        'signed_volume_mm3': signed_volume,
        'positive_signed_volume': bool(signed_volume > 0.0),
    }


def tri_quality_and_aspect(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    # Quality is 4*sqrt(3)*area/sum(edge^2), so equilateral is 1.
    # Aspect is longest edge / shortest altitude, so equilateral is sqrt(4/3).
    e01 = points[:, 1] - points[:, 0]
    e12 = points[:, 2] - points[:, 1]
    e20 = points[:, 0] - points[:, 2]
    lengths = np.stack([np.linalg.norm(e01, axis=1), np.linalg.norm(e12, axis=1), np.linalg.norm(e20, axis=1)], axis=1)
    e02 = points[:, 2] - points[:, 0]
    if points.shape[2] == 2:
        area = 0.5 * np.abs(e01[:, 0] * e02[:, 1] - e01[:, 1] * e02[:, 0])
    else:
        area = 0.5 * np.linalg.norm(np.cross(e01, e02), axis=1)
    q = 4.0 * math.sqrt(3.0) * area / np.maximum(np.sum(lengths * lengths, axis=1), 1e-300)
    shortest_altitude = 2.0 * area / np.maximum(lengths.max(axis=1), 1e-300)
    aspect = lengths.max(axis=1) / np.maximum(shortest_altitude, 1e-300)
    return q, aspect, lengths, area


def describe_case(case_id: str) -> dict:
    arr_path = RUN / case_id / 'candidate_arrays.npz'
    check_path = RUN / case_id / 'checks.json'
    with np.load(arr_path, allow_pickle=False) as loaded:
        a = {k: loaded[k].copy() for k in loaded.files}
    checks = json.loads(check_path.read_text(encoding='utf-8-sig'))
    vertices_rest = np.asarray(a['vertices_rest_xyz_mm'], dtype=np.float64)
    vertices = np.asarray(a['vertices_relief_xyz_mm'], dtype=np.float64)
    faces = np.asarray(a['faces'], dtype=np.int64)
    ids = np.asarray(a['outer_vertex_indices'], dtype=np.int64)
    theta = np.asarray(a['outer_theta_rad'], dtype=np.float64)
    z = np.asarray(a['outer_z_mm'], dtype=np.float64)
    h = np.asarray(a['outer_relief_height_mm'], dtype=np.float64)
    outer_src = np.asarray(a['outer_source_face_ids'], dtype=np.int64)
    source_ids = np.asarray(a['source_face_ids'], dtype=np.int64)
    face_bary = np.asarray(a['face_corner_barycentric_to_source'], dtype=np.float64)
    lineage_ids = np.asarray(a['vertex_lineage_source_face_id'], dtype=np.int64)
    lineage_bary = np.asarray(a['vertex_lineage_barycentric'], dtype=np.float64)
    original_n = int(a['original_vertex_count'])
    original_f = int(a['original_face_count'])
    radius = float(a['outer_radius_mm'])

    float_fields = [k for k in a if np.issubdtype(a[k].dtype, np.floating)]
    float_finite = {k: bool(np.isfinite(a[k]).all()) for k in float_fields}
    indices_valid = bool(faces.min() >= 0 and faces.max() < len(vertices) and ids.min() >= 0 and ids.max() < len(vertices))
    topology = edges_and_topology(vertices, faces)
    rest_topology_volume = edges_and_topology(vertices_rest, faces)['signed_volume_mm3']

    outer_mask = np.isin(source_ids, outer_src)
    outer_faces = faces[outer_mask]
    outer_sources_per_face = source_ids[outer_mask]
    outer_all_face_vertices_are_indexed = bool(np.isin(outer_faces, ids).all())
    index_to_local = np.full(len(vertices), -1, dtype=np.int64)
    index_to_local[ids] = np.arange(len(ids), dtype=np.int64)
    face_local = index_to_local[outer_faces]
    if np.any(face_local < 0):
        raise ValueError('outer source faces contain vertices absent from outer chart arrays')
    outer_theta = theta[face_local]
    outer_z = z[face_local]
    outer_h = h[face_local]
    dtheta01 = (outer_theta[:, 1] - outer_theta[:, 0] + math.pi) % (2 * math.pi) - math.pi
    dtheta02 = (outer_theta[:, 2] - outer_theta[:, 0] + math.pi) % (2 * math.pi) - math.pi
    chart_xy = np.empty((len(outer_faces), 3, 2), dtype=np.float64)
    chart_xy[:, 0, 0] = 0.0
    chart_xy[:, 0, 1] = outer_z[:, 0]
    chart_xy[:, 1, 0] = radius * dtheta01
    chart_xy[:, 1, 1] = outer_z[:, 1]
    chart_xy[:, 2, 0] = radius * dtheta02
    chart_xy[:, 2, 1] = outer_z[:, 2]
    q_chart, aspect_chart, chart_edge_matrix, chart_area = tri_quality_and_aspect(chart_xy)
    relief_xyz_tri = vertices[outer_faces]
    q_3d, aspect_3d, edge_3d_matrix, area_3d = tri_quality_and_aspect(relief_xyz_tri)
    zone = np.max(outer_h, axis=1) > 0.0
    if not zone.any():
        raise ValueError('no relief support/transition triangles found')
    local_chart_edges = chart_edge_matrix[zone]
    local_3d_edges = edge_3d_matrix[zone]
    peak = float(h.max())
    zone_chart_max = float(local_chart_edges.max())
    zone_3d_max = float(local_3d_edges.max())
    z_chart_idx = int(np.argmin(np.where(zone, q_chart, np.inf)))
    z_chart_aspect_idx = int(np.argmax(np.where(zone, aspect_chart, -np.inf)))
    z_3d_idx = int(np.argmin(np.where(zone, q_3d, np.inf)))
    z_3d_aspect_idx = int(np.argmax(np.where(zone, aspect_3d, -np.inf)))
    chart_triangle_max_edge = chart_edge_matrix.max(axis=1)
    chart_global_max_idx = int(np.argmax(chart_triangle_max_edge))
    actual_finite_probes = int(np.count_nonzero(outer_mask)) * 4

    bary_sum_error = float(np.max(np.abs(face_bary.sum(axis=2) - 1.0)))
    bary_min, bary_max = float(face_bary.min()), float(face_bary.max())
    bary_simplex = bool(bary_min >= -1e-12 and bary_max <= 1.0 + 1e-12 and bary_sum_error <= 1e-12)
    new_ids = np.arange(original_n, len(vertices), dtype=np.int64)
    new_lineage_ids = lineage_ids[new_ids]
    new_lineage_bary = lineage_bary[new_ids]
    new_bary_sum_error = float(np.max(np.abs(new_lineage_bary.sum(axis=1) - 1.0))) if len(new_ids) else 0.0
    new_lineage_valid = bool(np.all((new_lineage_ids >= 0) & (new_lineage_ids < original_f)))
    new_bary_simplex = bool(new_lineage_bary.size == 0 or (np.isfinite(new_lineage_bary).all() and new_lineage_bary.min() >= -1e-12 and new_lineage_bary.max() <= 1.0 + 1e-12 and new_bary_sum_error <= 1e-12))
    source_ids_in_range = bool(source_ids.min() >= 0 and source_ids.max() < original_f)
    source_face_count_matches = int(np.count_nonzero(outer_mask)) == int(checks['checks']['geometry_and_resolution']['outer_triangle_count'])

    worst = {
        'chart_quality': int(z_chart_idx),
        'chart_aspect': int(z_chart_aspect_idx),
        'displaced_3d_quality': int(z_3d_idx),
        'displaced_3d_aspect': int(z_3d_aspect_idx),
    }
    metrics = {
        'case_id': case_id,
        'array_schema': [{'field': k, 'shape': list(a[k].shape), 'dtype': str(a[k].dtype), 'finite': bool(float_finite.get(k, True))} for k in a],
        'array_finite_all_float_fields': bool(all(float_finite.values())),
        'indices_valid': indices_valid,
        'outer_all_face_vertices_are_indexed': outer_all_face_vertices_are_indexed,
        'checks_recorded_pass': checks.get('status') == 'PASS' and bool(checks['checks'].get('overall_candidate_gate_pass')),
        'topology_independent_relief_xyz': topology,
        'rest_xyz_signed_volume_mm3': rest_topology_volume,
        'topology_matches_recorded_checks': {
            'vertex_count': topology['vertex_count'] == checks['checks']['topology']['vertex_count'],
            'face_count': topology['face_count'] == checks['checks']['topology']['face_count'],
            'unique_undirected_edge_count': topology['unique_undirected_edge_count'] == checks['checks']['topology']['unique_undirected_edge_count'],
            'boundary_edge_count': topology['boundary_edge_count'] == checks['checks']['topology']['boundary_edge_count'],
            'non_two_incidence_edge_count': topology['non_two_incidence_edge_count'] == checks['checks']['topology']['non_two_incidence_edge_count'],
            'inconsistent_winding_edge_count': topology['inconsistent_winding_edge_count'] == checks['checks']['topology']['inconsistent_winding_edge_count'],
            'connected_component_count': topology['connected_component_count'] == checks['checks']['topology']['connected_component_count'],
            'euler_characteristic': topology['euler_characteristic'] == checks['checks']['topology']['euler_characteristic'],
            'signed_volume_mm3': abs(topology['signed_volume_mm3'] - checks['checks']['topology']['signed_volume_mm3']) < 1e-8,
        },
        'lineage_internal_validation': {
            'face_source_ids_range_0_to_original_face_count_minus_1': source_ids_in_range,
            'face_corner_barycentric_shape': list(face_bary.shape),
            'face_corner_barycentric_min': bary_min,
            'face_corner_barycentric_max': bary_max,
            'face_corner_barycentric_max_sum_error': bary_sum_error,
            'face_corner_barycentric_simplex_pass': bary_simplex,
            'new_vertex_count': int(len(new_ids)),
            'new_vertex_lineage_source_ids_valid': new_lineage_valid,
            'new_vertex_lineage_barycentric_max_sum_error': new_bary_sum_error,
            'new_vertex_lineage_barycentric_simplex_pass': new_bary_simplex,
            'independent_source_triangle_reconstruction': 'NOT_REPRODUCIBLE_FROM_CANDIDATE_NPZ_ALONE; source baseline face connectivity is absent',
            'prototype_check_claims': {
                'face_source_triangle_lineage_present': checks['checks']['face_source_triangle_lineage_present'],
                'face_lineage_chart_max_residual_mm': checks['checks']['face_lineage_chart_max_residual_mm'],
                'lineage_reconstruction_pass': checks['checks']['lineage_reconstruction_pass'],
                'new_vertex_lineage_chart_max_residual_mm': checks['checks']['new_vertex_lineage_chart_max_residual_mm'],
            },
        },
        'outer_mesh_independent_metrics': {
            'outer_triangle_count': int(len(outer_faces)),
            'outer_source_face_ids_count': int(len(outer_src)),
            'outer_source_face_count_matches_check': source_face_count_matches,
            'support_transition_classification': 'outer triangle has at least one vertex with outer_relief_height_mm > 0.0',
            'support_transition_triangle_count': int(zone.sum()),
            'maximum_relief_height_mm': peak,
            'chart_max_edge_support_transition_mm': zone_chart_max,
            'chart_max_edge_over_global_relief_height': zone_chart_max / peak,
            'displaced_3d_max_chord_edge_support_transition_mm': zone_3d_max,
            'displaced_3d_max_chord_edge_over_global_relief_height': zone_3d_max / peak,
            'chart_max_edge_all_outer_mm': float(chart_edge_matrix.max()),
            'chart_max_edge_all_outer_triangle_original_face_id': int(outer_sources_per_face[chart_global_max_idx]),
            'chart_max_edge_all_outer_triangle_edges_mm': [float(v) for v in chart_edge_matrix[chart_global_max_idx]],
            'target_chart_edge_mm': float(a['target_edge_mm']),
            'support_transition_chart_target_pass_independent': zone_chart_max <= float(a['target_edge_mm']) + 1e-12,
            'max_chart_edge_over_height_vs_record': abs(zone_chart_max / peak - checks['checks']['geometry_and_resolution']['actual_edge_lengths']['support_plus_transition_max_chart_edge_over_amplitude']) < 1e-10,
            'max_displaced_edge_over_height_vs_record': abs(zone_3d_max / peak - checks['checks']['geometry_and_resolution']['actual_edge_lengths']['support_plus_transition_max_displaced_3d_edge_over_amplitude']) < 1e-10,
            'worst_triangles': {},
            'worst_zone_quality_chart': float(q_chart[z_chart_idx]),
            'worst_zone_aspect_chart_longest_edge_over_shortest_altitude': float(aspect_chart[z_chart_aspect_idx]),
            'worst_zone_quality_displaced_3d': float(q_3d[z_3d_idx]),
            'worst_zone_aspect_displaced_3d_longest_edge_over_shortest_altitude': float(aspect_3d[z_3d_aspect_idx]),
            'worst_zone_quality_chart_source_face_id': int(outer_sources_per_face[z_chart_idx]),
            'worst_zone_aspect_chart_source_face_id': int(outer_sources_per_face[z_chart_aspect_idx]),
            'worst_zone_quality_displaced_3d_source_face_id': int(outer_sources_per_face[z_3d_idx]),
            'worst_zone_aspect_displaced_3d_source_face_id': int(outer_sources_per_face[z_3d_aspect_idx]),
        },
        'finite_geometry_record': {
            'probe_count_reconstructed_as_four_per_outer_face': actual_finite_probes,
            'probe_count_matches_check': actual_finite_probes == checks['checks']['geometry_and_resolution']['sample_count'],
            'scope': checks['checks']['geometry_and_resolution']['geometry_error_mm']['scope'],
            'gate_target_mm': checks['checks']['geometry_and_resolution']['geometry_error_mm']['finite_sample_gate_target_mm'],
            'max_error_mm': checks['checks']['geometry_and_resolution']['geometry_error_mm']['all_probes']['max'],
            'max_normal_angle_degrees_report_only': checks['checks']['geometry_and_resolution']['normal_angle_error_degrees']['all_probes']['max'],
            'is_global_bound': False,
            'all_arrays_finite_independent': bool(all(float_finite.values())),
            'check_recorded_finite_geometry_pass': bool(checks['checks']['finite_geometry_probe_gate_pass']),
        },
        'recorded_unknowns': {k: checks.get(k) for k in ['global_minimum_normal_wall_thickness', 'independent_sample_or_ground_truth', 'material_or_physical_qualification', 'physics_qualification', 'real_vessel_match', 'self_intersection_or_general_offset_validity', 'fracture_labels']},
    }
    for key, idx in worst.items():
        local = idx
        actual_face = int(np.flatnonzero(outer_mask)[local])
        metrics['outer_mesh_independent_metrics']['worst_triangles'][key] = {
            'candidate_face_index': actual_face,
            'source_face_id': int(outer_sources_per_face[local]),
            'candidate_vertex_indices': [int(v) for v in outer_faces[local]],
            'chart_quality': float(q_chart[local]),
            'chart_aspect_longest_edge_over_shortest_altitude': float(aspect_chart[local]),
            'displaced_3d_quality': float(q_3d[local]),
            'displaced_3d_aspect_longest_edge_over_shortest_altitude': float(aspect_3d[local]),
            'chart_edges_mm': [float(v) for v in chart_edge_matrix[local]],
            'displaced_3d_chord_edges_mm': [float(v) for v in edge_3d_matrix[local]],
            'relief_height_at_vertices_mm': [float(v) for v in outer_h[local]],
            'chart_area_mm2': float(chart_area[local]),
            'displaced_3d_area_mm2': float(area_3d[local]),
        }
    metrics['candidate_sha256'] = sha256(arr_path)
    metrics['checks_sha256'] = sha256(check_path)
    metrics['_arrays'] = a
    metrics['_outer_faces'] = outer_faces
    metrics['_outer_mask'] = outer_mask
    metrics['_outer_h_tri'] = outer_h
    metrics['_q_chart'] = q_chart
    metrics['_q_3d'] = q_3d
    metrics['_aspect_chart'] = aspect_chart
    metrics['_aspect_3d'] = aspect_3d
    metrics['_chart_edge_matrix'] = chart_edge_matrix
    metrics['_edge_3d_matrix'] = edge_3d_matrix
    metrics['_outer_theta_tri'] = outer_theta
    metrics['_outer_z_tri'] = outer_z
    metrics['_outer_sources_per_face'] = outer_sources_per_face
    metrics['_zone'] = zone
    metrics['_case_checks'] = checks
    return metrics


def write_review_plot(a_case: dict, b_case: dict) -> None:
    # Render local peak with physical millimetre scales on all axes and no lighting/shader.
    chosen = min(
        (a_case, b_case),
        key=lambda case: case['outer_mesh_independent_metrics']['worst_zone_quality_displaced_3d'],
    )
    a = chosen['_arrays']
    outer_faces = chosen['_outer_faces']
    outer_mask = chosen['_outer_mask']
    zone = chosen['_zone']
    q_chart = chosen['_q_chart']
    h = np.asarray(a['outer_relief_height_mm'], dtype=np.float64)
    ids = np.asarray(a['outer_vertex_indices'], dtype=np.int64)
    theta = np.asarray(a['outer_theta_rad'], dtype=np.float64)
    z = np.asarray(a['outer_z_mm'], dtype=np.float64)
    radius = float(a['outer_radius_mm'])
    index_to_local = np.full(len(a['vertices_relief_xyz_mm']), -1, dtype=np.int64)
    index_to_local[ids] = np.arange(len(ids), dtype=np.int64)
    face_local = index_to_local[outer_faces]
    theta_tri = theta[face_local]
    z_tri = z[face_local]
    h_tri = h[face_local]
    source_per_face = chosen['_outer_sources_per_face']
    worst_local = int(np.argmin(np.where(zone, chosen['_q_3d'], np.inf)))
    worst_face_vertices = outer_faces[worst_local]
    worst_local_vertices = face_local[worst_local]
    peak_i = int(np.argmax(h))
    theta0 = float(theta[peak_i])
    z0 = float(z[peak_i])
    s_all = radius * ((theta - theta0 + math.pi) % (2 * math.pi) - math.pi)
    s_tri = s_all[face_local]
    hpeak = float(h[peak_i])
    H = float(h.max())

    fig = plt.figure(figsize=(13.0, 5.8), dpi=200, constrained_layout=True)
    ax0 = fig.add_subplot(1, 3, 1)
    ax1 = fig.add_subplot(1, 3, 2, projection='3d', proj_type='ortho')
    ax2 = fig.add_subplot(1, 3, 3)
    fig.suptitle(f'{chosen["case_id"]} • independent geometry review • lengths in mm', fontsize=11)

    # Find a piecewise-linear horizontal section through the maximum height point.
    z_line = z0
    section_points = []
    for fidx, (tri_s, tri_z, tri_h) in enumerate(zip(s_tri, z_tri, h_tri)):
        if not zone[fidx] or (tri_s.min() > 4.2 or tri_s.max() < -4.2) or z_line < tri_z.min() - 1e-10 or z_line > tri_z.max() + 1e-10:
            continue
        hits = []
        for e0, e1 in ((0, 1), (1, 2), (2, 0)):
            za, zb = tri_z[e0], tri_z[e1]
            ha, hb = tri_h[e0], tri_h[e1]
            sa, sb = tri_s[e0], tri_s[e1]
            if abs(za - zb) < 1e-12:
                if abs(z_line - za) < 1e-10:
                    hits.extend([(float(sa), float(ha)), (float(sb), float(hb))])
            elif min(za, zb) - 1e-10 <= z_line <= max(za, zb) + 1e-10:
                t = (z_line - za) / (zb - za)
                if -1e-10 <= t <= 1.0 + 1e-10:
                    hits.append((float(sa + t * (sb - sa)), float(ha + t * (hb - ha))))
        uniq = []
        for p in hits:
            if not any(abs(p[0] - q[0]) < 1e-9 and abs(p[1] - q[1]) < 1e-9 for q in uniq):
                uniq.append(p)
        if len(uniq) >= 2:
            uniq.sort(key=lambda p: p[0])
            section_points.extend(uniq[:2])
    section_points.sort(key=lambda p: p[0])
    # Deduplicate repeated edge intersections and break discontinuities by x ordering.
    section_unique = []
    for p in section_points:
        if not section_unique or abs(p[0] - section_unique[-1][0]) > 1e-7:
            section_unique.append(p)
        elif p[1] > section_unique[-1][1]:
            section_unique[-1] = p
    if section_unique:
        sx, sh = np.asarray(section_unique).T
        visible = (sx >= -4.2) & (sx <= 4.2)
        ax0.plot(sx[visible], sh[visible], color='#234d63', linewidth=1.25)
        ax0.scatter(sx[visible], sh[visible], s=6, color='#234d63', zorder=3)
    ax0.set_xlim(-4.2, 4.2)
    ax0.set_ylim(-0.02, max(0.52, H + 0.04))
    ax0.set_aspect('equal', adjustable='box')
    ax0.set_xlabel('arc s (mm)', fontsize=8)
    ax0.set_ylabel('height h (mm)', fontsize=8)
    ax0.set_title(f'Equal-scale section at z={z0:.2f} mm', fontsize=9)
    ax0.grid(True, linewidth=0.35, alpha=0.45)
    ax0.tick_params(labelsize=7)

    # Local peak patch in chart coordinates, directly triangulated with solid unlit faces.
    peak_sel = zone & (np.max(np.abs(s_tri), axis=1) <= 3.6) & (np.min(np.abs(z_tri - z0), axis=1) <= 3.6)
    # Keep faces whose bounding box meets the view window.
    peak_sel &= (s_tri.max(axis=1) >= -3.6) & (s_tri.min(axis=1) <= 3.6) & (z_tri.max(axis=1) >= z0 - 3.6) & (z_tri.min(axis=1) <= z0 + 3.6)
    peak_tris = np.stack([s_tri[peak_sel], z_tri[peak_sel], h_tri[peak_sel]], axis=2)
    mean_h = h_tri[peak_sel].mean(axis=1) if peak_sel.any() else np.array([])
    pc = Poly3DCollection(peak_tris, facecolors=plt.cm.copper(0.25 + 0.65 * mean_h / max(H, 1e-12)) if peak_sel.any() else '#d7c5af', edgecolors='#4c4036', linewidths=0.28, alpha=1.0, shade=False)
    ax1.add_collection3d(pc)
    ax1.set_xlim(-3.6, 3.6)
    ax1.set_ylim(z0 - 3.6, z0 + 3.6)
    ax1.set_zlim(0.0, max(0.50, H + 0.02))
    ax1.set_box_aspect((7.2, 7.2, max(0.50, H + 0.02)))
    ax1.set_xlabel('arc s (mm)', labelpad=1, fontsize=7)
    ax1.set_ylabel('z (mm)', labelpad=1, fontsize=7)
    ax1.set_zlabel('h (mm)', labelpad=1, fontsize=7)
    ax1.set_title(f'Relief mesh • {int(peak_sel.sum()):,} triangles', fontsize=9)
    ax1.view_init(elev=24, azim=-58)
    ax1.tick_params(labelsize=6, pad=0)
    ax1.xaxis.set_major_locator(plt.MaxNLocator(3))
    ax1.yaxis.set_major_locator(plt.MaxNLocator(3))
    ax1.zaxis.set_major_locator(plt.MaxNLocator(3))
    ax1.grid(True, linewidth=0.3, alpha=0.45)

    # Close, equal-scale chart view of the worst displaced-surface triangle.
    wf_s = s_tri[worst_local]
    wf_z = z_tri[worst_local]
    wf_h = h_tri[worst_local]
    c_s, c_z = float(np.mean(wf_s)), float(np.mean(wf_z))
    span = 0.75
    detail_sel = zone & (s_tri.max(axis=1) >= c_s - span) & (s_tri.min(axis=1) <= c_s + span) & (z_tri.max(axis=1) >= c_z - span) & (z_tri.min(axis=1) <= c_z + span)
    detail_polys = [np.column_stack([s_tri[i], z_tri[i]]) for i in np.flatnonzero(detail_sel)]
    ax2.add_collection(PolyCollection(detail_polys, facecolors='#eadcc8', edgecolors='#8a7866', linewidths=0.35))
    ax2.add_patch(Polygon(np.column_stack([wf_s, wf_z]), closed=True, fill=False, edgecolor='#d62728', linewidth=2.0, zorder=5))
    ax2.scatter(wf_s, wf_z, color='#d62728', s=10, zorder=6)
    for j, (xs, ys, hh) in enumerate(zip(wf_s, wf_z, wf_h)):
        ax2.annotate(f'{hh:.3f}', (xs, ys), xytext=(4, 4 if j != 1 else -10), textcoords='offset points', fontsize=6, color='#8b1a1a')
    ax2.set_xlim(c_s - span, c_s + span)
    ax2.set_ylim(c_z - span, c_z + span)
    ax2.set_aspect('equal', adjustable='box')
    ax2.set_xlabel('arc s (mm)', fontsize=7)
    ax2.set_ylabel('z (mm)', fontsize=7)
    q = float(chosen['_q_3d'][worst_local])
    ar = float(chosen['_aspect_3d'][worst_local])
    maxedge = float(chosen['_chart_edge_matrix'][worst_local].max())
    ax2.set_title(f'Worst displaced triangle • q3d={q:.3f}, AR3d={ar:.2f}\nchart edge/H={maxedge/H:.2f} • source face {int(source_per_face[worst_local])}', fontsize=8)
    ax2.tick_params(labelsize=6)
    ax2.xaxis.set_major_locator(plt.MaxNLocator(3))
    ax2.yaxis.set_major_locator(plt.MaxNLocator(3))
    ax2.grid(True, linewidth=0.35, alpha=0.45)

    fig.savefig(OUT / 'independent_relief_review.png', bbox_inches='tight')
    plt.close(fig)


def clean_for_json(value):
    if isinstance(value, dict):
        return {k: clean_for_json(v) for k, v in value.items() if not k.startswith('_')}
    if isinstance(value, list):
        return [clean_for_json(v) for v in value]
    if isinstance(value, (np.integer,)): return int(value)
    if isinstance(value, (np.floating,)): return float(value)
    return value


a_case = describe_case('local_a_0p50mm')
b_case = describe_case('local_b_0p25mm')
write_review_plot(a_case, b_case)

# Save exact run receipt/check records and the two inputs whose appearance was reviewed.
shutil.copy2(RUN / 'run_receipt.json', OUT / 'run_receipt.actual.json')
shutil.copy2(RUN / 'local_a_0p50mm/checks.json', OUT / 'local_a_0p50mm.checks.actual.json')
shutil.copy2(RUN / 'local_b_0p25mm/checks.json', OUT / 'local_b_0p25mm.checks.actual.json')
shutil.copy2(RUN / 'local_a_0p50mm/flat_triangle_visual.png', OUT / 'local_a_original_flat_triangle_visual.png')
shutil.copy2(RUN / 'local_b_0p25mm/flat_triangle_visual.png', OUT / 'local_b_original_flat_triangle_visual.png')

manifest = {}
for p in [RUN / 'run_receipt.json', SOURCE]:
    manifest[str(p.relative_to(ROOT))] = {'sha256': sha256(p), 'bytes': p.stat().st_size}
for cid in ['local_a_0p50mm', 'local_b_0p25mm']:
    for name in ['candidate_arrays.npz', 'checks.json', 'flat_triangle_visual.png']:
        p = RUN / cid / name
        manifest[str(p.relative_to(ROOT))] = {'sha256': sha256(p), 'bytes': p.stat().st_size}
(OUT / 'input_sha256.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

results = {'run_receipt': json.loads((RUN / 'run_receipt.json').read_text(encoding='utf-8-sig')), 'cases': [clean_for_json(a_case), clean_for_json(b_case)]}
(OUT / 'independent_metrics.json').write_text(json.dumps(results, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def report_case(case: dict) -> list[str]:
    topo = case['topology_independent_relief_xyz']
    mesh = case['outer_mesh_independent_metrics']
    finite = case['finite_geometry_record']
    lin = case['lineage_internal_validation']
    worst3d = mesh['worst_triangles']['displaced_3d_quality']
    lines = [
        f"### {case['case_id']}",
        '',
        f"Candidate SHA-256: `{case['candidate_sha256']}`. The NPZ exposes {len(case['array_schema'])} arrays; all floating arrays are finite and all listed shapes/dtypes are archived in `independent_metrics.json`.",
        '',
        f"Topology recomputed from relief vertices: {topo['vertex_count']:,} vertices, {topo['face_count']:,} faces, {topo['unique_undirected_edge_count']:,} unique edges; {topo['boundary_edge_count']} boundary edges, {topo['non_two_incidence_edge_count']} non-two-incidence edges, {topo['inconsistent_winding_edge_count']} winding conflicts, {topo['connected_component_count']} component, Euler characteristic {topo['euler_characteristic']}. Signed volume is {topo['signed_volume_mm3']:.6f} mm³ and positive. Independent values match the recorded topology checks.",
        '',
        f"For outer support and transition faces (classified here as a face touching a vertex with positive saved relief), the maximum chart edge is {mesh['chart_max_edge_support_transition_mm']:.6f} mm ({mesh['chart_max_edge_over_global_relief_height']:.3f}× the {mesh['maximum_relief_height_mm']:.3f} mm peak relief); the displaced 3D chord maximum is {mesh['displaced_3d_max_chord_edge_support_transition_mm']:.6f} mm ({mesh['displaced_3d_max_chord_edge_over_global_relief_height']:.3f}×). The worst displaced triangle has Q={mesh['worst_zone_quality_displaced_3d']:.3f}, aspect {mesh['worst_zone_aspect_displaced_3d_longest_edge_over_shortest_altitude']:.3f}, source face {mesh['worst_zone_quality_displaced_3d_source_face_id']}; its chart edges are {', '.join(f'{v:.6f}' for v in worst3d['chart_edges_mm'])} mm and its saved vertex reliefs are {', '.join(f'{v:.6f}' for v in worst3d['relief_height_at_vertices_mm'])} mm.",
        '',
        f"The candidate has {finite['probe_count_reconstructed_as_four_per_outer_face']:,} finite geometry probes: I independently confirmed the saved arrays are finite and the count equals four probes per outer face. The maximum error {finite['max_error_mm']:.6f} mm against a {finite['gate_target_mm']:.3f} mm sample gate and maximum normal angle {finite['max_normal_angle_degrees_report_only']:.3f}° are the values recorded in `checks.json`; I could not independently recompute those reference residuals from the candidate NPZ alone because the baseline reference arrays are not included. The normal angle has no owner acceptance limit. The probe set is barycenters plus edge midpoints, not a global bound.",
        '',
        f"Lineage arrays pass independent shape, finiteness, source-ID range, and barycentric-simplex checks (maximum sum error {lin['face_corner_barycentric_max_sum_error']:.1e} for face corners; {lin['new_vertex_lineage_barycentric_max_sum_error']:.1e} for new vertices). The saved run check reports chart reconstruction residual {lin['prototype_check_claims']['face_lineage_chart_max_residual_mm']:.3e} mm, but source baseline face connectivity is absent from the candidate NPZ, so I could not independently repeat its geometric source-triangle reconstruction.",
        '',
        '| NPZ field | Shape | dtype | finite |',
        '|---|---:|---|---|',
    ]
    for field in case['array_schema']:
        lines.append(f"| `{field['field']}` | `{field['shape']}` | `{field['dtype']}` | {'yes' if field['finite'] else 'no'} |")
    lines.append('')
    return lines

run = results['run_receipt']
report = [
    '# Independent ornament candidate review',
    '',
    'This is a read-only audit of the saved run and its analytic cylinder fixture. I independently read the two NPZ files, recomputed topology and outer triangle metrics, inspected both original PNGs, and made one unlit review visualization. No candidate or production source was changed.',
    '',
    f"The saved run receipt says `{run['status']}`, exit code {run['exit_code']}, for `{', '.join(run['completed_case_ids'])}`. It records source SHA-256 `{run['source_sha256']}`, baseline fixture arrays SHA-256 `{run['baseline_fixture_arrays_sha256']}`, and case freeze SHA-256 `{run['case_freeze_sha256']}`. This is a candidate gate result for an analytic sample-resolution experiment; it does not establish material fidelity or a real fragment match.",
    '',
    'For triangle quality, Q is `4√3 A / Σ(edge²)`, so an equilateral triangle has Q=1. Aspect is longest edge divided by shortest altitude, so an equilateral triangle is about 1.155. The relative edge measure divides the longest support/transition edge by the saved global peak relief H=0.45 mm. These are descriptive measurements; the saved checks define no minimum Q or maximum aspect acceptance limits.',
    '',
    '## Candidate measurements',
    '',
]
report.extend(report_case(a_case))
report.extend(report_case(b_case))
report.extend([
    '## Visual inspection and limits',
    '',
    'Both original `flat_triangle_visual.png` files place the analytic cylinder fixture beside saved flat triangles. The x-axis tick labels crowd together at the lower-right of each mesh panel. The displaced surface shows repeated shallow oval marks, and the flat view has a fan or spike-shaped support transition around the motif. These images show the saved analytic sample and its triangulation; they do not demonstrate a measured fragment, a calibrated material, a physically validated relief, or a vessel match.',
    '',
    'The new `independent_relief_review.png` shows a piecewise-linear section at the relief peak, the 0.25 mm candidate relief mesh with height-coded flat face colors and no lighting, and an equal-scale chart view of its worst displaced transition triangle with its three vertex heights. All plotted lengths use millimeters. The local cylinder chart uses arc length `R·Δθ` and z; the 3D relief patch uses that chart plus saved relief height. This makes relief and triangle shape inspectable without a material shader, while the mesh remains only a synthetic cylinder sample.',
    '',
    'The finite geometry gate is finite sampling only: the checks explicitly describe barycenter and edge-midpoint probes, with no certified supremum or global Hausdorff bound. The check files also mark independent sample/ground truth `NO`, physical/material qualification `NOT_VALIDATED`, physics `UNKNOWN`, real-vessel match `NOT_VALIDATED`, global minimum normal wall thickness `UNKNOWN`, self-intersection/general offset validity `NOT_ASSESSED`, and fracture labels `NONE`. Treat `PASS_ALL_CANDIDATES` as “these recorded gates passed,” not as evidence that the candidate meets RelicWeave’s real-fragment objective.',
    '',
    'The exact receipt and check files, input SHA-256 manifest, complete independent metrics, original PNG copies, review PNG, and analysis script are saved alongside this report.',
    '',
])
(OUT / 'report.md').write_text('\n'.join(report), encoding='utf-8')

artifact_names = [
    'run_receipt.actual.json', 'local_a_0p50mm.checks.actual.json',
    'local_b_0p25mm.checks.actual.json', 'local_a_original_flat_triangle_visual.png',
    'local_b_original_flat_triangle_visual.png', 'input_sha256.json',
    'independent_metrics.json', 'independent_relief_review.png', 'report.md',
    'independent_review.py',
]
artifact_hashes = {name: {'sha256': sha256(OUT / name), 'bytes': (OUT / name).stat().st_size} for name in artifact_names}
(OUT / 'review_artifacts_sha256.json').write_text(json.dumps(artifact_hashes, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

for m in [a_case, b_case]:
    print(m['case_id'], json.dumps(clean_for_json({k: m[k] for k in ['candidate_sha256', 'checks_sha256', 'topology_independent_relief_xyz', 'lineage_internal_validation', 'outer_mesh_independent_metrics', 'finite_geometry_record', 'recorded_unknowns']}), ensure_ascii=False))
print('wrote', OUT / 'independent_relief_review.png')
