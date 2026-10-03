"""Fail-closed semantic classification of canonical STEP B-rep faces."""

from __future__ import annotations

from collections import Counter
from importlib.metadata import PackageNotFoundError, version as package_version
from math import hypot, isfinite
from typing import Any

import cadquery as cq
import numpy as np
import OCP
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.BRepLProp import BRepLProp_SLProps
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Torus
from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_REVERSED
from OCP.gp import gp_Pnt2d

CLASSIFIER_VERSION = "vf.canonical-step-face-semantics/1.0.0"
REGIONS: dict[int, str] = {
    1: "body_outer",
    2: "body_inner",
    3: "natural_rim",
    4: "base",
    5: "handle",
}
FRACTURE_RESERVE_CODE = 255
_UV_SAMPLE_FRACTIONS = (0.12, 0.25, 0.375, 0.5, 0.625, 0.75, 0.88)
_GEOMETRY_TOLERANCE_MM = 2e-3


def _vector(value: Any) -> list[float]:
    return [float(value.X()), float(value.Y()), float(value.Z())]


def _surface_name(surface_type: Any) -> str:
    return {
        GeomAbs_Plane: "plane",
        GeomAbs_Cylinder: "cylinder",
        GeomAbs_Cone: "cone",
        GeomAbs_Torus: "torus",
    }.get(surface_type, "unsupported")


def _interior_sample(face: cq.Face, adaptor: BRepAdaptor_Surface) -> dict[str, Any] | None:
    """Find a valid interior UV sample and its face-oriented normal."""
    u_min, u_max, v_min, v_max = BRepTools.UVBounds_s(face.wrapped)
    if not all(isfinite(float(value)) for value in (u_min, u_max, v_min, v_max)):
        return None
    if u_max - u_min <= 1e-12 or v_max - v_min <= 1e-12:
        return None
    candidates: list[tuple[float, dict[str, Any]]] = []
    for fu in _UV_SAMPLE_FRACTIONS:
        for fv in _UV_SAMPLE_FRACTIONS:
            u = float(u_min + fu * (u_max - u_min))
            v = float(v_min + fv * (v_max - v_min))
            classifier = BRepClass_FaceClassifier(face.wrapped, gp_Pnt2d(u, v), 1e-7)
            if classifier.State() not in (TopAbs_IN, TopAbs_ON):
                continue
            properties = BRepLProp_SLProps(adaptor, u, v, 1, 1e-7)
            if not properties.IsNormalDefined():
                continue
            point = adaptor.Value(u, v)
            normal = properties.Normal()
            if face.wrapped.Orientation() == TopAbs_REVERSED:
                normal.Reverse()
            sample = {
                "u": u,
                "v": v,
                "uv_state": "IN_OR_ON",
                "point_mm": _vector(point),
                "oriented_outward_normal": _vector(normal),
            }
            # Prefer UV samples far from the rectangle boundary. The trimmed
            # classifier still decides membership; this score only selects an
            # auditable representative point within that domain.
            margin = min(fu, 1.0 - fu, fv, 1.0 - fv)
            candidates.append((margin, sample))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _axis_surface_data(adaptor: BRepAdaptor_Surface, kind: str) -> dict[str, Any]:
    if kind == "plane":
        surface = adaptor.Plane()
        axis = surface.Axis()
        return {"origin_mm": _vector(surface.Location()), "axis_direction": _vector(axis.Direction())}
    if kind == "cylinder":
        surface = adaptor.Cylinder()
        axis = surface.Axis()
        return {
            "radius_mm": float(surface.Radius()),
            "axis_location_mm": _vector(axis.Location()),
            "axis_direction": _vector(axis.Direction()),
        }
    if kind == "cone":
        surface = adaptor.Cone()
        axis = surface.Axis()
        return {
            "semi_angle_rad": float(surface.SemiAngle()),
            "axis_location_mm": _vector(axis.Location()),
            "axis_direction": _vector(axis.Direction()),
        }
    if kind == "torus":
        surface = adaptor.Torus()
        axis = surface.Axis()
        return {
            "major_radius_mm": float(surface.MajorRadius()),
            "minor_radius_mm": float(surface.MinorRadius()),
            "center_mm": _vector(axis.Location()),
            "axis_direction": _vector(axis.Direction()),
        }
    return {}


