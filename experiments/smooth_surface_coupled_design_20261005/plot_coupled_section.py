"""Plot one frozen pure-math RZ section; this script never creates CAD geometry."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import coupled_profile_math as profile


CASE_FILE = Path(__file__).with_name("fixed_case_beaker_coupled_v2.json")
EXPECTED_CURVATURE_SAMPLES = 1001
EXPECTED_RAY_SAMPLES = 101
PLOT_SAMPLES_PER_SPAN = 501
LEGACY_V1_UNKNOWN_XYZ_MM = (13.565030591, -9.063863664, 4.531738447)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _role_group(role: str) -> tuple[str, str]:
    if role == "outer_underside":
        return "Outer underside", "#253c78"
    if role.startswith("outer_base_fairing:"):
        return "Outer base fairing", "#4267ac"
    if role.startswith("outer_side:"):
        return "Outer wall", "#168c83"
    if role == "rounded_lip_bridge":
        return "Rounded lip", "#dc7f22"
    if role.startswith("inner_side:"):
        return "Inner wall", "#8f61a8"
    if role.startswith("inner_base_fairing:"):
        return "Inner base fairing", "#bc5473"
    if role == "inner_floor":
        return "Inner floor", "#59636e"
    if role == "axis_closure":
        return "Axis closure", "#9a9a9a"
    raise ValueError(f"unrecognized section role: {role}")


def build_plot(report_path: Path, output_dir: Path) -> tuple[Path, Path]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    case = json.loads(CASE_FILE.read_text(encoding="utf-8"))
    if report.get("candidate_id") != case.get("candidate_id"):
        raise ValueError("diagnostic report candidate does not match the fixed case")
    if report.get("cad_or_step_run") is not False:
        raise ValueError("this plot accepts only the frozen pure-math report")
    if report.get("curvature_sampling", {}).get("samples_per_span") != EXPECTED_CURVATURE_SAMPLES:
        raise ValueError("expected exactly 1001 curvature samples per span")
    if report.get("finite_normal_ray_diagnostic", {}).get("ray_samples_per_outer_span") != EXPECTED_RAY_SAMPLES:
        raise ValueError("expected exactly 101 normal-ray samples per eligible span")

    png_path = output_dir / "coupled_profile_rz.png"
    arrays_path = output_dir / "coupled_profile_rz_arrays.json"
    if png_path.exists() or arrays_path.exists():
        raise FileExistsError("refusing to overwrite an existing plot or sampled-array artifact")
    output_dir.mkdir(parents=True, exist_ok=True)

    model = profile.build_model(case)
    parameters = np.linspace(0.0, 1.0, PLOT_SAMPLES_PER_SPAN, dtype=np.float64)
    sampled: list[dict[str, Any]] = []
    point_by_role: dict[str, np.ndarray] = {}
    for span in model["ordered_section"]:
        points = profile._bezier_many(profile._float_controls(span), parameters)
        label, color = _role_group(span.role)
        sampled.append(
            {
                "span_role": span.role,
                "display_role": label,
                "parameter_samples": parameters.tolist(),
                "rz_mm": points.tolist(),
            }
        )
        point_by_role[span.role] = points

    ray_rows = report["finite_normal_ray_diagnostic"]["all_rows"]
    measured = [row for row in ray_rows if row.get("status") == "MEASURED_CANDIDATE_INNER_BOUNDARY_DISTANCE"]
    if not measured:
        raise ValueError("frozen report has no measured candidate inner-boundary ray to plot")
    min_ray = min(measured, key=lambda row: row["first_positive_inner_boundary_hit"]["distance_mm"])
    source_rz = [float(value) for value in min_ray["point_rz_mm"]]
    hit_rz = [float(value) for value in min_ray["first_positive_inner_boundary_hit"]["hit_rz_mm"]]
    legacy_r = float(np.hypot(LEGACY_V1_UNKNOWN_XYZ_MM[0], LEGACY_V1_UNKNOWN_XYZ_MM[1]))

    arrays_payload = {
        "schema": "vesselforge.smooth_surface_coupled_design.rz_plot_arrays/0.1.0",
        "candidate_id": case["candidate_id"],
        "units": "mm",
        "coordinate_order": ["radius", "z"],
        "source_sha256": _sha256(Path(profile.__file__).resolve()),
        "fixed_case_sha256": _sha256(CASE_FILE),
        "diagnostic_report_sha256": _sha256(report_path),
        "sampling": {"plot_samples_per_span": PLOT_SAMPLES_PER_SPAN},
        "sampled_spans": sampled,
        "sampled_ray_min_candidate_inner_boundary_hit": {
            "source_span": min_ray["source_span"],
            "source_t": min_ray["t"],
            "distance_mm": min_ray["first_positive_inner_boundary_hit"]["distance_mm"],
            "source_rz_mm": source_rz,
            "hit_rz_mm": hit_rz,
            "interpretation": "finite 2D section-generator candidate inner-boundary distance; not a material interval, surface-normal wall, or global minimum",
        },
        "legacy_v1_classifier_unknown": {
            "xyz_mm": list(LEGACY_V1_UNKNOWN_XYZ_MM),
            "rz_mm": [legacy_r, LEGACY_V1_UNKNOWN_XYZ_MM[2]],
            "interpretation": "historical native-classifier UNKNOWN from v1; not tested on or transferred to v2",
        },
    }
    arrays_path.write_text(json.dumps(arrays_payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    fig, ax = plt.subplots(figsize=(7.5, 12.0), constrained_layout=True)
    labeled: set[str] = set()
    for span in model["ordered_section"]:
        label, color = _role_group(span.role)
        points = point_by_role[span.role]
        ax.plot(
            points[:, 0],
            points[:, 1],
            color=color,
            linewidth=2.0,
            label=label if label not in labeled else "_nolegend_",
        )
        labeled.add(label)

    ax.plot(
        [source_rz[0], hit_rz[0]],
        [source_rz[1], hit_rz[1]],
        color="#111111",
        linestyle="--",
        linewidth=1.25,
        marker="o",
        markersize=3,
        label="Smallest sampled 2D inner-boundary candidate",
    )
    ax.scatter([legacy_r], [LEGACY_V1_UNKNOWN_XYZ_MM[2]], marker="x", color="#ba3030", s=45, zorder=5, label="Legacy v1 classifier UNKNOWN")
    ax.annotate(
        "v1 native classifier UNKNOWN\nnot tested on v2",
        xy=(legacy_r, LEGACY_V1_UNKNOWN_XYZ_MM[2]),
        xytext=(27.0, 19.0),
        arrowprops={"arrowstyle": "->", "color": "#ba3030", "linewidth": 0.8},
        color="#762020",
        fontsize=8,
    )

    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-2.0, 45.0)
    ax.set_ylim(-2.0, 115.0)
    ax.set_xlabel("Radius r (mm)")
    ax.set_ylabel("Height z (mm)")
    ax.set_title("Fixed beaker coupled section — pure mathematical RZ profile\n110 mm is rim endpoint; symmetric lip crest = 112.1875 mm")
    ax.grid(True, color="#d7dce2", linewidth=0.55)
    ax.legend(loc="upper right", fontsize=7.5, framealpha=0.94)
    fig.savefig(png_path, dpi=180)
    plt.close(fig)
    return png_path, arrays_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="frozen 1001/101 pure-math diagnostic JSON")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    png_path, arrays_path = build_plot(args.report, args.output_dir)
    print(json.dumps({"png": str(png_path), "arrays": str(arrays_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
