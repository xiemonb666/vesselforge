#!/usr/bin/env python3
"""One-shot, bounded finite normal-wall probes on one frozen STEP B-rep."""
from __future__ import annotations
import hashlib, json, math, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
RUN = ROOT / "vesselforge/experiments/smooth_surface_native_adapter_20261005/tmp/runs/single_inner_native_01"
STEP = RUN / "candidate.step"
RUN_RECEIPT = RUN / "run_receipt.json"
STEP_SHA = "9a6ac86efb2d714e5d2d737263307014487fe2e45979c4181f6071c6f0cf6c71"
RECEIPT_SHA = "4c17fe03c74a6fe4474d98b3de9305916572910247c64bd144189ca2c3f711c8"
CAD_TOL_MM, ORIENTATION_OFFSET_MM = 1e-7, 0.025
RAY_START_MM, MAX_RAY_MM = 1e-4, 20.0
END_BAND_MM, MAX_RAYS, MAX_HITS, WALL_SECONDS = 12.0, 128, 512, 180
UV_FRACTIONS = (0.25, 0.75)
DATA = OUT / "normal_wall_probe_data.json"
SECTION_PNG = OUT / "normal_wall_probe_section_y0.png"
RAYS_PNG = OUT / "normal_wall_probe_rays_3d.png"
MANIFEST = OUT / "normal_wall_probe_run_manifest.json"
ATTEMPT_LOCK = OUT / "normal_wall_probe_attempt.lock"

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def checked_receipt() -> tuple[str, dict]:
    step_hash, receipt_hash = sha256(STEP), sha256(RUN_RECEIPT)
    if step_hash != STEP_SHA or receipt_hash != RECEIPT_SHA:
        raise RuntimeError(f"frozen input hash mismatch: STEP={step_hash}, receipt={receipt_hash}")
    receipt = json.loads(RUN_RECEIPT.read_text(encoding="utf-8"))
    native = receipt["native_step"]
    radial_gap = receipt["required_exact_monotonicity_report"]["paired_side_control_gap_exact_mm_before_rim_transition"]
    if (receipt["run_id"] != "single_inner_native_01" or native["step_sha256"] != STEP_SHA
            or native["step_face_count"] != 19 or native["solid_count"] != 1
            or native["shell_count"] != 1 or receipt["units"] != "mm" or radial_gap != "5/2"):
        raise RuntimeError("receipt identity/topology/units do not match this frozen review")
    return step_hash, receipt

def state_name(state, topabs) -> str:
    return {topabs.TopAbs_IN: "IN", topabs.TopAbs_OUT: "OUT", topabs.TopAbs_ON: "ON"}.get(state, str(state))

def sidewall_region(is_revolution: bool, point, radial_dot, bbox) -> str:
    z = float(point[2])
    if z <= float(bbox.zmin) + END_BAND_MM:
        return "LOWER_BBOX_END_BAND_BASE_FLOOR_CANDIDATE_EXCLUDED"
    if z >= float(bbox.zmax) - END_BAND_MM:
        return "UPPER_BBOX_END_BAND_RIM_LIP_CANDIDATE_EXCLUDED_UNKNOWN"
    if not is_revolution:
        return "NONREVOLUTION_FACE_NOT_SIDEWALL"
    if radial_dot is None:
        return "RADIAL_DIRECTION_UNDEFINED_UNKNOWN"
    if abs(float(radial_dot)) < math.cos(math.radians(30.0)):
        return "ROUNDED_SHOULDER_OR_BASE_TRANSITION_EXCLUDED"
    return "INNER_SIDEWALL_NORMAL_SAMPLE_ONLY" if radial_dot < 0 else "OUTER_SIDEWALL_INTERIOR_RAY_CANDIDATE"

