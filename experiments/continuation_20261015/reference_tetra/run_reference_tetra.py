from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
VF = REPO / "vesselforge"
V5 = VF / "experiments" / "continuation_20261015" / "reference_forms" / "outputs" / "daily_aberdeen_108x53_v5"
STEP = V5 / "geometry" / "solid.step"
SECTION = V5 / "geometry" / "section.json"
FACE_LINEAGE = V5 / "geometry" / "face_lineage.json"
GEOMETRY_REPORT = V5 / "geometry_report.json"
OUTPUT = HERE / "daily_aberdeen_v5_diagnostic"
GMSH_LIB = REPO / "third_party" / "pgfrag-geometry-runtime" / "sdk" / "gmsh-4.15.2-Windows64-sdk" / "lib"

sys.path.insert(0, str(VF / "src"))
sys.path.insert(0, str(GMSH_LIB))

from vesselforge.step_partition import ResourceCaps, partition_step_at_x


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _arc_points(points: list[list[float]], samples: int) -> list[list[float]]:
    start, middle, end = [tuple(map(float, point)) for point in points]
    ax, ay = start
    bx, by = middle
    cx, cy = end
    determinant = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(determinant) < 1e-14:
        raise ValueError("meridian arc control points are collinear")
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    center_x = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / determinant
    center_y = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / determinant
    start_angle = math.atan2(ay - center_y, ax - center_x)
    middle_angle = math.atan2(by - center_y, bx - center_x)
    end_angle = math.atan2(cy - center_y, cx - center_x)
    ccw_middle = (middle_angle - start_angle) % (2.0 * math.pi)
    ccw_end = (end_angle - start_angle) % (2.0 * math.pi)
    sweep = ccw_end if ccw_middle <= ccw_end + 1e-12 else ccw_end - 2.0 * math.pi
    radius = math.hypot(ax - center_x, ay - center_y)
    return [
        [center_x + radius * math.cos(start_angle + sweep * i / samples),
         center_y + radius * math.sin(start_angle + sweep * i / samples)]
        for i in range(samples)
    ]


def meridian_area_mm2(section: dict, samples_per_curve: int = 4096) -> float:
    """Numerically integrate the positive-radius closed section boundary."""
    points: list[list[float]] = []
    for segment in section["segments"]:
        controls = [[float(a), float(b)] for a, b in segment["points_rz_mm"]]
        curve = segment["curve"]
        if curve == "line":
            sampled = controls[:1]
        elif curve == "bezier":
            degree = len(controls) - 1
            sampled = []
            for index in range(samples_per_curve):
                t = index / samples_per_curve
                weights = [
                    math.comb(degree, j) * ((1.0 - t) ** (degree - j)) * (t ** j)
                    for j in range(degree + 1)
                ]
                sampled.append([
                    sum(weights[j] * controls[j][axis] for j in range(degree + 1))
                    for axis in range(2)
                ])
        elif curve == "arc":
            sampled = _arc_points(controls, samples_per_curve)
        else:
            raise ValueError(f"unsupported meridian curve type {curve!r}")
        points.extend(sampled)
    twice_area = 0.0
    for index, point in enumerate(points):
        following = points[(index + 1) % len(points)]
        twice_area += point[0] * following[1] - following[0] * point[1]
    area = abs(twice_area) / 2.0
    if not math.isfinite(area) or area <= 0:
        raise ValueError("meridian section has nonpositive area")
    return area


def main() -> None:
    if not GMSH_LIB.is_dir():
        raise FileNotFoundError(f"Gmsh SDK not found: {GMSH_LIB}")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(GMSH_LIB))
    import gmsh

    section = json.loads(SECTION.read_text(encoding="utf-8"))
    geometry = json.loads(GEOMETRY_REPORT.read_text(encoding="utf-8"))
    expected_volume_m3 = geometry["measurements"]["independent_meridian_integral_volume_mm3"] * 1e-9
    expected_section_area_m2 = meridian_area_mm2(section) * 1e-6
    caps = ResourceCaps(
        max_step_bytes=32 * 1024 * 1024,
        max_tetrahedra=100_000,
        max_memory_bytes=2 * 1024**3,
        max_source_faces=250,
        tetrahedra_per_volume_cell=10.0,
    )
    gmsh.initialize()
    try:
        result = partition_step_at_x(
            gmsh,
            STEP,
            _sha256(STEP),
            OUTPUT,
            resource_caps=caps,
            plane_x_m=0.0,
            expected_volume_m3=expected_volume_m3,
            expected_meridian_section_area_m2=expected_section_area_m2,
            mesh_size_m=0.0015,
            source_face_metadata=FACE_LINEAGE,
        )
    finally:
        gmsh.finalize()
    print(json.dumps({
        "status": result["status"],
        "output": str(OUTPUT),
        "source_step_sha256": result["source_step_sha256"],
        "source_step_declared_length_unit": result["source_step_declared_length_unit"],
        "counts": result["counts"],
        "source_volume_m3": result["cad"]["source_volume_m3"],
        "tetrahedral_volume_m3": result["mesh"]["tetrahedral_volume_m3"],
        "cad_mesh_volume_relative_error": result["mesh"]["cad_mesh_volume_relative_error"],
        "shared_area_m2": result["cad"]["shared_area_m2"],
        "expected_complete_cut_area_m2": result["cad"]["expected_complete_cut_area_m2"],
        "source_face_ancestry": result["source_face_ancestry"],
        "elapsed_s": result["elapsed_s"],
    }, indent=2))


if __name__ == "__main__":
    main()
