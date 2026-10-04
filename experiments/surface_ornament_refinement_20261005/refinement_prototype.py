"""Source-only local refinement prototype for the frozen run02 analytic fixture.

This module is deliberately isolated from production VesselForge code. It reads
the immutable run02 NPZ, refines only outer-wall triangles near the unchanged
continuous motif field, and can write candidate arrays plus finite geometry,
normal, and topology reports when a later run is explicitly approved. Importing
the module performs no IO, mesh generation, CAD work, or rendering.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


HERE = Path(__file__).resolve().parent
VESSEL_FORGE_ROOT = HERE.parents[1]
DEFAULT_CASES = HERE / "candidate_cases.json"
DEFAULT_BASE = (
    VESSEL_FORGE_ROOT
    / "tmp"
    / "review_20261004"
    / "surface_ornament_route"
    / "run02"
)
TWO_PI = 2.0 * math.pi
GEOMETRY_SAMPLE_TARGET_MM = 0.02
SUPPORT_TRANSITION_SCALE = 1.5
MAX_REFINEMENT_ROUNDS = 32
MAX_FACES = 200_000
BASELINE_FIELD_TOL = 1e-12
BASELINE_COLOR_TOL = 1e-12
NEW_ANALYTIC_COORDINATE_TOL_MM = 1e-12
LINEAGE_CHART_TOL_MM = 1e-9
LINEAGE_BARYCENTRIC_TOL = 1e-12
SEAM_ANGLE_TOL_RAD = 1e-12


class RefinementBudgetUnknown(RuntimeError):
    """The frozen refinement budget ended before the candidate was assessed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def wrap_delta(from_theta: np.ndarray | float, to_theta: np.ndarray | float) -> np.ndarray:
    """Shortest signed angular difference from ``from_theta`` to ``to_theta``."""
    return (np.asarray(to_theta) - np.asarray(from_theta) + math.pi) % TWO_PI - math.pi


def wrap_angle(theta: np.ndarray | float) -> np.ndarray:
    return np.asarray(theta) % TWO_PI


def linear_rgb_to_srgb(linear_rgb: np.ndarray) -> np.ndarray:
    linear = np.clip(np.asarray(linear_rgb, dtype=np.float64), 0.0, 1.0)
    return np.where(
        linear <= 0.0031308,
        12.92 * linear,
        1.055 * np.power(linear, 1.0 / 2.4) - 0.055,
    )


def field_at(
    theta_rad: np.ndarray | float,
    z_mm: np.ndarray | float,
    radius_mm: float,
    field: dict[str, Any],
) -> dict[str, np.ndarray]:
    """Evaluate the frozen continuous relief, color, and displaced normal field.

    ``h_theta`` is the derivative with respect to radians. The local cylinder
    metric is exact for this constant-radius fixture only.
    """
    theta = np.asarray(theta_rad, dtype=np.float64)
    z = np.asarray(z_mm, dtype=np.float64)
    if theta.shape != z.shape:
        raise ValueError("theta and z arrays must have the same shape")

    repeat = int(field["repeat_count"])
    half_width = float(field["circumferential_half_width_mm"])
    half_height = float(field["vertical_half_height_mm"])
    center_z = float(field["center_z_mm"])
    amplitude = float(field["raised_height_mm"])

    phase_delta = np.remainder(repeat * theta / TWO_PI + 0.5, 1.0) - 0.5
    arc_delta = radius_mm * (TWO_PI / repeat) * phase_delta
    dz = z - center_z
    q = np.sqrt((arc_delta / half_width) ** 2 + (dz / half_height) ** 2)
    ramp = np.clip(1.0 - q, 0.0, 1.0)
    coverage = ramp * ramp * (3.0 - 2.0 * ramp)
    height = amplitude * coverage

    # The derivative is zero at the motif center and support boundary. The
    # explicit masked divide avoids an undefined q derivative at the center.
    dcoverage_dq = -6.0 * ramp * (1.0 - ramp)
    dcoverage_dq = np.where(q < 1.0, dcoverage_dq, 0.0)
    nonzero_q = q > 0.0
    dq_dtheta = np.divide(
        arc_delta * radius_mm,
        half_width * half_width * q,
        out=np.zeros_like(q),
        where=nonzero_q,
    )
    dq_dz = np.divide(
        dz,
        half_height * half_height * q,
        out=np.zeros_like(q),
        where=nonzero_q,
    )
    h_theta = amplitude * dcoverage_dq * dq_dtheta
    h_z = amplitude * dcoverage_dq * dq_dz

    base = np.asarray(field["base_linear_rgb"], dtype=np.float64)
    pigment = np.asarray(field["pigment_linear_rgb"], dtype=np.float64)
    rgb_linear = base + coverage[..., None] * (pigment - base)
    rgb_srgb = linear_rgb_to_srgb(rgb_linear)

    radial = np.stack((np.cos(theta), np.sin(theta), np.zeros_like(theta)), axis=-1)
    tangent = np.stack((-np.sin(theta), np.cos(theta), np.zeros_like(theta)), axis=-1)
    z_axis = np.zeros_like(radial)
    z_axis[..., 2] = 1.0
    normal = (
        radial
        - (h_theta / (radius_mm + height))[..., None] * tangent
        - h_z[..., None] * z_axis
    )
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    displaced = np.stack(
        (
            (radius_mm + height) * np.cos(theta),
            (radius_mm + height) * np.sin(theta),
            z,
        ),
        axis=-1,
    )
    rest = np.stack(
        (radius_mm * np.cos(theta), radius_mm * np.sin(theta), z), axis=-1
    )
    return {
        "coverage": coverage,
        "height_mm": height,
        "h_theta_mm_per_rad": h_theta,
        "h_z_mm_per_mm": h_z,
        "linear_rgb": rgb_linear,
        "srgb": rgb_srgb,
        "normal": normal,
        "rest_xyz_mm": rest,
        "displaced_xyz_mm": displaced,
    }


def _point_segment_distance_sq_to_origin(a: np.ndarray, b: np.ndarray) -> float:
    delta = b - a
    denominator = float(np.dot(delta, delta))
    if denominator == 0.0:
        return float(np.dot(a, a))
    t = float(np.clip(-np.dot(a, delta) / denominator, 0.0, 1.0))
    closest = a + t * delta
    return float(np.dot(closest, closest))


def _origin_in_triangle(points: np.ndarray) -> bool:
    a, b, c = points
    ab_vec, ab_origin = b - a, -a
    bc_vec, bc_origin = c - b, -b
    ca_vec, ca_origin = a - c, -c
    ab = ab_vec[0] * ab_origin[1] - ab_vec[1] * ab_origin[0]
    bc = bc_vec[0] * bc_origin[1] - bc_vec[1] * bc_origin[0]
    ca = ca_vec[0] * ca_origin[1] - ca_vec[1] * ca_origin[0]
    return bool((ab >= 0.0 and bc >= 0.0 and ca >= 0.0) or (ab <= 0.0 and bc <= 0.0 and ca <= 0.0))