class SolidProbeClassifier:
    def __init__(self, solid):
        from OCP.BRepClass3d import BRepClass3d_SolidClassifier
        self._classifier = BRepClass3d_SolidClassifier()
        self._classifier.Load(solid.wrapped)
        from OCP import TopAbs
        self._topabs = TopAbs

    def state(self, xyz) -> str:
        from OCP.gp import gp_Pnt
        self._classifier.Perform(gp_Pnt(float(xyz[0]), float(xyz[1]), float(xyz[2])), CAD_TOL_MM)
        return state_name(self._classifier.State(), self._topabs)

def face_sample_grid(shape, solid, bbox) -> tuple[list[dict], list[dict]]:
    import numpy as np
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.BRepTools import BRepTools
    from OCP.GeomAbs import GeomAbs_SurfaceOfRevolution
    from OCP import TopAbs
    from OCP.TopAbs import TopAbs_IN, TopAbs_REVERSED
    from OCP.gp import gp_Pnt2d
    classifier = SolidProbeClassifier(solid)
    faces, samples, face_rows = shape.Faces(), [], []
    z_lo, z_hi = float(bbox.zmin), float(bbox.zmax)
    if z_hi <= z_lo:
        raise RuntimeError("global-Z bounds are degenerate")
    for face_id, face in enumerate(faces):
        adaptor = BRepAdaptor_Surface(face.wrapped, True)
        u0, u1, v0, v1 = (float(x) for x in BRepTools.UVBounds_s(face.wrapped))
        face_row = {"face_id_zero_based": face_id, "surface_type": str(adaptor.GetType()),
                    "uv_bounds": [u0, u1, v0, v1], "uv_samples": []}
        if not all(math.isfinite(x) for x in (u0, u1, v0, v1)) or u1 - u0 <= 1e-12 or v1 - v0 <= 1e-12:
            face_row["status"] = "UNKNOWN_NONFINITE_OR_DEGENERATE_UV_BOUNDS"
            face_rows.append(face_row)
            continue
        revolution = adaptor.GetType() == GeomAbs_SurfaceOfRevolution
        for fu in UV_FRACTIONS:
            for fv in UV_FRACTIONS:
                u, v = u0 + fu * (u1 - u0), v0 + fv * (v1 - v0)
                uv_state = BRepClass_FaceClassifier(face.wrapped, gp_Pnt2d(u, v), CAD_TOL_MM).State()
                row = {"face_id_zero_based": face_id, "surface_type": str(adaptor.GetType()),
                       "u": float(u), "v": float(v), "uv_fraction": [fu, fv],
                       "uv_classifier_state": state_name(uv_state, TopAbs),
                       "on_surface_of_revolution": bool(revolution)}
                face_row["uv_samples"].append(row)
                if uv_state != TopAbs_IN:
                    row["region"] = "TRIM_BOUNDARY_OR_OUTSIDE_UNKNOWN"
                    samples.append(row)
                    continue
                du, dv = 0.005 * (u1 - u0), 0.005 * (v1 - v0)
                neighbor_states = []
                for un, vn in ((u-du, v), (u+du, v), (u, v-dv), (u, v+dv)):
                    if not (u0 < un < u1 and v0 < vn < v1):
                        neighbor_states.append("UV_BOUNDARY")
                    else:
                        st = BRepClass_FaceClassifier(face.wrapped, gp_Pnt2d(un, vn), CAD_TOL_MM).State()
                        neighbor_states.append(state_name(st, TopAbs))
                row["local_uv_neighbor_states"] = neighbor_states
                if any(st != "IN" for st in neighbor_states):
                    row["region"] = "TRIM_EDGE_OR_SEAM_AMBIGUOUS"
                    samples.append(row)
                    continue
                props = BRepLProp_SLProps(adaptor, u, v, 1, CAD_TOL_MM)
                if not props.IsNormalDefined():
                    row["region"] = "NORMAL_UNDEFINED_UNKNOWN"
                    samples.append(row)
                    continue
                p, n = adaptor.Value(u, v), props.Normal()
                if face.wrapped.Orientation() == TopAbs_REVERSED:
                    n.Reverse()
                point = np.asarray([p.X(), p.Y(), p.Z()], dtype=np.float64)
                normal = np.asarray([n.X(), n.Y(), n.Z()], dtype=np.float64)
                magnitude = float(np.linalg.norm(normal))
                if not math.isfinite(magnitude) or magnitude <= 1e-12:
                    row["region"] = "DEGENERATE_NORMAL_UNKNOWN"
                    samples.append(row)
                    continue
                normal /= magnitude
                radius = float(math.hypot(point[0], point[1]))
                radial = np.asarray([point[0] / radius, point[1] / radius, 0.0]) if radius > 1e-9 else None
                radial_dot = float(np.dot(normal, radial)) if radial is not None else None
                row.update({"point_mm": point.tolist(), "outward_from_material_normal": normal.tolist(),
                            "normal_length_before_normalization": magnitude, "radius_mm": radius,
                            "radial_normal_dot": radial_dot,
                            "normal_angle_to_radial_rad": math.acos(max(-1.0, min(1.0, radial_dot))) if radial_dot is not None else None,
                            "source_plus_state": classifier.state(point + ORIENTATION_OFFSET_MM * normal),
                            "source_minus_state": classifier.state(point - ORIENTATION_OFFSET_MM * normal)})
                row["region"] = sidewall_region(revolution, point, radial_dot, bbox)
                if row["region"] == "OUTER_SIDEWALL_INTERIOR_RAY_CANDIDATE" and (
                        row["source_plus_state"] != "OUT" or row["source_minus_state"] != "IN"):
                    row["region"] = "SURFACE_ORIENTATION_CLASSIFIER_AMBIGUOUS"
                if row["region"] == "OUTER_SIDEWALL_INTERIOR_RAY_CANDIDATE":
                    samples.append(row)
                    continue
                samples.append(row)
        face_rows.append(face_row)
    return samples, face_rows

