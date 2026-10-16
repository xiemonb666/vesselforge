"""Small parametric turned vessel with a genuinely fused swept handle."""

from __future__ import annotations

from dataclasses import dataclass
from math import acos, degrees, hypot, isfinite, sqrt
from pathlib import Path

import cadquery as cq
import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepTools import BRepTools
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_Orientation
from OCP.TopLoc import TopLoc_Location
from OCP.gp import gp_Pnt, gp_Pnt2d


PROFILE: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (14.0, 0.0),
    (14.8, 2.0),
    (15.8, 6.0),
    (17.8, 12.0),
    (19.6, 20.0),
    (20.5, 28.0),
    (20.0, 36.0),
    (18.8, 44.0),
    (18.0, 50.0),
    (18.0, 56.0),
)


@dataclass(frozen=True)
class VesselSpec:
    """Locally adjustable parameters for this prototype form only."""

    body_width_mm: float = 41.0
    body_height_mm: float = 56.0
    wall_mm: float = 4.0
    handle_radius_mm: float = 2.6
    handle_outreach_mm: float = 30.0
    handle_low_z_mm: float = 12.0
    handle_high_z_mm: float = 44.0
    tessellation_linear_mm: float = 0.10
    tessellation_angular_rad: float = 0.08

    def validate(self) -> None:
        numeric = {
            "body_width_mm": self.body_width_mm,
            "body_height_mm": self.body_height_mm,
            "wall_mm": self.wall_mm,
            "handle_radius_mm": self.handle_radius_mm,
            "handle_outreach_mm": self.handle_outreach_mm,
            "handle_low_z_mm": self.handle_low_z_mm,
            "handle_high_z_mm": self.handle_high_z_mm,
            "tessellation_linear_mm": self.tessellation_linear_mm,
            "tessellation_angular_rad": self.tessellation_angular_rad,
        }
        for name, value in numeric.items():
            if isinstance(value, bool) or not isfinite(float(value)):
                raise ValueError(f"{name} must be a finite number; received {value!r}")
        if not (36.0 <= self.body_width_mm <= 48.0):
            raise ValueError("body_width_mm must be between 36 and 48 for this prototype")
        if not (50.0 <= self.body_height_mm <= 62.0):
            raise ValueError("body_height_mm must be between 50 and 62 for this prototype")
        if not (3.5 <= self.wall_mm <= 5.0):
            raise ValueError("wall_mm must be between 3.5 and 5 for this prototype")
        if not (1.5 <= self.handle_radius_mm <= 4.0):
            raise ValueError("handle_radius_mm must be between 1.5 and 4.0 for this prototype")
        if not (self.body_width_mm / 2 < self.handle_outreach_mm <= 45.0):
            raise ValueError("handle_outreach_mm must extend beyond the body radius and be at most 45 mm")
        if not (0.15 * self.body_height_mm <= self.handle_low_z_mm <= 0.40 * self.body_height_mm):
            raise ValueError("handle_low_z_mm must lie in the lower 15%-40% of body height")
        if not (0.60 * self.body_height_mm <= self.handle_high_z_mm <= 0.90 * self.body_height_mm):
            raise ValueError("handle_high_z_mm must lie in the upper 60%-90% of body height")
        if self.handle_high_z_mm - self.handle_low_z_mm < 0.40 * self.body_height_mm:
            raise ValueError("handle attachment heights must be separated by at least 40% of body height")
        if not (0.04 <= self.tessellation_linear_mm <= 0.25):
            raise ValueError("tessellation_linear_mm must be between 0.04 and 0.25 mm to bound local mesh size")
        if not (0.02 <= self.tessellation_angular_rad <= 0.20):
            raise ValueError("tessellation_angular_rad must be between 0.02 and 0.20 radians")


def scaled_outer_profile(spec: VesselSpec) -> list[tuple[float, float]]:
    scale_r = spec.body_width_mm / 41.0
    scale_z = spec.body_height_mm / 56.0
    return [(r * scale_r, z * scale_z) for r, z in PROFILE]


