import csv, json, pathlib
import numpy as np

root = pathlib.Path.cwd()
audit = root / "vesselforge/experiments/continuation_20261015/scanned_anchor_audit/refinement_v2"
asset = root / "third_party/reference-assets/apsida-shm17946-0047/refined_v2"
with np.load(asset / "SHM17946_0047_main_component_exactweld_candidate.npz") as z:
    v = z["vertices_source_units"]
    f = z["faces"]
    cand_to_raw_v = z["candidate_vertex_to_raw_source_vertex"]
    cand_to_raw_f = z["candidate_face_to_raw_source_face"]
directed = np.concatenate((f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]), axis=0)
face_ids = np.tile(np.arange(len(f), dtype=np.int64), 3)
local_edge_ids = np.tile(np.array([0, 1, 2], dtype=np.int8), len(f))
edge = directed.copy(); edge.sort(axis=1)
unique_edge, inverse, counts = np.unique(edge, axis=0, return_inverse=True, return_counts=True)
bad_edges = np.flatnonzero(counts > 2)
rows = []
for eid in bad_edges:
    occurrence_ids = np.flatnonzero(inverse == eid)
    local_faces = face_ids[occurrence_ids]
    vpair = unique_edge[eid]
    rows.append({
        "candidate_edge_index": int(eid),
        "candidate_vertex_indices": json.dumps(vpair.tolist()),
        "raw_source_vertex_indices": json.dumps(cand_to_raw_v[vpair].tolist()),
        "endpoint_xyz_source_units": json.dumps(v[vpair].tolist(), separators=(",", ":")),
        "incident_edge_occurrence_count": int(counts[eid]),
        "candidate_face_indices": json.dumps(local_faces.tolist()),
        "raw_source_face_indices": json.dumps(cand_to_raw_f[local_faces].tolist()),
        "edge_slot_in_incident_faces": json.dumps(local_edge_ids[occurrence_ids].tolist()),
        "incident_winding_faces": json.dumps(f[local_faces].tolist()),
    })
with (audit / "nonmanifold_edges_diagnostic.csv").open("w", newline="", encoding="utf-8") as out:
    cols = list(rows[0]) if rows else ["candidate_edge_index"]
    w = csv.DictWriter(out, fieldnames=cols); w.writeheader(); w.writerows(rows)

sorted_f = np.sort(f, axis=1)
u, inv, cnt = np.unique(sorted_f, axis=0, return_inverse=True, return_counts=True)
dup_rows = []
for gid in np.flatnonzero(cnt > 1):
    faces = np.flatnonzero(inv == gid)
    dup_rows.append({
        "canonical_candidate_vertex_indices": json.dumps(u[gid].tolist()),
        "candidate_face_indices": json.dumps(faces.tolist()),
        "raw_source_face_indices": json.dumps(cand_to_raw_f[faces].tolist()),
        "winding_variants": json.dumps(f[faces].tolist()),
        "coordinates_source_units": json.dumps(v[u[gid]].tolist(), separators=(",", ":")),
    })
with (audit / "duplicate_faces_diagnostic.csv").open("w", newline="", encoding="utf-8") as out:
    cols = list(dup_rows[0]) if dup_rows else ["canonical_candidate_vertex_indices"]
    w = csv.DictWriter(out, fieldnames=cols); w.writeheader(); w.writerows(dup_rows)
print(json.dumps({"nonmanifold_edges": rows, "duplicate_face_groups": dup_rows}, indent=2))