def _triangle_intersects_support_band(
    theta_vertices: np.ndarray,
    z_vertices: np.ndarray,
    radius_mm: float,
    field: dict[str, Any],
    scale: float,
) -> bool:
    """Analytic floating-point predicate for triangle/ellipse intersection."""
    anchor = float(theta_vertices[0])
    theta_local = anchor + wrap_delta(anchor, theta_vertices)
    theta_mean = float(np.mean(theta_local))
    repeat = int(field["repeat_count"])
    center_z = float(field["center_z_mm"])
    a_mm = float(field["circumferential_half_width_mm"]) * scale
    b_mm = float(field["vertical_half_height_mm"]) * scale
    chart = np.column_stack(
        (
            radius_mm * (theta_local - theta_mean),
            z_vertices - center_z,
        )
    )
    transformed = np.empty_like(chart)
    transformed[:, 0] = chart[:, 0] / a_mm
    transformed[:, 1] = chart[:, 1] / b_mm
    vertices_per_turn = TWO_PI / repeat
    for motif in range(repeat):
        center = motif * vertices_per_turn
        center_near = theta_mean + float(wrap_delta(theta_mean, center))
        origin = np.asarray(
            (
                radius_mm * (center_near - theta_mean) / a_mm,
                0.0,
            ),
            dtype=np.float64,
        )
        local = transformed.copy()
        local[:, 0] -= origin[0]
        if _origin_in_triangle(local):
            return True
        if min(
            _point_segment_distance_sq_to_origin(local[0], local[1]),
            _point_segment_distance_sq_to_origin(local[1], local[2]),
            _point_segment_distance_sq_to_origin(local[2], local[0]),
        ) <= 1.0:
            return True
    return False


def _segment_intersects_support_band(
    theta_a: float,
    z_a: float,
    theta_b: float,
    z_b: float,
    radius_mm: float,
    field: dict[str, Any],
    scale: float,
) -> bool:
    anchor = theta_a
    theta_b_local = anchor + float(wrap_delta(anchor, theta_b))
    theta_mid = 0.5 * (anchor + theta_b_local)
    a_mm = float(field["circumferential_half_width_mm"]) * scale
    b_mm = float(field["vertical_half_height_mm"]) * scale
    center_z = float(field["center_z_mm"])
    repeat = int(field["repeat_count"])
    for motif in range(repeat):
        center = motif * TWO_PI / repeat
        center_near = theta_mid + float(wrap_delta(theta_mid, center))
        p0 = np.asarray(
            (
                radius_mm * (anchor - center_near) / a_mm,
                (z_a - center_z) / b_mm,
            ),
            dtype=np.float64,
        )
        p1 = np.asarray(
            (
                radius_mm * (theta_b_local - center_near) / a_mm,
                (z_b - center_z) / b_mm,
            ),
            dtype=np.float64,
        )
        if _point_segment_distance_sq_to_origin(p0, p1) <= 1.0:
            return True
    return False


def _edge_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _edge_chart_length(
    a: int,
    b: int,
    theta_values: list[float],
    z_values: list[float],
    radius_mm: float,
) -> float:
    return math.hypot(
        radius_mm * float(wrap_delta(theta_values[a], theta_values[b])),
        z_values[b] - z_values[a],
    )


def _split_templates(
    a: int,
    b: int,
    c: int,
    ab: int | None,
    bc: int | None,
    ca: int | None,
) -> list[tuple[int, int, int]]:
    """Return oriented conforming red/green children for marked edges."""
    count = sum(mid is not None for mid in (ab, bc, ca))
    if count == 0:
        return [(a, b, c)]
    if count == 1:
        if ab is not None:
            return [(a, ab, c), (ab, b, c)]
        if bc is not None:
            return [(b, bc, a), (bc, c, a)]
        assert ca is not None
        return [(c, ca, b), (ca, a, b)]
    if count == 2:
        if ab is not None and bc is not None:
            return [(b, bc, ab), (a, ab, c), (ab, bc, c)]
        if bc is not None and ca is not None:
            return [(c, ca, bc), (b, bc, a), (bc, ca, a)]
        assert ca is not None and ab is not None
        return [(a, ab, ca), (c, ca, b), (ca, ab, b)]
    assert ab is not None and bc is not None and ca is not None
    return [
        (a, ab, ca),
        (ab, b, bc),
        (ca, bc, c),
        (ab, bc, ca),
    ]


def _split_barycentric_templates(
    bary: np.ndarray,
    ab: bool,
    bc: bool,
    ca: bool,
) -> list[np.ndarray]:
    a, b, c = bary
    mab = 0.5 * (a + b) if ab else None
    mbc = 0.5 * (b + c) if bc else None
    mca = 0.5 * (c + a) if ca else None
    count = int(ab) + int(bc) + int(ca)
    if count == 0:
        return [np.asarray((a, b, c))]
    if count == 1:
        if ab:
            return [np.asarray((a, mab, c)), np.asarray((mab, b, c))]
        if bc:
            return [np.asarray((b, mbc, a)), np.asarray((mbc, c, a))]
        return [np.asarray((c, mca, b)), np.asarray((mca, a, b))]
    if count == 2:
        if ab and bc:
            return [
                np.asarray((b, mbc, mab)),
                np.asarray((a, mab, c)),
                np.asarray((mab, mbc, c)),
            ]
        if bc and ca:
            return [
                np.asarray((c, mca, mbc)),
                np.asarray((b, mbc, a)),
                np.asarray((mbc, mca, a)),
            ]
        return [
            np.asarray((a, mab, mca)),
            np.asarray((c, mca, b)),
            np.asarray((mca, mab, b)),
        ]
    return [
        np.asarray((a, mab, mca)),
        np.asarray((mab, b, mbc)),
        np.asarray((mca, mbc, c)),
        np.asarray((mab, mbc, mca)),
    ]


def load_baseline(cases: dict[str, Any]) -> dict[str, np.ndarray | float]:
    source = DEFAULT_BASE / "fixture_arrays.npz"
    expected_sha = cases["immutable_source"]["fixture_arrays_sha256"]
    actual_sha = sha256_file(source)
    if actual_sha != expected_sha:
        raise ValueError(f"baseline NPZ SHA mismatch: expected {expected_sha}, got {actual_sha}")
    expected_files = cases["immutable_source"]["related_sha256"]
    for relative, expected in expected_files.items():
        actual = sha256_file(DEFAULT_BASE / relative)
        if actual != expected:
            raise ValueError(f"baseline source artifact SHA mismatch for {relative}")
    original_experiment = VESSEL_FORGE_ROOT / "experiments" / "surface_ornament_route_20261004"
    source_pins = (
        (
            original_experiment / "surface_mapping_prototype.py",
            cases["immutable_source"]["prototype_sha256"],
        ),
        (
            original_experiment / "fixture_once_check_run02.py",
            cases["immutable_source"]["run02_checker_sha256"],
        ),
    )
    for path, expected in source_pins:
        if sha256_file(path) != expected:
            raise ValueError(f"immutable source pin mismatch: {path.name}")
    parameter_record = json.loads((DEFAULT_BASE / "fixture_parameters.json").read_text(encoding="utf-8"))
    source_parameter_record = json.loads((DEFAULT_BASE / "source_parameter_hashes.json").read_text(encoding="utf-8"))
    if source_parameter_record["parameters_sha256"] != cases["immutable_source"]["fixture_parameters_sha256"]:
        raise ValueError("canonical run02 fixture parameter digest mismatch")
    fixture_map = {
        "outer_radius_mm": "outer_radius_mm",
        "wall_declaration_mm": "wall_mm",
        "height_mm": "height_mm",
        "floor_mm": "floor_mm",
        "around": "around",
        "side_rows": "side_rows",
    }
    for case_key, run_key in fixture_map.items():
        if parameter_record["fixture"][run_key] != cases["fixed_fixture"][case_key]:
            raise ValueError(f"fixed fixture case mismatch at {case_key}")
    field_map = {
        "repeat_count": "repeat_count",
        "center_z_mm": "center_z_mm",
        "circumferential_half_width_mm": "circumferential_half_width_mm",
        "vertical_half_height_mm": "vertical_half_height_mm",
        "raised_height_mm": "raised_height_mm",
        "base_linear_rgb": "base_linear_rgb",
        "pigment_linear_rgb": "pigment_linear_rgb",
    }
    for case_key, run_key in field_map.items():
        if parameter_record["field"][run_key] != cases["field"][case_key]:
            raise ValueError(f"frozen continuous field mismatch at {case_key}")
    with np.load(source, allow_pickle=False) as archive:
        baseline = {name: archive[name].copy() for name in archive.files}
    return baseline