def _unit(vector: tuple[float, float]) -> tuple[float, float]:
    length = hypot(*vector)
    if length == 0:
        raise ValueError("profile has a zero-length segment")
    return vector[0] / length, vector[1] / length


def _offset_body_profile_inward(
    outer: list[tuple[float, float]], wall_mm: float
) -> list[tuple[float, float]]:
    """Miter-offset the vessel side profile by a true meridian normal distance."""
    # The first three profile points form the solid foot/base. The open vessel side
    # starts at the 6 mm shoulder and continues to the lip.
    side = outer[3:]
    tangents = [_unit((b[0] - a[0], b[1] - a[1])) for a, b in zip(side, side[1:])]
    inward_normals = [(-tz, tr) for tr, tz in tangents]
    result = [
        (side[0][0] + wall_mm * inward_normals[0][0], side[0][1] + wall_mm * inward_normals[0][1])
    ]
    for i in range(1, len(side) - 1):
        n0, n1 = inward_normals[i - 1], inward_normals[i]
        miter = _unit((n0[0] + n1[0], n0[1] + n1[1]))
        denom = miter[0] * n1[0] + miter[1] * n1[1]
        if denom <= 0.1:
            raise ValueError("profile offset is unstable at a corner")
        scale = wall_mm / denom
        result.append((side[i][0] + scale * miter[0], side[i][1] + scale * miter[1]))
    result.append(
        (side[-1][0] + wall_mm * inward_normals[-1][0], side[-1][1] + wall_mm * inward_normals[-1][1])
    )
    return result


def build_components(spec: VesselSpec = VesselSpec()) -> tuple[cq.Shape, cq.Shape, cq.Shape]:
    """Build and return body, swept handle, and boolean-fused assembly."""
    spec.validate()
    outer = scaled_outer_profile(spec)
    inner_side = _offset_body_profile_inward(outer, spec.wall_mm)
    floor_z = spec.wall_mm
    inner_floor_radius = inner_side[0][0]
    if inner_floor_radius <= 0 or inner_side[0][1] <= floor_z:
        raise ValueError("wall/floor combination leaves no usable cavity")

    # Meridian polygon: outer underside→outer wall→lip→normal-offset inner wall→floor.
    section = outer + list(reversed(inner_side)) + [(inner_floor_radius, floor_z), (0.0, floor_z)]
    body = (
        cq.Workplane("XZ")
        .polyline(section)
        .close()
        .revolve(360, (0, 0, 0), (0, 1, 0), combine=False)
        .val()
    )
    outer_radius = spec.body_width_mm / 2
    root_x = outer_radius * 0.83
    low = spec.handle_low_z_mm
    high = spec.handle_high_z_mm
    reach = spec.handle_outreach_mm
    path = (
        cq.Workplane("XZ")
        .moveTo(root_x, low)
        .lineTo(reach - 5.0, low)
        .threePointArc((reach - 1.464466094, low + 1.464466094), (reach, low + 5.0))
        .lineTo(reach, high - 5.0)
        .threePointArc((reach - 1.464466094, high - 1.464466094), (reach - 5.0, high))
        .lineTo(outer_radius * 0.88, high)
        .wire()
        .val()
    )
    tangent = path.Edges()[0].tangentAt(0).toTuple()
    plane = cq.Plane(origin=(root_x, 0, low), xDir=(0, 1, 0), normal=tangent)
    handle = cq.Workplane(plane).circle(spec.handle_radius_mm).sweep(path, isFrenet=True, transition="round").val()
    merged = body.fuse(handle).clean()
    if not merged.isValid() or len(merged.Solids()) != 1 or len(merged.Shells()) != 1:
        raise ValueError("vessel and handle did not produce one valid connected solid")
    if merged.Volume() <= body.Volume() or body.Volume() <= 0:
        raise ValueError("fused vessel has invalid or non-positive volume")
    return body, handle, merged


def build_vessel(spec: VesselSpec = VesselSpec()) -> cq.Shape:
    """Build one open-cavity turned body fused to an actually swept handle."""
    return build_components(spec)[2]


