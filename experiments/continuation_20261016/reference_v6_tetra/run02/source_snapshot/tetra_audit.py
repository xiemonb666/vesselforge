"""Independent, NumPy-only topology and quality checks for linear tetra meshes.

Connectivity uses zero-based row indices into ``nodes_m`` and ``tets``.  The
optional interface parent table therefore contains tetrahedron row indices,
not external element tags.
"""
from __future__ import annotations

from collections import defaultdict, deque
from itertools import combinations
from typing import Any

import numpy as np


class MeshAuditError(ValueError):
    """Raised when a tetrahedral mesh violates an audit invariant."""


# Outward-oriented faces of a positively oriented tetrahedron, indexed by the
# opposite vertex.  These orders also let the audit check shared-face winding.
_OUTWARD_FACE_CORNERS = ((1, 2, 3), (0, 3, 2), (0, 1, 3), (0, 2, 1))


def _integer_array(name: str, value: Any, ndim: int) -> np.ndarray:
    array = np.asarray(value)
    if array.ndim != ndim or not np.issubdtype(array.dtype, np.integer):
        raise MeshAuditError(f"{name} must be a {ndim}-D integer array")
    return array.astype(np.int64, copy=False)


def _summary(values: np.ndarray) -> dict[str, float]:
    return {
        "min": float(np.min(values)),
        "median": float(np.median(values)),
        "p95": float(np.percentile(values, 95)),
        "p99": float(np.percentile(values, 99)),
        "max": float(np.max(values)),
    }


def _orientation_parity(oriented: tuple[int, int, int], canonical: tuple[int, int, int]) -> int:
    ranks = [canonical.index(vertex) for vertex in oriented]
    inversions = sum(ranks[i] > ranks[j] for i in range(3) for j in range(i + 1, 3))
    return -1 if inversions % 2 else 1


