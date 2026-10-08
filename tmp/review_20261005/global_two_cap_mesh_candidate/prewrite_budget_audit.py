"""Read-only two-cap prewrite audit; computes no triangulation or candidate mesh."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path.cwd().resolve()
REVIEW = ROOT / "vesselforge" / "tmp" / "review_20261005" / "global_two_cap_mesh_candidate"
BASELINE = ROOT / "vesselforge" / "tmp" / "review_20261004" / "surface_ornament_route" / "run02" / "fixture_arrays.npz"
LOCAL_B = ROOT / "vesselforge" / "tmp" / "review_20261005" / "ornament_resume" / "local_refinement_run" / "local_b_0p25mm" / "candidate_arrays.npz"
LOCAL_B_CHECKS = LOCAL_B.parent / "checks.json"
REFINEMENT_SOURCE = ROOT / "vesselforge" / "experiments" / "surface_ornament_refinement_20261005" / "refinement_prototype.py"
CASE_FREEZE = ROOT / "vesselforge" / "experiments" / "surface_ornament_refinement_20261005" / "candidate_cases.json"
EXPECTED = {
    "baseline_npz": "b44bb78176e690d8bc92ab2fc10f0803e142a0311acee8ff3944d4e324b9b974",
    "local_b_npz": "8a2539dff0a05444951ecae6bd66ba2d849c753764dc635a4bacdf8382c6cfdf",
    "local_b_checks": "4e4c08b96bd6e7dd47a3285377979fc93fc3865a0bc1fcdd48d79397c23e14e8",
    "refinement_source": "5e946c205fb233e9354dfdde10d562597484ee38193e7930f93ce999f5840f74",
    "case_freeze": "ab89a0832366d0391b9539248cfbfab62e7ea770f3cf9b1499ee6b39b0b533c1",
}
GRID_SPACING_MM = 1.0
BOUNDARY_MARGIN_MM = 0.40
MAX_NEW_VERTICES = 2500
MAX_OUTPUT_FACES = 45000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cross2(a: np.ndarray, b: np.ndarray) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def polygon_area(poly: np.ndarray) -> float:
    return 0.5 * float(np.sum(poly[:, 0] * np.roll(poly[:, 1], -1) - poly[:, 1] * np.roll(poly[:, 0], -1)))


def inside_convex(point: np.ndarray, polygon_ccw: np.ndarray, margin: float) -> bool:
    for i, a in enumerate(polygon_ccw):
        edge = polygon_ccw[(i + 1) % len(polygon_ccw)] - a
        distance = cross2(edge, point - a) / float(np.linalg.norm(edge))
        if distance < margin - 1e-12:
            return False
    return True


def lattice_count(polygon_xy: np.ndarray) -> dict[str, Any]:
    poly = polygon_xy if polygon_area(polygon_xy) >= 0 else polygon_xy[::-1].copy()
    spacing = GRID_SPACING_MM
    row_height = spacing * math.sqrt(3.0) / 2.0
    low, high = poly.min(axis=0), poly.max(axis=0)
    first_row = int(math.ceil(low[1] / row_height))
    last_row = int(math.floor(high[1] / row_height))
    points: list[tuple[float, float]] = []
    rejected = 0
    for row in range(first_row, last_row + 1):
        y = row * row_height
        offset = 0.5 * spacing if row % 2 else 0.0
        first_col = int(math.ceil((low[0] - offset) / spacing))
        last_col = int(math.floor((high[0] - offset) / spacing))
        for col in range(first_col, last_col + 1):
            point = np.asarray((col * spacing + offset, y), dtype=np.float64)
            if float(np.linalg.norm(point)) <= 1e-10:
                continue  # use the retained frozen center vertex
            if inside_convex(point, poly, BOUNDARY_MARGIN_MM):
                points.append((float(point[0]), float(point[1])))
            else:
                rejected += 1
    if len(points) != len(set(points)):
        raise ValueError("triangular lattice produced duplicate coordinates")
    return {
        "new_interior_lattice_vertex_count": len(points),
        "examined_grid_points_inside_bbox_excluding_center": len(points) + rejected,
        "fixed_boundary_margin_mm": BOUNDARY_MARGIN_MM,
        "fixed_spacing_mm": GRID_SPACING_MM,
        "polygon_area_mm2": polygon_area(poly),
        "boundary_vertex_count": int(len(poly)),
    }


def triangle_quality(vertices: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    tri = vertices[faces.astype(np.int64)]
    e0 = tri[:, 1] - tri[:, 0]
    e1 = tri[:, 2] - tri[:, 1]
    e2 = tri[:, 0] - tri[:, 2]
    lengths = np.column_stack((np.linalg.norm(e0, axis=1), np.linalg.norm(e1, axis=1), np.linalg.norm(e2, axis=1)))
    double_area = np.linalg.norm(np.cross(e0, tri[:, 2] - tri[:, 0]), axis=1)
    q = np.divide(4.0 * math.sqrt(3.0) * (0.5 * double_area), np.sum(lengths * lengths, axis=1),
                  out=np.zeros_like(double_area), where=np.sum(lengths * lengths, axis=1) > 0.0)
    aspect = np.divide(np.max(lengths, axis=1) ** 2, double_area,
                       out=np.full_like(double_area, np.inf), where=double_area > 0.0)
    return q, aspect


def summarize_faces(vertices: np.ndarray, faces: np.ndarray, face_ids: np.ndarray, source_ids: np.ndarray) -> dict[str, Any]:
    local = faces[face_ids]
    q, aspect = triangle_quality(vertices, local)
    min_q_i = int(np.argmin(q))
    max_ar_i = int(np.argmax(aspect))
    def loc(i: int) -> dict[str, Any]:
        fid = int(face_ids[i])
        xyz = vertices[faces[fid].astype(np.int64)]
        return {
            "local_b_face_id": fid,
            "baseline_source_face_id": int(source_ids[fid]),
            "centroid_relief_xyz_mm": [float(x) for x in xyz.mean(axis=0)],
            "face_vertex_ids": [int(x) for x in faces[fid]],
        }
    return {
        "face_count": int(len(face_ids)),
        "minimum_Q": float(q[min_q_i]),
        "minimum_Q_worst_face": loc(min_q_i),
        "maximum_aspect_longest_edge_over_minimum_altitude": float(aspect[max_ar_i]),
        "maximum_aspect_worst_face": loc(max_ar_i),
        "zero_area_count": int(np.count_nonzero(~np.isfinite(aspect))),
    }


def find_cap(baseline: dict[str, np.ndarray], z: float, radius: float, surface_id: str) -> tuple[dict[str, Any], np.ndarray, int, np.ndarray]:
    rest = np.asarray(baseline["vertices_rest_xyz_mm"], dtype=np.float64)
    faces = np.asarray(baseline["faces"], dtype=np.int64)
    tri = rest[faces]
    z_ok = np.all(np.abs(tri[:, :, 2] - z) <= 1e-12, axis=1)
    radii = np.linalg.norm(tri[:, :, :2], axis=2)
    center_count = np.count_nonzero(radii <= 1e-12, axis=1)
    boundary_count = np.count_nonzero(np.abs(radii - radius) <= 1e-9, axis=1)
    ids = np.flatnonzero(z_ok & np.all(radii <= radius + 1e-10, axis=1) & (center_count == 1) & (boundary_count == 2))
    if len(ids) != 128:
        raise ValueError(f"{surface_id}: expected 128 source triangles with one center and two interface vertices; got {len(ids)}")
    center_ids = np.unique(faces[ids][radii[ids] <= 1e-12])
    if len(center_ids) != 1:
        raise ValueError(f"{surface_id}: expected a single exact center vertex")
    center_id = int(center_ids[0])
    boundary_ids = np.unique(faces[ids][faces[ids] != center_id])
    if len(boundary_ids) != 128:
        raise ValueError(f"{surface_id}: expected 128 unchanged interface vertices; got {len(boundary_ids)}")
    radial = np.linalg.norm(rest[boundary_ids, :2], axis=1)
    if not np.allclose(radial, radius, rtol=0.0, atol=1e-9):
        raise ValueError(f"{surface_id}: boundary does not lie on the pinned radius")
    theta = np.arctan2(rest[boundary_ids, 1], rest[boundary_ids, 0])
    boundary_ids = boundary_ids[np.argsort(theta, kind="stable")]
    polygon = rest[boundary_ids, :2].copy()
    if polygon_area(polygon) <= 0.0:
        raise ValueError(f"{surface_id}: ordered cap boundary does not form a positive-area CCW chart")
    record = {
        "physical_surface_id": surface_id,
        "plane_z_mm": z,
        "chart": "world_XY_mm_at_pinned_z",
        "orientation": "outward_-z" if z == 0.0 else "inward_+z",
        "pinned_radius_mm": radius,
        "baseline_source_face_ids": ids.astype(int).tolist(),
        "center_vertex_id": center_id,
        "unchanged_boundary_vertex_ids_angle_sorted": boundary_ids.astype(int).tolist(),
        "unchanged_boundary_vertex_count": int(len(boundary_ids)),
        "source_face_count": int(len(ids)),
        "polygon_area_mm2": polygon_area(polygon),
    }
    return record, ids.astype(np.int64), center_id, boundary_ids.astype(np.int64)


def main() -> int:
    start = datetime.now(timezone.utc).isoformat()
    input_paths = {
        "baseline_npz": BASELINE,
        "local_b_npz": LOCAL_B,
        "local_b_checks": LOCAL_B_CHECKS,
        "refinement_source": REFINEMENT_SOURCE,
        "case_freeze": CASE_FREEZE,
    }
    before = {name: sha256(path) for name, path in input_paths.items()}
    for name, expected in EXPECTED.items():
        if before[name] != expected:
            raise ValueError(f"pinned input hash mismatch: {name}={before[name]}")
    with np.load(BASELINE, allow_pickle=False) as z:
        baseline = {k: z[k].copy() for k in z.files}
    with np.load(LOCAL_B, allow_pickle=False) as z:
        local_b = {k: z[k].copy() for k in z.files}

    base_rest = np.asarray(baseline["vertices_rest_xyz_mm"], dtype=np.float64)
    base_faces = np.asarray(baseline["faces"], dtype=np.int64)
    input_rest = np.asarray(local_b["vertices_rest_xyz_mm"], dtype=np.float64)
    input_relief = np.asarray(local_b["vertices_relief_xyz_mm"], dtype=np.float64)
    input_faces = np.asarray(local_b["faces"], dtype=np.int64)
    source_ids = np.asarray(local_b["source_face_ids"], dtype=np.int64)
    if str(np.asarray(local_b["baseline_fixture_arrays_sha256"]).item()) != EXPECTED["baseline_npz"]:
        raise ValueError("local-B embedded baseline hash disagrees with pinned baseline")
    if not np.array_equal(input_rest[:len(base_rest)], base_rest):
        raise ValueError("local-B rest geometry does not retain the exact frozen baseline vertex prefix")
    if len(input_faces) != len(source_ids) or np.any(source_ids < 0) or np.any(source_ids >= len(base_faces)):
        raise ValueError("local-B source-face identity array is malformed")

    outer, outer_ids, outer_center, outer_boundary = find_cap(baseline, 0.0, 20.0, "bottom_exterior_z0")
    inner, inner_ids, inner_center, inner_boundary = find_cap(baseline, 2.0, 17.0, "interior_floor_z2")
    if np.intersect1d(outer_ids, inner_ids).size:
        raise ValueError("the two physical caps must have disjoint baseline face identities")
    caps = [(outer, outer_ids, outer_center, outer_boundary), (inner, inner_ids, inner_center, inner_boundary)]
    cap_source_union = np.concatenate((outer_ids, inner_ids))
    cap_local_face_mask = np.isin(source_ids, cap_source_union)
    cap_local_face_ids = np.flatnonzero(cap_local_face_mask)
    if len(cap_local_face_ids) != 256:
        raise ValueError(f"expected exactly 256 one-to-one local-B cap faces; got {len(cap_local_face_ids)}")
    cap_child_identity: dict[str, Any] = {}
    for cap, ids, center_id, boundary_ids in caps:
        child_face_ids: list[int] = []
        for parent_id in ids:
            children = np.flatnonzero(source_ids == int(parent_id))
            if len(children) != 1:
                raise ValueError(f"{cap['physical_surface_id']}: source parent {int(parent_id)} has {len(children)} local-B children")
            child_id = int(children[0])
            child_face_ids.append(child_id)
            if not np.array_equal(np.sort(input_faces[child_id]), np.sort(base_faces[int(parent_id)])):
                raise ValueError(f"{cap['physical_surface_id']}: local-B child connectivity differs from its actual baseline parent")
        cap["local_b_output_face_ids"] = child_face_ids
        cap_child_identity[cap["physical_surface_id"]] = {
            "one_to_one_parent_child_mapping": True,
            "child_face_count": len(child_face_ids),
            "rest_xyz_vertex_prefix_matches_baseline_bitwise": True,
            "center_vertex_id": center_id,
            "boundary_vertex_count": int(len(boundary_ids)),
        }

    noncap_face_ids = np.flatnonzero(~cap_local_face_mask)
    all_face_ids = np.arange(len(input_faces), dtype=np.int64)
    q_all, ar_all = triangle_quality(input_relief, input_faces)
    noncap_relief = summarize_faces(input_relief, input_faces, noncap_face_ids, source_ids)
    cap_quality: dict[str, Any] = {}
    for cap in (outer, inner):
        ids = np.asarray(cap["local_b_output_face_ids"], dtype=np.int64)
        q, ar = triangle_quality(input_relief, input_faces[ids])
        cap_quality[cap["physical_surface_id"]] = {
            "face_count": int(len(ids)),
            "minimum_Q": float(np.min(q)),
            "maximum_aspect_longest_edge_over_minimum_altitude": float(np.max(ar)),
        }
    outer_grid = lattice_count(base_rest[outer_boundary, :2])
    inner_grid = lattice_count(base_rest[inner_boundary, :2])
    p_total = outer_grid["new_interior_lattice_vertex_count"] + inner_grid["new_interior_lattice_vertex_count"]
    predicted_faces = len(input_faces) - 256 + 2 * p_total + 256
    after = {name: sha256(path) for name, path in input_paths.items()}
    if before != after:
        raise RuntimeError("one or more frozen inputs changed while the read-only audit ran")

    q_i = int(np.argmin(q_all))
    ar_i = int(np.argmax(ar_all))
    target = {
        "two_caps": [outer, inner],
        "source_identity_method": "baseline face indices from exact pinned planar triangles at z=0/R20 and z=2/R17, mapped to local-B through source_face_ids",
        "cap_local_b_face_ids_total": int(len(cap_local_face_ids)),
        "cap_parent_child_identity": cap_child_identity,
        "prewrite_input_global_quality_relief": {
            "face_count": int(len(input_faces)),
            "minimum_Q": float(np.min(q_all)),
            "minimum_Q_face_id": q_i,
            "minimum_Q_source_face_id": int(source_ids[q_i]),
            "maximum_aspect_longest_edge_over_minimum_altitude": float(np.max(ar_all)),
            "maximum_aspect_face_id": ar_i,
            "maximum_aspect_source_face_id": int(source_ids[ar_i]),
        },
        "independent_prewrite_leftover_noncap_quality_relief": noncap_relief,
        "unchanged_cap_input_quality_relief": cap_quality,
        "fixed_lattice_counts": {
            "bottom_exterior_z0_R20": outer_grid,
            "interior_floor_z2_R17": inner_grid,
            "sum_new_interior_vertices": int(p_total),
        },
        "Euler_disk_face_count_check": {
            "formula": "F=2P+B, with the frozen center and 128 boundary vertices retained and P new lattice interior vertices",
            "bottom_exterior_z0_R20_output_faces": int(2 * outer_grid["new_interior_lattice_vertex_count"] + 128),
            "interior_floor_z2_R17_output_faces": int(2 * inner_grid["new_interior_lattice_vertex_count"] + 128),
            "predicted_total_output_faces": int(predicted_faces),
        },
        "fixed_preflight_budgets": {
            "max_new_vertices": MAX_NEW_VERTICES,
            "new_vertex_budget_fits": bool(p_total <= MAX_NEW_VERTICES),
            "max_output_faces": MAX_OUTPUT_FACES,
            "face_budget_fits": bool(predicted_faces <= MAX_OUTPUT_FACES),
            "max_patch_records": 15000,
            "max_patch_vertices": 60000,
            "max_parents_per_output_face": 128,
            "patch_counts_geometry_clipping_not_computed": True,
            "patch_budgets_to_be_enforced_before_candidate_save": True,
        },
        "global_quality_gate_design": {
            "q_gain_required": "candidate global minimum Q minus prewrite local-B global minimum Q must exceed 64*float64_epsilon*max(1,|before|,|after|)",
            "aspect_gain_required": "prewrite local-B maximum aspect minus candidate global maximum aspect must exceed 64*float64_epsilon*max(1,|before|,|after|)",
            "unaffected_noncap_metrics_are_frozen_comparison_floor": True,
            "target_thresholds_are_quality_only_and_unchanged": {"cap_minimum_Q": 0.35, "cap_maximum_aspect": 5.0},
            "geometry_quality_does_not_claim_tet_or_mechanical_h_quality": True,
        },
        "no_candidate_geometry_or_triangulation_computed": True,
    }
    receipt = {
        "audit_id": "global_two_cap_mesh_candidate_20261005_prewrite_v1",
        "status": "PREWRITE_AUDIT_PASS" if p_total <= MAX_NEW_VERTICES and predicted_faces <= MAX_OUTPUT_FACES else "PREWRITE_BUDGET_FAIL",
        "started_at_utc": start,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "argv": sys.argv,
        "input_sha256_before": before,
        "input_sha256_after": after,
        "data": target,
    }
    out = REVIEW / "prewrite_budget_audit.json"
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False))
    return 0 if receipt["status"] == "PREWRITE_AUDIT_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