def mesh_shape(shape: cq.Shape, spec: VesselSpec) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    # CadQuery Shape.mesh requests relative deflection. This contract records an
    # absolute-mm chord target, so clear any stale triangulation and call the
    # mature OCC mesher with isRelative=False before extracting each B-rep face.
    BRepTools.Clean_s(shape.wrapped, True)
    mesher = BRepMesh_IncrementalMesh(
        shape.wrapped,
        spec.tessellation_linear_mm,
        False,
        spec.tessellation_angular_rad,
        False,
    )
    mesher.Perform()
    if not mesher.IsDone():
        raise ValueError("OpenCascade absolute-deflection tessellation failed")

    vertices: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []
    triangle_sources: list[int] = []
    offset = 0
    for face_index, face in enumerate(shape.Faces()):
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face.wrapped, location)
        if triangulation is None:
            continue
        transform = location.Transformation()
        for index in range(1, triangulation.NbNodes() + 1):
            point = triangulation.Node(index).Transformed(transform)
            vertices.append((point.X(), point.Y(), point.Z()))
        reverse = face.wrapped.Orientation() == TopAbs_Orientation.TopAbs_REVERSED
        for triangle in triangulation.Triangles():
            if reverse:
                triangles.append((triangle.Value(1) + offset - 1, triangle.Value(3) + offset - 1, triangle.Value(2) + offset - 1))
            else:
                triangles.append((triangle.Value(1) + offset - 1, triangle.Value(2) + offset - 1, triangle.Value(3) + offset - 1))
            triangle_sources.append(face_index)
        offset += triangulation.NbNodes()
    raw_vertices = np.asarray(vertices, dtype=np.float64)
    raw_faces = np.asarray(triangles, dtype=np.int64)
    # CadQuery/OCP may return a separate triangulation per B-rep face. Weld the
    # coincident seam vertices so the exported surface is a single manifold mesh.
    weld_tol_mm = min(1e-5, spec.tessellation_linear_mm * 1e-4)
    key_to_index: dict[tuple[int, int, int], int] = {}
    sums: list[np.ndarray] = []
    counts: list[int] = []
    remap = np.empty(len(raw_vertices), dtype=np.int64)
    for i, point in enumerate(raw_vertices):
        key = tuple(np.rint(point / weld_tol_mm).astype(np.int64).tolist())
        index = key_to_index.get(key)
        if index is None:
            index = len(sums)
            key_to_index[key] = index
            sums.append(point.copy())
            counts.append(1)
        else:
            sums[index] += point
            counts[index] += 1
        remap[i] = index
    vertex_array = np.asarray([point / count for point, count in zip(sums, counts)], dtype=np.float64)
    face_array = remap[raw_faces]
    source_array = np.asarray(triangle_sources, dtype=np.int32)
    nondegenerate = np.asarray(
        [len({int(a), int(b), int(c)}) == 3 for a, b, c in face_array], dtype=bool
    )
    face_array = face_array[nondegenerate]
    source_array = source_array[nondegenerate]
    if vertex_array.ndim != 2 or vertex_array.shape[1:] != (3,) or len(face_array) == 0:
        raise ValueError("CAD tessellation returned an empty or malformed mesh")
    signed = float(
        np.einsum(
            "ij,ij->i",
            vertex_array[face_array[:, 0]],
            np.cross(vertex_array[face_array[:, 1]], vertex_array[face_array[:, 2]]),
        ).sum()
        / 6.0
    )
    if signed < 0:
        face_array = face_array[:, [0, 2, 1]]
    return vertex_array, face_array.astype(np.int32), source_array