def _surface_measurements(
    oriented_faces: list[tuple[int, int, int]], nodes: np.ndarray, origin: np.ndarray
) -> dict[str, Any]:
    if not oriented_faces:
        return {
            "faces": 0,
            "vertices": 0,
            "edges": 0,
            "edge_incidence_min": 0,
            "edge_incidence_max": 0,
            "edges_with_incidence_other_than_two": 0,
            "edges_with_inconsistent_direction": 0,
            "vertex_link_issues": 0,
            "connected_components": 0,
            "surface_area_m2": 0.0,
            "signed_volume_m3": 0.0,
            "closed_oriented_vertex_manifold": False,
        }

    edge_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    edge_directions: dict[tuple[int, int], list[int]] = defaultdict(list)
    vertex_links: dict[int, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    for face_index, (a, b, c) in enumerate(oriented_faces):
        for u, v in ((a, b), (b, c), (c, a)):
            edge = (u, v) if u < v else (v, u)
            edge_faces[edge].append(face_index)
            edge_directions[edge].append(1 if (u, v) == edge else -1)
        for vertex, first, second in ((a, b, c), (b, c, a), (c, a, b)):
            vertex_links[vertex][first].append(second)
            vertex_links[vertex][second].append(first)

    incidence = np.fromiter((len(v) for v in edge_faces.values()), dtype=np.int64)
    bad_incidence = int(np.count_nonzero(incidence != 2))
    bad_direction = sum(
        len(directions) == 2 and sum(directions) != 0
        for directions in edge_directions.values()
    )

    vertex_link_issues = 0
    for link in vertex_links.values():
        if len(link) < 3 or any(len(neighbors) != 2 for neighbors in link.values()):
            vertex_link_issues += 1
            continue
        start = next(iter(link))
        visited = {start}
        pending = [start]
        while pending:
            current = pending.pop()
            for neighbor in link[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        if len(visited) != len(link):
            vertex_link_issues += 1

    face_graph: list[set[int]] = [set() for _ in oriented_faces]
    for sharing_faces in edge_faces.values():
        for first, second in combinations(sharing_faces, 2):
            face_graph[first].add(second)
            face_graph[second].add(first)
    components = 0
    unseen = set(range(len(oriented_faces)))
    while unseen:
        components += 1
        start = unseen.pop()
        pending = [start]
        while pending:
            for neighbor in face_graph[pending.pop()]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    pending.append(neighbor)

    triangles = nodes[np.asarray(oriented_faces, dtype=np.int64)]
    area = 0.5 * np.linalg.norm(
        np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1
    )
    shifted = triangles - origin
    signed_volume = np.einsum(
        "ij,ij->i", shifted[:, 0], np.cross(shifted[:, 1], shifted[:, 2])
    ).sum() / 6.0
    closed = bad_incidence == 0 and bad_direction == 0 and vertex_link_issues == 0
    return {
        "faces": len(oriented_faces),
        "vertices": len(vertex_links),
        "edges": len(edge_faces),
        "edge_incidence_min": int(incidence.min()),
        "edge_incidence_max": int(incidence.max()),
        "edges_with_incidence_other_than_two": bad_incidence,
        "edges_with_inconsistent_direction": int(bad_direction),
        "vertex_link_issues": int(vertex_link_issues),
        "connected_components": int(components),
        "surface_area_m2": float(area.sum()),
        "signed_volume_m3": float(signed_volume),
        "closed_oriented_vertex_manifold": bool(closed),
    }


def _point_in_spherical_bowl(
    points: np.ndarray, center: np.ndarray, inner_radius: float, outer_radius: float, tol: float
) -> np.ndarray:
    radii = np.linalg.norm(points - center, axis=1)
    return (
        (radii >= inner_radius - tol)
        & (radii <= outer_radius + tol)
        & (points[:, 2] <= center[2] + tol)
    )


def audit_tetra_mesh(
    nodes_m: Any,
    tets: Any,
    partition: Any,
    interface_triangles: Any | None = None,
    interface_parents: Any | None = None,
    *,
    stored_volume_m3: Any | None = None,
    center_m: Any | None = None,
    inner_radius_m: float | None = None,
    outer_radius_m: float | None = None,
    interface_plane_x_m: float | None = None,
    expected_volume_m3: float | None = None,
    expected_interface_area_m2: float | None = None,
    containment_grid_subdivisions: int = 10,
    require_connected: bool = True,
    require_single_surface_component: bool = True,
    analytic_relative_tolerance: float = 0.01,
) -> dict[str, Any]:
    """Audit tetra topology, orientation, quality, boundaries, and optional bowl geometry.

    This function depends only on NumPy.  It does not infer a continuous CAD
    containment proof from point samples; sampled geometric evidence is kept
    explicitly separate in the returned report.
    """
    xyz = np.asarray(nodes_m, dtype=np.float64)
    cells = _integer_array("tets", tets, 2)
    groups = _integer_array("partition", partition, 1)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or len(xyz) == 0 or not np.isfinite(xyz).all():
        raise MeshAuditError("nodes_m must be a nonempty finite array with shape (N, 3)")
    if cells.shape[1:] != (4,) or len(cells) == 0:
        raise MeshAuditError("tets must be a nonempty integer array with shape (T, 4)")
    if groups.shape != (len(cells),):
        raise MeshAuditError("partition must contain one integer label per tetrahedron")
    if np.any(cells < 0) or np.any(cells >= len(xyz)):
        raise MeshAuditError("tetrahedron connectivity references a missing node")
    if np.any(np.apply_along_axis(lambda row: len(set(row.tolist())), 1, cells) != 4):
        raise MeshAuditError("tetrahedron contains repeated node indices")

    canonical_cells = np.sort(cells, axis=1)
    if len(np.unique(canonical_cells, axis=0)) != len(cells):
        raise MeshAuditError("duplicate tetrahedron detected")
    used_nodes = np.unique(cells)

    points = xyz[cells]
    edge_matrix = np.stack(
        (points[:, 1] - points[:, 0], points[:, 2] - points[:, 0], points[:, 3] - points[:, 0]),
        axis=2,
    )
    determinant = np.linalg.det(edge_matrix)
    if not np.isfinite(determinant).all() or np.any(determinant <= 0.0):
        negative = int(np.count_nonzero(determinant < 0.0))
        zero = int(np.count_nonzero(determinant == 0.0))
        raise MeshAuditError(
            f"tetrahedra must have finite positive orientation (negative={negative}, zero={zero})"
        )
    cell_volumes = determinant / 6.0
    if stored_volume_m3 is not None:
        stored = np.asarray(stored_volume_m3, dtype=np.float64)
        if stored.shape != cell_volumes.shape or not np.isfinite(stored).all():
            raise MeshAuditError("stored_volume_m3 must be a finite value per tetrahedron")
        if not np.allclose(stored, cell_volumes, rtol=5e-12, atol=1e-24):
            raise MeshAuditError("stored tetrahedron volumes disagree with independent determinants")

    # Compute heights to all four opposite faces and a permutation-robust
    # worst-vertex edge-matrix condition number for every cell.
    opposite_face_areas = []
    for opposite in range(4):
        face_points = np.delete(points, opposite, axis=1)
        opposite_face_areas.append(
            0.5
            * np.linalg.norm(
                np.cross(face_points[:, 1] - face_points[:, 0], face_points[:, 2] - face_points[:, 0]),
                axis=1,
            )
        )
    face_areas = np.column_stack(opposite_face_areas)
    if np.any(face_areas <= 0.0) or not np.isfinite(face_areas).all():
        raise MeshAuditError("tetrahedron has a degenerate face")
    altitudes = (3.0 * cell_volumes[:, None]) / face_areas
    condition_by_anchor = []
    for anchor in range(4):
        other_corners = [index for index in range(4) if index != anchor]
        matrix = np.stack(
            [points[:, index] - points[:, anchor] for index in other_corners], axis=2
        )
        condition_by_anchor.append(np.linalg.cond(matrix))
    worst_anchor_condition = np.max(np.stack(condition_by_anchor), axis=0)
    if not np.isfinite(worst_anchor_condition).all():
        raise MeshAuditError("tetrahedron edge matrix has a non-finite condition number")

    face_records: dict[tuple[int, int, int], list[tuple[int, tuple[int, int, int]]]] = defaultdict(list)
    for cell_index, row in enumerate(cells):
        for corners in _OUTWARD_FACE_CORNERS:
            oriented = tuple(int(row[index]) for index in corners)
            canonical = tuple(sorted(oriented))
            face_records[canonical].append((cell_index, oriented))
    face_incidence = np.fromiter((len(records) for records in face_records.values()), dtype=np.int64)
    if np.any(face_incidence > 2):
        bad = int(np.count_nonzero(face_incidence > 2))
        raise MeshAuditError(f"non-manifold tetrahedral face incidence: {bad} face(s) have more than two parents")

    interior_faces = 0
    for canonical, records in face_records.items():
        if len(records) == 2:
            interior_faces += 1
            if _orientation_parity(records[0][1], canonical) == _orientation_parity(records[1][1], canonical):
                raise MeshAuditError("two-parent tetrahedral face orientations do not oppose")

    # Face adjacency checks that the declared mesh is a single connected body.
    cell_neighbors: list[set[int]] = [set() for _ in cells]
    for records in face_records.values():
        if len(records) == 2:
            first, second = records[0][0], records[1][0]
            cell_neighbors[first].add(second)
            cell_neighbors[second].add(first)
    unseen_cells = set(range(len(cells)))
    mesh_components = 0
    while unseen_cells:
        mesh_components += 1
        pending = [unseen_cells.pop()]
        while pending:
            for neighbor in cell_neighbors[pending.pop()]:
                if neighbor in unseen_cells:
                    unseen_cells.remove(neighbor)
                    pending.append(neighbor)
    if require_connected and mesh_components != 1:
        raise MeshAuditError(f"tetrahedral cells form {mesh_components} disconnected components")

    labels = np.unique(groups)
    label_surfaces: dict[int, list[tuple[int, int, int]]] = {int(label): [] for label in labels}
    exterior_faces: list[tuple[int, int, int]] = []
    cross_partition_faces: dict[tuple[int, int, int], tuple[int, int]] = {}
    for canonical, records in face_records.items():
        parent_labels = [int(groups[cell_index]) for cell_index, _ in records]
        if len(records) == 1:
            exterior_faces.append(records[0][1])
            label_surfaces[parent_labels[0]].append(records[0][1])
        elif parent_labels[0] != parent_labels[1]:
            cross_partition_faces[canonical] = (records[0][0], records[1][0])
            label_surfaces[parent_labels[0]].append(records[0][1])
            label_surfaces[parent_labels[1]].append(records[1][1])

    if (interface_triangles is None) != (interface_parents is None):
        raise MeshAuditError("interface_triangles and interface_parents must be provided together")
    if not np.isfinite(analytic_relative_tolerance) or analytic_relative_tolerance <= 0:
        raise MeshAuditError("analytic_relative_tolerance must be finite and positive")
    if interface_plane_x_m is not None and not np.isfinite(interface_plane_x_m):
        raise MeshAuditError("interface_plane_x_m must be finite")
    if expected_volume_m3 is not None and (expected_volume_m3 <= 0 or not np.isfinite(expected_volume_m3)):
        raise MeshAuditError("expected_volume_m3 must be finite and positive")
    interface_report: dict[str, Any] | None = None
    interface_nodes: np.ndarray | None = None
    if interface_triangles is not None:
        triangles = _integer_array("interface_triangles", interface_triangles, 2)
        parents = _integer_array("interface_parents", interface_parents, 2)
        if triangles.shape[1:] != (3,) or parents.shape != (len(triangles), 2):
            raise MeshAuditError("interface arrays must have shapes (F, 3) and (F, 2)")
        if not len(triangles):
            raise MeshAuditError("interface must contain at least one triangle")
        if np.any(triangles < 0) or np.any(triangles >= len(xyz)):
            raise MeshAuditError("interface triangle references a missing node")
        if np.any(parents < 0) or np.any(parents >= len(cells)):
            raise MeshAuditError("interface parent references a missing tetrahedron")
        canonical_triangles = [tuple(sorted(map(int, row))) for row in triangles]
        if len(set(canonical_triangles)) != len(canonical_triangles):
            raise MeshAuditError("interface triangle list contains duplicates")
        if set(canonical_triangles) != set(cross_partition_faces):
            missing = len(set(cross_partition_faces) - set(canonical_triangles))
            extra = len(set(canonical_triangles) - set(cross_partition_faces))
            raise MeshAuditError(
                "interface triangles do not exactly match cross-partition faces "
                f"(missing={missing}, extra={extra})"
            )
        for triangle, parent_pair in zip(canonical_triangles, parents, strict=True):
            expected_pair = tuple(sorted(cross_partition_faces[triangle]))
            if tuple(sorted(map(int, parent_pair))) != expected_pair:
                raise MeshAuditError("interface parent pair disagrees with tetrahedral face incidence")
            if groups[parent_pair[0]] == groups[parent_pair[1]]:
                raise MeshAuditError("interface triangle parents do not belong to distinct partitions")

        interface_nodes = np.unique(triangles)
        tri_xyz = xyz[triangles]
        tri_areas = 0.5 * np.linalg.norm(
            np.cross(tri_xyz[:, 1] - tri_xyz[:, 0], tri_xyz[:, 2] - tri_xyz[:, 0]), axis=1
        )
        if not np.isfinite(tri_areas).all() or np.any(tri_areas <= 0.0):
            raise MeshAuditError("interface contains a degenerate triangle")
        interface_area = float(tri_areas.sum())
        area_relative_error = None
        if expected_interface_area_m2 is not None:
            if expected_interface_area_m2 <= 0 or not np.isfinite(expected_interface_area_m2):
                raise MeshAuditError("expected_interface_area_m2 must be finite and positive")
            area_relative_error = abs(interface_area - expected_interface_area_m2) / expected_interface_area_m2
            if area_relative_error > analytic_relative_tolerance:
                raise MeshAuditError(
                    "triangular interface area differs from its analytic area by more than "
                    f"{analytic_relative_tolerance:.1%}"
                )
        max_plane_deviation = None
        if interface_plane_x_m is not None:
            max_plane_deviation = float(np.max(np.abs(xyz[interface_nodes, 0] - interface_plane_x_m)))
            if max_plane_deviation > 1e-10:
                raise MeshAuditError("interface vertices leave the declared x plane")
        interface_report = {
            "triangles": len(triangles),
            "unique_nodes": len(interface_nodes),
            "cross_partition_faces": len(cross_partition_faces),
            "parent_pairs_exact": True,
            "parents_from_distinct_partitions": True,
            "area_m2": interface_area,
            "expected_area_m2": expected_interface_area_m2,
            "relative_area_error": area_relative_error,
            "max_abs_x_plane_deviation_m": max_plane_deviation,
        }

    origin = np.asarray(center_m, dtype=np.float64) if center_m is not None else xyz[used_nodes].mean(axis=0)
    if origin.shape != (3,) or not np.isfinite(origin).all():
        raise MeshAuditError("center_m must be a finite vector with three coordinates")
    exterior_surface = _surface_measurements(exterior_faces, xyz, origin)
    if not exterior_surface["closed_oriented_vertex_manifold"]:
        raise MeshAuditError("whole-mesh exterior boundary is not a closed oriented vertex-manifold surface")
    if require_single_surface_component and exterior_surface["connected_components"] != 1:
        raise MeshAuditError("whole-mesh exterior boundary is not a single connected surface")

    partition_reports: dict[str, Any] = {}
    partition_volumes: dict[int, float] = {}
    for label in labels:
        label_int = int(label)
        cell_mask = groups == label
        volume = float(cell_volumes[cell_mask].sum())
        partition_volumes[label_int] = volume
        surface = _surface_measurements(label_surfaces[label_int], xyz, origin)
        if not surface["closed_oriented_vertex_manifold"]:
            raise MeshAuditError(f"partition {label_int} boundary is not closed and manifold")
        if require_single_surface_component and surface["connected_components"] != 1:
            raise MeshAuditError(f"partition {label_int} boundary is not a single connected surface")
        boundary_error = abs(surface["signed_volume_m3"] - volume) / volume
        if boundary_error > 1e-9:
            raise MeshAuditError(
                f"partition {label_int} boundary volume disagrees with tetrahedral volume "
                f"(relative error={boundary_error:.3g})"
            )
        analytic_partition_volume = (
            expected_volume_m3 / 2.0
            if expected_volume_m3 is not None and len(labels) == 2
            else None
        )
        analytic_partition_error = (
            abs(volume - analytic_partition_volume) / analytic_partition_volume
            if analytic_partition_volume is not None
            else None
        )
        if analytic_partition_error is not None and analytic_partition_error > analytic_relative_tolerance:
            raise MeshAuditError(
                f"partition {label_int} volume differs from analytic half-volume by more than "
                f"{analytic_relative_tolerance:.1%}"
            )
        partition_reports[str(label_int)] = {
            "tetrahedra": int(cell_mask.sum()),
            "tetrahedral_volume_m3": volume,
            "expected_analytic_half_volume_m3": analytic_partition_volume,
            "analytic_half_volume_relative_error": analytic_partition_error,
            "surface": surface,
            "boundary_volume_relative_error": float(boundary_error),
        }

    whole_volume = float(cell_volumes.sum())
    exterior_boundary_error = abs(exterior_surface["signed_volume_m3"] - whole_volume) / whole_volume
    if exterior_boundary_error > 1e-9:
        raise MeshAuditError(
            "whole-mesh exterior boundary volume disagrees with tetrahedral volume "
            f"(relative error={exterior_boundary_error:.3g})"
        )
    volume_relative_error = None
    if expected_volume_m3 is not None:
        volume_relative_error = abs(whole_volume - expected_volume_m3) / expected_volume_m3
        if volume_relative_error > analytic_relative_tolerance:
            raise MeshAuditError(
                "tetrahedral volume differs from analytic volume by more than "
                f"{analytic_relative_tolerance:.1%}"
            )

    if len(partition_volumes) == 2:
        target_half = whole_volume / 2.0
        partition_balance_relative_error = max(
            abs(value - target_half) / target_half for value in partition_volumes.values()
        )
    else:
        partition_balance_relative_error = None

    quality_edges = np.column_stack(
        [np.linalg.norm(points[:, first] - points[:, second], axis=1)
         for first, second in combinations(range(4), 2)]
    )
    quality = {
        "signed_volume_m3": _summary(cell_volumes),
        "minimum_altitude_m": _summary(np.min(altitudes, axis=1)),
        "maximum_edge_length_m": _summary(np.max(quality_edges, axis=1)),
        "worst_vertex_edge_matrix_condition": _summary(worst_anchor_condition),
    }

    geometry_report: dict[str, Any] | None = None
    bowl_options = (center_m, inner_radius_m, outer_radius_m)
    if any(value is not None for value in bowl_options):
        if center_m is None or inner_radius_m is None or outer_radius_m is None:
            raise MeshAuditError("center_m, inner_radius_m, and outer_radius_m must be supplied together")
        if not (0 < inner_radius_m < outer_radius_m) or not np.isfinite([inner_radius_m, outer_radius_m]).all():
            raise MeshAuditError("bowl radii must be finite with 0 < inner_radius_m < outer_radius_m")
        if containment_grid_subdivisions < 1:
            raise MeshAuditError("containment_grid_subdivisions must be positive")
        center = np.asarray(center_m, dtype=np.float64)
        centroid_points = points.mean(axis=1)
        centroid_inside = _point_in_spherical_bowl(
            centroid_points, center, inner_radius_m, outer_radius_m, 1e-12
        )
        if not centroid_inside.all():
            raise MeshAuditError(
                f"{int((~centroid_inside).sum())} tetrahedron centroids leave the analytic bowl material"
            )

        edges = sorted({tuple(sorted(edge)) for row in cells for edge in combinations(map(int, row), 2)})
        unique_faces = list(face_records)
        simplex_samples = {
            "vertices": xyz[used_nodes],
            "unique_edge_midpoints": xyz[np.asarray(edges)].mean(axis=1),
            "unique_face_centroids": xyz[np.asarray(unique_faces)].mean(axis=1),
            "tetrahedron_centroids": centroid_points,
        }
        simplex_results = {}
        tol = 1e-12
        for sample_name, sample_points in simplex_samples.items():
            inside = _point_in_spherical_bowl(sample_points, center, inner_radius_m, outer_radius_m, tol)
            radii = np.linalg.norm(sample_points - center, axis=1)
            simplex_results[sample_name] = {
                "evaluations": int(len(sample_points)),
                "inside_material": int(inside.sum()),
                "outside_material": int((~inside).sum()),
                "minimum_inner_radial_clearance_m": float(np.min(radii - inner_radius_m)),
                "maximum_outer_radial_clearance_m": float(np.max(outer_radius_m - radii)),
            }

        radial_node_distance = np.linalg.norm(xyz - center, axis=1)
        inner_face_tol = max(1e-12, outer_radius_m * 1e-8)
        inner_faces = [
            face for face in exterior_faces
            if np.max(np.abs(radial_node_distance[np.asarray(face)] - inner_radius_m)) <= inner_face_tol
        ]
        grid_points: list[np.ndarray] = []
        subdivisions = int(containment_grid_subdivisions)
        for face in inner_faces:
            tri = xyz[np.asarray(face)]
            for first_weight in range(subdivisions + 1):
                for second_weight in range(subdivisions + 1 - first_weight):
                    third_weight = subdivisions - first_weight - second_weight
                    grid_points.append(
                        (first_weight * tri[0] + second_weight * tri[1] + third_weight * tri[2])
                        / subdivisions
                    )
        if grid_points:
            sampled_boundary_points = np.asarray(grid_points)
            sampled_radii = np.linalg.norm(sampled_boundary_points - center, axis=1)
            cavity_samples = sampled_radii < inner_radius_m
            max_intrusion = float(np.max(np.maximum(inner_radius_m - sampled_radii, 0.0)))
            boundary_sampling = {
                "inner_radius_boundary_triangles": len(inner_faces),
                "barycentric_grid_subdivisions_per_edge": subdivisions,
                "sample_evaluations_including_face_edge_repeats": int(len(sampled_radii)),
                "samples_inside_analytic_cavity": int(cavity_samples.sum()),
                "maximum_sampled_radial_intrusion_m": max_intrusion,
                "maximum_sampled_radial_intrusion_mm": max_intrusion * 1000.0,
            }
        else:
            boundary_sampling = {
                "inner_radius_boundary_triangles": 0,
                "barycentric_grid_subdivisions_per_edge": subdivisions,
                "sample_evaluations_including_face_edge_repeats": 0,
                "samples_inside_analytic_cavity": 0,
                "maximum_sampled_radial_intrusion_m": 0.0,
                "maximum_sampled_radial_intrusion_mm": 0.0,
            }
        geometry_report = {
            "center_m": center.tolist(),
            "inner_radius_m": float(inner_radius_m),
            "outer_radius_m": float(outer_radius_m),
            "tetrahedron_centroids_inside_material": int(centroid_inside.sum()),
            "tetrahedron_centroids_outside_material": int((~centroid_inside).sum()),
            "simplex_barycenter_samples": simplex_results,
            "inner_spherical_boundary_chord_sampling": boundary_sampling,
            "continuous_global_containment_certified": False,
            "sampling_note": (
                "Finite simplex barycenters and a fixed barycentric lattice on detected inner-radius "
                "boundary triangles. Repeated edge samples occur once per incident triangle; these "
                "measure linear-chord intrusion but do not bound the continuous maximum."
            ),
        }

    if partition_balance_relative_error is not None and partition_balance_relative_error > analytic_relative_tolerance:
        raise MeshAuditError(
            "two partition volumes differ from an even split by more than "
            f"{analytic_relative_tolerance:.1%}"
        )

    return {
        "schema": "vesselforge.independent_tetra_audit.v1",
        "status": "PASS",
        "counts": {
            "nodes": len(xyz),
            "referenced_nodes": len(used_nodes),
            "unused_nodes": len(xyz) - len(used_nodes),
            "tetrahedra": len(cells),
            "unique_faces": len(face_records),
            "one_parent_boundary_faces": int(np.count_nonzero(face_incidence == 1)),
            "two_parent_internal_faces": interior_faces,
            "cross_partition_faces": len(cross_partition_faces),
            "partitions": len(labels),
            "mesh_connected_components": mesh_components,
        },
        "checks": {
            "finite_coordinates": True,
            "positive_oriented_non_degenerate_tetrahedra": True,
            "unique_tetrahedra": True,
            "all_face_incidence_at_most_two": True,
            "two_parent_face_windings_opposed": True,
            "connected_tetrahedral_body": mesh_components == 1,
            "interface_matches_all_cross_partition_faces": True if interface_report is not None else None,
            "whole_exterior_closed_oriented_vertex_manifold": True,
            "partition_boundaries_closed_oriented_vertex_manifold": True,
            "whole_boundary_volume_matches_cell_volume": True,
            "partition_boundary_volumes_match_cell_volumes": True,
            "stored_cell_volumes_match_determinants": True if stored_volume_m3 is not None else None,
        },
        "volume": {
            "tetrahedral_volume_m3": whole_volume,
            "exterior_boundary_signed_volume_m3": exterior_surface["signed_volume_m3"],
            "exterior_boundary_relative_error": float(exterior_boundary_error),
            "expected_volume_m3": expected_volume_m3,
            "analytic_relative_error": volume_relative_error,
            "partition_balance_relative_error": partition_balance_relative_error,
            "partitions": partition_reports,
        },
        "quality": quality,
        "exterior_surface": exterior_surface,
        "interface": interface_report,
        "geometry_sampling": geometry_report,
    }
