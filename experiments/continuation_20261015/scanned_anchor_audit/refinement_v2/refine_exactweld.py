from __future__ import annotations

import csv
import hashlib
import json
import math
import pathlib
import platform

import numpy as np
from scipy import __version__ as scipy_version
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
import vtk
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = pathlib.Path.cwd()
AUDIT = ROOT / "vesselforge/experiments/continuation_20261015/scanned_anchor_audit/refinement_v2"
ASSET = ROOT / "third_party/reference-assets/apsida-shm17946-0047"
ASSET_OUT = ASSET / "refined_v2"
V1_NPZ = ASSET / "refined_v1/SHM17946_0047_main_component.npz"
V1_RECEIPT = ROOT / "vesselforge/experiments/continuation_20261015/scanned_anchor_audit/refinement_v1/refinement_receipt.json"
SOURCE_OBJ = ASSET / "Footed_Bowl_SHM_17946_0047.obj"
SOURCE_ZIP = ASSET / "Footed_Bowl_SHM_17946_0047_Obj06.zip"
RAW_NPZ = ROOT / "vesselforge/experiments/continuation_20261015/scanned_anchor_audit/raw_geometry.npz"
AUDIT.mkdir(parents=True, exist_ok=True)
ASSET_OUT.mkdir(parents=True, exist_ok=True)


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def mesh_metrics(v: np.ndarray, f: np.ndarray, *, count_components: bool = True) -> dict:
    tri = v[f]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = np.linalg.norm(cross, axis=1) / 2.0
    volume_contrib = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])) / 6.0
    directed = np.concatenate((f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]), axis=0)
    signs = np.where(directed[:, 0] < directed[:, 1], 1, -1).astype(np.int8)
    undirected = directed.copy()
    undirected.sort(axis=1)
    unique_edges, edge_inverse, edge_counts = np.unique(
        undirected, axis=0, return_inverse=True, return_counts=True
    )
    edge_sign_sums = np.bincount(edge_inverse, weights=signs, minlength=len(unique_edges))
    boundary = int(np.count_nonzero(edge_counts == 1))
    nonmanifold = int(np.count_nonzero(edge_counts > 2))
    winding = int(np.count_nonzero((edge_counts == 2) & (edge_sign_sums != 0)))
    used_vertices = np.unique(f)
    if count_components:
        rows = np.concatenate((unique_edges[:, 0], unique_edges[:, 1]))
        cols = np.concatenate((unique_edges[:, 1], unique_edges[:, 0]))
        adj = csr_matrix((np.ones(len(rows), dtype=np.uint8), (rows, cols)), shape=(len(v), len(v)))
        cc_count, cc_labels = connected_components(adj, directed=False, return_labels=True)
        used_cc_count = int(len(np.unique(cc_labels[used_vertices])))
    else:
        cc_count = None
        used_cc_count = None
    chi = int(len(used_vertices) - len(unique_edges) + len(f))
    sorted_faces = np.sort(f, axis=1)
    _, duplicate_face_counts = np.unique(sorted_faces, axis=0, return_counts=True)
    duplicate_face_groups = duplicate_face_counts[duplicate_face_counts > 1]
    zero_area_count = int(np.count_nonzero(np.linalg.norm(cross, axis=1) == 0))
    formal_genus = None
    two_g = 2 - chi
    if two_g >= 0 and two_g % 2 == 0:
        formal_genus = int(two_g // 2)
    genus = None
    if (boundary == 0 and nonmanifold == 0 and winding == 0 and used_cc_count == 1
            and zero_area_count == 0 and len(duplicate_face_groups) == 0):
        genus = formal_genus
    return {
        "vertex_count_in_file": int(len(v)),
        "vertex_count_referenced": int(len(used_vertices)),
        "face_count": int(len(f)),
        "unique_edge_count": int(len(unique_edges)),
        "boundary_edge_count": boundary,
        "nonmanifold_edge_count": nonmanifold,
        "inconsistent_winding_edge_count": winding,
        "edge_connected_components_including_unused_vertices": None if cc_count is None else int(cc_count),
        "edge_connected_components_of_referenced_mesh": used_cc_count,
        "euler_characteristic_referenced_mesh": chi,
        "genus_if_closed_oriented_connected_manifold": genus,
        "formal_genus_from_chi_if_assuming_manifold": formal_genus,
        "exact_zero_area_face_count": zero_area_count,
        "duplicate_unoriented_triangle_group_count": int(len(duplicate_face_groups)),
        "faces_in_duplicate_unoriented_triangle_groups": int(duplicate_face_groups.sum()) if len(duplicate_face_groups) else 0,
        "surface_area_source_units2": float(area.sum(dtype=np.float64)),
        "signed_volume_source_units3": float(volume_contrib.sum(dtype=np.float64)),
        "bounds_min_xyz_source_units": v.min(axis=0).tolist(),
        "bounds_max_xyz_source_units": v.max(axis=0).tolist(),
        "bounds_extent_xyz_source_units": (v.max(axis=0) - v.min(axis=0)).tolist(),
    }


def build_polydata(v: np.ndarray, f: np.ndarray) -> vtk.vtkPolyData:
    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(np.ascontiguousarray(v), deep=True))
    cell_blob = np.empty((len(f), 4), dtype=np.int64)
    cell_blob[:, 0] = 3
    cell_blob[:, 1:] = f
    cells = vtk.vtkCellArray()
    cells.SetCells(len(f), numpy_to_vtkIdTypeArray(np.ascontiguousarray(cell_blob.ravel()), deep=True))
    poly = vtk.vtkPolyData()
    poly.SetPoints(points)
    poly.SetPolys(cells)
    return poly