def _initial_charts(baseline: dict[str, np.ndarray | float]) -> tuple[list[float], list[float]]:
    rest = np.asarray(baseline["vertices_rest_xyz_mm"])
    theta = np.arctan2(rest[:, 1], rest[:, 0])
    z = rest[:, 2].copy()
    outer = np.asarray(baseline["outer_side_vertex_indices"], dtype=np.int64)
    theta[outer] = np.asarray(baseline["outer_side_theta_rad"], dtype=np.float64)
    z[outer] = np.asarray(baseline["outer_side_z_mm"], dtype=np.float64)
    return theta.astype(float).tolist(), z.astype(float).tolist()


def _build_candidate(
    baseline: dict[str, np.ndarray | float],
    field: dict[str, Any],
    target_edge_mm: float,
) -> dict[str, Any]:
    rest_base = np.asarray(baseline["vertices_rest_xyz_mm"], dtype=np.float64)
    relief_base = np.asarray(baseline["vertices_relief_xyz_mm"], dtype=np.float64)
    base_faces = np.asarray(baseline["faces"], dtype=np.int64)
    outer_ids = np.asarray(baseline["outer_side_vertex_indices"], dtype=np.int64)
    radius = float(baseline["outer_radius_mm"])
    original_vertex_count = len(rest_base)
    theta_values, z_values = _initial_charts(baseline)
    rest_values = [row.copy() for row in rest_base]
    relief_values = [row.copy() for row in relief_base]
    outer_sample_ids = outer_ids.astype(int).tolist()
    outer_base_colors = np.asarray(baseline["outer_color_linear_rgb"], dtype=np.float64)
    outer_base_srgb = np.asarray(baseline["outer_color_srgb_for_display"], dtype=np.float64)

    face_list = [tuple(map(int, tri)) for tri in base_faces]
    source_faces = np.arange(len(base_faces), dtype=np.int64)
    face_bary = np.broadcast_to(np.eye(3), (len(base_faces), 3, 3)).copy()
    original_outer_face_ids = set(
        np.flatnonzero(np.isin(base_faces, outer_ids).all(axis=1)).astype(int).tolist()
    )
    lineage_face = [-1] * original_vertex_count
    lineage_bary = [np.zeros(3, dtype=np.float64) for _ in range(original_vertex_count)]
    midpoint_cache: dict[tuple[int, int], int] = {}
    rounds = 0

    while True:
        if rounds >= MAX_REFINEMENT_ROUNDS:
            raise RefinementBudgetUnknown("UNKNOWN: local refinement exceeded the fixed round cap")
        target_faces: list[int] = []
        for face_index, tri in enumerate(face_list):
            if int(source_faces[face_index]) not in original_outer_face_ids:
                continue
            tri_theta = np.asarray([theta_values[v] for v in tri], dtype=np.float64)
            tri_z = np.asarray([z_values[v] for v in tri], dtype=np.float64)
            if _triangle_intersects_support_band(
                tri_theta,
                tri_z,
                radius,
                field,
                SUPPORT_TRANSITION_SCALE,
            ):
                target_faces.append(face_index)

        marked_edges: set[tuple[int, int]] = set()
        for face_index in target_faces:
            tri = face_list[face_index]
            for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                if _edge_chart_length(a, b, theta_values, z_values, radius) > target_edge_mm + 1e-12:
                    marked_edges.add(_edge_key(a, b))
        if not marked_edges:
            break

        midpoint_for_edge: dict[tuple[int, int], int] = {}

        def midpoint_for(
            a: int,
            b: int,
            parent_face_id: int,
            bary_mid: np.ndarray,
        ) -> int:
            key = _edge_key(a, b)
            if key not in midpoint_cache:
                delta = float(wrap_delta(theta_values[a], theta_values[b]))
                theta_mid = float(wrap_angle(theta_values[a] + 0.5 * delta))
                z_mid = 0.5 * (z_values[a] + z_values[b])
                sample = field_at(np.asarray(theta_mid), np.asarray(z_mid), radius, field)
                new_id = len(rest_values)
                rest_values.append(np.asarray(sample["rest_xyz_mm"], dtype=np.float64))
                relief_values.append(np.asarray(sample["displaced_xyz_mm"], dtype=np.float64))
                theta_values.append(theta_mid)
                z_values.append(z_mid)
                lineage_face.append(int(parent_face_id))
                lineage_bary.append(np.asarray(bary_mid, dtype=np.float64).copy())
                midpoint_cache[key] = new_id
                outer_sample_ids.append(new_id)
            new_id = midpoint_cache[key]
            current_parent = lineage_face[new_id]
            if parent_face_id < current_parent:
                lineage_face[new_id] = int(parent_face_id)
                lineage_bary[new_id] = np.asarray(bary_mid, dtype=np.float64).copy()
            return new_id

        # Create one midpoint per shared topological edge. Every incident face
        # records its own barycentric mapping to its original source triangle.
        for face_index, tri in enumerate(face_list):
            tri_edges = (
                (tri[0], tri[1], 0, 1),
                (tri[1], tri[2], 1, 2),
                (tri[2], tri[0], 2, 0),
            )
            for a, b, local_a, local_b in tri_edges:
                key = _edge_key(a, b)
                if key not in marked_edges:
                    continue
                bary_mid = 0.5 * (face_bary[face_index, local_a] + face_bary[face_index, local_b])
                midpoint_for(
                    a,
                    b,
                    int(source_faces[face_index]),
                    bary_mid,
                )
                midpoint_for_edge[key] = midpoint_cache[key]

        next_faces: list[tuple[int, int, int]] = []
        next_sources: list[int] = []
        next_bary: list[np.ndarray] = []
        for face_index, tri in enumerate(face_list):
            a, b, c = tri
            key_ab, key_bc, key_ca = _edge_key(a, b), _edge_key(b, c), _edge_key(c, a)
            mid_ab = midpoint_for_edge.get(key_ab)
            mid_bc = midpoint_for_edge.get(key_bc)
            mid_ca = midpoint_for_edge.get(key_ca)
            children = _split_templates(a, b, c, mid_ab, mid_bc, mid_ca)
            bary_children = _split_barycentric_templates(
                face_bary[face_index],
                mid_ab is not None,
                mid_bc is not None,
                mid_ca is not None,
            )
            if len(children) != len(bary_children):
                raise AssertionError("face and lineage split templates disagree")
            for child, child_bary in zip(children, bary_children):
                next_faces.append(child)
                next_sources.append(int(source_faces[face_index]))
                next_bary.append(child_bary)
        face_list = next_faces
        source_faces = np.asarray(next_sources, dtype=np.int64)
        face_bary = np.asarray(next_bary, dtype=np.float64)
        rounds += 1
        if len(face_list) > MAX_FACES:
            raise RefinementBudgetUnknown("UNKNOWN: local refinement exceeded the 200000-face cap")

    faces = np.asarray(face_list, dtype=np.int64)
    rest = np.asarray(rest_values, dtype=np.float64)
    relief = np.asarray(relief_values, dtype=np.float64)
    outer_sample_ids_array = np.asarray(outer_sample_ids, dtype=np.int64)
    outer_theta = np.asarray([theta_values[i] for i in outer_sample_ids], dtype=np.float64)
    outer_z = np.asarray([z_values[i] for i in outer_sample_ids], dtype=np.float64)
    samples = field_at(outer_theta, outer_z, radius, field)
    vertex_lineage_bary = np.asarray(lineage_bary, dtype=np.float64)

    if not np.array_equal(rest[:original_vertex_count], rest_base):
        raise AssertionError("baseline rest-coordinate prefix changed")
    if not np.array_equal(relief[:original_vertex_count], relief_base):
        raise AssertionError("baseline displaced-coordinate prefix changed")

    return {
        "vertices_rest_xyz_mm": rest,
        "vertices_relief_xyz_mm": relief,
        "faces": faces,
        "outer_vertex_indices": outer_sample_ids_array,
        "outer_theta_rad": outer_theta,
        "outer_z_mm": outer_z,
        "outer_color_linear_rgb": np.asarray(samples["linear_rgb"]),
        "outer_color_srgb_for_display": np.asarray(samples["srgb"]),
        "outer_relief_height_mm": np.asarray(samples["height_mm"]),
        "outer_normals_analytic_displaced": np.asarray(samples["normal"]),
        "outer_source_face_ids": np.asarray(sorted(original_outer_face_ids), dtype=np.int64),
        "source_face_ids": source_faces,
        "face_corner_barycentric_to_source": face_bary,
        "vertex_lineage_source_face_id": np.asarray(lineage_face, dtype=np.int64),
        "vertex_lineage_barycentric": vertex_lineage_bary,
        "original_vertex_count": original_vertex_count,
        "original_face_count": len(base_faces),
        "refinement_rounds": rounds,
        "target_edge_mm": target_edge_mm,
        "outer_base_linear_rgb": outer_base_colors,
        "outer_base_srgb": outer_base_srgb,
    }


