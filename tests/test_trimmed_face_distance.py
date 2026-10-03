from __future__ import annotations

import numpy as np
import cadquery as cq
from OCP.BRep import BRep_Tool
from OCP.BRepTools import BRepTools

from vesselforge.geometry import point_to_trimmed_face_metrics


def _surface_point(face, u: float, v: float) -> np.ndarray:
    point = BRep_Tool.Surface_s(face.wrapped).Value(float(u), float(v))
    return np.asarray([point.X(), point.Y(), point.Z()], dtype=np.float64)


def test_trimmed_projection_inside_outside_periodic_seam_and_rim(sample_packages) -> None:
    asset = sample_packages[0]
    step = asset / "geometry" / "solid.step"
    solid = cq.importers.importStep(str(step)).val()
    faces = solid.Faces()

    torus = next(face for face in faces if face.geomType() == "TORUS")
    u_min, u_max, v_min, v_max = BRepTools.UVBounds_s(torus.wrapped)
    torus_point = _surface_point(torus, (u_min + u_max) / 2, (v_min + v_max) / 2)
    torus_inside = point_to_trimmed_face_metrics(torus, torus_point)
    assert torus_inside["status"] == "IN_OR_ON"
    assert torus_inside["distance_mm"] < 1e-8

    cylinder = next(face for face in faces if face.geomType() == "CYLINDER" and face.Area() > 100)
    u_min, u_max, v_min, v_max = BRepTools.UVBounds_s(cylinder.wrapped)
    cylinder_inside = _surface_point(cylinder, (u_min + u_max) / 2, (v_min + v_max) / 2)
    inside_metrics = point_to_trimmed_face_metrics(cylinder, cylinder_inside)
    assert inside_metrics["status"] == "IN_OR_ON"
    assert inside_metrics["distance_mm"] < 1e-8

    # This point lies exactly on the infinite cylindrical support surface but
    # one parameter unit below the trimmed face. It must use the real trim edge.
    support_only = _surface_point(cylinder, (u_min + u_max) / 2, v_min - 1.0)
    outside_metrics = point_to_trimmed_face_metrics(cylinder, support_only)
    assert outside_metrics["status"] == "OUTSIDE_PROJECTION_NEAREST_TRIM_EDGE"
    assert outside_metrics["distance_mm"] > 0.1

    # The periodic seam is a valid ON-boundary point after UV period handling.
    seam_point = _surface_point(cylinder, u_min, (v_min + v_max) / 2)
    seam_metrics = point_to_trimmed_face_metrics(cylinder, seam_point)
    assert seam_metrics["status"] == "IN_OR_ON"
    assert seam_metrics["distance_mm"] < 1e-8

    rim = next(face for face in faces if face.geomType() == "PLANE" and abs(face.Center().z - 56.0) < 1e-5)
    rim_vertex = rim.Edges()[0].startPoint()
    rim_point = np.asarray([rim_vertex.x, rim_vertex.y, rim_vertex.z], dtype=np.float64)
    rim_metrics = point_to_trimmed_face_metrics(rim, rim_point)
    assert rim_metrics["status"] == "IN_OR_ON"
    assert rim_metrics["distance_mm"] < 1e-8