def render_view(name: str, poly: vtk.vtkPolyData, direction, up) -> None:
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(poly)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(0.69, 0.57, 0.42)
    actor.GetProperty().SetInterpolationToPhong()
    actor.GetProperty().SetSpecular(0.16)
    actor.GetProperty().SetSpecularPower(18)
    ren = vtk.vtkRenderer()
    ren.SetBackground(0.95, 0.95, 0.93)
    ren.AddActor(actor)
    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.SetSize(1100, 1100)
    win.AddRenderer(ren)
    camera = ren.GetActiveCamera()
    camera.ParallelProjectionOn()
    bounds = poly.GetBounds()
    center = [(bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2, (bounds[4] + bounds[5]) / 2]
    extent = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4])
    camera.SetFocalPoint(*center)
    camera.SetPosition(*(np.asarray(center) + np.asarray(direction) * extent * 3.5))
    camera.SetViewUp(*up)
    camera.SetParallelScale(extent * 0.64)
    ren.ResetCameraClippingRange()
    win.Render()
    ren.ResetCameraClippingRange()
    win.Render()
    capture = vtk.vtkWindowToImageFilter()
    capture.SetInput(win)
    capture.SetInputBufferTypeToRGB()
    capture.ReadFrontBufferOff()
    capture.Update()
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(AUDIT / f"{name}.png"))
    writer.SetInputConnection(capture.GetOutputPort())
    writer.Write()
    win.Finalize()


def section_y(poly: vtk.vtkPolyData, v: np.ndarray) -> list[np.ndarray]:
    center_xy = np.mean(v[:, :2], axis=0)
    plane = vtk.vtkPlane()
    plane.SetOrigin(float(center_xy[0]), float(center_xy[1]), float((v[:, 2].min() + v[:, 2].max()) / 2))
    plane.SetNormal(0, 1, 0)
    cutter = vtk.vtkCutter()
    cutter.SetInputData(poly)
    cutter.SetCutFunction(plane)
    cutter.Update()
    stripper = vtk.vtkStripper()
    stripper.SetInputConnection(cutter.GetOutputPort())
    stripper.JoinContiguousSegmentsOn()
    stripper.Update()
    cut = stripper.GetOutput()
    points = vtk_to_numpy(cut.GetPoints().GetData()) if cut.GetPoints() else np.empty((0, 3))
    ids = vtk.vtkIdList()
    lines = cut.GetLines()
    lines.InitTraversal()
    result = []
    while lines.GetNextCell(ids):
        line = points[[ids.GetId(i) for i in range(ids.GetNumberOfIds())]]
        if len(line) >= 2:
            result.append(line)
    with (AUDIT / "refined_y_section.csv").open("w", newline="", encoding="utf-8") as fcsv:
        writer = csv.writer(fcsv)
        writer.writerow(["polyline_id", "path_order", "x_raw_obj_units", "y_raw_obj_units", "z_raw_obj_units"])
        for pid, line in enumerate(result):
            for order, point in enumerate(line):
                writer.writerow([pid, order, *map(float, point)])
    fig, ax = plt.subplots(figsize=(8, 8), dpi=150)
    for line in result:
        ax.plot(line[:, 0], line[:, 2], color="#473a2f", lw=0.65)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.22)
    ax.set_xlabel("x (raw OBJ units)")
    ax.set_ylabel("z (raw OBJ units)")
    ax.set_title(f"Exact-weld candidate Y-center section; {len(result)} joined polylines")
    fig.tight_layout()
    fig.savefig(AUDIT / "refined_y_section.png")
    plt.close(fig)
    return result


