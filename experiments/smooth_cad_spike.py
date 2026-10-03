"""Bounded C2 meridian + native inward-shell experiment.

This module is deliberately outside the production ``vesselforge`` package.
It creates a candidate CAD body from the prototype's profile control points,
then checks the actual OCC B-spline, native shell, STEP round-trip and delivered
mesh. It does not replace ``vesselforge.geometry`` or ``asset``.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any

import cadquery as cq
import numpy as np
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepGProp import BRepGProp_Face
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_BSplineCurve, GeomAbs_SurfaceOfRevolution
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.TopAbs import TopAbs_IN, TopAbs_ON
from OCP.Bnd import Bnd_Box
from OCP.gp import gp_Dir, gp_Lin, gp_Pnt, gp_Pnt2d, gp_Vec

from vesselforge.geometry import (
    VesselSpec,
    build_components,
    export_step,
    mesh_shape,
    mesh_topology_metrics,
    sampled_mesh_to_cad_metrics,
    scaled_outer_profile,
    section_shape,
)
from vesselforge.schema import sha256_file


EXPERIMENT_ID = "vf.c2-meridian-native-inward-shell-spike/1.0.0"
MESH_TARGET_MM = 0.10
MESH_ANGULAR_RAD = 0.08
WALL_SAMPLE_GRID = (12, 16)


def _finite_vec(vector: gp_Vec) -> list[float]:
    values = [float(vector.X()), float(vector.Y()), float(vector.Z())]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("OCC returned a non-finite derivative")
    return values


def _point_tuple(point: gp_Pnt) -> tuple[float, float, float]:
    return float(point.X()), float(point.Y()), float(point.Z())


def _shape_bbox(shape: cq.Shape) -> dict[str, float]:
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, box, False, False)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return {
        "xmin_mm": float(xmin),
        "ymin_mm": float(ymin),
        "zmin_mm": float(zmin),
        "xmax_mm": float(xmax),
        "ymax_mm": float(ymax),
        "zmax_mm": float(zmax),
        "xlen_mm": float(xmax - xmin),
        "ylen_mm": float(ymax - ymin),
        "zlen_mm": float(zmax - zmin),
    }


def make_c2_meridian_wire(spec: VesselSpec) -> tuple[cq.Workplane, dict[str, Any]]:
    """Use the existing outer control points with one native interpolating spline."""
    spec.validate()
    outer = scaled_outer_profile(spec)
    # The bottom is a straight floor radius. The spline starts tangent to it,
    # interpolates every remaining sidewall point with no interior tangent
    # constraints, and ends vertically at the open lip.
    sketch = (
        cq.Workplane("XZ")
        .moveTo(*outer[0])
        .lineTo(*outer[1])
        .spline(outer[2:], tangents=[(1.0, 0.0), (0.0, 1.0)], scale=True, includeCurrent=True)
        .lineTo(0.0, spec.body_height_mm)
        .close()
    )
    wire = sketch.val()
    spline_edges = []
    for edge in wire.Edges():
        adaptor = BRepAdaptor_Curve(edge.wrapped)
        if adaptor.GetType() == GeomAbs_BSplineCurve:
            spline_edges.append((edge, adaptor.BSpline()))
    if len(spline_edges) != 1:
        raise ValueError(f"expected exactly one native meridian B-spline edge, found {len(spline_edges)}")
    edge, curve = spline_edges[0]
    if not curve.IsCN(2):
        raise ValueError(f"native meridian B-spline is not C2: {curve.Continuity()}")
    degree = int(curve.Degree())
    first_parameter = float(curve.FirstParameter())
    last_parameter = float(curve.LastParameter())
    knots = [float(curve.Knot(index)) for index in range(1, curve.NbKnots() + 1)]
    multiplicities = [int(curve.Multiplicity(index)) for index in range(1, curve.NbKnots() + 1)]
    internal = []
    for index in range(1, len(knots) - 1):
        knot = knots[index]
        span_left = knot - knots[index - 1]
        span_right = knots[index + 1] - knot
        delta = min(span_left, span_right) * 1e-5
        left_p, left_d1, left_d2 = gp_Pnt(), gp_Vec(), gp_Vec()
        right_p, right_d1, right_d2 = gp_Pnt(), gp_Vec(), gp_Vec()
        curve.D2(knot - delta, left_p, left_d1, left_d2)
        curve.D2(knot + delta, right_p, right_d1, right_d2)
        d1_left = np.asarray(_finite_vec(left_d1), dtype=np.float64)
        d1_right = np.asarray(_finite_vec(right_d1), dtype=np.float64)
        d2_left = np.asarray(_finite_vec(left_d2), dtype=np.float64)
        d2_right = np.asarray(_finite_vec(right_d2), dtype=np.float64)
        internal.append(
            {
                "knot": knot,
                "multiplicity": multiplicities[index],
                "d1_left": d1_left.tolist(),
                "d1_right": d1_right.tolist(),
                "d1_relative_jump": float(
                    np.linalg.norm(d1_right - d1_left)
                    / max(np.linalg.norm(d1_left), np.linalg.norm(d1_right), 1e-12)
                ),
                "d2_left": d2_left.tolist(),
                "d2_right": d2_right.tolist(),
                "d2_relative_jump": float(
                    np.linalg.norm(d2_right - d2_left)
                    / max(np.linalg.norm(d2_left), np.linalg.norm(d2_right), 1e-12)
                ),
            }
        )
    start_p, start_d1 = gp_Pnt(), gp_Vec()
    end_p, end_d1 = gp_Pnt(), gp_Vec()
    curve.D1(first_parameter, start_p, start_d1)
    curve.D1(last_parameter, end_p, end_d1)
    start_vec = np.asarray(_finite_vec(start_d1), dtype=np.float64)
    end_vec = np.asarray(_finite_vec(end_d1), dtype=np.float64)
    start_dot = float(np.dot(start_vec / np.linalg.norm(start_vec), np.asarray([1.0, 0.0, 0.0])))
    end_dot = float(np.dot(end_vec / np.linalg.norm(end_vec), np.asarray([0.0, 0.0, 1.0])))
    native_curve = {
        "edge_type": "BSPLINE",
        "degree": degree,
        "global_continuity": str(curve.Continuity()),
        "is_C2_at_all_internal_knots": bool(curve.IsCN(2)),
        "knot_parameters": knots,
        "knot_multiplicities": multiplicities,
        "internal_knot_derivative_checks": internal,
        "start_point_mm": list(_point_tuple(start_p)),
        "end_point_mm": list(_point_tuple(end_p)),
        "start_tangent_dot_flat_floor_direction": start_dot,
        "end_tangent_dot_vertical_lip_direction": end_dot,
        "endpoint_join_continuity": "C1 constrained at start and lip endpoints; C2 at unconstrained interior interpolation points",
        "construction": "CadQuery Workplane.spline interpolation; no interior tangent constraints",
    }
    return sketch, native_curve


def build_shelled_body(spec: VesselSpec) -> tuple[cq.Shape, cq.Shape, dict[str, Any]]:
    sketch, meridian = make_c2_meridian_wire(spec)
    outer = sketch.revolve(360.0, (0, 0, 0), (0, 1, 0), combine=False).val()
    if not outer.isValid() or len(outer.Solids()) != 1:
        raise ValueError("C2 meridian revolve did not produce one valid outer solid")
    top_faces = cq.Workplane("XY").newObject([outer]).faces(">Z").vals()
    if len(top_faces) != 1:
        raise ValueError(f"expected one removable top cap, found {len(top_faces)}")
    hollow = cq.Workplane("XY").newObject([outer]).faces(">Z").shell(-spec.wall_mm, kind="arc").val()
    if not hollow.isValid() or len(hollow.Solids()) != 1 or len(hollow.Shells()) != 1:
        raise ValueError("native inward shell did not produce one valid solid/shell")
    return outer, hollow, {"meridian": meridian, "removed_top_face_count": len(top_faces)}


def _native_curve_inventory(shape: cq.Shape) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, edge in enumerate(shape.Edges()):
        adaptor = BRepAdaptor_Curve(edge.wrapped)
        if adaptor.GetType() != GeomAbs_BSplineCurve:
            continue
        curve = adaptor.BSpline()
        bounds = _shape_bbox(edge)
        result.append(
            {
                "edge_index_zero_based": index,
                "degree": int(curve.Degree()),
                "global_continuity": str(curve.Continuity()),
                "is_C2_at_all_internal_knots": bool(curve.IsCN(2)),
                "internal_knot_count": max(0, int(curve.NbKnots()) - 2),
                "multiplicities": [int(curve.Multiplicity(i)) for i in range(1, curve.NbKnots() + 1)],
                "bbox_mm": bounds,
            }
        )
    return result


def _solid_state(shape: cq.Shape, point: gp_Pnt, tolerance: float = 1e-7) -> str:
    classifier = BRepClass3d_SolidClassifier()
    classifier.Load(shape.wrapped)
    classifier.Perform(point, tolerance)
    return str(classifier.State())


def sample_sidewall_normal_rays(shape: cq.Shape) -> dict[str, Any]:
    """Sample actual outer revolved faces and ray to the next trimmed solid face."""
    u_steps, v_steps = WALL_SAMPLE_GRID
    ray_intersector = IntCurvesFace_ShapeIntersector()
    ray_intersector.Load(shape.wrapped, 1e-7)
    records: list[dict[str, Any]] = []
    face_records: list[dict[str, Any]] = []
    candidate_count = 0
    unknown: list[dict[str, Any]] = []
    for face_index, face in enumerate(shape.Faces()):
        surface = BRepAdaptor_Surface(face.wrapped, True)
        if surface.GetType() != GeomAbs_SurfaceOfRevolution:
            continue
        u_min, u_max, v_min, v_max = BRepTools.UVBounds_s(face.wrapped)
        normal_eval = BRepGProp_Face(face.wrapped)
        face_candidate = 0
        face_measured = 0
        for iu in range(u_steps):
            u = u_min + (u_max - u_min) * (iu + 0.5) / u_steps
            for iv in range(v_steps):
                v = v_min + (v_max - v_min) * (iv + 0.5) / v_steps
                trimmed = BRepClass_FaceClassifier(face.wrapped, gp_Pnt2d(u, v), 1e-7)
                if trimmed.State() not in (TopAbs_IN, TopAbs_ON):
                    continue
                point = surface.Value(u, v)
                normal = gp_Vec()
                normal_eval.Normal(u, v, point, normal)
                magnitude = normal.Magnitude()
                if not math.isfinite(magnitude) or magnitude < 1e-10:
                    unknown.append({"face_index": face_index, "u": u, "v": v, "reason": "degenerate_normal"})
                    continue
                normal.Normalize()
                xyz = np.asarray(_point_tuple(point), dtype=np.float64)
                nxyz = np.asarray(_finite_vec(normal), dtype=np.float64)
                radius = float(math.hypot(xyz[0], xyz[1]))
                if radius < 1e-6:
                    continue
                radial = np.asarray([xyz[0] / radius, xyz[1] / radius, 0.0])
                radial_dot = float(np.dot(nxyz, radial))
                # Only outward-facing sidewall samples are included; inner walls
                # have the opposite radial normal and are not counted as unknown.
                if radial_dot <= 0.25:
                    continue
                face_candidate += 1
                candidate_count += 1
                probe = 0.025
                plus_state = _solid_state(shape, gp_Pnt(*(xyz + probe * nxyz).tolist()))
                minus_state = _solid_state(shape, gp_Pnt(*(xyz - probe * nxyz).tolist()))
                if plus_state != "TopAbs_State.TopAbs_OUT" or minus_state != "TopAbs_State.TopAbs_IN":
                    unknown.append(
                        {
                            "face_index": face_index,
                            "u": u,
                            "v": v,
                            "point_mm": xyz.tolist(),
                            "normal": nxyz.tolist(),
                            "reason": "outward_normal_not_confirmed_by_solid_classification",
                            "plus_state": plus_state,
                            "minus_state": minus_state,
                        }
                    )
                    continue
                epsilon = 1e-4
                start = xyz - epsilon * nxyz
                if _solid_state(shape, gp_Pnt(*start.tolist())) != "TopAbs_State.TopAbs_IN":
                    unknown.append({"face_index": face_index, "u": u, "v": v, "reason": "ray_start_not_inside"})
                    continue
                line = gp_Lin(gp_Pnt(*start.tolist()), gp_Dir(*(-nxyz).tolist()))
                ray_intersector.Perform(line, 0.0, 3.0 * 4.0 + 2.0)
                if not ray_intersector.IsDone():
                    unknown.append({"face_index": face_index, "u": u, "v": v, "reason": "ray_intersector_not_done"})
                    continue
                distances = [
                    float(ray_intersector.WParameter(hit)) + epsilon
                    for hit in range(1, ray_intersector.NbPnt() + 1)
                    if float(ray_intersector.WParameter(hit)) > 1e-5
                ]
                if not distances:
                    unknown.append({"face_index": face_index, "u": u, "v": v, "reason": "no_inner_boundary_hit"})
                    continue
                distance = min(distances)
                face_measured += 1
                records.append(
                    {
                        "face_index_zero_based": face_index,
                        "u": float(u),
                        "v": float(v),
                        "point_xyz_mm": xyz.tolist(),
                        "outward_normal": nxyz.tolist(),
                        "radial_normal_dot": radial_dot,
                        "ray_inner_hit_distance_mm": distance,
                        "hit_count": len(distances),
                    }
                )
        face_records.append(
            {
                "face_index_zero_based": face_index,
                "uv_bounds": [float(u_min), float(u_max), float(v_min), float(v_max)],
                "candidate_outer_side_samples": face_candidate,
                "measured_samples": face_measured,
            }
        )
    distances = [record["ray_inner_hit_distance_mm"] for record in records]
    return {
        "method": "canonical STEP face UV samples; BRepClass_FaceClassifier trim inclusion; BRepGProp_Face normals; BRepClass3d solid inside/outside orientation; IntCurvesFace_ShapeIntersector first inward boundary hit",
        "sampling_grid_per_revolution_face": {"azimuth": u_steps, "meridian": v_steps},
        "candidate_outer_side_samples": candidate_count,
        "measured_sample_count": len(records),
        "coverage_fraction": float(len(records) / candidate_count) if candidate_count else 0.0,
        "unknown_count": len(unknown),
        "unknown_first_50": unknown[:50],
        "face_coverage": face_records,
        "sampled_wall_min_mm": float(min(distances)) if distances else None,
        "sampled_wall_max_mm": float(max(distances)) if distances else None,
        "sampled_wall_mean_mm": float(np.mean(distances)) if distances else None,
        "samples": records,
        "scope": "finite sampled sidewall-normal distances only; not a global minimum-wall proof",
    }


def measure_floor_thickness(shape: cq.Shape) -> dict[str, Any]:
    planar = [face for face in shape.Faces() if face.geomType() == "PLANE"]
    bottom = [face for face in planar if abs(face.Center().z) < 1e-4]
    floor = [face for face in planar if face.Center().z > 0.25 and face.Center().z < 10.0]
    if not bottom or not floor:
        return {"status": "UNKNOWN", "reason": "could_not_identify_bottom_and_cavity_floor_planar_faces"}
    candidates = []
    for outer in bottom:
        for inner in floor:
            distance = float(outer.distance(inner))
            if math.isfinite(distance) and distance > 0:
                candidates.append((distance, outer.Area(), inner.Area(), outer.Center().z, inner.Center().z))
    if not candidates:
        return {"status": "UNKNOWN", "reason": "no_finite_positive_face_distance"}
    distance, outer_area, inner_area, outer_z, inner_z = min(candidates)
    return {
        "status": "MEASURED_FROM_CANONICAL_STEP_PLANAR_FACES",
        "distance_mm": distance,
        "outer_face_area_mm2": float(outer_area),
        "inner_face_area_mm2": float(inner_area),
        "outer_face_center_z_mm": float(outer_z),
        "inner_face_center_z_mm": float(inner_z),
        "method": "OCC trimmed-face distance between canonical STEP planar underside and cavity-floor faces",
        "scope": "actual CAD floor face separation; not global solid minimum wall",
    }


def diagnose_handle_fusion(body: cq.Shape, handle: cq.Shape) -> dict[str, Any]:
    """Bounded boolean check; do not deliver an unverified fused candidate."""
    common = body.intersect(handle)
    overlap = float(common.Volume()) if not common.isNull() else 0.0
    direct: dict[str, Any]
    try:
        result = body.fuse(handle).clean()
        direct = {
            "status": "COMPUTED",
            "is_valid": bool(result.isValid()),
            "is_null": bool(result.isNull()),
            "solid_count": len(result.Solids()),
            "shell_count": len(result.Shells()),
            "volume_mm3": float(result.Volume()),
        }
    except Exception as exc:
        direct = {"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)}
    reverse: dict[str, Any]
    try:
        result = handle.fuse(body).clean()
        sum_volume = float(body.Volume() + handle.Volume())
        reverse_volume = float(result.Volume())
        reverse = {
            "status": "COMPUTED",
            "is_valid": bool(result.isValid()),
            "is_null": bool(result.isNull()),
            "solid_count": len(result.Solids()),
            "shell_count": len(result.Shells()),
            "volume_mm3": reverse_volume,
            "input_volume_sum_mm3": sum_volume,
            "excess_over_input_volume_sum_mm3": reverse_volume - sum_volume,
            "conservation_check": bool(reverse_volume <= sum_volume + 0.01),
        }
    except Exception as exc:
        reverse = {"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)}
    if direct.get("status") != "COMPUTED":
        reason = "body-then-handle fuse raised an exception; see the recorded error"
    elif direct.get("is_null"):
        reason = "body-then-handle fuse returned a null TopoDS_Shape"
    elif not direct.get("is_valid") or direct.get("solid_count") != 1 or direct.get("shell_count") != 1:
        reason = "body-then-handle fuse did not produce one valid solid and shell"
    else:
        reason = "the bounded diagnostic result is reported for review; no fused candidate is delivered"
    return {
        "status": "NOT_DELIVERED",
        "body_volume_mm3": float(body.Volume()),
        "handle_volume_mm3": float(handle.Volume()),
        "intersection_volume_mm3": overlap,
        "body_then_handle": direct,
        "handle_then_body": reverse,
        "reason": reason,
        "root_geometry_status": "PENDING; no root fillet or stress claim",
    }


def _write_npz(path: Path, arrays: dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrays)


def run_spike(output_dir: str | Path, wall_mm: float = 4.0, seed: int = 20261003) -> dict[str, Any]:
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty spike output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    spec = replace(
        VesselSpec(),
        body_width_mm=41.0,
        body_height_mm=56.0,
        wall_mm=float(wall_mm),
        tessellation_linear_mm=MESH_TARGET_MM,
        tessellation_angular_rad=MESH_ANGULAR_RAD,
    )
    spec.validate()
    outer_constructed, body_constructed, construction = build_shelled_body(spec)

    # Reuse the already-tested swept handle path without changing its geometry
    # code. Its attachment transition is explicitly out of scope for this spike.
    _, handle_only, _ = build_components(spec)
    handle_fusion = diagnose_handle_fusion(body_constructed, handle_only)

    geometry_dir = output / "geometry"
    body_step = geometry_dir / "smooth_body.step"
    export_step(body_constructed, str(body_step))
    canonical_body = cq.importers.importStep(str(body_step)).val()
    if not canonical_body.isValid() or len(canonical_body.Solids()) != 1 or len(canonical_body.Shells()) != 1:
        raise ValueError("canonical STEP re-import of smooth body is not one valid solid/shell")

    vertices, faces, triangle_sources = mesh_shape(canonical_body, spec)
    topology = mesh_topology_metrics(vertices, faces)
    mesh_cad = sampled_mesh_to_cad_metrics(canonical_body, vertices, faces, triangle_sources)
    section = section_shape(canonical_body)
    section_vertices, section_faces, section_sources = mesh_shape(section, spec)
    _write_npz(
        geometry_dir / "surface.npz",
        {"vertices_mm": vertices.astype(np.float64), "faces": faces.astype(np.int32)},
    )
    _write_npz(
        geometry_dir / "mesh_lineage.npz",
        {"face_source_brep_index": triangle_sources.astype(np.int32)},
    )
    _write_npz(
        geometry_dir / "axial_section.npz",
        {
            "vertices_mm": section_vertices.astype(np.float64),
            "faces": section_faces.astype(np.int32),
            "face_source_brep_index": section_sources.astype(np.int32),
        },
    )

    wall_samples = sample_sidewall_normal_rays(canonical_body)
    floor = measure_floor_thickness(canonical_body)
    bbox_body = _shape_bbox(canonical_body)
    bbox_handle = _shape_bbox(handle_only)
    native_curves = _native_curve_inventory(canonical_body)
    source_meridian = construction["meridian"]
    # Select a STEP-imported B-spline edge that spans nearly the full vessel
    # height; this is evidence about the delivered representation, not a
    # topology-ID match against the construction sketch.
    side_meridian_candidates = [
        edge
        for edge in native_curves
        if edge["bbox_mm"]["zlen_mm"] >= spec.body_height_mm - 1.0
    ]
    side_meridian = max(side_meridian_candidates, key=lambda item: item["bbox_mm"]["zlen_mm"]) if side_meridian_candidates else None
    report: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID,
        "status": "PASS_CANDIDATE_ONLY",
        "production_generator_changed": False,
        "asset_scope": "smooth open-vessel body only; existing handle fusion failed the bounded boolean acceptance and is not included",
        "construction": {
            "body": "CadQuery C2 interpolation spline meridian → OCC revolve → remove top cap → native inward shell(-wall_mm, kind='arc')",
            "handle": "existing swept CAD handle was tested as a separate B-rep; fusion result was rejected by boolean/volume evidence",
            "cadquery_version": cq.__version__,
            "ocp_version": getattr(__import__("OCP"), "__version__", "unknown"),
            "spec": spec.__dict__,
            "seed": int(seed),
            "source_profile_control_points_mm": scaled_outer_profile(spec),
            "source_meridian_native_curve": source_meridian,
            "canonical_STEP_body_BSpline_edges": native_curves,
            "full_height_STEP_BSpline_edge_candidate": side_meridian,
        },
        "artifacts": {
            "body_step": body_step.relative_to(output).as_posix(),
            "whole_step": None,
            "mesh_npz": "geometry/surface.npz",
            "lineage_npz": "geometry/mesh_lineage.npz",
            "axial_section_npz": "geometry/axial_section.npz",
            "files_sha256": {
                path.relative_to(output).as_posix(): sha256_file(path)
                for path in sorted(geometry_dir.iterdir())
                if path.is_file()
            },
        },
        "canonical_STEP": {
            "body_valid": bool(canonical_body.isValid()),
            "body_solids": len(canonical_body.Solids()),
            "body_shells": len(canonical_body.Shells()),
            "body_volume_mm3": float(canonical_body.Volume()),
            "body_bbox_mm": bbox_body,
            "handle_bbox_mm": bbox_handle,
            "bbox_note": "handle B-rep bounds are listed only as an independent fusion diagnostic; no fused mesh or STEP is delivered",
            "actual_body_height_mm": bbox_body["zlen_mm"],
            "actual_body_width_mm": max(bbox_body["xlen_mm"], bbox_body["ylen_mm"]),
            "nominal_body_height_mm": spec.body_height_mm,
            "nominal_body_width_mm": spec.body_width_mm,
            "height_delta_mm": float(bbox_body["zlen_mm"] - spec.body_height_mm),
            "width_delta_mm": float(max(bbox_body["xlen_mm"], bbox_body["ylen_mm"]) - spec.body_width_mm),
            "radial_overshoot_mm": float(max(bbox_body["xlen_mm"], bbox_body["ylen_mm"]) / 2 - spec.body_width_mm / 2),
            "outer_revolve_roundtrip_volume_relative_delta": float(
                abs(outer_constructed.Volume() - cq.importers.importStep(str(body_step)).val().Volume())
                / max(abs(outer_constructed.Volume()), 1e-12)
            ),
        },
        "meridian_continuity": {
            "source_native": source_meridian,
            "canonical_step_native_bspline_edge_count": len(native_curves),
            "height_spanning_step_edge_candidate": side_meridian,
            "c2_internal_knots_in_delivered_step_candidate": bool(
                side_meridian is not None and side_meridian["is_C2_at_all_internal_knots"]
            ),
        },
        "wall": {
            "declared_wall_mm": float(spec.wall_mm),
            "sidewall_normal_ray_sampling": wall_samples,
            "floor_thickness": floor,
            "warning": "Native shell validity and finite ray samples do not prove global wall thickness; local curvature/self-intersection and handle-root transitions require separate evidence.",
        },
        "handle_fusion_diagnostic": handle_fusion,
        "mesh": {
            "tessellation_chord_target_mm": MESH_TARGET_MM,
            "tessellation_angular_tolerance_rad": MESH_ANGULAR_RAD,
            "absolute_deflection": True,
            "vertex_count": int(len(vertices)),
            "triangle_count": int(len(faces)),
            "topology": topology,
            "mesh_to_trimmed_canonical_STEP": mesh_cad,
            "sampling_acceptance_max_mm": 0.10,
            "scope": "finite edge-midpoint and triangle-centroid sampling, not a global Hausdorff proof",
        },
        "limitations": [
            "This is an isolated candidate algorithm spike and does not replace the production generator or alter the forge.asset.v1 schema.",
            "No handle-root fillet was attempted; root shape/curvature remains PENDING.",
            "Native shell success is not proof of a global 4 mm minimum wall or absence of all offset self-intersections.",
            "No historical type/style authenticity, material calibration, impact or fracture validation is claimed.",
        ],
    }
    report["checks"] = {
        "canonical_body_one_valid_solid_shell": bool(
            canonical_body.isValid() and len(canonical_body.Solids()) == 1 and len(canonical_body.Shells()) == 1
        ),
        "delivered_mesh_watertight_and_positive": bool(topology["watertight"] and topology["signed_volume_mm3"] > 0),
        "native_source_meridian_c2": bool(source_meridian["is_C2_at_all_internal_knots"]),
        "delivered_step_meridian_c2": bool(
            side_meridian is not None and side_meridian["is_C2_at_all_internal_knots"]
        ),
        "actual_height_within_0_10mm": abs(bbox_body["zlen_mm"] - spec.body_height_mm) <= 0.10,
        "actual_width_within_0_10mm": abs(max(bbox_body["xlen_mm"], bbox_body["ylen_mm"]) - spec.body_width_mm) <= 0.10,
        "finite_sampled_mesh_to_step_deviation_under_0_10mm": bool(
            mesh_cad["unknown_sample_count"] == 0
            and mesh_cad["max_sampled_deviation_mm"] is not None
            and float(mesh_cad["max_sampled_deviation_mm"]) <= 0.10
        ),
        "wall_ray_sampling_has_no_unknowns": bool(wall_samples["candidate_outer_side_samples"] > 0 and wall_samples["unknown_count"] == 0),
        "wall_ray_samples_within_0_10mm_of_requested": bool(
            wall_samples["sampled_wall_min_mm"] is not None
            and wall_samples["sampled_wall_max_mm"] is not None
            and abs(float(wall_samples["sampled_wall_min_mm"]) - spec.wall_mm) <= 0.10
            and abs(float(wall_samples["sampled_wall_max_mm"]) - spec.wall_mm) <= 0.10
        ),
        "floor_face_distance_within_0_05mm_of_requested": bool(
            floor.get("status") == "MEASURED_FROM_CANONICAL_STEP_PLANAR_FACES"
            and abs(float(floor["distance_mm"]) - spec.wall_mm) <= 0.05
        ),
    }
    report["status"] = "PASS_CANDIDATE_ONLY" if all(report["checks"].values()) else "FAIL_OR_UNKNOWN_CANDIDATE"
    (output / "smooth_cad_spike_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wall-mm", type=float, default=4.0)
    parser.add_argument("--seed", type=int, default=20261003)
    args = parser.parse_args()
    report = run_spike(args.output, wall_mm=args.wall_mm, seed=args.seed)
    print(json.dumps({"status": report["status"], "checks": report["checks"], "report": str(args.output / "smooth_cad_spike_report.json")}, indent=2))
    return 0 if all(report["checks"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