def _classify_face(face: cq.Face, index: int, spec: Any, step_hash: str) -> dict[str, Any]:
    adaptor = BRepAdaptor_Surface(face.wrapped, True)
    kind = _surface_name(adaptor.GetType())
    data = _axis_surface_data(adaptor, kind)
    sample = _interior_sample(face, adaptor)
    row: dict[str, Any] = {
        "face_index_zero_based": index,
        "status": "UNKNOWN",
        "region_code": None,
        "region_name": "UNKNOWN",
        "surface_type": kind,
        "surface_parameters": data,
        "interior_sample": sample,
        "face_area_mm2": float(face.Area()),
        "classifier_version": CLASSIFIER_VERSION,
        "canonical_step_sha256": step_hash,
        "classification_basis": None,
        "reason": None,
    }
    if sample is None:
        row["reason"] = "no UV sample passed trimmed-face classification with a defined normal"
        return row

    point = np.asarray(sample["point_mm"], dtype=np.float64)
    normal = np.asarray(sample["oriented_outward_normal"], dtype=np.float64)

    if kind in {"cone", "cylinder"}:
        direction = np.asarray(data["axis_direction"], dtype=np.float64)
        location = np.asarray(data["axis_location_mm"], dtype=np.float64)
        centered_axis_offset = hypot(float(location[0]), float(location[1])) if abs(float(direction[2])) >= 0.999999 else float("inf")
        if abs(direction[2]) >= 0.999999 and centered_axis_offset <= 1e-5:
            radial_dot = float(normal[0] * point[0] + normal[1] * point[1])
            if radial_dot > 1e-4:
                return _classified(row, 1, "body-of-revolution support axis is global Z through the vessel axis; face-oriented normal has positive radial dot product", {"axis_offset_from_global_z_mm": centered_axis_offset, "oriented_radial_normal_dot_mm": radial_dot})
            if radial_dot < -1e-4:
                return _classified(row, 2, "body-of-revolution support axis is global Z through the vessel axis; face-oriented normal has negative radial dot product", {"axis_offset_from_global_z_mm": centered_axis_offset, "oriented_radial_normal_dot_mm": radial_dot})
            row["reason"] = "body-of-revolution face has an indeterminate radial normal sign"
            return row

    if kind == "plane":
        origin = data["origin_mm"]
        plane_z = float(origin[2])
        if abs(plane_z - float(spec.body_height_mm)) <= _GEOMETRY_TOLERANCE_MM and normal[2] > 0.999:
            return _classified(row, 3, "horizontal planar annulus at declared open-body lip; outward normal is +Z", {"plane_z_mm": plane_z, "normal_z": float(normal[2])})
        if abs(plane_z) <= _GEOMETRY_TOLERANCE_MM and normal[2] < -0.999:
            return _classified(row, 4, "horizontal planar underside at z=0; outward normal is -Z", {"plane_z_mm": plane_z, "normal_z": float(normal[2]), "subregion": "underside"})
        if abs(plane_z - float(spec.wall_mm)) <= _GEOMETRY_TOLERANCE_MM and normal[2] > 0.999:
            return _classified(row, 4, "horizontal cavity-floor plane at the declared floor thickness; outward normal is +Z", {"plane_z_mm": plane_z, "normal_z": float(normal[2]), "subregion": "cavity_floor"})
        root_x = float(spec.body_width_mm) * 0.5 * 0.83
        if (
            abs(abs(float(normal[0])) - 1.0) <= 1e-5
            and abs(float(normal[1])) <= 1e-5
            and abs(float(normal[2])) <= 1e-5
            and abs(float(origin[0]) - root_x) <= _GEOMETRY_TOLERANCE_MM
            and abs(float(origin[1])) <= _GEOMETRY_TOLERANCE_MM
            and abs(float(origin[2]) - float(spec.handle_low_z_mm)) <= _GEOMETRY_TOLERANCE_MM
        ):
            return _classified(row, 5, "planar sweep-start root section: support plane normal is parallel to the initial handle tangent and its origin matches the declared lower root", {"plane_origin_mm": origin, "expected_lower_root_mm": [root_x, 0.0, float(spec.handle_low_z_mm)]})
        row["reason"] = "plane does not match the open lip, declared base/floor, or sweep-start root plane"
        return row

    if kind == "cylinder":
        radius = float(data["radius_mm"])
        location = np.asarray(data["axis_location_mm"], dtype=np.float64)
        direction = np.asarray(data["axis_direction"], dtype=np.float64)
        radius_matches = abs(radius - float(spec.handle_radius_mm)) <= _GEOMETRY_TOLERANCE_MM
        low_axis = abs(abs(float(direction[0])) - 1.0) <= 1e-5 and abs(location[1]) <= _GEOMETRY_TOLERANCE_MM and abs(location[2] - float(spec.handle_low_z_mm)) <= _GEOMETRY_TOLERANCE_MM
        high_axis = abs(abs(float(direction[0])) - 1.0) <= 1e-5 and abs(location[1]) <= _GEOMETRY_TOLERANCE_MM and abs(location[2] - float(spec.handle_high_z_mm)) <= _GEOMETRY_TOLERANCE_MM
        vertical_axis = abs(abs(float(direction[2])) - 1.0) <= 1e-5 and abs(location[1]) <= _GEOMETRY_TOLERANCE_MM and abs(location[0] - float(spec.handle_outreach_mm)) <= _GEOMETRY_TOLERANCE_MM
        if radius_matches and (low_axis or high_axis or vertical_axis):
            return _classified(row, 5, "cylindrical sweep segment: radius matches declared handle section and its axis matches a declared straight handle-path segment", {"radius_matches_handle_section": radius_matches, "straight_segment_axis": "lower_horizontal" if low_axis else "upper_horizontal" if high_axis else "outer_vertical"})

    if kind == "torus":
        center = np.asarray(data["center_mm"], dtype=np.float64)
        direction = np.asarray(data["axis_direction"], dtype=np.float64)
        expected_centers = {
            "lower_bend": np.asarray([float(spec.handle_outreach_mm) - 5.0, 0.0, float(spec.handle_low_z_mm) + 5.0]),
            "upper_bend": np.asarray([float(spec.handle_outreach_mm) - 5.0, 0.0, float(spec.handle_high_z_mm) - 5.0]),
        }
        matching_bend = next(
            (name for name, expected in expected_centers.items() if float(np.linalg.norm(center - expected)) <= _GEOMETRY_TOLERANCE_MM),
            None,
        )
        if (
            matching_bend is not None
            and abs(float(data["minor_radius_mm"]) - float(spec.handle_radius_mm)) <= _GEOMETRY_TOLERANCE_MM
            and abs(float(data["major_radius_mm"]) - 5.0) <= _GEOMETRY_TOLERANCE_MM
            and abs(abs(float(direction[1])) - 1.0) <= 1e-5
        ):
            return _classified(row, 5, "toroidal sweep bend: center, Y-axis, 5 mm path bend radius, and minor radius match the declared handle path and section", {"matching_path_bend": matching_bend, "expected_center_mm": expected_centers[matching_bend].tolist()})

    row["reason"] = f"surface type/axis/normal does not match a declared vessel or handle surface rule ({kind})"
    return row