def main() -> None:
    v1_receipt = json.loads(V1_RECEIPT.read_text(encoding="utf-8"))
    source_obj_sha = sha256(SOURCE_OBJ)
    source_zip_sha = sha256(SOURCE_ZIP)
    expected_obj = v1_receipt["source"]["source_obj_sha256"]
    expected_zip = v1_receipt["source"]["source_zip_sha256"]
    if source_obj_sha.lower() != expected_obj.lower() or source_zip_sha.lower() != expected_zip.lower():
        raise SystemExit("Unchanged source asset hash mismatch; refusing exact-coordinate derivative.")
    if sha256(V1_NPZ) != v1_receipt["derivative_files"]["npz"]["sha256"]:
        raise SystemExit("V1 source candidate NPZ hash mismatch; refusing derivation.")
    with np.load(V1_NPZ) as z:
        old_v = z["vertices_source_units"].astype(np.float64, copy=True)
        old_f = z["faces"].astype(np.int64, copy=True)
        source_vertex_ids = z["source_vertex_indices"].astype(np.int64, copy=True)
        source_face_ids = z["source_face_indices"].astype(np.int64, copy=True)
    raw = np.load(RAW_NPZ)
    raw_v, raw_f = raw["vertices_source_units"], raw["faces"]
    if len(old_v) > 2_000_000 or len(old_f) > 4_000_000:
        raise SystemExit("Mesh exceeds configured 2M vertex / 4M face cap.")
    if len(old_v) != len(source_vertex_ids) or len(old_f) != len(source_face_ids):
        raise SystemExit("V1 provenance arrays have inconsistent lengths.")
    if not np.array_equal(old_v, raw_v[source_vertex_ids]):
        raise SystemExit("V1 main positions do not exactly map to raw source vertices.")
    if not np.array_equal(old_f, np.searchsorted(source_vertex_ids, raw_f[source_face_ids])):
        raise SystemExit("V1 main faces do not map to raw source faces as expected.")

    before = mesh_metrics(old_v, old_f)

    # Exact coordinate equality only: no decimal rounding, distance tolerance, or smoothing.
    unique_xyz, first_index, old_to_unique = np.unique(
        old_v, axis=0, return_index=True, return_inverse=True
    )
    first_order = np.argsort(first_index, kind="stable")
    unique_to_new = np.empty(len(first_order), dtype=np.int64)
    unique_to_new[first_order] = np.arange(len(first_order), dtype=np.int64)
    new_v = old_v[first_index[first_order]].copy()
    old_to_new = unique_to_new[old_to_unique]
    remapped_all_faces = old_to_new[old_f]
    distinct_counts = np.apply_along_axis(lambda row: len(np.unique(row)), 1, remapped_all_faces)
    removed_local_face_ids = np.flatnonzero(distinct_counts < 3)
    retained_local_face_ids = np.flatnonzero(distinct_counts == 3)
    if np.any(distinct_counts > 3):
        raise SystemExit("Impossible triangle unique-index count > 3")
    new_f = remapped_all_faces[retained_local_face_ids].copy()
    retained_source_face_ids = source_face_ids[retained_local_face_ids]
    removed_source_face_ids = source_face_ids[removed_local_face_ids]

    # Duplicate XYZ groups are evidence of exact seam duplication, not a claim about source intent.
    duplicate_groups = []
    _, group_ids, group_counts = np.unique(old_v, axis=0, return_inverse=True, return_counts=True)
    for group_id in np.flatnonzero(group_counts > 1):
        old_ids = np.flatnonzero(group_ids == group_id)
        duplicate_groups.append({
            "new_vertex_index": int(old_to_new[old_ids[0]]),
            "main_v1_local_vertex_indices": json.dumps(old_ids.tolist()),
            "raw_source_vertex_indices": json.dumps(source_vertex_ids[old_ids].tolist()),
            "xyz_source_units": json.dumps(old_v[old_ids[0]].tolist(), separators=(",", ":")),
            "duplicate_index_count": int(len(old_ids)),
        })
    with (AUDIT / "exact_duplicate_xyz_groups.csv").open("w", newline="", encoding="utf-8") as fcsv:
        writer = csv.DictWriter(fcsv, fieldnames=list(duplicate_groups[0]) if duplicate_groups else ["new_vertex_index"])
        writer.writeheader()
        writer.writerows(duplicate_groups)

    mapping = np.full(len(raw_v), -1, dtype=np.int64)
    mapping[source_vertex_ids] = old_to_new
    face_mapping = np.full(len(raw_f), -1, dtype=np.int64)
    face_mapping[retained_source_face_ids] = np.arange(len(retained_source_face_ids), dtype=np.int64)
    if len(removed_source_face_ids):
        removed_rows = []
        for old_local, source_id in zip(removed_local_face_ids, removed_source_face_ids):
            face_vertices_raw = source_vertex_ids[old_f[old_local]]
            xyz = raw_v[face_vertices_raw]
            removed_rows.append({
                "source_face_index_zero_based": int(source_id),
                "v1_local_face_index": int(old_local),
                "raw_source_vertex_indices": json.dumps(face_vertices_raw.tolist()),
                "post_weld_vertex_indices": json.dumps(remapped_all_faces[old_local].tolist()),
                "distinct_source_vertex_indices": int(len(np.unique(face_vertices_raw))),
                "distinct_post_weld_indices": int(distinct_counts[old_local]),
                "distinct_xyz_positions": int(len(np.unique(xyz, axis=0))),
                "coordinates_xyz_source_units": json.dumps(xyz.tolist(), separators=(",", ":")),
                "disposition": "REMOVED only because exact coordinate remap produced fewer than 3 unique vertex indices; zero-area face; no cap or replacement added",
            })
    else:
        removed_rows = []
    with (AUDIT / "removed_degenerate_faces.csv").open("w", newline="", encoding="utf-8") as fcsv:
        cols = list(removed_rows[0]) if removed_rows else ["source_face_index_zero_based"]
        writer = csv.DictWriter(fcsv, fieldnames=cols)
        writer.writeheader()
        writer.writerows(removed_rows)

    after = mesh_metrics(new_v, new_f)
    # Explicit duplicate face diagnostics. Never delete duplicate faces in this branch.
    sorted_f = np.sort(new_f, axis=1)
    unique_sorted_f, inverse_sorted_f, counts_sorted_f = np.unique(
        sorted_f, axis=0, return_inverse=True, return_counts=True
    )
    duplicate_source_faces = []
    for group_id in np.flatnonzero(counts_sorted_f > 1):
        local_ids = np.flatnonzero(inverse_sorted_f == group_id)
        duplicate_source_faces.append({
            "canonical_vertex_indices": json.dumps(unique_sorted_f[group_id].tolist()),
            "candidate_face_indices": json.dumps(local_ids.tolist()),
            "source_face_indices": json.dumps(retained_source_face_ids[local_ids].tolist()),
            "winding_variants": json.dumps([new_f[i].tolist() for i in local_ids]),
            "count": int(len(local_ids)),
            "disposition": "DIAGNOSTIC ONLY; duplicate triangles are retained, not deleted",
        })
    with (AUDIT / "duplicate_faces_diagnostic.csv").open("w", newline="", encoding="utf-8") as fcsv:
        cols = list(duplicate_source_faces[0]) if duplicate_source_faces else ["canonical_vertex_indices"]
        writer = csv.DictWriter(fcsv, fieldnames=cols)
        writer.writeheader()
        writer.writerows(duplicate_source_faces)

    directed_edges = np.concatenate((new_f[:, [0, 1]], new_f[:, [1, 2]], new_f[:, [2, 0]]), axis=0)
    edge_face_ids = np.tile(np.arange(len(new_f), dtype=np.int64), 3)
    edge_slots = np.tile(np.array([0, 1, 2], dtype=np.int8), len(new_f))
    canonical_edges = directed_edges.copy()
    canonical_edges.sort(axis=1)
    unique_edges, edge_inverse, edge_counts = np.unique(canonical_edges, axis=0, return_inverse=True, return_counts=True)
    nonmanifold_edge_details = []
    for edge_id in np.flatnonzero(edge_counts > 2):
        occurrence_ids = np.flatnonzero(edge_inverse == edge_id)
        incident_faces = edge_face_ids[occurrence_ids]
        endpoints = unique_edges[edge_id]
        nonmanifold_edge_details.append({
            "candidate_edge_index": int(edge_id),
            "candidate_vertex_indices": endpoints.tolist(),
            "raw_source_vertex_indices": source_vertex_ids[first_index[first_order][endpoints]].tolist(),
            "endpoint_xyz_source_units": new_v[endpoints].tolist(),
            "incident_edge_occurrence_count": int(edge_counts[edge_id]),
            "candidate_face_indices": incident_faces.tolist(),
            "raw_source_face_indices": retained_source_face_ids[incident_faces].tolist(),
            "edge_slots_in_incident_faces": edge_slots[occurrence_ids].tolist(),
            "incident_winding_faces": new_f[incident_faces].tolist(),
        })

    # Emit enough provenance maps to restore each candidate element to raw source indices.
    map_npz = ASSET_OUT / "SHM17946_0047_exactweld_maps.npz"
    np.savez_compressed(
        map_npz,
        raw_source_vertex_to_candidate_vertex=mapping,
        v1_local_vertex_to_candidate_vertex=old_to_new,
        candidate_vertex_to_v1_local_vertex=first_index[first_order],
        candidate_vertex_to_raw_source_vertex=source_vertex_ids[first_index[first_order]],
        raw_source_face_to_candidate_face=face_mapping,
        v1_local_face_to_candidate_face=np.where(
            np.isin(np.arange(len(old_f)), retained_local_face_ids),
            np.searchsorted(retained_local_face_ids, np.arange(len(old_f))), -1
        ).astype(np.int64),
        candidate_face_to_raw_source_face=retained_source_face_ids,
        removed_v1_local_face_indices=removed_local_face_ids,
        removed_raw_source_face_indices=removed_source_face_ids,
    )

    # Write candidate arrays and geometry-only OBJ. Keep raw coordinates unchanged.
    out_obj = ASSET_OUT / "SHM17946_0047_main_component_exactweld_candidate.obj"
    with out_obj.open("w", encoding="utf-8", newline="\n") as fout:
        fout.write("# Exact-coordinate-weld derivative of Apsida SHM 17946:0047.\n")
        fout.write("# Coordinates copied unchanged; source unit UNKNOWN. See refinement_v2 receipt.\n")
        fout.write("# Exact XYZ duplicate-index weld only; four collapsed zero-area triangles omitted.\n")
        fout.write("o SHM_17946_0047_main_component_exactweld_candidate\n")
        for point in new_v:
            fout.write("v %.9f %.9f %.9f\n" % tuple(point))
        for face in new_f:
            fout.write("f %d %d %d\n" % (face[0] + 1, face[1] + 1, face[2] + 1))
    out_npz = ASSET_OUT / "SHM17946_0047_main_component_exactweld_candidate.npz"
    np.savez_compressed(
        out_npz,
        vertices_source_units=new_v,
        faces=new_f,
        candidate_vertex_to_v1_local_vertex=first_index[first_order],
        candidate_vertex_to_raw_source_vertex=source_vertex_ids[first_index[first_order]],
        candidate_face_to_raw_source_face=retained_source_face_ids,
    )

    # Reparse serialized output; decimal precision of source is six digits.
    check_v, check_f = [], []
    with out_obj.open("r", encoding="utf-8") as fin:
        for line in fin:
            if line.startswith("v "):
                check_v.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("f "):
                check_f.append([int(x) - 1 for x in line.split()[1:4]])
    check_v = np.asarray(check_v, dtype=np.float64)
    check_f = np.asarray(check_f, dtype=np.int64)
    if not np.array_equal(check_v, new_v) or not np.array_equal(check_f, new_f):
        raise SystemExit("Candidate OBJ serialization did not round-trip exactly.")
    if not np.array_equal(new_v, old_v[first_index[first_order]]):
        raise SystemExit("Candidate coordinates differ from exact source positions.")

    volume_delta = after["signed_volume_source_units3"] - before["signed_volume_source_units3"]
    volume_abs_tol = 1e-12
    volume_rel_tol = 1e-9
    volume_ok = abs(volume_delta) <= max(volume_abs_tol, abs(before["signed_volume_source_units3"]) * volume_rel_tol)
    topology_ok = (
        after["exact_zero_area_face_count"] == 0
        and after["boundary_edge_count"] == 0
        and after["nonmanifold_edge_count"] == 0
        and after["inconsistent_winding_edge_count"] == 0
        and after["edge_connected_components_of_referenced_mesh"] == 1
        and after["duplicate_unoriented_triangle_group_count"] == 0
        and volume_ok
    )

    # Render candidate only after preserving every connected face; normals are visualization-only.
    poly = build_polydata(new_v, new_f)
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(poly)
    normals.SplittingOff()
    normals.ConsistencyOff()
    normals.AutoOrientNormalsOff()
    normals.ComputePointNormalsOn()
    normals.ComputeCellNormalsOff()
    normals.Update()
    view_poly = normals.GetOutput()
    views = {
        "exactweld_side": ((0, -1, 0), (0, 0, 1)),
        "exactweld_oblique": ((2.6, -3.4, 1.4), (0, 0, 1)),
        "exactweld_top": ((0, 0, 1), (0, 1, 0)),
        "exactweld_bottom": ((0, 0, -1), (0, 1, 0)),
    }
    for name, (direction, up) in views.items():
        render_view(name, view_poly, direction, up)
    polylines = section_y(poly, new_v)
    render_hashes = {p.name: sha256(p) for p in sorted(AUDIT.glob("*.png"))}

    raw_hash = sha256(RAW_NPZ)
    receipt = {
        "record_type": "exact-coordinate-weld derivative audit; acceptance depends on topology result",
        "source": {
            "item_url": v1_receipt["source"]["item_url"],
            "archive_url": v1_receipt["source"]["archive_url"],
            "identifier": "SHM 17946:0047",
            "title": "Footed bowl",
            "rights": "CC BY-SA 4.0",
            "attribution": "Medelhavsmuseet, SHM 17946:0047; via Apsida / Digital Heritage Research Lab",
            "source_zip_sha256": source_zip_sha,
            "source_obj_sha256": source_obj_sha,
            "prior_raw_geometry_npz_sha256": raw_hash,
            "parent_v1_candidate_npz_sha256": sha256(V1_NPZ),
            "source_native_units": "UNKNOWN in the OBJ header; no calibration applied",
        },
        "method": {
            "exact_merge": "np.unique over exact float64 XYZ rows; no rounding and no tolerance",
            "coordinate_order": "Distinct XYZs are serialized in first-occurrence order from the V1 main-component vertex list; positions copied exactly",
            "faces": "All V1 main-component faces remapped. Only faces with fewer than 3 distinct post-weld indices were removed; no duplicate-face removal, cap, fill, smoothing, decimation, or rescale",
            "removed_source_face_ids_zero_based": removed_source_face_ids.tolist(),
            "removed_source_face_count": int(len(removed_source_face_ids)),
            "exact_duplicate_xyz_group_count": int(len(duplicate_groups)),
            "v1_vertices": int(len(old_v)),
            "candidate_vertices": int(len(new_v)),
            "v1_faces": int(len(old_f)),
            "candidate_faces": int(len(new_f)),
            "vertex_count_reduction_exact_xyz_only": int(len(old_v) - len(new_v)),
        },
        "topology_before": before,
        "topology_after": after,
        "topology_anomaly_detail": {
            "nonmanifold_edges": nonmanifold_edge_details,
            "duplicate_unoriented_face_groups": duplicate_source_faces,
            "interpretation": "These details are diagnostics only. No offending connected faces were removed or repaired; exact welding exposes overlapping opposite-winding triangles and edge incidence 4.",
        },
        "comparison": {
            "euler_characteristic_change": int(after["euler_characteristic_referenced_mesh"] - before["euler_characteristic_referenced_mesh"]),
            "genus_before_valid": before["genus_if_closed_oriented_connected_manifold"],
            "genus_after_valid": after["genus_if_closed_oriented_connected_manifold"],
            "signed_volume_delta_source_units3": float(volume_delta),
            "volume_absolute_tolerance_source_units3": volume_abs_tol,
            "volume_relative_tolerance": volume_rel_tol,
            "volume_within_tolerance": bool(volume_ok),
            "main_foot_handles_cavity_geometry_retained": "No connected geometry was masked or intentionally removed; only exact-coordinate duplicate IDs were merged and four collapsed zero-area triangles are omitted. See full-shape renders for visual comparison. Rendering normals were recomputed for display only.",
        },
        "acceptance": {
            "status": "PASS_TOPOLOGY_CANDIDATE" if topology_ok else "FAIL_DO_NOT_USE_AS_CLOSED_PHYSICAL_MESH",
            "requirements": {
                "zero_area_faces_zero": after["exact_zero_area_face_count"] == 0,
                "boundary_edges_zero": after["boundary_edge_count"] == 0,
                "nonmanifold_edges_zero": after["nonmanifold_edge_count"] == 0,
                "inconsistent_winding_edges_zero": after["inconsistent_winding_edge_count"] == 0,
                "one_referenced_component": after["edge_connected_components_of_referenced_mesh"] == 1,
                "no_duplicate_triangles": after["duplicate_unoriented_triangle_group_count"] == 0,
                "volume_within_tolerance": bool(volume_ok),
            },
            "scope_limit": "A topology-pass only makes this exact-weld derivative a reviewed mesh candidate. It does not establish native physical units, scan metrology, material, photographic scale, correct real-world wall thickness, or physical truth.",
        },
        "maps": {
            "file": map_npz.name,
            "contains": ["raw_source_vertex_to_candidate_vertex (-1 for omitted islands)", "v1_local_vertex_to_candidate_vertex", "candidate_vertex_to_v1_local_vertex", "candidate_vertex_to_raw_source_vertex", "raw_source_face_to_candidate_face (-1 for omitted islands and four collapsed triangles)", "v1_local_face_to_candidate_face", "candidate_face_to_raw_source_face", "removed_v1_local_face_indices", "removed_raw_source_face_indices"],
            "duplicate_xyz_groups_csv": "exact_duplicate_xyz_groups.csv",
            "removed_triangles_csv": "removed_degenerate_faces.csv",
            "duplicate_faces_csv": "duplicate_faces_diagnostic.csv",
        },
        "tool_versions": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy_version, "vtk": vtk.vtkVersion.GetVTKVersion(), "matplotlib": matplotlib.__version__},
        "visual_review": {
            "render_files_sha256": render_hashes,
            "views": {"exactweld_side.png": "orthographic Y-axis side with full Z extent and clipping range reset", "exactweld_oblique.png": "oblique view of handles/opening/body/stem/foot", "exactweld_top.png": "opening, inner surface, and handle arrangement", "exactweld_bottom.png": "underside and foot", "refined_y_section.png": "actual candidate mesh Y-center section; no revolve/rotation"},
            "section_y_joined_polylines": len(polylines),
            "display_normals": "Recomputed point normals are display-only; connectivity/winding/coordinates in saved mesh are unchanged.",
        },
        "derivative_files": {},
        "license_and_attribution": "CC BY-SA 4.0 from the Apsida source. Derivatives and images must retain attribution and ShareAlike terms. Attribution: Medelhavsmuseet, SHM 17946:0047; via Apsida / Digital Heritage Research Lab.",
        "limitations": [
            "Captured coordinates' native unit is unknown. The 1 raw unit = 1 m (x1000 mm) value is only a scale candidate inferred from model extents and catalog dimensions, not declared calibration.",
            "Exact coordinate duplicates are merged by index only. This does not prove each seam was a redundant render duplicate or that each source surface is complete.",
            "Four triangles collapsed to fewer than three unique vertex indices after exact weld and were omitted. They were already exact zero-area faces; no geometric holes were capped or repaired.",
            "The other 388 indexed disconnected islands remain omitted from this derivative only; raw ZIP/OBJ and V1 receipt are retained, and this is not a claim those islands are nonphysical.",
            "V1's Euler characteristic is -36, which yields a formal genus of 19 only under a closed orientable manifold assumption; its four degenerate faces make that genus unvalidated. V2 has χ=-40 and formal genus 21 from χ, but it is non-manifold. These mesh cycles/tunnels may be scan/topology artifacts and are not evidence for 19 or 21 real vessel handles or intended object features.",
            "A closed mesh / topology pass does not establish real wall thickness, object solidity, scan accuracy, or complete capture.",
        ],
    }
    for file in [out_obj, out_npz, map_npz]:
        receipt["derivative_files"][file.name] = {"bytes": file.stat().st_size, "sha256": sha256(file)}
    (AUDIT / "refinement_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    readme = f'''# Exact-coordinate-weld derivative audit: Apsida SHM 17946:0047

This is a separate reviewed derivative branch from `refined_v1`; the source ZIP/OBJ/MTL, raw NPZ, and V1 files were not modified. Source item: [Apsida record 49281]({v1_receipt['source']['item_url']}). License: **CC BY-SA 4.0**. Attribution: “Medelhavsmuseet, SHM 17946:0047; via Apsida / Digital Heritage Research Lab.” Any redistribution must preserve attribution and ShareAlike terms.

## Operation and measured result

V1 main-only source: {len(old_v):,} vertices, {len(old_f):,} faces. The exact-coordinate map found {len(duplicate_groups):,} duplicate XYZ groups and reduced the vertex count by {len(old_v)-len(new_v):,}. It used exact float64 XYZ equality (`numpy.unique`), with no rounding, tolerance, smoothing, scaling, hole filling, or capping. Four faces (raw source IDs {', '.join(map(str, removed_source_face_ids.tolist()))}) collapsed to fewer than three unique indices and were removed; each was already zero-area from duplicate coordinates. No other triangle or connected handle/foot/body geometry was deleted. See the full old-to-new maps and per-face record.

The candidate status is **{receipt['acceptance']['status']}**. Before: V={before['vertex_count_referenced']}, E={before['unique_edge_count']}, F={before['face_count']}, χ={before['euler_characteristic_referenced_mesh']}; after: V={after['vertex_count_referenced']}, E={after['unique_edge_count']}, F={after['face_count']}, χ={after['euler_characteristic_referenced_mesh']}. Formal genus from χ is before={before['formal_genus_from_chi_if_assuming_manifold']} and after={after['formal_genus_from_chi_if_assuming_manifold']}, but neither is a physical shape measurement; V1 has four degenerate faces and V2 is non-manifold. After metrics: {after['boundary_edge_count']} boundary edges; {after['nonmanifold_edge_count']} non-manifold edges; {after['inconsistent_winding_edge_count']} inconsistent-winding edges; {after['exact_zero_area_face_count']} exact zero-area faces; {after['duplicate_unoriented_triangle_group_count']} duplicate triangle groups. Signed volume delta={volume_delta:.17g} raw-units³ (tolerance: abs {volume_abs_tol:g}, rel {volume_rel_tol:g}).

The reported source-coordinate unit is **UNKNOWN**. `1 raw unit = 1 m` (multiply by 1000 for mm) remains a scale candidate only, inferred from extents and catalogue dimensions, not calibrated. Passing mesh topology does not qualify wall thickness, scan completeness, physical solidity, or metrology.

## Outputs

- `SHM17946_0047_main_component_exactweld_candidate.obj` and `.npz`: exact-weld derivative, retaining original source positions with unit unknown.
- `SHM17946_0047_exactweld_maps.npz`: raw/V1 vertex and face maps, plus all four removed face IDs.
- `exact_duplicate_xyz_groups.csv`, `removed_degenerate_faces.csv`, `duplicate_faces_diagnostic.csv`: audit trails.
- `refinement_receipt.json`: source hashes, topology comparisons, license, acceptance gates, and render hashes.
- `exactweld_side.png`, `exactweld_oblique.png`, `exactweld_top.png`, `exactweld_bottom.png`, `refined_y_section.png`: full candidate views; display normals are recomputed only for visualization.

See the sibling `refinement_v1` for the pre-weld main-only candidate and full disconnected-island inventory. Raw source and prior renders remain preserved.
'''
    (AUDIT / "README.md").write_text(readme, encoding="utf-8")
    asset_readme = f'''# Apsida SHM 17946:0047 exact-coordinate-weld candidate

This folder holds a geometry-only derivative of the official Apsida 3D model. Source: [Apsida item 49281]({v1_receipt['source']['item_url']}); attribution “Medelhavsmuseet, SHM 17946:0047; via Apsida / Digital Heritage Research Lab”; license CC BY-SA 4.0. Preserve ShareAlike and attribution on derivatives. The unchanged source ZIP, full OBJ, MTL, and license record are in the parent folder.

The candidate merges only exactly equal XYZ positions in the V1 main component and omits only the four zero-area faces which become fewer than three unique indices. It does not rescale, smooth, repair, cap, decimate, or alter connected handles/foot/body. Native coordinate unit is **UNKNOWN**; any metre-to-millimetre interpretation is an uncalibrated scale hypothesis. This is a derivative for review, not proof of physical truth, complete capture, or measured wall thickness. See [the v2 audit and receipt](../../../vesselforge/experiments/continuation_20261015/scanned_anchor_audit/refinement_v2/README.md) for exact maps, topology outcome, and limits.
'''
    (ASSET_OUT / "README.md").write_text(asset_readme, encoding="utf-8")
    print(json.dumps({"status": receipt["acceptance"]["status"], "before": before, "after": after, "volume_delta": volume_delta, "duplicate_xyz_groups": len(duplicate_groups), "vertices_welded": len(old_v)-len(new_v), "removed_face_source_ids": removed_source_face_ids.tolist(), "obj": str(out_obj), "receipt": str(AUDIT/"refinement_receipt.json")}, indent=2))


if __name__ == "__main__":
    main()