def face_id_for_hit(hit_face, faces) -> int | None:
    for face_id, face in enumerate(faces):
        if face.wrapped.IsSame(hit_face):
            return face_id
    return None

def trace_ray(shape, faces, sample, classifier, bbox, hit_budget_left: int) -> tuple[dict, int]:
    import numpy as np
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    from OCP import TopAbs
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
    point = np.asarray(sample["point_mm"], dtype=np.float64)
    normal = np.asarray(sample["outward_from_material_normal"], dtype=np.float64)
    start = point - RAY_START_MM * normal
    direction = -normal
    record = {"source_face_id_zero_based": sample["face_id_zero_based"], "u": sample["u"], "v": sample["v"],
              "source_point_mm": point.tolist(), "source_outward_normal": normal.tolist(),
              "direction_into_material": direction.tolist(), "ray_start_mm": start.tolist(),
              "ray_start_state": classifier.state(start), "search_length_mm": MAX_RAY_MM,
              "all_hits": [], "status": "UNKNOWN"}
    if record["ray_start_state"] != "IN":
        record["reason"] = "RAY_START_NOT_CLASSIFIED_IN"
        return record, 0
    intersector = IntCurvesFace_ShapeIntersector()
    intersector.Load(shape.wrapped, CAD_TOL_MM)
    line = gp_Lin(gp_Pnt(*[float(x) for x in start]), gp_Dir(*[float(x) for x in direction]))
    intersector.Perform(line, 0.0, MAX_RAY_MM)
    if not intersector.IsDone():
        record["reason"] = "FINITE_BREP_INTERSECTOR_NOT_DONE"
        return record, 0
    n_hits = int(intersector.NbPnt())
    record["raw_hit_count"] = n_hits
    if n_hits > hit_budget_left:
        record["reason"] = "GLOBAL_HIT_CAP_EXCEEDED_NO_TRUNCATED_RESULT_USED"
        record["hit_cap_exceeded_by"] = n_hits - hit_budget_left
        return record, n_hits
    for i in range(1, n_hits + 1):
        hit_face = intersector.Face(i)
        xyz = intersector.Pnt(i)
        w = float(intersector.WParameter(i))
        face_id = face_id_for_hit(hit_face, faces)
        hit = {"raw_hit_index_one_based": i, "ray_parameter_mm": w,
               "point_mm": [float(xyz.X()), float(xyz.Y()), float(xyz.Z())],
               "hit_face_id_zero_based": face_id,
               "hit_u": float(intersector.UParameter(i)), "hit_v": float(intersector.VParameter(i)),
               "hit_trim_classifier_state": "UNKNOWN"}
        if face_id is not None:
            from OCP.BRepClass import BRepClass_FaceClassifier
            from OCP.gp import gp_Pnt2d
            hit["hit_trim_classifier_state"] = state_name(
                BRepClass_FaceClassifier(faces[face_id].wrapped, gp_Pnt2d(hit["hit_u"], hit["hit_v"]), CAD_TOL_MM).State(),
                TopAbs)
            hit_surface = BRepAdaptor_Surface(faces[face_id].wrapped, True)
            hit_props = BRepLProp_SLProps(hit_surface, hit["hit_u"], hit["hit_v"], 1, CAD_TOL_MM)
            hit["hit_surface_type"] = str(hit_surface.GetType())
            if hit_props.IsNormalDefined():
                hit_normal = hit_props.Normal()
                if faces[face_id].wrapped.Orientation() == TopAbs_REVERSED:
                    hit_normal.Reverse()
                hn = np.asarray([hit_normal.X(), hit_normal.Y(), hit_normal.Z()], dtype=np.float64)
                hn_len = float(np.linalg.norm(hn))
                if math.isfinite(hn_len) and hn_len > 1e-12:
                    hn /= hn_len
                    incidence = float(np.dot(direction, hn))
                    hit["hit_outward_from_material_normal"] = hn.tolist()
                    hit["ray_to_hit_normal_angle_rad"] = math.acos(max(-1.0, min(1.0, incidence)))
                    hit["hit_normal_length_before_normalization"] = hn_len
                    hit_radius = math.hypot(hit["point_mm"][0], hit["point_mm"][1])
                    hit_radial = ([hit["point_mm"][0] / hit_radius, hit["point_mm"][1] / hit_radius, 0.0]
                                  if hit_radius > 1e-9 else None)
                    hit_radial_dot = float(np.dot(hn, hit_radial)) if hit_radial is not None else None
                    hit["hit_radius_mm"] = hit_radius
                    hit["hit_radial_normal_dot"] = hit_radial_dot
                    hit["hit_normal_angle_to_radial_rad"] = (
                        math.acos(max(-1.0, min(1.0, hit_radial_dot))) if hit_radial_dot is not None else None)
                    from OCP.GeomAbs import GeomAbs_SurfaceOfRevolution
                    hit["hit_region"] = sidewall_region(
                        hit_surface.GetType() == GeomAbs_SurfaceOfRevolution,
                        hit["point_mm"], hit_radial_dot, bbox)
            if "hit_region" not in hit:
                hit["hit_region"] = "HIT_NORMAL_UNDEFINED_UNKNOWN"
        record["all_hits"].append(hit)
    ordered = sorted(record["all_hits"], key=lambda h: (h["ray_parameter_mm"], h["raw_hit_index_one_based"]))
    for pos, hit in enumerate(ordered):
        t = hit["ray_parameter_mm"]
        previous = 0.0 if pos == 0 else ordered[pos-1]["ray_parameter_mm"]
        following = MAX_RAY_MM if pos + 1 == len(ordered) else ordered[pos+1]["ray_parameter_mm"]
        before_gap, after_gap = t - previous, following - t
        hit["coincident_raw_hit_indices"] = [
            h["raw_hit_index_one_based"] for h in ordered
            if h["raw_hit_index_one_based"] != hit["raw_hit_index_one_based"]
            and abs(h["ray_parameter_mm"] - t) <= CAD_TOL_MM]
        if before_gap <= 2 * CAD_TOL_MM:
            hit["before_state"] = "UNRESOLVED_INTERVAL_TOO_SHORT"
        else:
            before = start + direction * (previous + t) * 0.5
            hit["before_state"] = classifier.state(before)
        if after_gap <= 2 * CAD_TOL_MM:
            hit["after_state"] = "UNRESOLVED_INTERVAL_TOO_SHORT"
        else:
            after = start + direction * (t + following) * 0.5
            hit["after_state"] = classifier.state(after)
        hit["transition"] = ("IN_TO_OUT" if hit["before_state"] == "IN" and hit["after_state"] == "OUT" else
                             "OUT_TO_IN" if hit["before_state"] == "OUT" and hit["after_state"] == "IN" else
                             "NO_CLEAR_TRANSITION")
    if not ordered:
        record["reason"] = "NO_BREP_HIT_WITHIN_FINITE_SEARCH_LENGTH"
        return record, n_hits
    first = ordered[0]
    if first["transition"] != "IN_TO_OUT":
        record["reason"] = "FIRST_HIT_DOES_NOT_ESTABLISH_LOCAL_IN_TO_OUT_INTERVAL"
    elif first["coincident_raw_hit_indices"]:
        record["reason"] = "COINCIDENT_FACE_OR_SEAM_HITS_ARE_AMBIGUOUS"
    elif first["hit_trim_classifier_state"] != "IN":
        record["reason"] = "EXIT_HIT_ON_TRIM_BOUNDARY_OR_OUTSIDE"
    elif first["hit_face_id_zero_based"] is None:
        record["reason"] = "HIT_FACE_ID_NOT_MAPPED_TO_IMPORTED_BREP"
    elif first["hit_face_id_zero_based"] == record["source_face_id_zero_based"]:
        record["reason"] = "FIRST_EXIT_RETURNS_TO_SOURCE_FACE"
    elif first.get("hit_region") != "INNER_SIDEWALL_NORMAL_SAMPLE_ONLY":
        record["reason"] = "FIRST_EXIT_IS_RIM_BASE_OR_ROUNDED_NONWALL_REGION"
    elif "hit_outward_from_material_normal" not in first:
        record["reason"] = "EXIT_FACE_NORMAL_UNDEFINED"
    elif "hit_outward_from_material_normal" not in first:
        record["reason"] = "EXIT_FACE_NORMAL_UNDEFINED"
    else:
        record["status"] = "MEASURED_LOCAL_NORMAL_INTERVAL"
        record["normal_wall_interval_mm"] = RAY_START_MM + first["ray_parameter_mm"]
        record["interval_entry_state"] = "IN_AT_OUTER_SOURCE_OFFSET"
        record["interval_exit_state"] = "OUT_AFTER_UNIQUE_IN_TO_OUT_HIT"
        record["exit_hit_raw_index_one_based"] = first["raw_hit_index_one_based"]
    return record, n_hits