def _summary(values: np.ndarray) -> dict[str, float | int]:
    flattened = np.asarray(values, dtype=np.float64).reshape(-1)
    if flattened.size == 0 or not np.isfinite(flattened).all():
        return {"count": int(flattened.size), "finite": False}
    return {
        "count": int(flattened.size),
        "finite": True,
        "rms": float(np.sqrt(np.mean(flattened * flattened))),
        "p95": float(np.percentile(flattened, 95.0)),
        "p99": float(np.percentile(flattened, 99.0)),
        "max": float(np.max(flattened)),
    }


def _topology_report(candidate: dict[str, Any]) -> dict[str, Any]:
    faces = np.asarray(candidate["faces"], dtype=np.int64)
    vertices = np.asarray(candidate["vertices_relief_xyz_mm"], dtype=np.float64)
    edge_incidence: dict[tuple[int, int], int] = {}
    edge_winding: dict[tuple[int, int], int] = {}
    duplicate_faces: set[tuple[int, int, int]] = set()
    duplicate_face_count = 0
    repeated_vertex_face_count = 0
    for tri in faces:
        canonical = tuple(sorted(map(int, tri)))
        if canonical in duplicate_faces:
            duplicate_face_count += 1
        duplicate_faces.add(canonical)
        if len(set(map(int, tri))) != 3:
            repeated_vertex_face_count += 1
        for a, b in ((int(tri[0]), int(tri[1])), (int(tri[1]), int(tri[2])), (int(tri[2]), int(tri[0]))):
            key = _edge_key(a, b)
            edge_incidence[key] = edge_incidence.get(key, 0) + 1
            edge_winding[key] = edge_winding.get(key, 0) + (1 if a < b else -1)

    boundary = sum(count == 1 for count in edge_incidence.values())
    non_two = sum(count != 2 for count in edge_incidence.values())
    inconsistent = sum(
        edge_incidence[key] == 2 and edge_winding[key] != 0
        for key in edge_incidence
    )
    triangle_xyz = vertices[faces]
    cross = np.cross(triangle_xyz[:, 1] - triangle_xyz[:, 0], triangle_xyz[:, 2] - triangle_xyz[:, 0])
    double_areas = np.linalg.norm(cross, axis=1)
    signed_volume = float(
        np.einsum(
            "ij,ij->i",
            triangle_xyz[:, 0],
            np.cross(triangle_xyz[:, 1], triangle_xyz[:, 2]),
        ).sum()
        / 6.0
    )

    adjacency: list[set[int]] = [set() for _ in range(len(vertices))]
    for a, b in edge_incidence:
        adjacency[a].add(b)
        adjacency[b].add(a)
    components = 0
    seen: set[int] = set()
    for start in range(len(vertices)):
        if start in seen or not adjacency[start]:
            continue
        components += 1
        stack = [start]
        seen.add(start)
        while stack:
            current = stack.pop()
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)

    return {
        "vertex_count": int(len(vertices)),
        "face_count": int(len(faces)),
        "unique_undirected_edge_count": int(len(edge_incidence)),
        "euler_characteristic": int(len(vertices) - len(edge_incidence) + len(faces)),
        "boundary_edge_count": int(boundary),
        "non_two_incidence_edge_count": int(non_two),
        "inconsistent_winding_edge_count": int(inconsistent),
        "duplicate_face_count_unoriented": int(duplicate_face_count),
        "repeated_vertex_face_count": int(repeated_vertex_face_count),
        "connected_component_count": int(components),
        "minimum_double_area_mm2": float(double_areas.min()),
        "zero_area_face_count_threshold_1e-12_mm2_double_area": int(np.count_nonzero(double_areas <= 1e-12)),
        "signed_volume_mm3": signed_volume,
        "positive_signed_volume": bool(signed_volume > 0.0),
    }