def mesh_topology_metrics(vertices: np.ndarray, faces: np.ndarray) -> dict[str, int | float | bool]:
    edge_counts: dict[tuple[int, int], int] = {}
    area2_min = float("inf")
    for a, b, c in faces.astype(np.int64, copy=False):
        pa, pb, pc = vertices[a], vertices[b], vertices[c]
        area2 = float(np.linalg.norm(np.cross(pb - pa, pc - pa)))
        area2_min = min(area2_min, area2)
        for i, j in ((a, b), (b, c), (c, a)):
            edge = (int(min(i, j)), int(max(i, j)))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    volumes = float(
        np.einsum(
            "ij,ij->i",
            vertices[faces[:, 0]],
            np.cross(vertices[faces[:, 1]], vertices[faces[:, 2]]),
        ).sum()
        / 6.0
    )
    return {
        "vertices": int(len(vertices)),
        "triangles": int(len(faces)),
        "boundary_edges": sum(count == 1 for count in edge_counts.values()),
        "nonmanifold_edges": sum(count != 2 for count in edge_counts.values()),
        "minimum_double_area_mm2": area2_min,
        "signed_volume_mm3": volumes,
        "watertight": all(count == 2 for count in edge_counts.values()),
    }


def measure_profile_wall(spec: VesselSpec) -> dict[str, float | str]:
    """Measure the analytic meridian offset profile; not a full-solid B-rep test."""
    outer = scaled_outer_profile(spec)
    inner = _offset_body_profile_inward(outer, spec.wall_mm)
    outer_side = outer[3:]

    def point_segment_distance(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        dx, dz = b[0] - a[0], b[1] - a[1]
        denom = dx * dx + dz * dz
        u = 0.0 if denom == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dz) / denom))
        return hypot(p[0] - (a[0] + u * dx), p[1] - (a[1] + u * dz))

    distances: list[float] = []
    for a, b in zip(inner, inner[1:]):
        for k in range(21):
            t = k / 20
            p = (a[0] * (1 - t) + b[0] * t, a[1] * (1 - t) + b[1] * t)
            distances.append(min(point_segment_distance(p, oa, ob) for oa, ob in zip(outer_side, outer_side[1:])))
    # The flat base is exactly floor_z above the exterior underside at z=0.
    return {
        "declared_wall_mm": float(spec.wall_mm),
        "analytic_min_side_profile_separation_mm": float(min(distances)),
        "analytic_floor_thickness_mm": float(spec.wall_mm),
        "source": "construction-profile point-to-segment measurement; CAD base/joint checks are reported separately",
        "scope": "side profile and flat floor only; not a global minimum-wall proof over the fused CAD solid",
    }


def measure_cad_floor_and_handle_roots(
    body: cq.Shape, handle: cq.Shape, merged: cq.Shape, spec: VesselSpec
) -> dict[str, object]:
    """Measure floor face separation and actual CAD overlap at both handle roots."""
    planar = [face for face in body.Faces() if face.geomType() == "PLANE"]
    bottom_candidates = [face for face in planar if abs(face.Center().z) < 1e-5]
    floor_candidates = [face for face in planar if abs(face.Center().z - spec.wall_mm) < 1e-5]
    if not bottom_candidates or not floor_candidates:
        raise ValueError("could not identify CAD underside and cavity floor faces")
    floor_distance = min(bottom.distance(floor) for bottom in bottom_candidates for floor in floor_candidates)

    radius = spec.body_width_mm / 2
    root_x = radius * 0.83
    root_metrics: dict[str, object] = {}
    for name, z in (("lower", spec.handle_low_z_mm), ("upper", spec.handle_high_z_mm)):
        # The window includes the complete swept section embedded in the vessel.
        window = cq.Solid.makeBox(
            2 * spec.handle_radius_mm + 10.0,
            2 * spec.handle_radius_mm + 8.0,
            2 * spec.handle_radius_mm + 4.0,
            cq.Vector(root_x - spec.handle_radius_mm - 5.0, -spec.handle_radius_mm - 4.0, z - spec.handle_radius_mm - 2.0),
        )
        local = merged.intersect(window).clean()
        root_metrics[name] = {
            "window_solid_count": len(local.Solids()),
            "window_volume_mm3": float(local.Volume()),
            "cad_valid": bool(local.isValid() and len(local.Solids()) == 1 and local.Volume() > 0),
            "measurement": "actual B-rep intersection within documented local window; not a load-strength test",
        }
    body_handle_overlap = float(body.Volume() + handle.Volume() - merged.Volume())
    return {
        "cad_floor_face_separation_mm": float(floor_distance),
        "floor_measurement": "minimum OCC distance between planar underside and cavity-floor B-rep faces",
        "handle_attachment_windows": root_metrics,
        "body_handle_intersection_volume_mm3": body_handle_overlap,
        "body_handle_intersection_status": "positive overlap is required; this is geometric connectivity evidence only",
    }


