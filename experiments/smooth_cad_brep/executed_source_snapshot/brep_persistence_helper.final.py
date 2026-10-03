"""Small, isolated helpers for the native BREP persistence candidate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cadquery as cq
import numpy as np
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffset
from OCP.GeomAbs import GeomAbs_JoinType


def build_exact_profile_candidate(design: Any, wall_mm: float) -> tuple[cq.Shape, dict[str, Any]]:
    """Rebuild the already accepted exact-Bezier profile and its +wall offset."""
    lower = design.bezier_as_bspline(design.LOWER_POLES_RZ)
    upper = design.bezier_as_bspline(design.UPPER_POLES_RZ)
    side_wire = cq.Wire.assembleEdges([lower, upper])
    if not side_wire.isValid() or side_wire.IsClosed() or len(side_wire.Edges()) != 2:
        raise ValueError("physical profile did not produce a valid open two-edge meridian")

    native_edges = [design.native_edge_report(edge) for edge in (lower, upper)]
    join = design.derivative_join_report(lower, upper)
    curvature = design.curvature_report([lower, upper], sample_count_per_edge=2001)
    if (
        any(edge["degree"] != 5 or not edge["is_C2"] for edge in native_edges)
        or not join["C2_join"]
        or curvature["samples_below_threshold"] != 0
    ):
        raise ValueError("the unchanged source meridian failed its degree-5/C2/curvature checks")

    offset = BRepOffsetAPI_MakeOffset()
    offset.Init(GeomAbs_JoinType.GeomAbs_Arc, True)
    offset.AddWire(side_wire.wrapped)
    offset.Perform(wall_mm)
    offset.Build()
    raw = offset.Shape()
    if not offset.IsDone() or raw.IsNull():
        raise ValueError("native OCC planar offset failed")
    offset_shape = cq.Shape.cast(raw)
    offset_wires = offset_shape.Wires()
    if len(offset_wires) != 1 or not offset_wires[0].isValid() or offset_wires[0].IsClosed():
        raise ValueError("native planar offset is not one valid open wire")
    offset_wire = offset_wires[0]

    bottom_inner = min(
        (vertex.Center().toTuple() for vertex in offset_wire.Vertices()),
        key=lambda point: float(point[2]),
    )
    top_inner = max(
        (vertex.Center().toTuple() for vertex in offset_wire.Vertices()),
        key=lambda point: float(point[2]),
    )
    expected_bottom = np.asarray([12.5, 0.0, wall_mm], dtype=np.float64)
    expected_top = np.asarray([14.0, 0.0, 56.0], dtype=np.float64)
    bottom_error = float(np.linalg.norm(np.asarray(bottom_inner) - expected_bottom))
    top_error = float(np.linalg.norm(np.asarray(top_inner) - expected_top))
    if max(bottom_error, top_error) > 0.10:
        raise ValueError("native offset endpoints no longer meet the accepted floor and lip")

    profile_edges = [
        cq.Edge.makeLine(cq.Vector(0.0, 0.0, 0.0), lower.startPoint()),
        lower,
        upper,
        cq.Edge.makeLine(upper.endPoint(), cq.Vector(14.0, 0.0, 56.0)),
        *[edge.reverse() for edge in reversed(offset_wire.Edges())],
        cq.Edge.makeLine(cq.Vector(12.5, 0.0, wall_mm), cq.Vector(0.0, 0.0, wall_mm)),
        cq.Edge.makeLine(cq.Vector(0.0, 0.0, wall_mm), cq.Vector(0.0, 0.0, 0.0)),
    ]
    profiles = cq.Wire.combine(profile_edges, tol=1e-6)
    if len(profiles) != 1 or not profiles[0].isValid() or not profiles[0].IsClosed():
        raise ValueError("closed material meridian did not form one valid wire")
    profile_face = cq.Face.makeFromWires(profiles[0])
    if not profile_face.isValid() or profile_face.Area() <= 0.0:
        raise ValueError("closed material meridian face is invalid or has non-positive area")

    revolved = (
        cq.Workplane("XZ")
        .newObject([profiles[0]])
        .toPending()
        .revolve(360.0, (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), combine=False)
        .val()
    )
    if not revolved.isValid() or len(revolved.Solids()) != 1 or len(revolved.Shells()) != 1:
        raise ValueError("unchanged profile revolve did not make one valid solid and shell")

    details = {
        "source_meridian": {
            "native_edges": native_edges,
            "internal_join": join,
            "sampled_curvature": curvature,
        },
        "offset": {
            "api": "OCP BRepOffsetAPI_MakeOffset",
            "distance_mm": float(wall_mm),
            "join": "GeomAbs_Arc",
            "is_done": bool(offset.IsDone()),
            "valid": bool(offset_shape.isValid()),
            "wire_count": len(offset_wires),
            "edge_count": len(offset_wire.Edges()),
            "bottom_endpoint_mm": [float(value) for value in bottom_inner],
            "top_endpoint_mm": [float(value) for value in top_inner],
            "bottom_endpoint_error_mm": bottom_error,
            "top_endpoint_error_mm": top_error,
        },
        "closed_profile": {
            "valid": bool(profiles[0].isValid()),
            "face_valid": bool(profile_face.isValid()),
            "face_area_mm2": float(profile_face.Area()),
        },
    }
    return revolved.Solids()[0], details


def save_actual_brep_preview(
    path: Path,
    body_vertices: np.ndarray,
    body_faces: np.ndarray,
    section_vertices: np.ndarray,
    section_faces: np.ndarray,
) -> dict[str, Any]:
    """Render tessellations created from the actual reimported BREP shapes."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    def triangles(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
        return np.asarray(vertices, dtype=np.float64)[np.asarray(faces, dtype=np.int64)]

    def add_surface(ax: Any, tris: np.ndarray, base_rgb: tuple[float, float, float], cut_mask: np.ndarray | None = None) -> None:
        normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        norms = np.linalg.norm(normals, axis=1)
        normals = normals / np.maximum(norms[:, None], 1e-12)
        light = np.asarray([-0.42, -0.62, 0.66], dtype=np.float64)
        light /= np.linalg.norm(light)
        shade = 0.70 + 0.30 * np.clip(np.abs(normals @ light), 0.0, 1.0)
        colors = np.clip(np.asarray(base_rgb)[None, :] * shade[:, None], 0.0, 1.0)
        if cut_mask is not None:
            colors[cut_mask] = np.asarray([0.78, 0.43, 0.29])
        collection = Poly3DCollection(
            tris,
            facecolors=colors,
            edgecolors=(0.20, 0.18, 0.16, 0.12),
            linewidths=0.035,
            antialiased=True,
        )
        ax.add_collection3d(collection)
        points = tris.reshape(-1, 3)
        lo = points.min(axis=0)
        hi = points.max(axis=0)
        pad = np.asarray([2.5, 2.5, 2.0])
        ax.set_xlim(float(lo[0] - pad[0]), float(hi[0] + pad[0]))
        ax.set_ylim(float(lo[1] - pad[1]), float(hi[1] + pad[1]))
        ax.set_zlim(float(lo[2] - pad[2]), float(hi[2] + pad[2]))
        ax.set_box_aspect((max(hi[0] - lo[0], 1.0), max(hi[1] - lo[1], 1.0), max(hi[2] - lo[2], 1.0)))
        ax.set_axis_off()

    body_tris = triangles(body_vertices, body_faces)
    section_tris = triangles(section_vertices, section_faces)
    section_cut_mask = np.all(np.abs(section_tris[:, :, 1]) <= 1e-5, axis=1)

    fig = plt.figure(figsize=(15.5, 8.0), facecolor="#f3f0e9")
    ax_body = fig.add_subplot(1, 2, 1, projection="3d")
    ax_section = fig.add_subplot(1, 2, 2, projection="3d")
    for axis in (ax_body, ax_section):
        axis.set_facecolor("#f3f0e9")
    add_surface(ax_body, body_tris, (0.78, 0.81, 0.78))
    add_surface(ax_section, section_tris, (0.73, 0.78, 0.77), section_cut_mask)
    ax_body.view_init(elev=24, azim=-54, roll=0)
    ax_section.view_init(elev=15, azim=-90, roll=0)
    fig.suptitle("Native OCC BREP persistence candidate", fontsize=21, color="#28333a", y=0.96)
    fig.text(0.27, 0.08, "Reimported solid", ha="center", fontsize=13, color="#35424a")
    fig.text(0.74, 0.08, "Actual half-space cut • section face highlighted", ha="center", fontsize=13, color="#35424a")
    fig.text(0.5, 0.035, "Tessellations sampled from the native BREP candidate; no STEP file used", ha="center", fontsize=10, color="#68747a")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.91, bottom=0.13, wspace=0.03)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return {
        "renderer": "Matplotlib Poly3DCollection of mesh_shape outputs from reimported BREP and native half-space-cut BREP",
        "body_triangles": int(len(body_faces)),
        "section_triangles": int(len(section_faces)),
        "highlighted_section_triangles": int(section_cut_mask.sum()),
        "path": str(path),
    }