def _geometry_and_normal_report(
    candidate: dict[str, Any],
    field: dict[str, Any],
    radius_mm: float,
) -> dict[str, Any]:
    faces = np.asarray(candidate["faces"], dtype=np.int64)
    source_faces = np.asarray(candidate["source_face_ids"], dtype=np.int64)
    outer_source_ids = set(
        np.flatnonzero(
            np.isin(
                np.asarray(candidate["_baseline_faces"], dtype=np.int64),
                np.asarray(candidate["_outer_vertex_indices_original"], dtype=np.int64),
            ).all(axis=1)
        ).tolist()
    )
    outer_face_mask = np.fromiter(
        (int(source) in outer_source_ids for source in source_faces),
        dtype=bool,
        count=len(source_faces),
    )
    outer_faces = faces[outer_face_mask]
    theta_values = np.asarray(candidate["_theta_all"], dtype=np.float64)
    z_values = np.asarray(candidate["_z_all"], dtype=np.float64)
    xyz = np.asarray(candidate["vertices_relief_xyz_mm"], dtype=np.float64)

    edge_set = {
        _edge_key(int(a), int(b))
        for tri in outer_faces
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0]))
    }
    theta_list = theta_values.tolist()
    z_list = z_values.tolist()
    chart_lengths: list[float] = []
    displaced_lengths: list[float] = []
    zone_chart_lengths: list[float] = []
    zone_displaced_lengths: list[float] = []
    for a, b in edge_set:
        chart_length = _edge_chart_length(a, b, theta_list, z_list, radius_mm)
        displaced_length = float(np.linalg.norm(xyz[a] - xyz[b]))
        chart_lengths.append(chart_length)
        displaced_lengths.append(displaced_length)
        if _segment_intersects_support_band(
            float(theta_values[a]),
            float(z_values[a]),
            float(theta_values[b]),
            float(z_values[b]),
            radius_mm,
            field,
            SUPPORT_TRANSITION_SCALE,
        ):
            zone_chart_lengths.append(chart_length)
            zone_displaced_lengths.append(displaced_length)

    if len(outer_faces):
        tri_theta = theta_values[outer_faces]
        anchor = tri_theta[:, :1]
        unwrapped = anchor + wrap_delta(anchor, tri_theta)
        tri_z = z_values[outer_faces]
        weights = np.asarray(
            (
                (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0),
                (0.5, 0.5, 0.0),
                (0.0, 0.5, 0.5),
                (0.5, 0.0, 0.5),
            ),
            dtype=np.float64,
        )
        query_theta = wrap_angle(np.einsum("qj,fj->fq", weights, unwrapped)).reshape(-1)
        query_z = np.einsum("qj,fj->fq", weights, tri_z).reshape(-1)
        tri_xyz = xyz[outer_faces]
        triangle_points = np.einsum("qj,fjk->fqk", weights, tri_xyz).reshape(-1, 3)
        exact = field_at(query_theta, query_z, radius_mm, field)
        errors = np.linalg.norm(triangle_points - exact["displaced_xyz_mm"], axis=1)
        error_by_probe = {
            "barycenter": _summary(errors.reshape(-1, 4)[:, 0]),
            "edge_midpoints": _summary(errors.reshape(-1, 4)[:, 1:]),
        }

        triangle_normal = np.cross(
            tri_xyz[:, 1] - tri_xyz[:, 0],
            tri_xyz[:, 2] - tri_xyz[:, 0],
        )
        normal_length = np.linalg.norm(triangle_normal, axis=1, keepdims=True)
        triangle_normal = triangle_normal / normal_length
        query_triangle_normal = np.repeat(triangle_normal[:, None, :], 4, axis=1).reshape(-1, 3)
        cosine = np.einsum("ij,ij->i", query_triangle_normal, exact["normal"])
        angle_error = np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))
        angle_by_probe = {
            "barycenter": _summary(angle_error.reshape(-1, 4)[:, 0]),
            "edge_midpoints": _summary(angle_error.reshape(-1, 4)[:, 1:]),
        }
    else:
        errors = np.asarray([], dtype=np.float64)
        angle_error = np.asarray([], dtype=np.float64)
        error_by_probe = {"barycenter": _summary(errors), "edge_midpoints": _summary(errors)}
        angle_by_probe = {"barycenter": _summary(errors), "edge_midpoints": _summary(errors)}

    amplitude = float(field["raised_height_mm"])
    max_error = float(np.max(errors)) if errors.size else math.nan
    return {
        "outer_triangle_count": int(len(outer_faces)),
        "sample_count": int(errors.size),
        "geometry_error_mm": {
            "all_probes": _summary(errors),
            "by_probe": error_by_probe,
            "finite_sample_gate_target_mm": GEOMETRY_SAMPLE_TARGET_MM,
            "finite_sample_gate_pass": bool(np.isfinite(max_error) and max_error <= GEOMETRY_SAMPLE_TARGET_MM),
            "scope": "finite barycenter and edge-midpoint probes; not a certified supremum or global Hausdorff bound",
        },
        "normal_angle_error_degrees": {
            "all_probes": _summary(angle_error),
            "by_probe": angle_by_probe,
            "acceptance_gate": "REPORT_ONLY_NO_OWNER_LIMIT_SET",
        },
        "actual_edge_lengths": {
            "maximum_outer_chart_edge_mm": float(max(chart_lengths)),
            "maximum_outer_displaced_3d_edge_mm": float(max(displaced_lengths)),
            "maximum_outer_chart_edge_over_amplitude": float(max(chart_lengths) / amplitude),
            "maximum_outer_displaced_3d_edge_over_amplitude": float(max(displaced_lengths) / amplitude),
            "support_plus_transition_max_chart_edge_mm": float(max(zone_chart_lengths)),
            "support_plus_transition_max_displaced_3d_edge_mm": float(max(zone_displaced_lengths)),
            "support_plus_transition_target_chart_edge_mm": float(candidate["target_edge_mm"]),
            "support_plus_transition_chart_gate_pass": bool(
                max(zone_chart_lengths) <= float(candidate["target_edge_mm"]) + 1e-10
            ),
            "support_plus_transition_max_chart_edge_over_amplitude": float(max(zone_chart_lengths) / amplitude),
            "support_plus_transition_max_displaced_3d_edge_over_amplitude": float(max(zone_displaced_lengths) / amplitude),
        },
    }