def profile_curvature_metrics(spec: VesselSpec) -> dict[str, float | bool]:
    profile = scaled_outer_profile(spec)[3:]
    tangents = [_unit((b[0] - a[0], b[1] - a[1])) for a, b in zip(profile, profile[1:])]
    turns = []
    for a, b in zip(tangents, tangents[1:]):
        dot = max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1]))
        turns.append(degrees(acos(dot)))
    max_circ = 0.0
    for a, b in zip(profile, profile[1:]):
        r = (a[0] + b[0]) / 2
        slope = (b[0] - a[0]) / (b[1] - a[1])
        max_circ = max(max_circ, 1.0 / (max(r, 1e-9) * sqrt(1 + slope * slope)))
    return {
        "max_meridian_corner_turn_deg": max(turns, default=0.0),
        "max_azimuthal_curvature_per_mm": max_circ,
        "profile_corners_filleted": False,
    }


def point_to_trimmed_face_metrics(
    face: cq.Face, point: np.ndarray, tolerance: float = 1e-7
) -> dict[str, object]:
    """Measure a point against the true trimmed face domain.

    Every supporting-surface projection candidate is UV-classified, including
    periodic copies. If no candidate lies on the trimmed face, the nearest real
    trim edge/vertex distance is measured; a zero supporting-surface distance
    outside the trim is never treated as a face hit.
    """
    surface = BRep_Tool.Surface_s(face.wrapped)
    projection = GeomAPI_ProjectPointOnSurf(
        gp_Pnt(float(point[0]), float(point[1]), float(point[2])), surface
    )
    u_min, u_max, v_min, v_max = BRepTools.UVBounds_s(face.wrapped)
    u_period = float(surface.UPeriod()) if surface.IsUPeriodic() else None
    v_period = float(surface.VPeriod()) if surface.IsVPeriodic() else None
    valid: list[dict[str, object]] = []
    candidates: list[dict[str, object]] = []
    for i in range(1, projection.NbPoints() + 1):
        u, v = projection.Parameters(i)
        u_shifts = (-2, -1, 0, 1, 2) if u_period else (0,)
        v_shifts = (-2, -1, 0, 1, 2) if v_period else (0,)
        for du in u_shifts:
            for dv in v_shifts:
                uu = float(u + du * (u_period or 0.0))
                vv = float(v + dv * (v_period or 0.0))
                if uu < u_min - tolerance or uu > u_max + tolerance or vv < v_min - tolerance or vv > v_max + tolerance:
                    continue
                classifier = BRepClass_FaceClassifier(face.wrapped, gp_Pnt2d(uu, vv), tolerance)
                state = classifier.State()
                item = {
                    "u": uu,
                    "v": vv,
                    "distance_mm": float(projection.Distance(i)),
                    "state": str(state),
                    "periodic_shift": [du, dv],
                }
                candidates.append(item)
                if state in (TopAbs_IN, TopAbs_ON):
                    valid.append(item)
    if valid:
        chosen = min(valid, key=lambda item: float(item["distance_mm"]))
        return {
            "status": "IN_OR_ON",
            "distance_mm": float(chosen["distance_mm"]),
            "projection_count": projection.NbPoints(),
            "chosen": chosen,
            "candidates_in_bounds": candidates,
        }

    # Outside a trimmed face, the nearest point must lie on one of its real
    # boundary edges (including vertices). Keep the winning edge explicit.
    vertex = cq.Vertex.makeVertex(float(point[0]), float(point[1]), float(point[2]))
    edge_distances = []
    for edge_index, edge in enumerate(face.Edges()):
        distance_shape = BRepExtrema_DistShapeShape(vertex.wrapped, edge.wrapped)
        distance_shape.Perform()
        if distance_shape.IsDone() and np.isfinite(float(distance_shape.Value())):
            edge_distances.append((float(distance_shape.Value()), edge_index))
    if edge_distances:
        edge_distance, edge_index = min(edge_distances)
        return {
            "status": "OUTSIDE_PROJECTION_NEAREST_TRIM_EDGE",
            "distance_mm": edge_distance,
            "projection_count": projection.NbPoints(),
            "nearest_trim_edge_index_zero_based": edge_index,
            "candidates_in_bounds": candidates,
        }
    return {
        "status": "UNKNOWN_NO_FINITE_TRIM_EDGE_DISTANCE",
        "distance_mm": None,
        "projection_count": projection.NbPoints(),
        "candidates_in_bounds": candidates,
    }


