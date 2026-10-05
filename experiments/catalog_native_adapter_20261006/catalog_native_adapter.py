"""One bounded CadQuery/OCP pilot for existing VesselForge catalog profiles.

This experiment adapts the catalog's validated, piecewise-linear meridian to a
closed material section and revolves that section as-is. It does not modify the
production builder or fit, smooth, or otherwise tune the catalog geometry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Mapping, Sequence


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
VF_SOURCE_ROOT = REPO_ROOT / "vesselforge" / "src"
OUTPUT_ROOT = REPO_ROOT / "vesselforge" / "tmp" / "review_20261006" / "catalog_native_adapter_20261006"
RUNTIME = REPO_ROOT / "third_party" / "vesselforge-runtime" / "venv" / "Scripts" / "python.exe"
EXPECTED_RUNTIME_SHA256 = "2b83f3f84ea2f51132fa1aae73815be54126a799521de85ff6ea70627cde6da7"
CATALOG_SOURCE = VF_SOURCE_ROOT / "vesselforge" / "profile_catalog.py"
GEOMETRY_SOURCE = VF_SOURCE_ROOT / "vesselforge" / "geometry.py"
SMOOTH_ADAPTER_SOURCE = REPO_ROOT / "vesselforge" / "experiments" / "smooth_surface_native_adapter_20261005" / "native_adapter.py"
SOURCE_PATHS = {
    "profile_catalog": CATALOG_SOURCE,
    "geometry": GEOMETRY_SOURCE,
    "existing_smooth_native_adapter": SMOOTH_ADAPTER_SOURCE,
    "catalog_native_adapter": Path(__file__).resolve(),
    "vesselforge_python_runtime": RUNTIME,
}
ALLOWED_FAMILIES = ("bowl", "jar")
MAX_CASE_SECONDS = 38.0
MAX_PARENT_SECONDS = 85.0
MAX_CANDIDATE_BYTES = 10 * 1024 * 1024
STEP_TOLERANCE_MM = 1e-5


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _source_snapshot() -> dict[str, dict[str, str]]:
    snapshot: dict[str, dict[str, str]] = {}
    for name, path in SOURCE_PATHS.items():
        if not path.is_file():
            raise FileNotFoundError(f"PINNED_SOURCE_MISSING:{name}:{path}")
        snapshot[name] = {"path": str(path.relative_to(REPO_ROOT)), "sha256": _sha256(path)}
    if snapshot["vesselforge_python_runtime"]["sha256"] != EXPECTED_RUNTIME_SHA256:
        raise ValueError("PINNED_VF_RUNTIME_SHA256_MISMATCH")
    return snapshot


def _cross(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_intersect(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float],
    distance_epsilon: float, cross_epsilon: float,
) -> bool:
    def on_segment(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> bool:
        return (
            min(p[0], q[0]) - distance_epsilon <= r[0] <= max(p[0], q[0]) + distance_epsilon
            and min(p[1], q[1]) - distance_epsilon <= r[1] <= max(p[1], q[1]) + distance_epsilon
            and abs(_cross(p, q, r)) <= cross_epsilon
        )

    ab_c, ab_d = _cross(a, b, c), _cross(a, b, d)
    cd_a, cd_b = _cross(c, d, a), _cross(c, d, b)
    if ((ab_c > cross_epsilon and ab_d < -cross_epsilon) or (ab_c < -cross_epsilon and ab_d > cross_epsilon)) and (
        (cd_a > cross_epsilon and cd_b < -cross_epsilon) or (cd_a < -cross_epsilon and cd_b > cross_epsilon)
    ):
        return True
    return (
        (abs(ab_c) <= cross_epsilon and on_segment(a, b, c))
        or (abs(ab_d) <= cross_epsilon and on_segment(a, b, d))
        or (abs(cd_a) <= cross_epsilon and on_segment(c, d, a))
        or (abs(cd_b) <= cross_epsilon and on_segment(c, d, b))
    )


def validate_profile_input(family: str, profile: Any) -> dict[str, Any]:
    """Purely validate and serialize one catalog profile without altering it."""
    if family not in ALLOWED_FAMILIES:
        raise ValueError(f"PILOT_FAMILY_NOT_ALLOWED:{family!r}")
    if getattr(profile, "family", None) != family or getattr(profile, "units", None) != "mm":
        raise ValueError("PROFILE_FAMILY_OR_UNITS_MISMATCH")
    params = getattr(profile, "parameters", None)
    if not isinstance(params, Mapping) or not params:
        raise ValueError("PROFILE_PARAMETERS_MISSING")
    for key, value in params.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"PROFILE_PARAMETER_INVALID:{key}")
    qualification = getattr(profile, "geometry_only_qualification", None)
    if not isinstance(qualification, Mapping):
        raise ValueError("PROFILE_QUALIFICATION_MISSING")
    if (
        qualification.get("status") != "GEOMETRY_ONLY_CANDIDATE"
        or qualification.get("real_vessel_match") != "NOT_VALIDATED"
        or qualification.get("material_or_physical_qualification") != "NOT_VALIDATED"
        or "radial meridian offset" not in str(qualification.get("wall_declaration_interpretation", ""))
    ):
        raise ValueError("PROFILE_QUALIFICATION_SCOPE_CHANGED")

    outer = tuple(tuple(float(v) for v in point) for point in profile.outer_profile_mm)
    inner = tuple(tuple(float(v) for v in point) for point in profile.inner_profile_mm)
    section = tuple(tuple(float(v) for v in point) for point in profile.closed_material_section_mm)
    if len(outer) < 4 or len(inner) < 3 or len(section) < 8:
        raise ValueError("PROFILE_POINT_COUNT_INVALID")
    for name, points in (("outer", outer), ("inner", inner), ("section", section)):
        for index, point in enumerate(points):
            if len(point) != 2 or any(not math.isfinite(v) for v in point) or point[0] < 0.0 or point[1] < 0.0:
                raise ValueError(f"PROFILE_POINT_INVALID:{name}:{index}")
    expected_section = outer + (inner[-1],) + tuple(reversed(inner[:-1]))
    if section != expected_section:
        raise ValueError("PROFILE_CLOSED_SECTION_DOES_NOT_MATCH_CATALOG_PROFILES")
    if outer[0] != (0.0, 0.0) or inner[0] != (0.0, float(params["base_thickness_declaration_mm"])):
        raise ValueError("PROFILE_AXIS_OR_BASE_DATUM_INVALID")
    if abs(max(z for _, z in section) - float(params["height_mm"])) > 1e-10:
        raise ValueError("PROFILE_HEIGHT_DOES_NOT_MATCH_DECLARED_PARAMETER")
    if abs(max(r for r, _ in outer) - float(params["max_radius_mm"])) > 1e-10:
        raise ValueError("PROFILE_RADIUS_DOES_NOT_MATCH_DECLARED_PARAMETER")

    extent = max(float(params["height_mm"]), float(params["max_radius_mm"]), 1.0)
    dist_eps, cross_eps = extent * 1e-12, extent * extent * 1e-12
    edge_count = len(section)
    edges = list(zip(section, section[1:] + section[:1]))
    for i, (a, b) in enumerate(edges):
        if (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 <= dist_eps**2:
            raise ValueError(f"PROFILE_SECTION_ZERO_LENGTH_EDGE:{i}")
        for j in range(i + 1, edge_count):
            if j == i + 1 or (i == 0 and j == edge_count - 1):
                continue
            c, d = edges[j]
            if _segments_intersect(a, b, c, d, dist_eps, cross_eps):
                raise ValueError(f"PROFILE_SECTION_SELF_INTERSECTION:{i}:{j}")
    signed_area = sum(
        section[i][0] * section[(i + 1) % len(section)][1]
        - section[(i + 1) % len(section)][0] * section[i][1]
        for i in range(len(section))
    ) / 2.0
    if not math.isfinite(signed_area) or signed_area <= cross_eps:
        raise ValueError("PROFILE_SECTION_ORIENTATION_OR_AREA_INVALID")
    return {
        "profile": profile.to_dict(),
        "profile_canonical_sha256": _canonical_sha256(profile.to_dict()),
        "section_signed_area_mm2": signed_area,
        "section_points_count": len(section),
        "section_edge_count": len(edges),
        "native_input": "closed_material_section_mm passed as an unchanged polyline; no curve fitting or smoothing",
    }


def _catalog_defaults(family: str) -> dict[str, Any]:
    if str(VF_SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(VF_SOURCE_ROOT))
    from vesselforge.profile_catalog import build_profile

    profile = build_profile(family)
    return {"profile_object": profile, **validate_profile_input(family, profile)}


def _bounds(shape: Any) -> list[float]:
    box = shape.BoundingBox()
    return [float(box.xmin), float(box.xmax), float(box.ymin), float(box.ymax), float(box.zmin), float(box.zmax)]


def _validate_native_shape(shape: Any, phase: str, family: str, profile: Any) -> dict[str, Any]:
    solids, shells = shape.Solids(), shape.Shells()
    volume = float(shape.Volume())
    if (
        shape.isNull() or not shape.isValid() or len(solids) != 1 or len(shells) != 1
        or not bool(shells[0].Closed()) or not solids[0].isValid()
        or not math.isfinite(volume) or volume <= 0.0
    ):
        raise ValueError(f"{phase}_NOT_ONE_VALID_CLOSED_POSITIVE_SOLID")

    expected_radius = float(profile.parameters["max_radius_mm"])
    expected_height = float(profile.parameters["height_mm"])
    bounds = _bounds(shape)
    expected = [-expected_radius, expected_radius, -expected_radius, expected_radius, 0.0, expected_height]
    delta = max(abs(a - b) for a, b in zip(bounds, expected))
    if delta > STEP_TOLERANCE_MM:
        raise ValueError(f"{phase}_BOUNDS_PARAMETER_MISMATCH:{delta:.12g}mm")

    # Probe the axial cavity and a point halfway through one sloped material wall.
    cavity_z = float(profile.parameters["base_thickness_declaration_mm"]) + 0.5 * (
        expected_height - float(profile.parameters["base_thickness_declaration_mm"])
    )
    outer = profile.outer_profile_mm
    i = 3
    r0, z0 = outer[i]
    r1, z1 = outer[i + 1]
    wall = float(profile.parameters["wall_thickness_declaration_mm"])
    material_probe = ((r0 + r1) / 2.0 - wall / 2.0, (z0 + z1) / 2.0)
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.TopAbs import TopAbs_IN
    from OCP.gp import gp_Pnt

    solid = solids[0].wrapped
    cavity_is_inside = BRepClass3d_SolidClassifier(solid, gp_Pnt(0.0, 0.0, cavity_z), 1e-7).State() == TopAbs_IN
    wall_is_inside = BRepClass3d_SolidClassifier(
        solid, gp_Pnt(material_probe[0], 0.0, material_probe[1]), 1e-7
    ).State() == TopAbs_IN
    if cavity_is_inside:
        raise ValueError(f"{phase}_CAVITY_PROBE_IS_FILLED:{family}")
    if not wall_is_inside:
        raise ValueError(f"{phase}_MATERIAL_WALL_PROBE_IS_EMPTY:{family}")
    return {
        "phase": phase,
        "is_valid": bool(shape.isValid()),
        "solid_count": len(solids),
        "shell_count": len(shells),
        "all_shells_closed": all(bool(shell.Closed()) for shell in shells),
        "volume_mm3": volume,
        "bbox_mm_xmin_xmax_ymin_ymax_zmin_zmax": bounds,
        "expected_bbox_mm_xmin_xmax_ymin_ymax_zmin_zmax": expected,
        "max_bbox_parameter_delta_mm": delta,
        "cavity_probe_point_mm": [0.0, 0.0, cavity_z],
        "cavity_probe_is_inside_solid": cavity_is_inside,
        "wall_material_probe_point_mm": [material_probe[0], 0.0, material_probe[1]],
        "wall_material_probe_is_inside_solid": wall_is_inside,
    }


def _face_inventory(shape: Any, phase: str) -> list[dict[str, Any]]:
    result = []
    for index, face in enumerate(shape.Faces()):
        box = face.BoundingBox()
        center = face.Center().toTuple()
        values = [float(v) for v in center] + [
            float(box.xmin), float(box.xmax), float(box.ymin), float(box.ymax), float(box.zmin), float(box.zmax),
            float(face.Area()),
        ]
        if not all(math.isfinite(v) for v in values):
            raise ValueError(f"{phase}_FACE_INVENTORY_NONFINITE:{index}")
        result.append({
            "index_zero_based": index,
            "geom_type": str(face.geomType()),
            "center_mm": [float(v) for v in center],
            "bbox_mm_xmin_xmax_ymin_ymax_zmin_zmax": values[3:9],
            "area_mm2": values[-1],
            "face_source_scope": "native OCC 360-degree revolution of the catalog meridian section; per-section-edge face correspondence is not asserted",
        })
    if not result:
        raise ValueError(f"{phase}_FACE_INVENTORY_EMPTY")
    return result


def _native_visual(shape: Any, output_path: Path, family: str, profile: Any) -> dict[str, Any]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    import cadquery as cq
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

    plane = gp_Pln(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 1.0, 0.0))
    section_builder = BRepAlgoAPI_Section(shape.wrapped, plane, True)
    if hasattr(section_builder, "IsDone") and not section_builder.IsDone():
        raise ValueError("NATIVE_BREP_SECTION_OPERATION_FAILED")
    section_shape = cq.Shape.cast(section_builder.Shape())
    section_edges = section_shape.Edges()
    if not section_edges:
        raise ValueError("NATIVE_BREP_SECTION_HAS_NO_EDGES")

    fig = plt.figure(figsize=(12.5, 6.5), dpi=130, facecolor="#f8f6f0")
    left = fig.add_subplot(1, 2, 1)
    right = fig.add_subplot(1, 2, 2, projection="3d")
    for edge in section_edges:
        try:
            points, _ = edge.sample(24)
        except Exception:
            points = [vertex.Center() for vertex in edge.Vertices()]
        if len(points) < 2:
            continue
        xs = [float(point.x) for point in points]
        ys = [float(point.z) for point in points]
        plane_error = max(abs(float(point.y)) for point in points)
        if plane_error > STEP_TOLERANCE_MM:
            raise ValueError(f"NATIVE_BREP_SECTION_LEFT_PLANE:{plane_error:.12g}mm")
        left.plot(xs, ys, color="#304a62", linewidth=1.5)
    left.set_title("OCC planar section of STEP BRep (y = 0)", fontsize=11)
    left.set_xlabel("x (mm)")
    left.set_ylabel("z (mm)")
    left.set_aspect("equal", adjustable="box")
    left.grid(True, color="#d9d5cb", linewidth=0.55)
    left.set_xlim(-float(profile.parameters["max_radius_mm"]) * 1.15, float(profile.parameters["max_radius_mm"]) * 1.15)
    left.set_ylim(-3.0, float(profile.parameters["height_mm"]) * 1.06)

    vertices, triangles = shape.tessellate(0.30, 0.16)
    if not vertices or not triangles:
        raise ValueError("NATIVE_BREP_TESSELLATION_FOR_VISUAL_EMPTY")
    vertex_rows = [[float(v.x), float(v.y), float(v.z)] for v in vertices]
    triangle_rows = [[int(a), int(b), int(c)] for a, b, c in triangles]
    mesh = Poly3DCollection(
        [[vertex_rows[index] for index in tri] for tri in triangle_rows],
        facecolor="#c99c61", edgecolor="#513f2a", linewidths=0.10, alpha=0.99,
    )
    right.add_collection3d(mesh)
    radius = float(profile.parameters["max_radius_mm"])
    height = float(profile.parameters["height_mm"])
    right.set_xlim(-radius * 1.05, radius * 1.05)
    right.set_ylim(-radius * 1.05, radius * 1.05)
    right.set_zlim(0.0, height * 1.03)
    right.set_box_aspect((2.0 * radius, 2.0 * radius, height))
    right.view_init(elev=31, azim=-55)
    right.set_title("STEP-roundtripped native BRep (display tessellation)", fontsize=11)
    right.set_xlabel("x (mm)", labelpad=-2)
    right.set_ylabel("y (mm)", labelpad=-2)
    right.set_zlabel("z (mm)", labelpad=1)
    fig.suptitle(f"VesselForge catalog {family} default — segmented analytic candidate", fontsize=14, y=0.98)
    fig.text(
        0.5, 0.012,
        "Visualization only • piecewise-linear profile • no smoothness, normal-wall, real-style, or physical qualification",
        ha="center", fontsize=8, color="#5e5a52",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return {
        "path": str(output_path),
        "bytes": output_path.stat().st_size,
        "source_shape": "STEP-roundtripped CadQuery/OCP BRep",
        "section_plane": "global y=0 plane through global Z revolve axis",
        "section_edge_count": len(section_edges),
        "display_tessellation_vertex_count": len(vertex_rows),
        "display_tessellation_triangle_count": len(triangle_rows),
        "display_tessellation_is_deliverable_mesh": False,
    }


def _native_case(family: str, output_dir: Path) -> dict[str, Any]:
    started = time.monotonic()
    receipt: dict[str, Any] = {
        "schema": "vesselforge.catalog_native_adapter.case_receipt/1",
        "family": family,
        "status": "RUNNING",
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "units": "mm",
        "coordinate_frame": "right-handed global Z-up; catalog (radius_mm,z_mm) mapped to the CadQuery XZ workplane and revolved about global Z",
        "construction": "closed_material_section_mm passed to CadQuery Workplane(XZ).polyline().close().revolve(360); no fitting or smoothing",
        "smoothness_claim": "NOT_CLAIMED; input is a piecewise-linear profile",
        "normal_wall_status": "UNKNOWN_NOT_CHECKED; catalog wall declaration is a constant radial meridian offset, not a measured or global normal minimum",
        "real_vessel_match": "NOT_VALIDATED",
        "material_or_physical_qualification": "NOT_VALIDATED",
        "retry_count": 0,
    }
    try:
        if family not in ALLOWED_FAMILIES:
            raise ValueError(f"PILOT_FAMILY_NOT_ALLOWED:{family!r}")
        if output_dir.exists() and any(output_dir.iterdir()):
            raise FileExistsError("CASE_OUTPUT_ALREADY_HAS_ARTIFACTS_NO_OVERWRITE_OR_RETRY")
        output_dir.mkdir(parents=True, exist_ok=True)
        from vesselforge.profile_catalog import build_profile

        profile = build_profile(family)
        validated = validate_profile_input(family, profile)
        receipt.update({
            "catalog_schema": validated["profile"]["schema"],
            "catalog_profile_sha256": validated["profile_canonical_sha256"],
            "catalog_profile": validated["profile"],
            "pure_adapter_validation": {
                key: value for key, value in validated.items() if key not in ("profile", "profile_canonical_sha256")
            },
        })
        _write_json(output_dir / "catalog_profile_input.json", validated["profile"])

        import OCP
        import cadquery as cq

        section = [tuple(float(v) for v in point) for point in profile.closed_material_section_mm]
        body = (
            cq.Workplane("XZ")
            .polyline(section)
            .close()
            .revolve(360.0, (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), combine=False)
            .val()
        )
        native = _validate_native_shape(body, "NATIVE_REVOLVE", family, profile)
        native["face_inventory"] = _face_inventory(body, "NATIVE_REVOLVE")
        step_path = output_dir / "candidate.step"
        cq.exporters.export(body, str(step_path), exportType="STEP")
        if not step_path.is_file() or step_path.stat().st_size <= 0:
            raise ValueError("STEP_EXPORT_MISSING_OR_EMPTY")
        if step_path.stat().st_size > MAX_CANDIDATE_BYTES:
            raise ValueError("STEP_EXCEEDS_10_MIB_ARTIFACT_CAP")
        canonical = cq.importers.importStep(str(step_path)).val()
        roundtrip = _validate_native_shape(canonical, "STEP_ROUNDTRIP", family, profile)
        bbox_delta = max(abs(a - b) for a, b in zip(
            native["bbox_mm_xmin_xmax_ymin_ymax_zmin_zmax"],
            roundtrip["bbox_mm_xmin_xmax_ymin_ymax_zmin_zmax"],
        ))
        volume_delta = abs(native["volume_mm3"] - roundtrip["volume_mm3"])
        volume_delta_limit = max(1e-4, native["volume_mm3"] * 1e-7)
        if bbox_delta > STEP_TOLERANCE_MM or volume_delta > volume_delta_limit:
            raise ValueError(f"STEP_ROUNDTRIP_IDENTITY_FAILURE:bbox={bbox_delta:.12g};volume={volume_delta:.12g}")
        roundtrip["face_inventory"] = _face_inventory(canonical, "STEP_ROUNDTRIP")
        roundtrip["bbox_delta_from_native_mm"] = bbox_delta
        roundtrip["volume_delta_from_native_mm3"] = volume_delta
        roundtrip["volume_delta_limit_mm3"] = volume_delta_limit
        image_path = output_dir / "native_brep_section_and_3d.png"
        visual = _native_visual(canonical, image_path, family, profile)
        receipt.update({
            "status": "PASS_NATIVE_CAD_STEP_AND_CAVITY_CHECK_ONLY",
            "cadquery_version": str(cq.__version__),
            "ocp_version": str(getattr(OCP, "__version__", "")) or None,
            "native_brep": native,
            "step": {
                "path": str(step_path),
                "bytes": step_path.stat().st_size,
                "sha256": _sha256(step_path),
                "roundtrip": roundtrip,
                "geometry_identity_status": "PASS_BBOX_AND_VOLUME_TOLERANCE_ONLY",
            },
            "native_brep_visual": visual,
        })
    except Exception as exc:
        receipt.update({
            "status": "FAIL_OR_UNKNOWN_NATIVE_CAD_PILOT",
            "failure_type": type(exc).__name__,
            "failure_reason": str(exc),
            "traceback": traceback.format_exc(),
        })
    receipt["elapsed_seconds"] = round(time.monotonic() - started, 6)
    receipt["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_json(output_dir / "native_case_receipt.json", receipt)
    return receipt


def _tree_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _run_pilot() -> int:
    start = time.monotonic()
    if not RUNTIME.is_file():
        raise FileNotFoundError(f"PINNED_VF_RUNTIME_MISSING:{RUNTIME}")
    run_dir = OUTPUT_ROOT / "pilot_01"
    if run_dir.exists():
        raise FileExistsError("PILOT_OUTPUT_ALREADY_EXISTS_NO_RETRY_OR_OVERWRITE")
    run_dir.mkdir(parents=True)
    source_before = _source_snapshot()
    _write_json(run_dir / "PRE_RUN_SOURCE_PINS.json", source_before)
    cases: list[dict[str, Any]] = []
    overall_failure: str | None = None

    # Pure catalog generation and validation are complete before either native subprocess starts.
    try:
        pure_inputs = {family: _catalog_defaults(family) for family in ALLOWED_FAMILIES}
        _write_json(run_dir / "PURE_ADAPTER_INPUT_VALIDATION.json", {
            "status": "PASS_CATALOG_DEFAULTS_AND_UNCHANGED_SECTIONS_VALIDATED",
            "families": {
                family: {
                    "profile_canonical_sha256": item["profile_canonical_sha256"],
                    "profile": item["profile"],
                    "section_signed_area_mm2": item["section_signed_area_mm2"],
                    "section_points_count": item["section_points_count"],
                    "section_edge_count": item["section_edge_count"],
                }
                for family, item in pure_inputs.items()
            },
        })
    except Exception as exc:
        overall_failure = f"PURE_ADAPTER_VALIDATION_FAILED:{type(exc).__name__}:{exc}"
        _write_json(run_dir / "PURE_ADAPTER_INPUT_VALIDATION.json", {
            "status": "FAIL_PURE_ADAPTER_INPUT_VALIDATION",
            "failure_type": type(exc).__name__,
            "failure_reason": str(exc),
            "traceback": traceback.format_exc(),
        })
        pure_inputs = {}

    if overall_failure is None:
        for family in ALLOWED_FAMILIES:
            elapsed = time.monotonic() - start
            remaining = MAX_PARENT_SECONDS - elapsed
            case_dir = run_dir / f"{family}_default"
            if remaining <= 2.0:
                receipt = {
                    "family": family,
                    "status": "NOT_STARTED_PARENT_WALL_BUDGET_EXHAUSTED",
                    "elapsed_seconds": 0.0,
                    "retry_count": 0,
                }
                _write_json(case_dir / "native_case_receipt.json", receipt)
                cases.append(receipt)
                continue
            timeout = min(MAX_CASE_SECONDS, remaining - 1.0)
            child_env = dict(os.environ)
            child_env["MPLBACKEND"] = "Agg"
            child_env["MPLCONFIGDIR"] = str(case_dir / "matplotlib_config")
            command = [
                str(RUNTIME), "-B", str(Path(__file__).resolve()),
                "--native-case", family, "--output-dir", str(case_dir),
            ]
            launched = time.monotonic()
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(REPO_ROOT),
                    env=child_env,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
                child_elapsed = time.monotonic() - launched
                receipt_path = case_dir / "native_case_receipt.json"
                if receipt_path.is_file():
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                else:
                    receipt = {
                        "family": family,
                        "status": "FAIL_OR_UNKNOWN_CHILD_RETURNED_WITHOUT_RECEIPT",
                        "elapsed_seconds": round(child_elapsed, 6),
                        "retry_count": 0,
                    }
                receipt["child_return_code"] = int(completed.returncode)
                receipt["child_stdout"] = completed.stdout[-6000:]
                receipt["child_stderr"] = completed.stderr[-6000:]
                if completed.returncode != 0 and receipt.get("status", "").startswith("PASS_"):
                    receipt["status"] = "FAIL_OR_UNKNOWN_CHILD_RETURN_CODE"
                if _tree_bytes(case_dir) > MAX_CANDIDATE_BYTES:
                    receipt["status"] = "FAIL_CANDIDATE_ARTIFACT_BUDGET_EXCEEDED"
                    receipt["artifact_bytes"] = _tree_bytes(case_dir)
                else:
                    receipt["artifact_bytes"] = _tree_bytes(case_dir)
            except subprocess.TimeoutExpired as exc:
                child_elapsed = time.monotonic() - launched
                receipt = {
                    "family": family,
                    "status": "FAIL_PER_CASE_TIMEOUT_NO_RETRY",
                    "timeout_seconds": timeout,
                    "elapsed_seconds": round(child_elapsed, 6),
                    "retry_count": 0,
                    "child_stdout": (exc.stdout or "")[-6000:],
                    "child_stderr": (exc.stderr or "")[-6000:],
                }
                _write_json(case_dir / "native_case_receipt.json", receipt)
            cases.append(receipt)

    source_after = _source_snapshot()
    _write_json(run_dir / "POST_RUN_SOURCE_PINS.json", source_after)
    sources_unchanged = source_before == source_after
    if not sources_unchanged:
        overall_failure = "PINNED_SOURCES_CHANGED_DURING_PILOT"
    all_pass = len(cases) == len(ALLOWED_FAMILIES) and all(
        row.get("status") == "PASS_NATIVE_CAD_STEP_AND_CAVITY_CHECK_ONLY" for row in cases
    )
    elapsed_total = time.monotonic() - start
    if elapsed_total > MAX_PARENT_SECONDS:
        overall_failure = "PARENT_WALL_BUDGET_EXCEEDED"
    manifest = {
        "schema": "vesselforge.catalog_native_adapter.pilot_manifest/1",
        "status": "PASS_TWO_DEFAULT_CATALOG_NATIVE_CANDIDATES" if all_pass and overall_failure is None else "FAIL_OR_UNKNOWN_PILOT",
        "run_id": "pilot_01",
        "families": list(ALLOWED_FAMILIES),
        "catalog": "vesselforge.profile_catalog.build_profile(family) using its default parameters",
        "source_pins_before": source_before,
        "source_pins_after": source_after,
        "all_pinned_sources_unchanged": sources_unchanged,
        "frame": "right-handed Z-up; meridian radius maps to global X in Workplane XZ; revolve axis is global Z",
        "units": "mm",
        "geometry_preservation": "closed_material_section_mm is passed unchanged as a polyline; no smoothing, fitting, corner rounding, refinement, or parameter tuning",
        "wall_declaration_semantics": "preserved from catalog: constant radial meridian offset at corresponding control heights; not a global minimum normal wall and not a measured wall thickness",
        "base_declaration_semantics": "preserved from catalog: inner floor datum is base_thickness_declaration_mm above outside floor datum",
        "face_source": "native OCC faces are inventoried from the revolved catalog closed material section; each face records actual STEP/native geometry type, bounds, center, and area; no one-to-one segment-to-face mapping is claimed",
        "not_qualified": {
            "C2_or_smooth_profile": "NOT_CLAIMED; catalog generator is piecewise linear",
            "smooth_normal_wall": "NOT_CHECKED; global minimum normal wall is UNKNOWN",
            "real_style_or_vessel_match": "NOT_VALIDATED",
            "material_or_physical_qualification": "NOT_VALIDATED",
            "mesh_or_solver_validation": "NOT_RUN",
        },
        "budget": {
            "native_candidates_max": 2,
            "one_candidate_per_family": True,
            "per_case_timeout_seconds_max": MAX_CASE_SECONDS,
            "parent_wall_seconds_max": MAX_PARENT_SECONDS,
            "step_exports_per_candidate": 1,
            "step_imports_per_candidate": 1,
            "retries_or_tuning": 0,
            "artifact_bytes_per_candidate_max": MAX_CANDIDATE_BYTES,
        },
        "cases": cases,
        "elapsed_total_seconds": round(elapsed_total, 6),
        "overall_failure_reason": overall_failure,
    }
    _write_json(run_dir / "pilot_manifest.json", manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0 if manifest["status"] == "PASS_TWO_DEFAULT_CATALOG_NATIVE_CANDIDATES" else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-case", choices=ALLOWED_FAMILIES)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if args.native_case:
        if args.output_dir is None:
            parser.error("--output-dir is required with --native-case")
        sys.dont_write_bytecode = True
        if str(VF_SOURCE_ROOT) not in sys.path:
            sys.path.insert(0, str(VF_SOURCE_ROOT))
        result = _native_case(args.native_case, args.output_dir.resolve())
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("status") == "PASS_NATIVE_CAD_STEP_AND_CAVITY_CHECK_ONLY" else 1
    try:
        return _run_pilot()
    except Exception as exc:
        print(json.dumps({
            "status": "BLOCKED_BEFORE_NATIVE_PILOT",
            "failure_type": type(exc).__name__,
            "failure_reason": str(exc),
            "traceback": traceback.format_exc(),
        }, indent=2, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