def sampled_mesh_to_native_brep_detail(
    shape: cq.Shape,
    vertices: np.ndarray,
    faces: np.ndarray,
    source_face_indices: np.ndarray,
    sample_limit: int = 600,
) -> dict[str, Any]:
    """Return max and percentile distances for the VF trimmed-face sample set."""
    from vesselforge.geometry import point_to_trimmed_face_metrics

    brep_faces = shape.Faces()
    edge_triangles: dict[tuple[int, int], list[int]] = {}
    for triangle_index, (a, b, c) in enumerate(faces):
        for i, j in ((int(a), int(b)), (int(b), int(c)), (int(c), int(a))):
            edge_triangles.setdefault((min(i, j), max(i, j)), []).append(triangle_index)

    sorted_edges = sorted(edge_triangles)
    edge_stride = max(1, len(sorted_edges) // max(1, sample_limit // 2))
    tri_stride = max(1, len(faces) // max(1, sample_limit // 2))
    samples: list[tuple[str, np.ndarray, int, list[int]]] = []
    for a, b in sorted_edges[::edge_stride]:
        triangle_ids = edge_triangles[(a, b)]
        triangle_id = triangle_ids[0]
        source_ids = sorted({int(source_face_indices[index]) for index in triangle_ids})
        samples.append(
            (
                "edge_midpoint",
                (vertices[a].astype(np.float64) + vertices[b].astype(np.float64)) / 2,
                triangle_id,
                source_ids,
            )
        )
    for triangle_id in range(0, len(faces), tri_stride):
        triangle = faces[triangle_id]
        samples.append(
            (
                "triangle_centroid",
                vertices[triangle].astype(np.float64).mean(axis=0),
                triangle_id,
                [int(source_face_indices[triangle_id])],
            )
        )

    distances: list[float] = []
    unknown_count = 0
    worst: dict[str, Any] | None = None
    for sample_index, (sample_kind, point, triangle_id, source_ids) in enumerate(samples):
        candidates: list[tuple[float, int, dict[str, Any]]] = []
        for face_id in source_ids:
            if not 0 <= face_id < len(brep_faces):
                continue
            projection = point_to_trimmed_face_metrics(brep_faces[face_id], point)
            if projection["status"] in ("IN_OR_ON", "OUTSIDE_PROJECTION_NEAREST_TRIM_EDGE"):
                candidates.append((float(projection["distance_mm"]), face_id, projection))
        if not candidates:
            unknown_count += 1
            continue
        distance, face_id, projection = min(candidates, key=lambda candidate: candidate[0])
        distances.append(distance)
        if worst is None or distance > worst["distance_mm"]:
            worst = {
                "sample_index": sample_index,
                "sample_kind": sample_kind,
                "sample_xyz_mm": [float(value) for value in point],
                "mesh_triangle_index": int(triangle_id),
                "mesh_triangle_source_brep_face_indices": source_ids,
                "matched_native_brep_face_index_zero_based": int(face_id),
                "distance_mm": float(distance),
                "trimmed_face_projection": projection,
            }

    percentiles = np.percentile(np.asarray(distances, dtype=np.float64), [50.0, 95.0, 99.0]) if distances else []
    return {
        "method": "same deterministic 600-sample edge-midpoint and triangle-centroid set as sampled_mesh_to_cad_metrics; identity lineage to native BREP face; BRep point-to-trimmed-face projection with UV IN/ON classification and exact nearest trim-edge fallback",
        "sample_limit": int(sample_limit),
        "sample_count": len(samples),
        "valid_sample_count": len(distances),
        "unknown_sample_count": int(unknown_count),
        "max_sampled_deviation_mm": float(max(distances)) if distances else None,
        "p50_sampled_deviation_mm": float(percentiles[0]) if len(percentiles) else None,
        "p95_sampled_deviation_mm": float(percentiles[1]) if len(percentiles) else None,
        "p99_sampled_deviation_mm": float(percentiles[2]) if len(percentiles) else None,
        "worst_sample": worst,
        "scope": "finite deterministic samples; not a full Hausdorff proof",
    }