def sampled_mesh_to_cad_metrics(
    shape: cq.Shape,
    vertices: np.ndarray,
    faces: np.ndarray,
    source_face_indices: np.ndarray,
    sample_limit: int = 600,
) -> dict[str, object]:
    """Compare deterministic samples with the same canonical STEP B-rep used
    to create the delivered surface mesh.

    Triangle lineage indexes faces on ``shape`` directly. There is deliberately
    no source-solid-to-imported-STEP face matching: the STEP re-import is the
    canonical solid for both meshing and this trimmed-domain check.
    """
    step_faces = shape.Faces()
    face_map: dict[int, int] = {}
    face_match_detail: dict[str, object] = {}
    for source_index in sorted(set(int(index) for index in source_face_indices)):
        if 0 <= source_index < len(step_faces):
            face_map[source_index] = source_index
            face_match_detail[str(source_index)] = {
                "status": "MATCHED",
                "canonical_step_face_index_zero_based": source_index,
                "method": "identity: triangle was tessellated from this canonical STEP-imported face",
            }
        else:
            face_match_detail[str(source_index)] = {
                "status": "UNKNOWN",
                "reason": "triangle lineage index is outside canonical STEP face inventory",
            }

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
        sources = sorted({int(source_face_indices[index]) for index in triangle_ids})
        samples.append(("edge_midpoint", (vertices[a].astype(np.float64) + vertices[b].astype(np.float64)) / 2, triangle_id, sources))
    for triangle_id in range(0, len(faces), tri_stride):
        tri = faces[triangle_id]
        samples.append(("triangle_centroid", vertices[tri].astype(np.float64).mean(axis=0), triangle_id, [int(source_face_indices[triangle_id])]))
    max_distance: float | None = None
    valid_sample_count = 0
    unknown_count = 0
    periodic_distance_disagreement_count = 0
    unknown_samples: list[dict[str, object]] = []
    worst_valid_sample: dict[str, object] = {}
    first_unknown_sample: dict[str, object] = {}
    for sample_index, (sample_kind, point, triangle_id, source_ids) in enumerate(samples):
        candidate_checks = []
        for source_id in source_ids:
            if source_id not in face_map:
                continue
            step_id = face_map[source_id]
            step_projection = point_to_trimmed_face_metrics(step_faces[step_id], point)
            if step_projection["status"] == "IN_OR_ON":
                step_error = float(step_projection["chosen"]["distance_mm"])
                candidate_checks.append((step_error, source_id, step_id, step_projection))
            elif step_projection["status"] == "OUTSIDE_PROJECTION_NEAREST_TRIM_EDGE":
                edge_error = float(step_projection["distance_mm"])
                candidate_checks.append((edge_error, source_id, step_id, step_projection))
        if not candidate_checks:
            unknown_count += 1
            unknown_record: dict[str, object] = {
                    "sample_index": sample_index,
                    "sample_kind": sample_kind,
                    "sample_xyz_mm": [float(v) for v in point],
                    "mesh_triangle_index": triangle_id,
                    "mesh_triangle_source_brep_face_indices": source_ids,
                    "status": "UNKNOWN_OUTSIDE_OR_UNMATCHED_TRIMMED_DOMAIN",
                    "source_step_mapping_status": {str(source_id): face_match_detail.get(str(source_id)) for source_id in source_ids},
                }
            for source_id in source_ids:
                if source_id in face_map:
                    step_id = face_map[source_id]
                    unknown_record.setdefault("trimmed_projection_status", {})[str(source_id)] = point_to_trimmed_face_metrics(step_faces[step_id], point)
            if len(unknown_samples) < 20:
                unknown_samples.append(unknown_record)
            if not first_unknown_sample:
                first_unknown_sample = unknown_record
            continue
        candidate_checks.sort(key=lambda item: item[0])
        distance, selected_source_id, selected_step_id, step_projection = candidate_checks[0]
        valid_sample_count += 1
        if max_distance is None or distance > max_distance:
            max_distance = float(distance)
            vertex = cq.Vertex.makeVertex(float(point[0]), float(point[1]), float(point[2]))
            direct = BRepExtrema_DistShapeShape(vertex.wrapped, step_faces[selected_step_id].wrapped)
            direct.Perform()
            direct_distance = float(direct.Value()) if direct.IsDone() else None
            if direct_distance is not None and direct_distance > max(distance, 0.0) + 1e-4:
                periodic_distance_disagreement_count += 1
            worst_valid_sample = {
                "sample_index": sample_index,
                "sample_kind": sample_kind,
                "sample_xyz_mm": [float(v) for v in point],
                "max_valid_trimmed_surface_projection_distance_mm": distance,
                "source_brep_face_index_zero_based": selected_source_id,
                "matched_step_face_index_zero_based": selected_step_id,
                "step_face_match": face_match_detail.get(str(selected_source_id)),
                "step_trimmed_projection": step_projection,
                "BRepExtrema_DistShapeShape_step_point_to_trimmed_face_mm": direct_distance,
                "BRepExtrema_note": "diagnostic only; periodic-seam mismatch is recorded when it disagrees with classifier-valid UV projection",
                "mesh_triangle_index": triangle_id,
                "mesh_triangle_source_brep_face_indices": source_ids,
                "mesh_triangle_vertices_xyz_mm": vertices[faces[triangle_id]].astype(float).tolist(),
                "status": "CANONICAL_STEP_TRIMMED_FACE_DISTANCE_MEASURED",
            }
    return {
        "max_sampled_deviation_mm": max_distance,
        "valid_sample_count": valid_sample_count,
        "projection_status": "PASS" if unknown_count == 0 and valid_sample_count == len(samples) else "UNKNOWN",
        "sample_count": len(samples),
        "unknown_sample_count": unknown_count,
        "unknown_samples_first_20": unknown_samples,
        "periodic_brep_extrema_disagreement_sample_count": periodic_distance_disagreement_count,
        "face_match_method": "identity triangle lineage on canonical STEP-imported solid",
        "trim_validation_method": "all GeomAPI projection candidates + periodic shifts + BRepClass_FaceClassifier IN/ON; out-of-trim projections use exact BRepExtrema point-to-trim-edge distance",
        "sampling_method": "deterministic edge-midpoint and triangle-centroid samples linked to canonical STEP B-rep face; not a full Hausdorff proof",
        "canonical_step_face_map": face_match_detail,
        "worst_valid_sample": worst_valid_sample or None,
        "first_unknown_sample": first_unknown_sample or None,
    }


def section_shape(shape: cq.Shape) -> cq.Shape:
    """Return an actual CAD half-section through the bowl and handle center plane."""
    cutter = cq.Solid.makeBox(120, 70, 100, cq.Vector(-40, 0, -20))
    result = shape.intersect(cutter).clean()
    if not result.isValid() or len(result.Solids()) != 1:
        raise ValueError("axial half-section did not remain one valid CAD solid")
    return result


def export_step(shape: cq.Shape, destination: str) -> None:
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(shape, destination, exportType="STEP")