def actual_section(shape) -> tuple[list[dict], int]:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
    section = BRepAlgoAPI_Section(shape.wrapped, gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0)), True)
    section.Build()
    if not section.IsDone():
        raise RuntimeError("actual BRep y=0 section did not complete")
    explorer, curves = TopExp_Explorer(section.Shape(), TopAbs_EDGE), []
    while explorer.More():
        curve = BRepAdaptor_Curve(TopoDS.Edge_s(explorer.Current()))
        a, b = float(curve.FirstParameter()), float(curve.LastParameter())
        if not math.isfinite(a) or not math.isfinite(b) or a == b:
            raise RuntimeError("section edge has invalid parameter interval")
        xyz = []
        for k in range(101):
            p = curve.Value(a + (b-a) * k / 100)
            xyz.append([float(p.X()), float(p.Y()), float(p.Z())])
        curves.append({"edge_index": len(curves), "sample_count": len(xyz), "xyz_mm": xyz})
        explorer.Next()
    if not curves:
        raise RuntimeError("actual BRep y=0 section returned no edges")
    return curves, len(curves)

def render(shape, bbox, data) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    fig, ax = plt.subplots(figsize=(8, 9), dpi=150)
    for curve in data["section_y0"]["curves"]:
        xyz = np.asarray(curve["xyz_mm"], dtype=np.float64)
        ax.plot(xyz[:, 0], xyz[:, 2], color="#183b52", linewidth=1.1)
    ax.set_xlim(bbox.xmin, bbox.xmax); ax.set_ylim(bbox.zmin, bbox.zmax)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x (mm)"); ax.set_ylabel("z (mm)"); ax.grid(True, alpha=0.3)
    ax.set_title("Actual STEP B-rep section at y=0 · equal mm scale")
    fig.suptitle("Section evidence only · finite probes · no global wall proof")
    fig.tight_layout(rect=(0, 0, 1, 0.95)); fig.savefig(SECTION_PNG, facecolor="white"); plt.close(fig)

    fig = plt.figure(figsize=(11, 9), dpi=150)
    ax3 = fig.add_subplot(1, 1, 1, projection="3d")
    colors = {"MEASURED_LOCAL_NORMAL_INTERVAL": "#16834a", "UNKNOWN": "#d17a00"}
    for ray in data["rays"]:
        p = np.asarray(ray["source_point_mm"], dtype=np.float64)
        d = np.asarray(ray["direction_into_material"], dtype=np.float64)
        end = np.asarray(ray["ray_start_mm"], dtype=np.float64) + ray["search_length_mm"] * d
        color = colors.get(ray["status"], "#b33b3b")
        ax3.plot([p[0], end[0]], [p[1], end[1]], [p[2], end[2]], color=color, alpha=0.5, linewidth=0.8)
        ax3.quiver(*p, *np.asarray(ray["source_outward_normal"]), length=1.0, color="#204a87", normalize=True)
        ax3.scatter([p[0]], [p[1]], [p[2]], color="#204a87", s=9)
        for hit in ray.get("all_hits", []):
            q = hit["point_mm"]
            ax3.scatter([q[0]], [q[1]], [q[2]], color=color, s=8)
    ax3.set_xlim(bbox.xmin, bbox.xmax); ax3.set_ylim(bbox.ymin, bbox.ymax); ax3.set_zlim(bbox.zmin, bbox.zmax)
    ax3.set_box_aspect((bbox.xlen, bbox.ylen, bbox.zlen))
    ax3.set_xlabel("x (mm)"); ax3.set_ylabel("y (mm)"); ax3.set_zlabel("z (mm)")
    ax3.set_title("Actual B-rep normal rays and raw hits · mm · no hit averaging")
    fig.suptitle("Finite sidewall probes only · UNKNOWN rays retained · not global wall proof")
    fig.tight_layout(rect=(0, 0, 1, 0.95)); fig.savefig(RAYS_PNG, facecolor="white"); plt.close(fig)

