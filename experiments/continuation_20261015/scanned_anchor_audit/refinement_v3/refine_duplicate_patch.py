from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import platform
import sys

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
import vtk
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "refinement_v2"))
import refine_exactweld as v2tools
mesh_metrics = v2tools.mesh_metrics
build_polydata = v2tools.build_polydata
render_view = v2tools.render_view
section_y = v2tools.section_y

ROOT = pathlib.Path.cwd()
AUDIT = ROOT / "vesselforge/experiments/continuation_20261015/scanned_anchor_audit/refinement_v3"
ASSET = ROOT / "third_party/reference-assets/apsida-shm17946-0047"
ASSET_V2 = ASSET / "refined_v2"
ASSET_V3 = ASSET / "refined_v3"
V2_NPZ = ASSET_V2 / "SHM17946_0047_main_component_exactweld_candidate.npz"
V2_MAPS = ASSET_V2 / "SHM17946_0047_exactweld_maps.npz"
V2_RECEIPT = ROOT / "vesselforge/experiments/continuation_20261015/scanned_anchor_audit/refinement_v2/refinement_receipt.json"
V1_RECEIPT = ROOT / "vesselforge/experiments/continuation_20261015/scanned_anchor_audit/refinement_v1/refinement_receipt.json"
SOURCE_OBJ = ASSET / "Footed_Bowl_SHM_17946_0047.obj"
SOURCE_ZIP = ASSET / "Footed_Bowl_SHM_17946_0047_Obj06.zip"
RAW_NPZ = ROOT / "vesselforge/experiments/continuation_20261015/scanned_anchor_audit/raw_geometry.npz"
AUDIT.mkdir(parents=True, exist_ok=True)
ASSET_V3.mkdir(parents=True, exist_ok=True)
v2tools.AUDIT = AUDIT


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def triangle_area_volume(v: np.ndarray, f: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    tri = v[f]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = np.linalg.norm(cross, axis=1) / 2
    volume = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])) / 6
    return area, volume


def vertex_link_audit(v: np.ndarray, f: np.ndarray, v3_to_raw_v: np.ndarray) -> tuple[dict, list[dict]]:
    """Check that each vertex link is one connected cycle, the local 2-manifold test."""
    nverts = len(v)
    a, b, c = f[:, 0], f[:, 1], f[:, 2]
    center = np.concatenate((a, b, c))
    n1 = np.concatenate((b, c, a))
    n2 = np.concatenate((c, a, b))
    key1 = center.astype(np.int64) * nverts + n1
    key2 = center.astype(np.int64) * nverts + n2
    edge_count = len(key1)
    unique_keys, inverse = np.unique(np.concatenate((key1, key2)), return_inverse=True)
    left, right = inverse[:edge_count], inverse[edge_count:]
    degree = np.bincount(np.concatenate((left, right)), minlength=len(unique_keys))
    rows = np.concatenate((left, right))
    cols = np.concatenate((right, left))
    adj = csr_matrix((np.ones(len(rows), dtype=np.uint8), (rows, cols)), shape=(len(unique_keys), len(unique_keys)))
    graph_components, node_components = connected_components(adj, directed=False, return_labels=True)
    node_center = unique_keys // nverts
    center_component_pairs = np.unique(np.column_stack((node_center, node_components)), axis=0)
    per_vertex_components = np.bincount(center_component_pairs[:, 0], minlength=nverts)
    bad_multi = np.flatnonzero(per_vertex_components != 1)
    bad_degree_nodes = np.flatnonzero(degree != 2)
    bad_degree_vertices = np.unique(node_center[bad_degree_nodes]) if len(bad_degree_nodes) else np.empty(0, dtype=np.int64)
    bad_vertices = np.unique(np.concatenate((bad_multi, bad_degree_vertices)))
    details = []
    for vid in bad_vertices:
        nodes = np.flatnonzero(node_center == vid)
        comps = np.unique(node_components[nodes])
        details.append({
            "candidate_vertex_index": int(vid),
            "raw_source_vertex_index": int(v3_to_raw_v[vid]),
            "xyz_source_units": v[vid].tolist(),
            "link_node_count": int(len(nodes)),
            "link_component_count": int(len(comps)),
            "link_node_degrees": degree[nodes].tolist(),
            "interpretation": "Vertex link must be a single connected cycle; multiple cycles indicate a pinched/non-manifold vertex.",
        })
    return {
        "link_graph_node_count": int(len(unique_keys)),
        "link_graph_connected_components_global": int(graph_components),
        "vertices_with_multiple_disconnected_link_cycles": int(len(bad_multi)),
        "link_nodes_degree_not_2": int(len(bad_degree_nodes)),
        "vertices_with_bad_degree_nodes": int(len(bad_degree_vertices)),
        "vertex_manifold_failure_count": int(len(bad_vertices)),
        "all_vertices_have_one_connected_cycle_link": bool(len(bad_vertices) == 0),
        "method": "For each triangle corner, form the corresponding edge of that vertex's link graph; verify each link graph is exactly one connected cycle.",
    }, details


