import csv, json, pathlib, sys
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

root = pathlib.Path.cwd()
asset = root / "third_party/reference-assets/apsida-shm17946-0047/refined_v3"
audit = root / "vesselforge/experiments/continuation_20261015/scanned_anchor_audit/refinement_v3"
with np.load(asset / "SHM17946_0047_main_component_localrepair_candidate.npz") as z:
    v = z["vertices_source_units"]
    f = z["faces"].astype(np.int64, copy=False)
    v3_to_raw = z["candidate_vertex_to_raw_source_vertex"]

nverts = len(v)
a, b, c = f[:, 0], f[:, 1], f[:, 2]
center = np.concatenate((a, b, c))
n1 = np.concatenate((b, c, a))
n2 = np.concatenate((c, a, b))
key1 = center.astype(np.int64) * nverts + n1
key2 = center.astype(np.int64) * nverts + n2
all_keys = np.concatenate((key1, key2))
unique_keys, inv = np.unique(all_keys, return_inverse=True)
edge_count = len(key1)
left = inv[:edge_count]
right = inv[edge_count:]
degree = np.bincount(np.concatenate((left, right)), minlength=len(unique_keys))
rows = np.concatenate((left, right))
cols = np.concatenate((right, left))
adj = csr_matrix((np.ones(len(rows), dtype=np.uint8), (rows, cols)), shape=(len(unique_keys), len(unique_keys)))
component_count, component = connected_components(adj, directed=False, return_labels=True)
node_center = unique_keys // nverts
center_component_pairs = np.unique(np.column_stack((node_center, component)), axis=0)
link_component_count = np.bincount(center_component_pairs[:, 0], minlength=nverts)
bad_multi = np.flatnonzero(link_component_count != 1)
bad_degree_nodes = np.flatnonzero(degree != 2)
bad_centers_degree = np.unique(node_center[bad_degree_nodes]) if len(bad_degree_nodes) else np.empty(0, dtype=np.int64)
bad_centers = np.unique(np.concatenate((bad_multi, bad_centers_degree)))
rows_out = []
for vid in bad_centers:
    this_nodes = np.flatnonzero(node_center == vid)
    this_components = np.unique(component[this_nodes])
    rows_out.append({
        "v3_vertex_index": int(vid),
        "raw_source_vertex_index": int(v3_to_raw[vid]),
        "xyz_source_units": json.dumps(v[vid].tolist(), separators=(",", ":")),
        "link_node_count": int(len(this_nodes)),
        "link_component_count": int(len(this_components)),
        "link_node_degrees": json.dumps(degree[this_nodes].tolist()),
        "link_component_labels": json.dumps(this_components.tolist()),
        "interpretation": "Vertex link must be one connected cycle for a 2-manifold; mesh is not vertex-manifold here." if len(this_components) != 1 or np.any(degree[this_nodes] != 2) else "",
    })
with (audit / "vertex_link_anomalies.csv").open("w", newline="", encoding="utf-8") as out:
    fields = list(rows_out[0]) if rows_out else ["v3_vertex_index"]
    w = csv.DictWriter(out, fieldnames=fields); w.writeheader(); w.writerows(rows_out)
print(json.dumps({
    "vertex_count": int(nverts),
    "link_node_count": int(len(unique_keys)),
    "link_graph_connected_components_global": int(component_count),
    "vertices_with_multiple_disconnected_link_cycles": int(len(bad_multi)),
    "link_nodes_degree_not_2": int(len(bad_degree_nodes)),
    "vertices_with_bad_degree_nodes": int(len(bad_centers_degree)),
    "bad_vertices": rows_out,
}, indent=2))