def check_candidate(
    candidate: dict[str, Any],
    baseline: dict[str, np.ndarray | float],
    field: dict[str, Any],
) -> dict[str, Any]:
    radius = float(baseline["outer_radius_mm"])
    original_vertex_count = int(candidate["original_vertex_count"])
    rest = np.asarray(candidate["vertices_rest_xyz_mm"], dtype=np.float64)
    relief = np.asarray(candidate["vertices_relief_xyz_mm"], dtype=np.float64)
    outer_ids = np.asarray(candidate["outer_vertex_indices"], dtype=np.int64)
    theta = np.asarray(candidate["outer_theta_rad"], dtype=np.float64)
    z = np.asarray(candidate["outer_z_mm"], dtype=np.float64)
    samples = field_at(theta, z, radius, field)
    old_outer_count = len(np.asarray(baseline["outer_side_vertex_indices"]))
    old_field_error = float(
        np.max(
            np.abs(
                samples["height_mm"][:old_outer_count]
                - np.asarray(baseline["outer_relief_height_mm"], dtype=np.float64)
            )
        )
    )
    old_color_error = float(
        np.max(
            np.abs(
                samples["linear_rgb"][:old_outer_count]
                - np.asarray(baseline["outer_color_linear_rgb"], dtype=np.float64)
            )
        )
    )
    srgb_transfer_error = float(
        np.max(
            np.abs(
                linear_rgb_to_srgb(samples["linear_rgb"])
                - samples["srgb"]
            )
        )
    )
    expected_rest = samples["rest_xyz_mm"][old_outer_count:]
    expected_relief = samples["displaced_xyz_mm"][old_outer_count:]
    new_ids = outer_ids[old_outer_count:]
    new_rest_error = float(np.max(np.abs(rest[new_ids] - expected_rest))) if len(new_ids) else 0.0
    new_relief_error = float(np.max(np.abs(relief[new_ids] - expected_relief))) if len(new_ids) else 0.0
    original_rest = np.asarray(baseline["vertices_rest_xyz_mm"], dtype=np.float64)
    original_relief = np.asarray(baseline["vertices_relief_xyz_mm"], dtype=np.float64)

    # Supply private views used by the finite geometry checker; remove them from
    # the serialized candidate payload before writing.
    candidate["_baseline_faces"] = np.asarray(baseline["faces"], dtype=np.int64)
    candidate["_outer_vertex_indices_original"] = np.asarray(baseline["outer_side_vertex_indices"], dtype=np.int64)
    all_theta, all_z = _initial_charts(baseline)
    if len(all_theta) < len(rest):
        all_theta.extend([0.0] * (len(rest) - len(all_theta)))
        all_z.extend([0.0] * (len(rest) - len(all_z)))
    for sample_index, vertex_id in enumerate(outer_ids):
        all_theta[int(vertex_id)] = float(theta[sample_index])
        all_z[int(vertex_id)] = float(z[sample_index])
    candidate["_theta_all"] = np.asarray(all_theta, dtype=np.float64)
    candidate["_z_all"] = np.asarray(all_z, dtype=np.float64)
    source_faces = np.asarray(candidate["source_face_ids"], dtype=np.int64)
    face_bary = np.asarray(candidate["face_corner_barycentric_to_source"], dtype=np.float64)
    source_min = int(source_faces.min()) if len(source_faces) else -1
    source_max = int(source_faces.max()) if len(source_faces) else -1
    lineage_ids = np.asarray(candidate["vertex_lineage_source_face_id"], dtype=np.int64)
    base_faces = np.asarray(baseline["faces"], dtype=np.int64)
    base_theta, base_z = _initial_charts(baseline)
    base_theta_array = np.asarray(base_theta, dtype=np.float64)
    base_z_array = np.asarray(base_z, dtype=np.float64)
    outer_source_ids = np.asarray(candidate["outer_source_face_ids"], dtype=np.int64)
    outer_source_mask = np.isin(source_faces, outer_source_ids)
    outer_child_faces = np.asarray(candidate["faces"], dtype=np.int64)[outer_source_mask]
    outer_child_sources = source_faces[outer_source_mask]
    outer_child_bary = face_bary[outer_source_mask]
    parent_vertices = base_faces[outer_child_sources]
    parent_theta = base_theta_array[parent_vertices]
    parent_anchor = parent_theta[:, :1]
    parent_theta_local = parent_anchor + wrap_delta(parent_anchor, parent_theta)
    expected_face_theta = np.einsum("fci,fi->fc", outer_child_bary, parent_theta_local)
    expected_face_z = np.einsum("fci,fi->fc", outer_child_bary, base_z_array[parent_vertices])
    actual_face_theta = np.asarray(candidate["_theta_all"])[outer_child_faces]
    actual_face_z = np.asarray(candidate["_z_all"])[outer_child_faces]
    face_lineage_residual = np.hypot(
        radius * wrap_delta(expected_face_theta, actual_face_theta),
        actual_face_z - expected_face_z,
    )
    new_vertex_ids = np.arange(original_vertex_count, len(rest), dtype=np.int64)
    vertex_lineage_residual = np.asarray([], dtype=np.float64)
    if len(new_vertex_ids):
        vertex_parent_ids = lineage_ids[new_vertex_ids]
        vertex_parent_vertices = base_faces[vertex_parent_ids]
        vertex_parent_theta = base_theta_array[vertex_parent_vertices]
        vertex_anchor = vertex_parent_theta[:, :1]
        vertex_parent_theta_local = vertex_anchor + wrap_delta(vertex_anchor, vertex_parent_theta)
        vertex_expected_theta = np.einsum(
            "fi,fi->f",
            np.asarray(candidate["vertex_lineage_barycentric"])[new_vertex_ids],
            vertex_parent_theta_local,
        )
        vertex_expected_z = np.einsum(
            "fi,fi->f",
            np.asarray(candidate["vertex_lineage_barycentric"])[new_vertex_ids],
            base_z_array[vertex_parent_vertices],
        )
        vertex_lineage_residual = np.hypot(
            radius * wrap_delta(vertex_expected_theta, np.asarray(candidate["_theta_all"])[new_vertex_ids]),
            np.asarray(candidate["_z_all"])[new_vertex_ids] - vertex_expected_z,
        )
    all_new_bary = np.asarray(candidate["vertex_lineage_barycentric"])[new_vertex_ids]
    all_face_bary = outer_child_bary.reshape(-1, 3)
    combined_bary = np.concatenate((all_new_bary, all_face_bary), axis=0)
    bary_sum_error = float(np.max(np.abs(combined_bary.sum(axis=1) - 1.0))) if len(combined_bary) else 0.0
    bary_min = float(np.min(combined_bary)) if len(combined_bary) else 0.0
    bary_max = float(np.max(combined_bary)) if len(combined_bary) else 1.0
    new_lineage_ok = bool(
        np.all(lineage_ids[original_vertex_count:] >= 0)
        and np.isfinite(np.asarray(candidate["vertex_lineage_barycentric"])[original_vertex_count:]).all()
    )

    topology = _topology_report(candidate)
    geometry = _geometry_and_normal_report(candidate, field, radius)
    outer_rest_rounded = np.round(rest[outer_ids], decimals=12)
    unique_outer_rest = np.unique(outer_rest_rounded, axis=0)
    seam_mask = np.minimum(theta, TWO_PI - theta) <= SEAM_ANGLE_TOL_RAD
    seam_vertex_ids = outer_ids[seam_mask]
    seam_rest_rounded = np.round(rest[seam_vertex_ids], decimals=12)
    unique_seam_rest = np.unique(seam_rest_rounded, axis=0)
    seam_duplicate_count = int(len(seam_vertex_ids) - len(unique_seam_rest))
    baseline_coordinates_pass = bool(
        np.array_equal(rest[:original_vertex_count], original_rest)
        and np.array_equal(relief[:original_vertex_count], original_relief)
    )
    baseline_field_and_color_pass = bool(
        old_field_error <= BASELINE_FIELD_TOL
        and old_color_error <= BASELINE_COLOR_TOL
        and srgb_transfer_error <= BASELINE_COLOR_TOL
    )
    new_analytic_coordinates_pass = bool(
        new_rest_error <= NEW_ANALYTIC_COORDINATE_TOL_MM
        and new_relief_error <= NEW_ANALYTIC_COORDINATE_TOL_MM
    )
    lineage_pass = bool(
        new_lineage_ok
        and np.isfinite(face_bary).all()
        and source_min >= 0
        and source_max < int(candidate["original_face_count"])
        and np.isfinite(face_lineage_residual).all()
        and np.isfinite(vertex_lineage_residual).all()
        and (not len(face_lineage_residual) or np.max(face_lineage_residual) <= LINEAGE_CHART_TOL_MM)
        and (not len(vertex_lineage_residual) or np.max(vertex_lineage_residual) <= LINEAGE_CHART_TOL_MM)
        and bary_sum_error <= LINEAGE_BARYCENTRIC_TOL
        and bary_min >= -LINEAGE_BARYCENTRIC_TOL
        and bary_max <= 1.0 + LINEAGE_BARYCENTRIC_TOL
    )
    seam_unique_pass = bool(len(seam_vertex_ids) > 0 and seam_duplicate_count == 0)
    finite_geometry_pass = bool(
        geometry["geometry_error_mm"]["all_probes"].get("finite", False)
        and geometry["geometry_error_mm"]["finite_sample_gate_pass"]
    )
    zone_edge_pass = bool(geometry["actual_edge_lengths"]["support_plus_transition_chart_gate_pass"])
    checks = {
        "baseline_prefix_ids_and_coordinates_stable": bool(
            baseline_coordinates_pass
        ),
        "baseline_coordinate_gate_pass": baseline_coordinates_pass,
        "baseline_field_height_max_difference_mm": old_field_error,
        "baseline_linear_rgb_max_difference": old_color_error,
        "standard_srgb_transfer_max_difference": srgb_transfer_error,
        "baseline_field_and_color_gate_pass": baseline_field_and_color_pass,
        "new_vertices_rest_analytic_max_abs_error_mm": new_rest_error,
        "new_vertices_displaced_analytic_max_abs_error_mm": new_relief_error,
        "new_analytic_coordinate_gate_pass": new_analytic_coordinates_pass,
        "new_vertex_source_triangle_lineage_present": new_lineage_ok,
        "new_vertex_lineage_chart_max_residual_mm": float(np.max(vertex_lineage_residual)) if len(vertex_lineage_residual) else 0.0,
        "face_source_triangle_lineage_present": bool(
            len(face_bary) == len(np.asarray(candidate["faces"]))
            and np.isfinite(face_bary).all()
            and source_min >= 0
            and source_max < int(candidate["original_face_count"])
        ),
        "face_lineage_chart_max_residual_mm": float(np.max(face_lineage_residual)) if len(face_lineage_residual) else 0.0,
        "lineage_barycentric_sum_max_error": bary_sum_error,
        "lineage_barycentric_min": bary_min,
        "lineage_barycentric_max": bary_max,
        "lineage_reconstruction_pass": bool(
            np.isfinite(face_lineage_residual).all()
            and np.isfinite(vertex_lineage_residual).all()
            and (not len(face_lineage_residual) or np.max(face_lineage_residual) <= 1e-9)
            and (not len(vertex_lineage_residual) or np.max(vertex_lineage_residual) <= 1e-9)
            and bary_sum_error <= 1e-12
            and bary_min >= -1e-12
            and bary_max <= 1.0 + 1e-12
        ),
        "outer_duplicate_rest_coordinate_count_rounded_1e-12_mm": int(len(outer_ids) - len(unique_outer_rest)),
        "periodic_seam_vertex_count": int(len(seam_vertex_ids)),
        "periodic_seam_duplicate_coordinate_count_rounded_1e-12_mm": seam_duplicate_count,
        "periodic_seam_unique_gate_pass": seam_unique_pass,
        "lineage_gate_pass": lineage_pass,
        "refinement_rounds": int(candidate["refinement_rounds"]),
        "topology": topology,
        "geometry_and_resolution": geometry,
    }
    checks["closed_oriented_sphere_gate_pass"] = bool(
        topology["boundary_edge_count"] == 0
        and topology["non_two_incidence_edge_count"] == 0
        and topology["inconsistent_winding_edge_count"] == 0
        and topology["duplicate_face_count_unoriented"] == 0
        and topology["repeated_vertex_face_count"] == 0
        and topology["connected_component_count"] == 1
        and topology["euler_characteristic"] == 2
        and topology["positive_signed_volume"]
        and topology["zero_area_face_count_threshold_1e-12_mm2_double_area"] == 0
    )
    checks["zone_edge_target_gate_pass"] = zone_edge_pass
    checks["finite_geometry_probe_gate_pass"] = finite_geometry_pass
    checks["all_local_geometry_and_lineage_checks_finite"] = bool(
        np.isfinite(rest).all()
        and np.isfinite(relief).all()
        and np.isfinite(samples["linear_rgb"]).all()
        and np.isfinite(samples["srgb"]).all()
        and np.isfinite(geometry["geometry_error_mm"]["all_probes"].get("max", math.nan))
        and np.isfinite(geometry["normal_angle_error_degrees"]["all_probes"].get("max", math.nan))
    )
    checks["overall_candidate_gate_pass"] = bool(
        checks["closed_oriented_sphere_gate_pass"]
        and baseline_coordinates_pass
        and baseline_field_and_color_pass
        and new_analytic_coordinates_pass
        and checks["face_source_triangle_lineage_present"]
        and lineage_pass
        and seam_unique_pass
        and zone_edge_pass
        and finite_geometry_pass
        and checks["all_local_geometry_and_lineage_checks_finite"]
    )
    return checks