def worker() -> int:
    started = time.monotonic()
    data = {"status": "FAILURE", "source_step_sha256": None, "run_receipt_sha256": None,
            "step_import_started": False, "step_import_completed": False, "ray_calls_started": 0,
            "tolerances": {"classifier_and_intersector_mm": CAD_TOL_MM,
                           "orientation_offset_mm": ORIENTATION_OFFSET_MM,
                           "ray_start_inside_mm": RAY_START_MM},
            "caps": {"rays": MAX_RAYS, "total_hits": MAX_HITS, "worker_wall_seconds": WALL_SECONDS},
            "sampling": {"uv_fractions": UV_FRACTIONS, "axial_end_exclusion_mm": END_BAND_MM,
                         "max_ray_search_length_mm": MAX_RAY_MM,
                         "axis_from_source_receipt": "global Z",
                         "nominal_rim_z_is_bbox_max_from_source_receipt": receipt["native_step"]["nominal_rim_z_is_bbox_max"],
                         "radial_control_gap_mm_context_only": "5/2; not normal wall thickness"},
            "global_wall_status": "UNKNOWN_FINITE_PROBES_ONLY",
            "section_y0": {"plane_normal": [0, 1, 0]}}
    rc = 2
    try:
        data["source_step_sha256"], receipt = checked_receipt()
        data["run_receipt_sha256"] = RECEIPT_SHA
        data["sampling"]["radial_control_gap_mm_context_only"] = (
            receipt["required_exact_monotonicity_report"]["paired_side_control_gap_exact_mm_before_rim_transition"]
            + "; control-pole radius difference, not normal wall thickness")
        import cadquery as cq
        from cadquery import importers
        data["step_import_started"] = True
        imported = importers.importStep(str(STEP))  # exactly one STEP import in this review
        data["step_import_completed"] = True
        shape = imported.val() if hasattr(imported, "val") else imported
        if shape is None or shape.wrapped.IsNull():
            raise RuntimeError("STEP import returned null B-rep")
        solids = shape.Solids()
        if len(solids) != 1 or not shape.isValid() or len(shape.Shells()) != 1:
            raise RuntimeError("imported STEP is not the expected valid one-solid/one-shell B-rep")
        bbox = shape.BoundingBox()
        data["brep_counts"] = {"solids": len(solids), "shells": len(shape.Shells()),
                               "faces": len(shape.Faces()), "edges": len(shape.Edges())}
        if data["brep_counts"]["faces"] != 19:
            raise RuntimeError("imported STEP face count differs from frozen receipt")
        samples, face_rows = face_sample_grid(shape, solids[0], bbox)
        candidates = [s for s in samples if s.get("region") == "OUTER_SIDEWALL_INTERIOR_RAY_CANDIDATE"]
        data["face_inventory"] = face_rows
        data["face_normal_samples"] = samples
        data["ray_candidate_count"] = len(candidates)
        if len(candidates) > MAX_RAYS:
            data.update({"status": "CAP_EXCEEDED_NO_PROBES", "failure": "ray candidate count exceeds 128; no subsampling"})
            rc = 3
        else:
            classifier = SolidProbeClassifier(solids[0])
            rays, total_hits = [], 0
            faces = shape.Faces()
            for ray_index, sample in enumerate(candidates):
                data["ray_calls_started"] = ray_index + 1
                row, hit_count = trace_ray(shape, faces, sample, classifier, bbox, MAX_HITS - total_hits)
                if total_hits + hit_count > MAX_HITS:
                    data["hit_cap_exceeded"] = {"prior_hits": total_hits, "overflow_ray_raw_hit_count": hit_count,
                                                 "cap": MAX_HITS, "no_truncated_measurement_used": True}
                    data["rays"] = rays
                    data["overflow_ray"] = row
                    data["status"] = "CAP_EXCEEDED_NO_QUALIFICATION"
                    rc = 3
                    break
                total_hits += hit_count
                rays.append(row)
            else:
                data["rays"] = rays
                data["total_raw_hits"] = total_hits
                data["finite_summary"] = {"ray_count": len(rays),
                    "measured_local_interval_count": sum(r["status"] == "MEASURED_LOCAL_NORMAL_INTERVAL" for r in rays),
                    "unknown_count": sum(r["status"] != "MEASURED_LOCAL_NORMAL_INTERVAL" for r in rays)}
                curves, edge_count = actual_section(shape)
                data["section_y0"].update({"edge_count": edge_count, "curves": curves,
                                            "sample_count": sum(c["sample_count"] for c in curves)})
                render(shape, bbox, data)
                data["status"] = "FINITE_PROBES_COMPLETE_GLOBAL_UNKNOWN"
                rc = 0
    except Exception as e:
        data["failure"] = f"{type(e).__name__}: {e}"
        rc = 2
    data["worker_elapsed_seconds"] = round(time.monotonic() - started, 3)
    DATA.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": data["status"], "failure": data.get("failure"),
                      "brep_counts": data.get("brep_counts"), "ray_candidate_count": data.get("ray_candidate_count"),
                      "total_raw_hits": data.get("total_raw_hits"), "finite_summary": data.get("finite_summary")}, ensure_ascii=False))
    return rc