def _classified(row: dict[str, Any], code: int, basis: str, evidence: dict[str, Any]) -> dict[str, Any]:
    row["status"] = "CLASSIFIED"
    row["region_code"] = code
    row["region_name"] = REGIONS[code]
    row["classification_basis"] = basis
    row["classification_evidence"] = evidence
    return row


def classify_canonical_faces(shape: cq.Shape, spec: Any, canonical_step_sha256: str) -> dict[str, Any]:
    """Classify every canonical STEP face or return explicit UNKNOWN rows."""
    rows = [_classify_face(face, i, spec, canonical_step_sha256) for i, face in enumerate(shape.Faces())]
    counts = Counter(row["region_name"] for row in rows if row["status"] == "CLASSIFIED")
    unknown_indices = [row["face_index_zero_based"] for row in rows if row["status"] != "CLASSIFIED"]
    try:
        ocp_distribution_version = package_version("cadquery-ocp")
    except PackageNotFoundError:
        ocp_distribution_version = None
    return {
        "schema": "vf.brep-face-semantics.v1",
        "status": "PASS" if not unknown_indices and rows else "PENDING",
        "classifier": CLASSIFIER_VERSION,
        "backend": {
            "cadquery_version": cq.__version__,
            "ocp_module_version": getattr(OCP, "__version__", None),
            "ocp_distribution_version": ocp_distribution_version,
        },
        "canonical_step_sha256": canonical_step_sha256,
        "canonical_step_face_count": len(rows),
        "region_codes": {str(code): name for code, name in sorted(REGIONS.items())},
        "fracture_reserve_code": FRACTURE_RESERVE_CODE,
        "counts": dict(sorted(counts.items())),
        "unknown_face_indices": unknown_indices,
        "unknown_blocks_coloring_and_generation": True,
        "faces": rows,
    }


def triangle_region_codes(classification: dict[str, Any], triangle_source_face_indices: np.ndarray) -> np.ndarray:
    """Project classified canonical face regions onto triangle lineage."""
    if classification.get("status") != "PASS":
        raise ValueError("canonical B-rep face classification is UNKNOWN/PENDING; coloring and asset generation are blocked")
    rows = classification.get("faces")
    if not isinstance(rows, list) or not rows:
        raise ValueError("canonical B-rep face classification report is empty")
    codes = np.asarray([row.get("region_code") for row in rows], dtype=object)
    if any(code not in REGIONS for code in codes.tolist()):
        raise ValueError("canonical B-rep face classification contains an unknown or reserved region code")
    source = np.asarray(triangle_source_face_indices)
    if source.ndim != 1 or source.dtype.kind not in "iu" or (len(source) and (int(source.min()) < 0 or int(source.max()) >= len(codes))):
        raise ValueError("triangle-to-B-rep face lineage is invalid")
    return np.asarray(codes[source.astype(np.int64, copy=False)], dtype=np.uint8)