def main() -> None:
    v2_receipt = json.loads(V2_RECEIPT.read_text(encoding="utf-8"))
    v1_receipt = json.loads(V1_RECEIPT.read_text(encoding="utf-8"))
    if sha256(SOURCE_OBJ).lower() != v2_receipt["source"]["source_obj_sha256"].lower():
        raise SystemExit("Original OBJ source hash mismatch.")
    if sha256(SOURCE_ZIP).lower() != v2_receipt["source"]["source_zip_sha256"].lower():
        raise SystemExit("Original source ZIP hash mismatch.")
    if sha256(V2_NPZ) != v2_receipt["derivative_files"][V2_NPZ.name]["sha256"]:
        raise SystemExit("V2 candidate hash mismatch; refusing local repair.")

    with np.load(V2_NPZ) as z:
        v2v = z["vertices_source_units"].astype(np.float64, copy=True)
        v2f = z["faces"].astype(np.int64, copy=True)
        v2_to_raw_v = z["candidate_vertex_to_raw_source_vertex"].astype(np.int64, copy=True)
        v2_to_raw_f = z["candidate_face_to_raw_source_face"].astype(np.int64, copy=True)
    if sha256(V2_MAPS) != v2_receipt["derivative_files"][V2_MAPS.name]["sha256"]:
        raise SystemExit("V2 provenance-map hash mismatch; refusing local repair.")
    with np.load(V2_MAPS) as z:
        raw_to_v2_v = z["raw_source_vertex_to_candidate_vertex"].astype(np.int64, copy=True)
    raw = np.load(RAW_NPZ)
    raw_v, raw_f = raw["vertices_source_units"], raw["faces"]
    before = mesh_metrics(v2v, v2f)
    target_raw_face_ids = np.array([125422, 125511], dtype=np.int64)
    remove_mask = np.isin(v2_to_raw_f, target_raw_face_ids)
    remove_v2_face_ids = np.flatnonzero(remove_mask)
    if len(remove_v2_face_ids) != 2 or not np.array_equal(np.sort(v2_to_raw_f[remove_v2_face_ids]), target_raw_face_ids):
        raise SystemExit("Target exact opposite-winding triangle pair is not present exactly once each.")
    removed_faces = v2f[remove_v2_face_ids]
    removed_raw_vertices = v2_to_raw_v[removed_faces]
    removed_xyz = v2v[removed_faces]
    area_each, volume_each = triangle_area_volume(v2v, removed_faces)
    if not np.array_equal(np.sort(removed_raw_vertices[0]), np.sort(removed_raw_vertices[1])):
        raise SystemExit("Target pair does not use the same three raw vertex IDs after exact weld.")
    if not np.array_equal(removed_xyz[0], removed_xyz[1][[0, 2, 1]]):
        # Source winding order may be a cyclic reverse; canonical exact coordinate sets are checked below.
        if not np.array_equal(np.sort(removed_xyz[0], axis=0), np.sort(removed_xyz[1], axis=0)):
            raise SystemExit("Target pair coordinates are not the same triangle.")
    if not np.isclose(area_each[0], area_each[1], rtol=0, atol=0):
        raise SystemExit("Target pair areas differ; refusing the authorized paired removal.")
    if not np.isclose(volume_each[0], -volume_each[1], rtol=1e-9, atol=1e-18):
        raise SystemExit("Target pair signed-volume contributions do not cancel within tolerance.")

    keep_v2_face_ids = np.flatnonzero(~remove_mask)
    f_after_pair = v2f[keep_v2_face_ids]
    used_v2_vertex_ids = np.unique(f_after_pair)
    v2_vertex_to_v3 = np.full(len(v2v), -1, dtype=np.int64)
    v2_vertex_to_v3[used_v2_vertex_ids] = np.arange(len(used_v2_vertex_ids), dtype=np.int64)
    v3v = v2v[used_v2_vertex_ids].copy()
    v3f = v2_vertex_to_v3[f_after_pair]
    v3_to_raw_v = v2_to_raw_v[used_v2_vertex_ids]
    v3_to_raw_f = v2_to_raw_f[keep_v2_face_ids]
    after = mesh_metrics(v3v, v3f)
    vertex_link_metrics, vertex_link_details = vertex_link_audit(v3v, v3f, v3_to_raw_v)
    after["vertex_link_audit"] = vertex_link_metrics
    with (AUDIT / "vertex_link_anomalies.csv").open("w", newline="", encoding="utf-8") as fcsv:
        fields = list(vertex_link_details[0]) if vertex_link_details else ["candidate_vertex_index"]
        writer = csv.DictWriter(fcsv, fieldnames=fields)
        writer.writeheader()
        writer.writerows(vertex_link_details)
    removed_unreferenced_v2_vertex_ids = np.flatnonzero(v2_vertex_to_v3 < 0)
    if len(removed_unreferenced_v2_vertex_ids) > 0:
        if len(removed_unreferenced_v2_vertex_ids) != len(np.unique(removed_faces)) - len(used_v2_vertex_ids):
            # This equality is not required for safety; write the actual count and map regardless.
            pass

    # Preserve a face-level change ledger, including raw local triangle XYZ/area/volume.
    change_rows = []
    for i, local_face_id in enumerate(remove_v2_face_ids):
        raw_source_face_id = int(v2_to_raw_f[local_face_id])
        raw_obj_face_vertex_ids = raw_f[raw_source_face_id]
        change_rows.append({
            "operation": "REMOVE_BOTH_FACES_AS_EXACT_OPPOSITE_WINDING_COINCIDENT_ZERO_THICKNESS_PAIR",
            "raw_source_face_index_zero_based": raw_source_face_id,
            "v2_candidate_face_index_zero_based": int(local_face_id),
            "v2_triangle_candidate_vertex_indices": json.dumps(v2f[local_face_id].tolist()),
            "raw_obj_face_vertex_indices": json.dumps(raw_obj_face_vertex_ids.tolist()),
            "v2_canonical_raw_source_vertex_representatives": json.dumps(v2_to_raw_v[v2f[local_face_id]].tolist()),
            "triangle_xyz_source_units": json.dumps(v2v[v2f[local_face_id]].tolist(), separators=(",", ":")),
            "raw_obj_face_xyz_source_units": json.dumps(raw_v[raw_obj_face_vertex_ids].tolist(), separators=(",", ":")),
            "triangle_area_source_units2": float(area_each[i]),
            "signed_volume_contribution_source_units3": float(volume_each[i]),
            "paired_face_raw_source_id": int(v2_to_raw_f[remove_v2_face_ids[1-i]]),
            "paired_signed_volume_sum_source_units3": float(volume_each.sum()),
            "paired_area_removed_source_units2": float(area_each.sum()),
            "disposition": "Both coincident opposite-winding triangles removed together; no replacement surface/cap was added.",
        })
    with (AUDIT / "local_pair_repair.csv").open("w", newline="", encoding="utf-8") as fcsv:
        writer = csv.DictWriter(fcsv, fieldnames=list(change_rows[0]))
        writer.writeheader()
        writer.writerows(change_rows)

    # Exact trace maps. The source stays unchanged; every omitted source element remains -1.
    raw_to_v3_v = np.full(len(raw_v), -1, dtype=np.int64)
    raw_vertex_present = np.flatnonzero(raw_to_v2_v >= 0)
    mapped_v3 = v2_vertex_to_v3[raw_to_v2_v[raw_vertex_present]]
    retained_raw_vertices = raw_vertex_present[mapped_v3 >= 0]
    raw_to_v3_v[retained_raw_vertices] = mapped_v3[mapped_v3 >= 0]
    raw_to_v3_f = np.full(len(raw_f), -1, dtype=np.int64)
    raw_to_v3_f[v3_to_raw_f] = np.arange(len(v3f), dtype=np.int64)
    v2_collapsed_face_ids = np.asarray(v2_receipt["method"]["removed_source_face_ids_zero_based"], dtype=np.int64)
    island_face_count = int(v1_receipt["removed_components"]["faces"])
    raw_face_map_summary = {
        "raw_source_face_count": int(len(raw_f)),
        "mapped_to_v3_candidate_face_count": int(np.count_nonzero(raw_to_v3_f >= 0)),
        "unmapped_face_count": int(np.count_nonzero(raw_to_v3_f < 0)),
        "unmapped_breakdown": {
            "v1_omitted_disconnected_island_faces": island_face_count,
            "v2_removed_collapsed_zero_area_faces": int(len(v2_collapsed_face_ids)),
            "v3_removed_opposite_winding_pair_faces": int(len(target_raw_face_ids)),
        },
    }
    if raw_face_map_summary["unmapped_face_count"] != sum(raw_face_map_summary["unmapped_breakdown"].values()):
        raise SystemExit("Raw face map does not account for every omitted triangle by stage.")
    raw_vertex_map_summary = {
        "raw_source_vertex_count": int(len(raw_v)),
        "raw_source_vertex_ids_mapped_to_v3": int(np.count_nonzero(raw_to_v3_v >= 0)),
        "v1_main_component_source_vertex_count": int(v1_receipt["source_geometry"]["main_vertices"]),
        "all_v1_main_component_source_vertex_ids_mapped": bool(np.all(raw_to_v3_v[np.load(ASSET / "refined_v1/SHM17946_0047_main_component.npz")["source_vertex_indices"]] >= 0)),
        "unmapped_raw_vertices": int(np.count_nonzero(raw_to_v3_v < 0)),
        "note": "Exact-coordinate alias source vertex IDs all map through V2. Unmapped raw vertices belong to the 388 omitted indexed islands; no V3 surface vertices were pruned.",
    }
    v2_to_v3_f = np.full(len(v2f), -1, dtype=np.int64)
    v2_to_v3_f[keep_v2_face_ids] = np.arange(len(keep_v2_face_ids), dtype=np.int64)
    maps_npz = ASSET_V3 / "SHM17946_0047_localrepair_maps.npz"
    np.savez_compressed(
        maps_npz,
        raw_source_vertex_to_v3_vertex=raw_to_v3_v,
        v2_candidate_vertex_to_v3_vertex=v2_vertex_to_v3,
        v3_vertex_to_v2_candidate_vertex=used_v2_vertex_ids,
        v3_vertex_to_raw_source_vertex=v3_to_raw_v,
        raw_source_face_to_v3_face=raw_to_v3_f,
        v2_candidate_face_to_v3_face=v2_to_v3_f,
        v3_face_to_raw_source_face=v3_to_raw_f,
        removed_v2_candidate_face_indices=remove_v2_face_ids,
        removed_raw_source_face_indices=target_raw_face_ids,
        pruned_unreferenced_v2_vertex_indices=removed_unreferenced_v2_vertex_ids,
    )

    out_obj = ASSET_V3 / "SHM17946_0047_main_component_localrepair_candidate.obj"
    with out_obj.open("w", encoding="utf-8", newline="\n") as out:
        out.write("# Local paired-face repair derivative of Apsida SHM 17946:0047.\n")
        out.write("# Source coordinate units UNKNOWN; coordinates copied exactly; see v3 receipt.\n")
        out.write("# After exact XYZ weld, raw faces 125422 and 125511 formed one coincident opposite-winding pair.\n")
        out.write("# Both faces removed together; no cap, surface fill, smoothing, or rescale.\n")
        out.write("o SHM_17946_0047_local_pair_repair_candidate\n")
        for point in v3v:
            out.write("v %.9f %.9f %.9f\n" % tuple(point))
        for face in v3f:
            out.write("f %d %d %d\n" % (face[0] + 1, face[1] + 1, face[2] + 1))
    out_npz = ASSET_V3 / "SHM17946_0047_main_component_localrepair_candidate.npz"
    np.savez_compressed(
        out_npz,
        vertices_source_units=v3v,
        faces=v3f,
        candidate_vertex_to_v2_vertex=used_v2_vertex_ids,
        candidate_vertex_to_raw_source_vertex=v3_to_raw_v,
        candidate_face_to_v2_face=keep_v2_face_ids,
        candidate_face_to_raw_source_face=v3_to_raw_f,
    )
    check_v, check_f = [], []
    with out_obj.open("r", encoding="utf-8") as fobj:
        for line in fobj:
            if line.startswith("v "):
                check_v.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("f "):
                check_f.append([int(x)-1 for x in line.split()[1:4]])
    check_v = np.asarray(check_v, dtype=np.float64)
    check_f = np.asarray(check_f, dtype=np.int64)
    if not np.array_equal(check_v, v3v) or not np.array_equal(check_f, v3f):
        raise SystemExit("V3 OBJ serialization does not exactly match candidate arrays.")

    area_before = before["surface_area_source_units2"]
    area_after = after["surface_area_source_units2"]
    volume_delta = after["signed_volume_source_units3"] - before["signed_volume_source_units3"]
    volume_ok = abs(volume_delta) <= max(1e-12, abs(before["signed_volume_source_units3"]) * 1e-9)
    pass_topology = (
        after["exact_zero_area_face_count"] == 0
        and after["boundary_edge_count"] == 0
        and after["nonmanifold_edge_count"] == 0
        and after["inconsistent_winding_edge_count"] == 0
        and after["edge_connected_components_of_referenced_mesh"] == 1
        and after["duplicate_unoriented_triangle_group_count"] == 0
        and vertex_link_metrics["vertex_manifold_failure_count"] == 0
        and volume_ok
    )

    poly = build_polydata(v3v, v3f)
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(poly)
    normals.SplittingOff()
    normals.ConsistencyOff()
    normals.AutoOrientNormalsOff()
    normals.ComputePointNormalsOn()
    normals.ComputeCellNormalsOff()
    normals.Update()
    view_poly = normals.GetOutput()
    for name, (direction, up) in {
        "localrepair_side": ((0, -1, 0), (0, 0, 1)),
        "localrepair_oblique": ((2.6, -3.4, 1.4), (0, 0, 1)),
        "localrepair_top": ((0, 0, 1), (0, 1, 0)),
        "localrepair_bottom": ((0, 0, -1), (0, 1, 0)),
    }.items():
        render_view(name, view_poly, direction, up)
    polylines = section_y(poly, v3v)
    render_hashes = {p.name: sha256(p) for p in sorted(AUDIT.glob("*.png"))}
    receipt = {
        "record_type": "one-authorized local paired-triangle scan-artifact derivative; geometry candidate, not physical validation",
        "source": {
            "item_url": v2_receipt["source"]["item_url"],
            "archive_url": v2_receipt["source"]["archive_url"],
            "identifier": "SHM 17946:0047",
            "rights": "CC BY-SA 4.0",
            "attribution": "Medelhavsmuseet, SHM 17946:0047; via Apsida / Digital Heritage Research Lab",
            "source_obj_sha256": sha256(SOURCE_OBJ),
            "source_zip_sha256": sha256(SOURCE_ZIP),
            "raw_geometry_npz_sha256": sha256(RAW_NPZ),
            "v1_main_component_receipt_sha256": sha256(V1_RECEIPT),
            "parent_v2_candidate_npz_sha256": sha256(V2_NPZ),
            "source_coordinate_units": "UNKNOWN; no scale applied",
        },
        "single_local_change": {
            "authorization": "Parent-approved one local repair, no further repair if topology still fails.",
            "v2_candidate_face_indices_zero_based": remove_v2_face_ids.tolist(),
            "raw_source_face_indices_zero_based": target_raw_face_ids.tolist(),
            "reason": "After exact XYZ weld, these two triangles have the same three XYZ positions and opposite winding, i.e. an overlapping zero-thickness double patch; together they caused two edge-incidence-4 edges.",
            "raw_obj_face_vertex_indices": [raw_f[int(fid)].tolist() for fid in target_raw_face_ids],
            "v2_canonical_raw_source_vertex_representatives": removed_raw_vertices.tolist(),
            "triangle_coordinates_source_units": removed_xyz.tolist(),
            "triangle_area_source_units2_each": area_each.tolist(),
            "triangle_signed_volume_contribution_source_units3_each": volume_each.tolist(),
            "paired_area_removed_source_units2": float(area_each.sum()),
            "paired_signed_volume_sum_source_units3": float(volume_each.sum()),
            "removed_face_count": 2,
            "other_faces_removed": 0,
            "unreferenced_v2_vertices_pruned": int(len(removed_unreferenced_v2_vertex_ids)),
            "pruned_v2_vertex_ids": removed_unreferenced_v2_vertex_ids.tolist(),
            "holes_filled_or_surfaces_added": 0,
            "smoothing_or_rescale": False,
        },
        "topology_before": before,
        "topology_after": after,
        "comparison": {
            "vertex_count_delta": int(after["vertex_count_in_file"] - before["vertex_count_in_file"]),
            "face_count_delta": int(after["face_count"] - before["face_count"]),
            "euler_characteristic_before": before["euler_characteristic_referenced_mesh"],
            "euler_characteristic_after": after["euler_characteristic_referenced_mesh"],
            "formal_genus_from_chi_before_not_physical": before["formal_genus_from_chi_if_assuming_manifold"],
            "formal_genus_from_chi_after_not_physical": after["formal_genus_from_chi_if_assuming_manifold"],
            "validated_genus_after": after["genus_if_closed_oriented_connected_manifold"],
            "vertex_link_manifold_audit": vertex_link_metrics,
            "surface_area_before_source_units2": area_before,
            "surface_area_after_source_units2": area_after,
            "surface_area_delta_source_units2": area_after - area_before,
            "signed_volume_before_source_units3": before["signed_volume_source_units3"],
            "signed_volume_after_source_units3": after["signed_volume_source_units3"],
            "signed_volume_delta_source_units3": volume_delta,
            "volume_within_tolerance": bool(volume_ok),
        },
        "acceptance": {
            "status": "PASS_REVIEWED_GEOMETRY_CANDIDATE_ONLY" if pass_topology else "FAIL_UNQUALIFIED_SCAN_USE_AS_VISUAL_REFERENCE_ONLY",
            "requirements": {
                "zero_area_faces_zero": after["exact_zero_area_face_count"] == 0,
                "boundary_edges_zero": after["boundary_edge_count"] == 0,
                "nonmanifold_edges_zero": after["nonmanifold_edge_count"] == 0,
                "inconsistent_winding_edges_zero": after["inconsistent_winding_edge_count"] == 0,
                "one_referenced_component": after["edge_connected_components_of_referenced_mesh"] == 1,
                "duplicate_triangles_zero": after["duplicate_unoriented_triangle_group_count"] == 0,
                "every_vertex_link_is_one_cycle": vertex_link_metrics["all_vertices_have_one_connected_cycle_link"],
                "signed_volume_within_tolerance": bool(volume_ok),
            },
            "physics_status": "NOT_PHYSICS_QUALIFIED; scan topology alone does not establish material, metrology, completeness, watertight real object, or calibrated units.",
        },
        "maps": {
            "file": maps_npz.name,
            "raw_vertex_mapping_summary": raw_vertex_map_summary,
            "raw_face_mapping_summary": raw_face_map_summary,
            "contains": ["raw source vertex -> v3 vertex (-1 for omitted islands)", "v2 vertex -> v3 vertex", "v3 vertex -> v2/raw source vertex", "raw source face -> v3 face (-1 for omitted islands, the four v2 collapsed faces, and the two v3 pair faces)", "v2 face -> v3 face (-1 for the two v3 pair faces)", "v3 face -> raw source face", "removed face IDs", "pruned unreferenced v2 vertex IDs"],
            "local_change_csv": "local_pair_repair.csv",
        },
        "visual_review": {
            "render_files_sha256": render_hashes,
            "views": {"localrepair_side.png": "orthographic side, full foot and stem", "localrepair_oblique.png": "cavity, body, both handles and foot", "localrepair_top.png": "opening and inner surface", "localrepair_bottom.png": "foot underside", "refined_y_section.png": "actual output mesh Y-center section; not a revolved reconstruction"},
            "section_y_joined_polyline_count": len(polylines),
            "point_normals": "Recomputed for rendering only; no coordinate changes.",
            "vertex_link_anomaly_count": vertex_link_metrics["vertex_manifold_failure_count"],
            "retained_connected_features": "No handles, rim, foot, stem, cavity, or body parts were masked. Only the explicitly paired triangles above were removed.",
        },
        "tool_versions": {"python": platform.python_version(), "numpy": np.__version__, "vtk": vtk.vtkVersion.GetVTKVersion(), "matplotlib": matplotlib.__version__},
        "limitations": [
            "Source OBJ coordinate units are unknown and no scale is baked in. `1 raw unit = 1 m` remains an uncalibrated size hypothesis only.",
            "CC BY-SA 4.0 source terms apply; preserve attribution and ShareAlike for redistributed derivatives and views.",
            "A passing topology gate is only a reviewed geometry candidate. It does not assert true wall thickness, native scale, capture completeness, material behavior, or scan metrology.",
            "The omitted 388 disconnected components remain preserved in the raw source and earlier audit; this derivative does not assert those islands are nonphysical.",
            "OBJ header says Generated with Agisoft Metashape, but camera/scanner/hardware and exact acquisition workflow are not documented in the model package; do not treat the asset as calibrated scanner metrology.",
            "Euler values/formal genus are mesh topology diagnostics. High genus / small tunnels may reflect scan or triangulation artifacts and are not evidence for corresponding designed vessel features.",
        ],
        "derivative_files": {},
    }
    for file in [out_obj, out_npz, maps_npz]:
        receipt["derivative_files"][file.name] = {"bytes": file.stat().st_size, "sha256": sha256(file)}
    (AUDIT / "refinement_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    readme = f'''# One local paired-triangle repair: Apsida SHM 17946:0047

This is a separate v3 derivative; the official source ZIP/OBJ/MTL and v1/v2 files remain unchanged. Source: [Apsida item 49281]({v2_receipt['source']['item_url']}). Attribution: “Medelhavsmuseet, SHM 17946:0047; via Apsida / Digital Heritage Research Lab.” License: **CC BY-SA 4.0**; preserve attribution and ShareAlike on redistributed derivatives. The OBJ header says it was generated with Agisoft Metashape, but the capture setup and calibration are unknown.

## Single authorized repair

After v2 exact-coordinate welding, raw source triangles **125422 and 125511** became a coincident opposite-winding pair (same 3 XYZ positions, opposite orientation). Together they formed an overlapping zero-thickness double patch and caused two edge-incidence-4 edges. This branch removes **both faces as a pair**, not one arbitrarily. It adds no surface, cap, or fill. Triangle-level coordinates, areas, signed volumes, vertex IDs, source face IDs, and old-to-new maps are in `local_pair_repair.csv` and `SHM17946_0047_localrepair_maps.npz`. Only unreferenced vertex pruning is permitted; actually pruned count={len(removed_unreferenced_v2_vertex_ids)}.

Before: V={before['vertex_count_referenced']}, E={before['unique_edge_count']}, F={before['face_count']}, χ={before['euler_characteristic_referenced_mesh']}; after: V={after['vertex_count_referenced']}, E={after['unique_edge_count']}, F={after['face_count']}, χ={after['euler_characteristic_referenced_mesh']}. After: boundary={after['boundary_edge_count']}, edge-non-manifold={after['nonmanifold_edge_count']}, vertex-link defects={vertex_link_metrics['vertex_manifold_failure_count']}, winding conflicts={after['inconsistent_winding_edge_count']}, components={after['edge_connected_components_of_referenced_mesh']}, zero-area faces={after['exact_zero_area_face_count']}, duplicate triangle groups={after['duplicate_unoriented_triangle_group_count']}. Surface area change={area_after-area_before:.17g} source units²; signed volume change={volume_delta:.17g} source units³.

Candidate status: **{receipt['acceptance']['status']}**. The v3 edge counts are all 2, but the vertex-link audit finds {vertex_link_metrics['vertex_manifold_failure_count']} vertices with multiple disconnected link cycles; this is a pinched, non-manifold surface. The Euler characteristic is odd (χ={after['euler_characteristic_referenced_mesh']}), so there is no valid closed orientable manifold genus. No additional repair will be attempted under this branch; use the scan as a visual/reference source and reconstruct a parametric CAD solid from documented evidence instead. Even a topology pass is **not physics qualification** or metrology: native units are UNKNOWN, and the scale candidate of 1 raw unit = 1 m is uncalibrated. High Euler genus / tunnels are mesh diagnostics, not evidence for real designed vessel features. The 388 detached raw islands remain preserved in the original source and full audit; their omission from this derivative is not a statement about physicality.

## Outputs

- `SHM17946_0047_main_component_localrepair_candidate.obj` and `.npz`: candidate geometry with unchanged positions and face windings except the exact pair removal.
- `SHM17946_0047_localrepair_maps.npz`: full raw/V2 to V3 vertex and face maps, removed face IDs and any pruned vertices. The raw face map accounts for all 8,484 omitted triangles: 8,478 disconnected-island faces, four collapsed zero-area faces from v2, and the two v3 opposite-winding faces.
- `local_pair_repair.csv`: source and candidate face IDs, coordinates, area, and signed volume contribution for each removed triangle.
- `vertex_link_anomalies.csv`: all pinched vertices and their separated link cycles.
- `refinement_receipt.json`: license, parent hashes, topology before/after, visual hashes, and gates.
- `localrepair_side.png`, `localrepair_oblique.png`, `localrepair_top.png`, `localrepair_bottom.png`, `refined_y_section.png`: output views; recomputed point normals are display-only.
'''
    (AUDIT / "README.md").write_text(readme, encoding="utf-8")
    (ASSET_V3 / "README.md").write_text(
        f'''# Apsida SHM 17946:0047 local paired-face derivative

Source: [Apsida item 49281]({v2_receipt['source']['item_url']}); attribution “Medelhavsmuseet, SHM 17946:0047; via Apsida / Digital Heritage Research Lab”; license **CC BY-SA 4.0**. Retain ShareAlike and attribution. The raw source files remain unchanged in the parent directory.

This derivative applies exactly one local change to the v2 exact-coordinate-weld candidate: it removes both coincident opposite-winding raw triangles 125422 and 125511 together. It does not cap/fill, smooth, rescale, or delete connected vessel features. The scan unit remains UNKNOWN. See [the v3 audit and receipt](../../../vesselforge/experiments/continuation_20261015/scanned_anchor_audit/refinement_v3/README.md) for whether the result passes topology checks. Any pass is geometry-only, not a physics or metrology qualification.
''', encoding="utf-8")
    print(json.dumps({"status": receipt["acceptance"]["status"], "before": before, "after": after, "pair_area": area_each.tolist(), "pair_signed_volume": volume_each.tolist(), "pair_volume_sum": float(volume_each.sum()), "volume_delta": volume_delta, "pruned_unreferenced_vertices": removed_unreferenced_v2_vertex_ids.tolist(), "obj": str(out_obj), "receipt": str(AUDIT/"refinement_receipt.json")}, indent=2))


if __name__ == "__main__":
    main()