def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--worker":
        return worker()
    argv = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]
    worker_argv = [sys.executable, str(Path(__file__).resolve()), "--worker"]
    status, rc, stdout, stderr = "FAILURE", 2, "", ""
    try:
        with ATTEMPT_LOCK.open("x", encoding="utf-8") as lock:
            lock.write("single source-reviewed attempt; no retries\n")
    except FileExistsError:
        print("probe attempt already consumed; refusing rerun", file=sys.stderr)
        return 5
    pre_step_hash, pre_receipt_hash = None, None
    try:
        pre_step_hash, _ = checked_receipt()
        pre_receipt_hash = sha256(RUN_RECEIPT)
        if len(sys.argv) != 1:
            raise RuntimeError("no user arguments accepted; inputs and limits are frozen")
        proc = subprocess.run(worker_argv, cwd=str(ROOT), capture_output=True, text=True,
                              timeout=WALL_SECONDS, check=False)
        rc, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
        status = "SUCCESS_FINITE_PROBES_GLOBAL_UNKNOWN" if rc == 0 else ("FAILURE_CAP_EXCEEDED" if rc == 3 else "FAILURE")
    except subprocess.TimeoutExpired as e:
        rc, status = 124, "FAILURE_TIMEOUT_NO_RETRY"
        stdout = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        stderr += f"\nworker exceeded {WALL_SECONDS}s hard wall-time limit; no retry"
    except Exception as e:
        rc, status, stderr = 2, "FAILURE", f"{type(e).__name__}: {e}"
    worker_data = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else None
    post_step_hash = sha256(STEP) if STEP.exists() else None
    post_receipt_hash = sha256(RUN_RECEIPT) if RUN_RECEIPT.exists() else None
    manifest = {"status": status, "actual_argv": argv, "worker_argv": worker_argv,
                "actual_rc": rc, "source_step": str(STEP), "source_step_sha256": STEP_SHA,
                "run_receipt": str(RUN_RECEIPT), "run_receipt_sha256": RECEIPT_SHA,
                "source_hashes_before_after": {"step_before": pre_step_hash,
                    "step_after": post_step_hash, "receipt_before": pre_receipt_hash,
                    "receipt_after": post_receipt_hash,
                    "unchanged": pre_step_hash == post_step_hash and pre_receipt_hash == post_receipt_hash if pre_step_hash else None},
                "tolerance_mm": CAD_TOL_MM, "max_rays": MAX_RAYS, "max_total_hits": MAX_HITS,
                "worker_wall_time_limit_seconds": WALL_SECONDS, "worker_data": worker_data,
                "solver_runs": 0, "normal_ray_calls_started": worker_data.get("ray_calls_started") if worker_data else "unknown_if_timeout",
                "section_png_sha256": sha256(SECTION_PNG) if SECTION_PNG.exists() else None,
                "rays_png_sha256": sha256(RAYS_PNG) if RAYS_PNG.exists() else None,
                "completed_utc": datetime.now(timezone.utc).isoformat(), "stdout": stdout, "stderr": stderr}
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if stdout: print(stdout, end="")
    if stderr: print(stderr, file=sys.stderr, end="")
    return rc

if __name__ == "__main__":
    raise SystemExit(main())
