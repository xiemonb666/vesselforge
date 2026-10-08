"""Source-only native B-rep / STEP pilot for the pinned C4 jar meridian.

No OCP imports occur until the explicit --root-go execution gate is passed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
import traceback
from fractions import Fraction
from pathlib import Path
from typing import Any
from native_input_gate import input_preflight

ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT = ROOT / "vesselforge/experiments/c4_jar_native_ingress_20261007"
REVIEW = ROOT / "vesselforge/tmp/review_20261007/c4_jar_native_ingress_20261007/native_source_v1"
CASE_PATH = EXPERIMENT / "native_c4_ingress_case.json"
PINS_PATH = REVIEW / "source_pins.json"
MAX_STEP_BYTES = 19 * 1024 * 1024
FACE_BBOX_TOL_MM = 1e-7
FACE_AREA_REL_TOL = 1e-8
ROLES = ("outer_base", "outer_side", "outer_neck", "inner_base", "inner_side", "inner_neck", "lip")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path: Path, data: Any) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    raw = (json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    with temp.open("wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def gate(report: dict[str, Any], name: str, passed: bool, detail: Any) -> None:
    report.setdefault("gates", {})[name] = {"pass": bool(passed), "detail": detail}
    if not passed:
        raise RuntimeError(f"gate failed: {name}: {detail}")


def xyz(point: Any) -> tuple[float, float, float]:
    return float(point.X()), float(point.Y()), float(point.Z())


def distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def enum_label(value: Any, names: dict[Any, str]) -> str:
    return names.get(value, str(value))


def worker(report: dict[str, Any], case: dict[str, Any], pins: dict[str, Any], output: Path) -> None:
    report["phase"] = "static_input_preflight"
    report["input_preflight"] = input_preflight(case, pins, report, root=ROOT, experiment=EXPERIMENT, case_path=CASE_PATH, sha256_file=sha256_file, read_json=read_json, gate=gate)
    report["scope"] = case["candidate_scope"]
    report["claim_limits"] = case["claim_limits"]
    output.mkdir(parents=True, exist_ok=True)
    result_path, step_path = output / "native_result.json", output / "native_candidate.step"
    if result_path.exists() or step_path.exists():
        raise RuntimeError("output collision; this one-shot route refuses overwrite or retry")

    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.Bnd import Bnd_Box
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
    from OCP.Geom import Geom_BSplineCurve, Geom_OffsetCurve
    from OCP.GeomAbs import GeomAbs_BSplineCurve, GeomAbs_BSplineSurface, GeomAbs_Cylinder, GeomAbs_Line, GeomAbs_OffsetCurve, GeomAbs_Plane, GeomAbs_SurfaceOfRevolution
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pln, gp_Pnt, gp_Vec
    from OCP.GProp import GProp_GProps
    from OCP.Interface import Interface_Static
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
    from OCP.TColgp import TColgp_Array1OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    curve_type_names = {GeomAbs_Line: "LINE", GeomAbs_BSplineCurve: "BSPLINE", GeomAbs_OffsetCurve: "OFFSET"}
    surface_type_names = {GeomAbs_Plane: "PLANE", GeomAbs_Cylinder: "CYLINDER", GeomAbs_SurfaceOfRevolution: "SURFACE_OF_REVOLUTION", GeomAbs_BSplineSurface: "BSPLINE_SURFACE"}
    exact_controls = report["input_preflight"]["exact_controls_rz_mm"]
    poles = [[Fraction(x), Fraction(z)] for x, z in exact_controls]
    pole_array = TColgp_Array1OfPnt(1, 17)
    weight_array = TColStd_Array1OfReal(1, 17)
    for index, (r_exact, z_exact) in enumerate(poles, 1):
        pole_array.SetValue(index, gp_Pnt(float(r_exact), 0.0, float(z_exact)))
        weight_array.SetValue(index, 1.0)
    knot_values = [Fraction(j, 12) for j in range(13)]
    multiplicities = [6] + [1] * 11 + [6]
    knot_array = TColStd_Array1OfReal(1, len(knot_values))
    mult_array = TColStd_Array1OfInteger(1, len(multiplicities))
    for index, value in enumerate(knot_values, 1):
        knot_array.SetValue(index, float(value))
    for index, value in enumerate(multiplicities, 1):
        mult_array.SetValue(index, value)
    outer = Geom_BSplineCurve(pole_array, weight_array, knot_array, mult_array, 5, False, True)
    gate(report, "constructed_outer_definition", outer.NbPoles() == 17 and outer.Degree() == 5 and outer.NbKnots() == 13, {"curve_type": type(outer).__name__, "poles": outer.NbPoles(), "degree": outer.Degree(), "unique_knots": outer.NbKnots(), "weights_all_one": all(abs(float(outer.Weight(i)) - 1.0) == 0.0 for i in range(1, 18))})
    pole_error = 0.0
    for index, (r_exact, z_exact) in enumerate(poles, 1):
        actual = outer.Pole(index)
        pole_error = max(pole_error, abs(actual.X() - float(r_exact)), abs(actual.Z() - float(z_exact)), abs(actual.Y()))
    gate(report, "constructed_outer_pole_roundtrip", pole_error <= 1e-12, {"max_pole_coordinate_delta_mm": pole_error})
    inner = Geom_OffsetCurve(outer, 3.0, gp_Dir(0.0, 1.0, 0.0), False)
    report["geometry_definition"] = {"outer_curve_type": type(outer).__name__, "inner_curve_type": type(inner).__name__, "degree": 5, "pole_count": 17, "exact_poles_rz_mm": exact_controls, "weights": ["1"] * 17, "exact_knots": [str(x) for x in knot_values], "multiplicities": multiplicities, "offset_mm": 3.0, "offset_api_sign": "+3 with V=+Y; OCCT T cross V", "conversion_boundary": "Fraction to float only at OCP point/knot/weight construction"}

    sample_rows = []
    max_residual = 0.0
    max_angle = 0.0
    endpoint_gaps: dict[str, float] = {}
    for span in range(12):
        for local_index in range(13):
            u_exact = Fraction(span, 12) + Fraction(local_index, 144)
            u = float(u_exact)
            outer_point, outer_tangent = gp_Pnt(), gp_Vec()
            inner_point, inner_tangent = gp_Pnt(), gp_Vec()
            outer.D1(u, outer_point, outer_tangent)
            inner.D1(u, inner_point, inner_tangent)
            ox, oy, oz = xyz(outer_point)
            tx, ty, tz = xyz(outer_tangent)
            ix, iy, iz = xyz(inner_point)
            itx, ity, itz = xyz(inner_tangent)
            speed = math.sqrt(tx * tx + ty * ty + tz * tz)
            inner_speed = math.sqrt(itx * itx + ity * ity + itz * itz)
            if speed <= 0 or inner_speed <= 0:
                raise RuntimeError(f"zero tangent at global u={u_exact}")
            target = (ox - 3.0 * tz / speed, oy, oz + 3.0 * tx / speed)
            actual = (ix, iy, iz)
            residual = distance(target, actual)
            cosine = max(-1.0, min(1.0, (tx * itx + ty * ity + tz * itz) / (speed * inner_speed)))
            angle = math.degrees(math.acos(cosine))
            max_residual, max_angle = max(max_residual, residual), max(max_angle, angle)
            sample_rows.append({"span": span, "u_exact": str(u_exact), "outer_xyz_mm": [ox, oy, oz], "analytic_target_xyz_mm": list(target), "native_offset_xyz_mm": list(actual), "target_residual_mm": residual, "tangent_angle_degrees": angle})
            if span == 0 and local_index == 0:
                endpoint_gaps["outer_axis_base"] = distance((ox, oy, oz), (0.0, 0.0, 0.0))
                endpoint_gaps["inner_axis_base"] = distance((ix, iy, iz), (0.0, 0.0, 3.0))
            if span == 11 and local_index == 12:
                endpoint_gaps["outer_mouth"] = distance((ox, oy, oz), (26.0, 0.0, 120.0))
                endpoint_gaps["inner_mouth"] = distance((ix, iy, iz), (23.0, 0.0, 120.0))
    gate(report, "finite_offset_target_residual", max_residual <= 1e-6, {"stations": len(sample_rows), "max_mm": max_residual, "scope": "finite same-parameter diagnostics only"})
    gate(report, "finite_normal_angle", max_angle <= 0.001, {"stations": len(sample_rows), "max_degrees": max_angle, "scope": "finite same-parameter diagnostics only"})
    gate(report, "finite_endpoint_closure", bool(endpoint_gaps) and max(endpoint_gaps.values()) <= 1e-6, {"endpoint_deltas_mm": endpoint_gaps})
    report["finite_diagnostics"] = {"stations": sample_rows, "stations_per_span": 13, "max_target_residual_mm": max_residual, "max_tangent_angle_degrees": max_angle, "endpoint_deltas_mm": endpoint_gaps, "global_native_wall": "UNKNOWN"}

    def make_curve_edge(curve: Any, first: Fraction, last: Fraction) -> Any:
        maker = BRepBuilderAPI_MakeEdge(curve, float(first), float(last))
        if not maker.IsDone():
            raise RuntimeError(f"MakeEdge failed for trim {first}..{last}")
        return maker.Edge()

    outer_edges = {
        "outer_base": make_curve_edge(outer, Fraction(0), Fraction(1, 12)),
        "outer_side": make_curve_edge(outer, Fraction(1, 12), Fraction(11, 12)),
        "outer_neck": make_curve_edge(outer, Fraction(11, 12), Fraction(1)),
    }
    inner_forward = {
        "inner_base": make_curve_edge(inner, Fraction(0), Fraction(1, 12)),
        "inner_side": make_curve_edge(inner, Fraction(1, 12), Fraction(11, 12)),
        "inner_neck": make_curve_edge(inner, Fraction(11, 12), Fraction(1)),
    }
    inner_edges = {role: TopoDS.Edge(edge.Reversed()) for role, edge in inner_forward.items()}
    lip_maker = BRepBuilderAPI_MakeEdge(gp_Pnt(26.0, 0.0, 120.0), gp_Pnt(23.0, 0.0, 120.0))
    axis_maker = BRepBuilderAPI_MakeEdge(gp_Pnt(0.0, 0.0, 3.0), gp_Pnt(0.0, 0.0, 0.0))
    if not lip_maker.IsDone() or not axis_maker.IsDone():
        raise RuntimeError("straight lip or axis closure edge construction failed")
    lip_edge, axis_edge = lip_maker.Edge(), axis_maker.Edge()
    ordered = [outer_edges["outer_base"], outer_edges["outer_side"], outer_edges["outer_neck"], lip_edge, inner_edges["inner_neck"], inner_edges["inner_side"], inner_edges["inner_base"], axis_edge]
    wire_maker = BRepBuilderAPI_MakeWire()
    for edge in ordered:
        wire_maker.Add(edge)
    if not wire_maker.IsDone():
        raise RuntimeError(f"closed meridian wire builder failed, error={wire_maker.Error()}")
    wire = wire_maker.Wire()
    face_maker = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, -1.0, 0.0)), wire, True)
    if not face_maker.IsDone():
        raise RuntimeError(f"planar meridian face construction failed, error={face_maker.Error()}")
    section_face = face_maker.Face()
    section_props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(section_face, section_props, False, False)
    section_area = float(section_props.Mass())
    section_valid = bool(wire.Closed() and BRepCheck_Analyzer(section_face, True).IsValid() and math.isfinite(section_area) and section_area > 0.0)
    gate(report, "closed_section_face", section_valid, {"wire_closed": bool(wire.Closed()), "face_valid": bool(BRepCheck_Analyzer(section_face, True).IsValid()), "section_area_mm2": section_area})
    axis = gp_Ax1(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 0.0, 1.0))
    revol = BRepPrimAPI_MakeRevol(section_face, axis, 2.0 * math.pi, False)
    if not revol.IsDone():
        raise RuntimeError("full-turn BRepPrimAPI_MakeRevol failed")
    body = revol.Shape()

    def explore(shape: Any, kind: Any, cast: Any = None) -> list[Any]:
        found, explorer = [], TopExp_Explorer(shape, kind)
        while explorer.More():
            item = explorer.Current()
            found.append(cast(item) if cast else item)
            explorer.Next()
        return found

    def shape_bbox(shape: Any) -> list[float]:
        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(shape, box, False, False)
        values = [float(x) for x in box.Get()]
        if not all(math.isfinite(x) for x in values):
            raise RuntimeError("non-finite geometry-only bounding box")
        return values

    def area(shape: Any) -> float:
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(shape, props, False, False)
        return float(props.Mass())

    def volume(shape: Any) -> float:
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, props)
        return float(props.Mass())

    def face_record(face: Any) -> dict[str, Any]:
        adapter = BRepAdaptor_Surface(face, True)
        typ = adapter.GetType()
        bounds = shape_bbox(face)
        record = {"surface_type": enum_label(typ, surface_type_names), "bbox_xyz_minmax_mm": bounds, "area_mm2": area(face)}
        return record

    def bbox_deltas(actual: list[float], expected: list[float]) -> list[float]: return [abs(a - b) for a, b in zip(actual, expected)]

    def revolved_edge_bbox(source_edge: Any) -> tuple[list[float], list[float]]:
        edge_bounds = shape_bbox(source_edge)
        meridian_y_error = max(abs(edge_bounds[1]), abs(edge_bounds[4]))
        if meridian_y_error > FACE_BBOX_TOL_MM:
            raise RuntimeError(f"source edge is outside the global XZ meridian plane: {meridian_y_error} mm")
        radial_max = max(abs(edge_bounds[0]), abs(edge_bounds[3]))
        return edge_bounds, [-radial_max, -radial_max, edge_bounds[2], radial_max, radial_max, edge_bounds[5]]

    def source_role_geometry_check(role: str, edge_bounds: list[float]) -> dict[str, Any]:
        curve = inner if role.startswith("inner_") else outer
        if role == "lip":
            ok = max(abs(edge_bounds[2] - 120.0), abs(edge_bounds[5] - 120.0), abs(edge_bounds[0] - 23.0), abs(edge_bounds[3] - 26.0)) <= FACE_BBOX_TOL_MM
            return {"pass": ok, "feature_signature": "flat_z_lip", "expected_z_bounds_mm": [120.0, 120.0], "expected_x_bounds_mm": [23.0, 26.0],
                    "observed_z_bounds_mm": [edge_bounds[2], edge_bounds[5]], "observed_x_bounds_mm": [edge_bounds[0], edge_bounds[3]]}
        u0, u1 = {"base": (Fraction(0), Fraction(1, 12)), "side": (Fraction(1, 12), Fraction(11, 12)),
                  "neck": (Fraction(11, 12), Fraction(1))}[role.rsplit("_", 1)[1]]
        endpoint_z = sorted((float(curve.Value(float(u0)).Z()), float(curve.Value(float(u1)).Z())))
        z_match = max(abs(edge_bounds[2] - endpoint_z[0]), abs(edge_bounds[5] - endpoint_z[1])) <= FACE_BBOX_TOL_MM
        if role.endswith("_base"):
            target_z = 3.0 if role.startswith("inner_") else 0.0
            signature_match, signature = z_match and max(abs(edge_bounds[2] - target_z), abs(edge_bounds[5] - target_z)) <= FACE_BBOX_TOL_MM, "flat_z_base"
        elif role.endswith("_neck"):
            radius = 23.0 if role.startswith("inner_") else 26.0
            signature_match, signature = z_match and max(abs(edge_bounds[0] - radius), abs(edge_bounds[3] - radius)) <= FACE_BBOX_TOL_MM, "near_constant_radius_neck"
        else:
            signature_match, signature = z_match and edge_bounds[3] - edge_bounds[0] > FACE_BBOX_TOL_MM, "nonflat_varying_radius_side"
        return {"pass": signature_match, "feature_signature": signature, "expected_z_bounds_mm": endpoint_z, "observed_z_bounds_mm": [edge_bounds[2], edge_bounds[5]], "observed_x_bounds_mm": [edge_bounds[0], edge_bounds[3]]}

    def fingerprint_delta(record: dict[str, Any], native_record: dict[str, Any]) -> dict[str, Any]:
        bounds = bbox_deltas(record["bbox_xyz_minmax_mm"], native_record["bbox_xyz_minmax_mm"])
        native_area = float(native_record["area_mm2"])
        face_area = float(record["area_mm2"])
        relative_area = abs(face_area - native_area) / abs(native_area) if native_area else math.inf
        return {"bbox_abs_deltas_mm": bounds, "area_relative_delta": relative_area, "bbox_pass": all(delta <= FACE_BBOX_TOL_MM for delta in bounds), "area_pass": relative_area <= FACE_AREA_REL_TOL}

    solids = explore(body, TopAbs_SOLID, TopoDS.Solid)
    shells = explore(body, TopAbs_SHELL, TopoDS.Shell)
    faces = explore(body, TopAbs_FACE, TopoDS.Face)
    shell_closed = [bool(shell.Closed()) for shell in shells]
    shape_valid = bool(BRepCheck_Analyzer(body, True).IsValid())
    body_area, body_volume = area(body), volume(body)
    face_areas = [area(face) for face in faces]
    gate(report, "native_topology", len(solids) == 1 and len(shells) == 1 and all(shell_closed) and shape_valid, {"solid_count": len(solids), "shell_count": len(shells), "shell_closed": shell_closed, "shape_valid": shape_valid})
    gate(report, "native_positive_metrics", math.isfinite(body_area) and body_area > 0 and math.isfinite(body_volume) and body_volume > 0 and len(face_areas) == 7 and all(math.isfinite(x) and x > 0 for x in face_areas), {"surface_area_mm2": body_area, "signed_volume_mm3": body_volume, "face_count": len(faces), "face_areas_mm2": face_areas})
    gate(report, "native_face_count", len(faces) == 7, {"face_count": len(faces), "expected_roles": list(ROLES)})
    edge_roles = {**outer_edges, **inner_edges, "lip": lip_edge}
    native_roles: dict[str, Any] = {}
    native_face_inventory: list[Any] = []
    native_face_history_unique = True
    for role, source_edge in edge_roles.items():
        generated = revol.Generated(source_edge)
        if generated.Extent() != 1:
            raise RuntimeError(f"Generated(edge) returned {generated.Extent()} shapes for {role}; expected one face")
        generated_shape = generated.First()
        if generated_shape.ShapeType() != TopAbs_FACE:
            raise RuntimeError(f"Generated(edge) returned {generated_shape.ShapeType()} for {role}; expected TopAbs_FACE")
        native_face = TopoDS.Face(generated_shape)
        inventory_matches = sum(1 for face in faces if face.IsSame(native_face))
        if inventory_matches != 1 or any(native_face.IsSame(previous) for previous in native_face_inventory):
            native_face_history_unique = False
        native_face_inventory.append(native_face)
        source_edge_bounds, source_derived_face_bounds = revolved_edge_bbox(source_edge)
        source_signature = source_role_geometry_check(role, source_edge_bounds)
        record = face_record(native_face)
        bbox_check = bbox_deltas(record["bbox_xyz_minmax_mm"], source_derived_face_bounds)
        bbox_pass = all(delta <= FACE_BBOX_TOL_MM for delta in bbox_check)
        record["semantic_role"] = role
        record["generated_edge_curve_type"] = enum_label(BRepAdaptor_Curve(source_edge).GetType(), curve_type_names)
        record.update({"role_assignment_method": "Generated(source_edge) history + unique TopoDS IsSame inventory",
                       "source_edge_bbox_xyz_minmax_mm": source_edge_bounds, "source_derived_revolved_bbox_xyz_minmax_mm": source_derived_face_bounds,
                       "source_to_native_bbox_abs_deltas_mm": bbox_check, "source_to_native_bbox_tolerance_mm": FACE_BBOX_TOL_MM,
                       "native_face_inventory_match_count": inventory_matches, "surface_type_role_use": "REPORT_ONLY",
                       "source_geometry_signature": source_signature})
        native_roles[role] = record
    gate(report, "native_generated_face_history_inventory", native_face_history_unique and len(native_face_inventory) == len(ROLES),
         {"role_count": len(native_roles), "actual_body_face_count": len(faces), "unique_IsSame_inventory_match_per_role": {role: native_roles[role]["native_face_inventory_match_count"] for role in native_roles}})
    gate(report, "native_source_derived_role_bboxes", all(row["source_to_native_bbox_abs_deltas_mm"] and max(row["source_to_native_bbox_abs_deltas_mm"]) <= FACE_BBOX_TOL_MM for row in native_roles.values()),
         {"tolerance_mm": FACE_BBOX_TOL_MM, "roles": {role: row["source_to_native_bbox_abs_deltas_mm"] for role, row in native_roles.items()}})
    gate(report, "native_source_role_geometry_signatures", all(row["source_geometry_signature"]["pass"] for row in native_roles.values()) and set(native_roles) == set(ROLES),
         {"tolerance_mm": FACE_BBOX_TOL_MM, "surface_types_used_for_role_assignment": False, "roles": {role: row["source_geometry_signature"] for role, row in native_roles.items()}})
    axis_generated = revol.Generated(axis_edge)
    degenerated = revol.Degenerated()
    topology_type_names = {TopAbs_EDGE: "EDGE", TopAbs_FACE: "FACE", TopAbs_SHELL: "SHELL", TopAbs_SOLID: "SOLID"}
    axis_generated_first = axis_generated.First() if axis_generated.Extent() == 1 else None
    axis_generated_type_value = axis_generated_first.ShapeType() if axis_generated_first is not None else None
    axis_generated_type = enum_label(axis_generated_type_value, topology_type_names) if axis_generated_type_value is not None else "NO_GENERATED_SHAPE" if axis_generated.Extent() == 0 else "UNKNOWN"
    axis_face_count = int(axis_generated_type_value == TopAbs_FACE) if axis_generated_type_value is not None else 0 if axis_generated.Extent() == 0 else -1
    degenerated_count = degenerated.Extent()
    degenerated_first = degenerated.First() if degenerated_count else None
    degenerated_last = degenerated.Last() if degenerated_count > 1 else degenerated_first
    degenerated_types = [enum_label(shape.ShapeType(), topology_type_names) for shape in (degenerated_first, degenerated_last) if shape is not None]
    degenerated_inventory = {"reported_by": "BRepPrimAPI_MakeRevol.Degenerated()", "shape_count": degenerated_count, "first_shape_type": degenerated_types[0] if degenerated_types else None, "last_shape_type": degenerated_types[-1] if degenerated_count > 1 and degenerated_types else None, "complete_member_identity_inventory": degenerated_count == 1, "single_degenerated_edge_is_axis_generated_shape": bool(degenerated_first.IsSame(axis_generated_first)) if degenerated_count == 1 and axis_generated_first is not None else None}
    degenerated_edge_type_recorded = bool(degenerated_types) and all(label == "EDGE" for label in degenerated_types)
    gate(report, "axis_degeneracy_and_face_roles", bool(revol.HasDegenerated()) and degenerated_count >= 1 and degenerated_edge_type_recorded and axis_generated.Extent() <= 1 and axis_face_count == 0 and set(native_roles) == set(ROLES),
         {"has_degenerated": bool(revol.HasDegenerated()), "degenerated_edges": degenerated_inventory, "axis_generated_shape_count": axis_generated.Extent(),
          "axis_generated_shape_type": axis_generated_type, "axis_generated_face_count": axis_face_count, "face_roles": sorted(native_roles)})
    report["native_geometry"] = {"bbox_xyz_minmax_mm": shape_bbox(body), "surface_area_mm2": body_area, "signed_volume_mm3": body_volume, "solid_count": len(solids), "shell_count": len(shells), "shell_closed": shell_closed, "valid": shape_valid, "face_count": len(faces), "face_roles": native_roles, "axis_degenerated_edge_count": degenerated_count, "axis_degenerated_edge_inventory": degenerated_inventory, "explicit_healing_called": False, "edge_curve_type_counts": {name: sum(1 for e in explore(body, TopAbs_EDGE) if enum_label(BRepAdaptor_Curve(TopoDS.Edge(e)).GetType(), curve_type_names) == name) for name in ("LINE", "BSPLINE", "OFFSET")}}
    report["phase"] = "native_geometry_validated"
    write_json(output / "native_result.json", report)

    Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    writer = STEPControl_Writer()
    transfer_status = writer.Transfer(body, STEPControl_AsIs)
    if transfer_status != IFSelect_RetDone:
        raise RuntimeError(f"STEP transfer failed: {transfer_status}")
    write_status = writer.Write(str(step_path))
    if write_status != IFSelect_RetDone:
        raise RuntimeError(f"STEP write failed: {write_status}")
    step_bytes = step_path.stat().st_size
    report["step_export"] = {"path": str(step_path), "sha256": sha256_file(step_path), "bytes": step_bytes, "transfer_status": str(transfer_status), "write_status": str(write_status), "units": "MM", "explicit_healing_called": False}
    report["phase"] = "step_exported"
    write_json(output / "native_result.json", report)
    gate(report, "step_output_reserve", step_bytes < MAX_STEP_BYTES, {"step_bytes": step_bytes, "max_step_bytes_before_capture_reserve": MAX_STEP_BYTES})

    reader = STEPControl_Reader()
    read_status = reader.ReadFile(str(step_path))
    if read_status != IFSelect_RetDone:
        raise RuntimeError(f"STEP ReadFile failed: {read_status}")
    transferred_roots = int(reader.TransferRoots())
    if transferred_roots < 1:
        raise RuntimeError("STEP TransferRoots returned no transferred roots")
    imported = reader.OneShape()
    post_solids = explore(imported, TopAbs_SOLID, TopoDS.Solid)
    post_shells = explore(imported, TopAbs_SHELL, TopoDS.Shell)
    post_faces = explore(imported, TopAbs_FACE, TopoDS.Face)
    post_closed = [bool(shell.Closed()) for shell in post_shells]
    post_valid = bool(BRepCheck_Analyzer(imported, True).IsValid())
    post_area, post_volume = area(imported), volume(imported)
    post_bbox = shape_bbox(imported)
    post_roles: dict[str, Any] = {}
    unclassified: list[dict[str, Any]] = []
    post_face_candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    candidate_role_counts: dict[str, int] = {}
    for face in post_faces:
        record = face_record(face)
        deltas = {role: fingerprint_delta(record, native_roles[role]) for role in ROLES}
        candidates = [role for role, delta in deltas.items() if delta["bbox_pass"] and delta["area_pass"]]
        for role in candidates:
            candidate_role_counts[role] = candidate_role_counts.get(role, 0) + 1
        post_face_candidates.append((record, deltas))
    for record, deltas_by_role in post_face_candidates:
        candidates = [role for role, delta in deltas_by_role.items() if delta["bbox_pass"] and delta["area_pass"]]
        if len(candidates) == 1 and candidate_role_counts[candidates[0]] == 1:
            role = candidates[0]
            record["semantic_role"] = role
            record["role_assignment_method"] = "unique native per-role bbox+area fingerprint match; metric semantic match only"
            record["native_fingerprint_delta"] = deltas_by_role[role]
            record["surface_type_role_use"] = "REPORT_ONLY"
            post_roles[role] = record
        else:
            unclassified.append({**record, "candidate_roles": candidates,
                                 "role_assignment_status": "UNKNOWN_AMBIGUOUS_OR_NO_FINGERPRINT_MATCH",
                                 "matching_tolerance_mm": FACE_BBOX_TOL_MM,
                                 "matching_area_relative_tolerance": FACE_AREA_REL_TOL})
    bbox_deltas = [abs(a - b) for a, b in zip(report["native_geometry"]["bbox_xyz_minmax_mm"], post_bbox)]
    area_relative = abs(post_area - body_area) / abs(body_area) if body_area else math.inf
    volume_relative = abs(post_volume - body_volume) / abs(body_volume) if body_volume else math.inf
    gate(report, "step_import_topology", len(post_solids) == 1 and len(post_shells) == 1 and all(post_closed) and post_valid and len(post_faces) == 7, {"solid_count": len(post_solids), "shell_count": len(post_shells), "shell_closed": post_closed, "valid": post_valid, "face_count": len(post_faces), "transferred_roots": transferred_roots})
    gate(report, "step_geometry_metrics", all(x <= 1e-7 for x in bbox_deltas) and area_relative <= 1e-8 and volume_relative <= 1e-8, {"bbox_abs_deltas_mm": bbox_deltas, "area_relative_delta": area_relative, "volume_relative_delta": volume_relative})
    gate(report, "step_semantic_face_roles", set(post_roles) == set(ROLES) and not unclassified,
         {"roles": sorted(post_roles), "unclassified_or_duplicate_count": len(unclassified),
          "post_face_candidate_roles": [[role for role, delta in deltas.items() if delta["bbox_pass"] and delta["area_pass"]] for _, deltas in post_face_candidates],
          "method": "unique native per-role bbox+area fingerprint match; metric semantic match only",
          "bbox_tolerance_mm": FACE_BBOX_TOL_MM, "area_relative_tolerance": FACE_AREA_REL_TOL,
          "full_geometry_equality_claim": False})
    post_edge_types: dict[str, int] = {}
    for edge in explore(imported, TopAbs_EDGE):
        label = enum_label(BRepAdaptor_Curve(TopoDS.Edge(edge)).GetType(), curve_type_names)
        post_edge_types[label] = post_edge_types.get(label, 0) + 1
    type_changes = {role: {"native": native_roles[role]["surface_type"], "step": post_roles[role]["surface_type"]} for role in ROLES if role in post_roles and native_roles[role]["surface_type"] != post_roles[role]["surface_type"]}
    role_metric_deltas = {role: {"native_area_mm2": native_roles[role]["area_mm2"], "step_area_mm2": post_roles[role]["area_mm2"], "area_relative_delta": abs(post_roles[role]["area_mm2"] - native_roles[role]["area_mm2"]) / native_roles[role]["area_mm2"] if native_roles[role]["area_mm2"] else None} for role in ROLES if role in post_roles}
    report["step_import"] = {"read_status": str(read_status), "transferred_roots": transferred_roots, "solid_count": len(post_solids), "shell_count": len(post_shells), "shell_closed": post_closed, "valid": post_valid, "face_count": len(post_faces), "bbox_xyz_minmax_mm": post_bbox, "surface_area_mm2": post_area, "signed_volume_mm3": post_volume, "bbox_abs_deltas_mm": bbox_deltas, "area_relative_delta": area_relative, "volume_relative_delta": volume_relative, "face_roles": post_roles, "unclassified_or_duplicate_faces": unclassified, "surface_type_changes": type_changes, "native_face_role_area_deltas": role_metric_deltas, "edge_curve_type_counts": post_edge_types, "full_geometry_equality_claim": False}
    report["claim_limits"]["global_native_wall"] = "UNKNOWN"
    report["claim_limits"]["native_wall_transfer_from_ideal_curve_pair"] = "UNKNOWN"
    report["claim_limits"]["lip_qualification"] = "UNKNOWN"
    report["claim_limits"]["physics"] = "UNKNOWN"
    report["status"] = "NATIVE_BREP_STEP_METRICS_PASS_GLOBAL_WALL_UNKNOWN"
    report["phase"] = "complete"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-go", action="store_true", help="explicit future root authorization; no default execution")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if not args.root_go:
        print("execution disabled; require --root-go")
        return 2
    report: dict[str, Any] = {"schema": "vesselforge.c4_jar_native_ingress.result/1.0", "status": "RUNNING", "phase": "startup", "argv": sys.argv[:], "started_unix": time.time(), "execution_scope": "one native B-rep build, one STEP export, one STEP import"}
    try:
        case = read_json(CASE_PATH)
        pins = read_json(PINS_PATH)
        if case.get("execution_authorized") is not False or pins.get("execution_authorized") is not False:
            raise RuntimeError("source freeze must remain marked execution_authorized=false")
        worker(report, case, pins, args.output_dir.resolve())
        return 0
    except BaseException as exc:
        report["status"] = "FAIL"
        report["failure"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        return 2
    finally:
        report["elapsed_seconds"] = time.time() - report["started_unix"]
        out = args.output_dir.resolve()
        if out.exists():
            try:
                write_json(out / "native_result.json", report)
            except Exception:
                pass
        print(json.dumps({"status": report["status"], "phase": report.get("phase"), "result": str(out / "native_result.json")}, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