def _json_clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_clean(item) for key, item in value.items() if not str(key).startswith("_")}
    if isinstance(value, (list, tuple)):
        return [_json_clean(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def render_saved_candidate(
    arrays: dict[str, np.ndarray],
    output_path: Path,
    field: dict[str, Any],
) -> None:
    """Render saved triangle coordinates with flat faces for visual inspection."""
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    xyz = np.asarray(arrays["vertices_relief_xyz_mm"], dtype=np.float64)
    faces = np.asarray(arrays["faces"], dtype=np.int64)
    source_ids = np.asarray(arrays["source_face_ids"], dtype=np.int64)
    outer_source_ids = set(np.asarray(arrays["outer_source_face_ids"], dtype=np.int64).tolist())
    outer_face_mask = np.fromiter(
        (int(source) in outer_source_ids for source in source_ids),
        dtype=bool,
        count=len(source_ids),
    )
    outer_indices = np.asarray(arrays["outer_vertex_indices"], dtype=np.int64)
    outer_colors = np.asarray(arrays["outer_color_srgb_for_display"], dtype=np.float64)
    color_by_vertex = {int(vertex): outer_colors[i] for i, vertex in enumerate(outer_indices)}
    base_srgb = linear_rgb_to_srgb(np.asarray(field["base_linear_rgb"], dtype=np.float64))
    face_colors = np.tile(np.r_[base_srgb, 1.0], (len(faces), 1))
    for i in np.flatnonzero(outer_face_mask):
        face_colors[i, :3] = np.mean([color_by_vertex[int(v)] for v in faces[i]], axis=0)
    all_triangles = xyz[faces]

    rest = np.asarray(arrays["vertices_rest_xyz_mm"], dtype=np.float64)
    theta = np.arctan2(rest[:, 1], rest[:, 0])
    z = rest[:, 2]
    theta[outer_indices] = np.asarray(arrays["outer_theta_rad"], dtype=np.float64)
    z[outer_indices] = np.asarray(arrays["outer_z_mm"], dtype=np.float64)
    detail_face_ids: list[int] = []
    for face_id in np.flatnonzero(outer_face_mask):
        tri = faces[face_id]
        anchor = float(theta[tri[0]])
        unwrapped = anchor + wrap_delta(anchor, theta[tri])
        mean_theta = float(np.mean(unwrapped))
        mean_z = float(np.mean(z[tri]))
        seam_distance_mm = float(np.linalg.norm((radius := float(arrays["outer_radius_mm"])) * wrap_delta(0.0, mean_theta)))
        if (
            seam_distance_mm <= 1.7 * float(field["circumferential_half_width_mm"])
            and abs(mean_z - float(field["center_z_mm"])) <= 1.7 * float(field["vertical_half_height_mm"])
        ):
            detail_face_ids.append(int(face_id))

    if not detail_face_ids:
        raise ValueError("no saved outer triangles selected for seam-motif detail view")
    detail_faces = faces[np.asarray(detail_face_ids, dtype=np.int64)]
    detail_xyz = xyz[detail_faces]
    detail_colors = face_colors[np.asarray(detail_face_ids, dtype=np.int64)]

    figure = plt.figure(figsize=(13.5, 6.4), constrained_layout=True)
    full_ax = figure.add_subplot(1, 2, 1, projection="3d")
    full_collection = Poly3DCollection(
        all_triangles,
        facecolors=face_colors,
        edgecolors="none",
        linewidths=0.0,
    )
    full_ax.add_collection3d(full_collection)
    full_ax.auto_scale_xyz(xyz[:, 0], xyz[:, 1], xyz[:, 2])
    full_ax.set_box_aspect((1.0, 1.0, 1.0))
    full_ax.view_init(elev=22, azim=35)
    full_ax.set_title("Saved displaced closed boundary")
    full_ax.set_xlabel("x (mm)")
    full_ax.set_ylabel("y (mm)")
    full_ax.set_zlabel("z (mm)")

    detail_ax = figure.add_subplot(1, 2, 2, projection="3d")
    detail_collection = Poly3DCollection(
        detail_xyz,
        facecolors=detail_colors,
        edgecolors=(0.10, 0.08, 0.07, 0.45),
        linewidths=0.28,
    )
    detail_ax.add_collection3d(detail_collection)
    points = detail_xyz.reshape(-1, 3)
    lower = points.min(axis=0)
    upper = points.max(axis=0)
    span = np.maximum(upper - lower, 0.5)
    pad = 0.08 * span
    detail_ax.set_xlim(lower[0] - pad[0], upper[0] + pad[0])
    detail_ax.set_ylim(lower[1] - pad[1], upper[1] + pad[1])
    detail_ax.set_zlim(lower[2] - pad[2], upper[2] + pad[2])
    detail_ax.set_box_aspect(span + 2.0 * pad)
    detail_ax.view_init(elev=14, azim=0)
    detail_ax.set_title("Seam motif: saved flat triangles, mm scale")
    detail_ax.set_xlabel("x (mm)")
    detail_ax.set_ylabel("y (mm)")
    detail_ax.set_zlabel("z (mm)")
    figure.suptitle(
        "Analytic cylinder fixture only | material/PBR calibration UNKNOWN | no fracture labels"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def run_candidates(output_dir: Path, cases_path: Path = DEFAULT_CASES) -> int:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to reuse non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    started_clock = time.perf_counter()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    attempted: list[str] = []
    completed: list[str] = []
    skipped: list[str] = []
    case_durations: dict[str, float] = {}
    final_status = "ERROR"
    source_hash = sha256_file(Path(__file__).resolve())
    cases_hash = sha256_file(cases_path)
    base_sha = "UNKNOWN"
    current_case: str | None = None

    try:
        cases = json.loads(cases_path.read_text(encoding="utf-8"))
        baseline = load_baseline(cases)
        field = cases["field"]
        base_sha = cases["immutable_source"]["fixture_arrays_sha256"]
        candidates = list(cases["candidates"])
        for candidate_index, case in enumerate(candidates):
            case_id = str(case["case_id"])
            current_case = case_id
            attempted.append(case_id)
            case_started_clock = time.perf_counter()
            case_dir = output_dir / case_id
            case_dir.mkdir()
            try:
                target = float(case["maximum_chart_edge_mm_in_support_and_transition"])
                candidate = _build_candidate(baseline, field, target)
                checks = check_candidate(candidate, baseline, field)
                gate_pass = bool(checks["overall_candidate_gate_pass"])
                artifact_arrays = {
                    key: value
                    for key, value in candidate.items()
                    if isinstance(value, np.ndarray) and not key.startswith("_")
                }
                artifact_arrays["baseline_fixture_arrays_sha256"] = np.asarray(base_sha)
                artifact_arrays["refinement_source_sha256"] = np.asarray(source_hash)
                artifact_arrays["case_freeze_sha256"] = np.asarray(cases_hash)
                artifact_arrays["outer_radius_mm"] = np.asarray(float(baseline["outer_radius_mm"]))
                artifact_arrays["original_vertex_count"] = np.asarray(int(candidate["original_vertex_count"]))
                artifact_arrays["original_face_count"] = np.asarray(int(candidate["original_face_count"]))
                artifact_arrays["refinement_rounds"] = np.asarray(int(candidate["refinement_rounds"]))
                artifact_arrays["target_edge_mm"] = np.asarray(target)
                arrays_path = case_dir / "candidate_arrays.npz"
                np.savez_compressed(arrays_path, **artifact_arrays)
                image_path = case_dir / "flat_triangle_visual.png"
                render_saved_candidate(
                    {key: np.asarray(value) for key, value in artifact_arrays.items()},
                    image_path,
                    field,
                )
                elapsed = time.perf_counter() - case_started_clock
                case_durations[case_id] = elapsed
                report = {
                    "case_id": case_id,
                    "status": "PASS" if gate_pass else "FAIL",
                    "candidate_scope": "ONE_ANALYTIC_SAMPLE_RESOLUTION_VARIANT",
                    "physics_qualification": "UNKNOWN",
                    "real_vessel_match": "NOT_VALIDATED",
                    "material_or_physical_qualification": "NOT_VALIDATED",
                    "global_minimum_normal_wall_thickness": "UNKNOWN",
                    "self_intersection_or_general_offset_validity": "NOT_ASSESSED",
                    "fracture_labels": "NONE",
                    "independent_sample_or_ground_truth": "NO",
                    "source_sha256": source_hash,
                    "case_freeze_sha256": cases_hash,
                    "baseline_fixture_arrays_sha256": base_sha,
                    "candidate_arrays_sha256": sha256_file(arrays_path),
                    "flat_triangle_visual_sha256": sha256_file(image_path),
                    "elapsed_seconds": elapsed,
                    "field_and_resolution": case,
                    "checks": checks,
                }
                (case_dir / "checks.json").write_text(
                    json.dumps(_json_clean(report), indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                completed.append(case_id)
                stdout_lines.append(
                    f"{report['status']} {case_id}: overall_gate_pass={gate_pass}, elapsed_seconds={elapsed:.6f}"
                )
                if not gate_pass:
                    final_status = "STOPPED_AFTER_CANDIDATE_FAIL"
                    skipped = [str(item["case_id"]) for item in candidates[candidate_index + 1 :]]
                    stdout_lines.append("Stopped after first failed candidate; no finer density was attempted.")
                    break
            except Exception as exc:
                elapsed = time.perf_counter() - case_started_clock
                case_durations[case_id] = elapsed
                stderr_lines.append(f"{case_id}: {type(exc).__name__}: {exc}")
                (case_dir / "failure.txt").write_text(stderr_lines[-1] + "\n", encoding="utf-8")
                error_status = (
                    "UNKNOWN_BUDGET_EXHAUSTED"
                    if isinstance(exc, RefinementBudgetUnknown)
                    else "ERROR"
                )
                (case_dir / "checks.json").write_text(
                    json.dumps(
                        {
                            "case_id": case_id,
                            "status": error_status,
                            "candidate_scope": "ONE_ANALYTIC_SAMPLE_RESOLUTION_VARIANT",
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                            "source_sha256": source_hash,
                            "case_freeze_sha256": cases_hash,
                            "baseline_fixture_arrays_sha256": base_sha,
                            "elapsed_seconds": elapsed,
                            "candidate_gate_pass": False,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                final_status = (
                    "UNKNOWN_BUDGET_STOPPED_BEFORE_NEXT_CANDIDATE"
                    if isinstance(exc, RefinementBudgetUnknown)
                    else "ERROR_STOPPED_BEFORE_NEXT_CANDIDATE"
                )
                skipped = [str(item["case_id"]) for item in candidates[candidate_index + 1 :]]
                break
        else:
            final_status = "PASS_ALL_CANDIDATES"
    except Exception as exc:
        stderr_lines.append(f"run: {type(exc).__name__}: {exc}")
        final_status = "ERROR"

    elapsed_total = time.perf_counter() - started_clock
    ended_at = datetime.now(timezone.utc).isoformat()
    exit_code = 0 if final_status == "PASS_ALL_CANDIDATES" else 1
    (output_dir / "stdout.txt").write_text("\n".join(stdout_lines) + "\n", encoding="utf-8")
    (output_dir / "stderr.txt").write_text("\n".join(stderr_lines), encoding="utf-8")
    (output_dir / "exit_code.txt").write_text(f"{exit_code}\n", encoding="utf-8")
    (output_dir / "execution_argv.json").write_text(
        json.dumps(
            {
                "executable": sys.executable,
                "argv": [sys.executable, *sys.argv],
                "working_directory": str(Path.cwd()),
                "output_directory": str(output_dir.resolve()),
                "cases_file": str(cases_path.resolve()),
                "python_no_bytecode_requested": "-B" in sys.argv,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    run_receipt = {
        "status": final_status,
        "started_at_utc": started_at,
        "ended_at_utc": ended_at,
        "elapsed_seconds": elapsed_total,
        "source_sha256": source_hash,
        "case_freeze_sha256": cases_hash,
        "baseline_fixture_arrays_sha256": base_sha,
        "attempted_case_ids": attempted,
        "completed_case_ids": completed,
        "not_run_case_ids": skipped,
        "case_elapsed_seconds": case_durations,
        "exit_code": exit_code,
    }
    (output_dir / "run_status.json").write_text(
        json.dumps(_json_clean(run_receipt), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "run_receipt.json").write_text(
        json.dumps(_json_clean(run_receipt), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cases", default=DEFAULT_CASES, type=Path)
    args = parser.parse_args()
    exit_code = run_candidates(args.output.resolve(), args.cases.resolve())
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
