"""Render only the already-saved exact B-spline controls; no solve or CAD."""
from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from fractions import Fraction as F
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
EXPERIMENT = ROOT / "vesselforge" / "experiments" / "semantic_base_neck_bspline_20261006"
DRIVER = EXPERIMENT / "semantic_base_neck_driver.py"
CASES = EXPERIMENT / "fixed_cases.json"
RESULT = HERE / "minimum_jerk_candidate" / "semantic_minimum_jerk_result.json"
RESULT_SHA256 = "1e882451d691430c01653617e997b115291a10996e273434b7fd9c71ab787e11"
OUTPUT = HERE / "actual_saved_candidate_render_layout_fixed"
SAMPLES_PER_SPAN = 101
OUTPUT_CAP = 2 * 1024 * 1024


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def display_bezier(poles, t: float) -> tuple[float, float]:
    work = [[float(point[0]), float(point[1])] for point in poles]
    while len(work) > 1:
        work = [[(1.0 - t) * work[i][axis] + t * work[i + 1][axis]
                 for axis in range(2)] for i in range(len(work) - 1)]
    return work[0][0], work[0][1]


def screen_summary(geometry: dict) -> dict:
    counts: dict[str, int] = defaultdict(int)
    endpoint_witnesses: dict[str, dict] = {}
    for span in geometry["spans"]:
        status = span["radius_9mm_status"]
        counts[status] += 1
        if status != "POINT_COUNTEREXAMPLE_AT_SPAN_ENDPOINT":
            continue
        u0, u1 = span["u"]
        coefficients = span["P_R_degree24_coefficients"]
        for u, value in ((u0, coefficients[0]), (u1, coefficients[-1])):
            if F(value) < 0:
                row = endpoint_witnesses.setdefault(u, {"P_R_exact": value, "spans": []})
                if row["P_R_exact"] != value:
                    raise ValueError("SHARED_ENDPOINT_P_R_VALUES_DISAGREE")
                row["spans"].append(span["span"])
    return {
        "span_status_counts": dict(sorted(counts.items())),
        "unique_endpoint_witnesses": [
            {"u": u, "P_R_exact": row["P_R_exact"], "span_indices": row["spans"]}
            for u, row in sorted(endpoint_witnesses.items(), key=lambda pair: F(pair[0]))
        ],
    }


def main() -> int:
    if OUTPUT.exists():
        raise FileExistsError("RENDER_OUTPUT_EXISTS_REFUSING_OVERWRITE")
    if sha256(RESULT) != RESULT_SHA256:
        raise ValueError("SAVED_RESULT_HASH_MISMATCH")
    if sha256(DRIVER) != "038974cbbe3965f7f03f1ad0199d0aba00b56294840e411ca9a21fbde42466a3":
        raise ValueError("FROZEN_DRIVER_HASH_MISMATCH")
    if sha256(CASES) != "4e18dbeaecbf13a54a87b3f1409e1c0f7fe54c3606122a01880689d9e3a6a83c":
        raise ValueError("FROZEN_CASE_HASH_MISMATCH")
    sys.path.insert(0, str(EXPERIMENT))
    import semantic_base_neck_driver as driver
    OUTPUT.mkdir(parents=False, exist_ok=False)
    os.environ["MPLCONFIGDIR"] = str(OUTPUT)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    if result["status"] != "EXACT_CANDIDATE_REQUIRES_GEOMETRY_REVIEW":
        raise ValueError("UNEXPECTED_SAVED_RESULT_STATUS")
    extraction = driver.exact_bezier_extraction()
    if len(extraction) != 12:
        raise ValueError("EXPECTED_TWELVE_EXACT_BEZIER_SPANS")
    fig, axes = plt.subplots(1, 2, figsize=(12, 7), constrained_layout=False)
    colors = {"base": "#6d7785", "body": "#2864a5", "neck": "#c57a1c"}
    render_records = {}
    for ax, family in zip(axes, ("bowl", "jar"), strict=True):
        saved = result["cases"][family]
        controls = tuple(tuple(F(value) for value in point)
                         for point in saved["control_points_rz_mm"])
        if len(controls) != 17:
            raise ValueError("SAVED_CONTROL_COUNT_MISMATCH")
        spans = driver._controls_to_spans(extraction, controls)
        if len(spans) != 12:
            raise ValueError("EXACT_EXTRACTION_SPAN_COUNT_MISMATCH")
        for index, poles in enumerate(spans):
            color = colors["base"] if index == 0 else colors["neck"] if index == 11 else colors["body"]
            values = [display_bezier(poles, j / (SAMPLES_PER_SPAN - 1))
                      for j in range(SAMPLES_PER_SPAN)]
            ax.plot([p[0] for p in values], [p[1] for p in values], color=color,
                    linewidth=2.0, solid_capstyle="round")
        case, geom = cases[family], saved["geometry"]
        screen = screen_summary(geom)
        status = screen["span_status_counts"]
        passes = status.get("PROVED_R9_ON_CLOSED_NONFLAT_SPAN", 0)
        span_fails = status.get("POINT_COUNTEREXAMPLE_AT_SPAN_ENDPOINT", 0)
        unknown = status.get("UNKNOWN_NOT_CERTIFIED", 0)
        exclusions = status.get("EXCLUDED_STRAIGHT_MERIDIAN_BASE_OR_NECK", 0)
        feature = {row["name"]: row for row in geom["feature_checks"]}
        apex = tuple(float(F(v)) for v in feature["max_radius_apex"]["value_rz_mm"])
        ax.plot([apex[0]], [apex[1]], marker="o", color="#141414", markersize=4)
        ax.annotate("apex datum", xy=apex, xytext=(7, -12), textcoords="offset points", fontsize=8)
        ax.axvline(0.0, color="#777777", linewidth=0.7, linestyle="--")
        max_r = float(F(case["max_outer_radius_mm"]))
        mouth_z = float(F(case["mouth_z_mm"]))
        ax.set_xlim(-4, max_r + 10)
        ax.set_ylim(-4, mouth_z + 10)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("Meridian radius r (mm)")
        ax.set_ylabel("Height z (mm)")
        ax.set_title(f"{family.title()} outer meridian")
        ax.grid(True, color="#d9dde2", linewidth=0.45)
        unique = len(screen["unique_endpoint_witnesses"])
        detail = (f"R9 meridian: {passes} PASS | {span_fails} endpoint fails "
                  f"({unique} locations) | {unknown} UNKNOWN")
        detail2 = "Base/neck: straight meridians only; no inner, wall, or lip"
        if max(len(detail), len(detail2)) > 75:
            raise ValueError("PANEL_STATUS_LINE_EXCEEDS_75_CHARACTERS")
        ax.text(0.5, -0.22, detail + "\n" + detail2, transform=ax.transAxes,
                ha="center", va="top", fontsize=8, linespacing=1.35, clip_on=False)
        render_records[family] = {
            "exact_feature_checks": geom["all_features_exact"],
            "strict_point_checks": geom["all_strict_point_checks_pass"],
            "exact_C4": geom["all_C4"],
            "all_control_hulls_proved": geom["all_hulls_proved"],
            "all_span_regularities_proved": geom["all_spans_regular_proved"],
            "display_samples_per_span": SAMPLES_PER_SPAN,
            "display_sample_points": len(spans) * SAMPLES_PER_SPAN,
            "screen": screen,
            "label": detail,
            "label_line_2": detail2,
            "global_normal_wall": geom["global_normal_wall"],
            "inner_profile": geom["inner_profile"],
        }
    handles = [
        Line2D([0], [0], color=colors["base"], lw=2, label="Flat base meridian (span 0)"),
        Line2D([0], [0], color=colors["body"], lw=2, label="Body and shoulder (spans 1–10)"),
        Line2D([0], [0], color=colors["neck"], lw=2, label="Constant-radius neck meridian (span 11)"),
    ]
    fig.suptitle("Saved controls · outer meridians only · display sampling · equal-unit axes",
                 y=0.995, fontsize=12)
    fig.legend(handles=handles, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 0.94))
    fig.subplots_adjust(top=0.84, bottom=0.24, wspace=0.28)
    png = OUTPUT / "semantic_outer_meridians_equal_scale_layout_fixed.png"
    fig.savefig(png, dpi=120, facecolor="white")
    plt.close(fig)
    summary = {
        "status": "SAVED_RESULT_RENDER_ONLY",
        "saved_result_sha256": sha256(RESULT),
        "driver_sha256": sha256(DRIVER),
        "case_sha256": sha256(CASES),
        "control_count_each": 17,
        "exact_extracted_bezier_spans_each": 12,
        "display_samples_per_span": SAMPLES_PER_SPAN,
        "families": render_records,
        "png_path": str(png),
        "png_sha256": sha256(png),
        "png_size_bytes": png.stat().st_size,
        "output_cap_bytes": OUTPUT_CAP,
        "cad_or_solver": "NOT_RUN",
    }
    meta = OUTPUT / "render_summary.json"
    total_bytes = sum(path.stat().st_size for path in OUTPUT.iterdir() if path.is_file())
    summary["total_output_bytes"] = total_bytes
    summary["total_output_bytes"] = total_bytes + len((json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    if total_bytes > OUTPUT_CAP:
        raise ValueError("RENDER_OUTPUT_EXCEEDS_2MIB")
    meta.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if sum(path.stat().st_size for path in OUTPUT.iterdir() if path.is_file()) > OUTPUT_CAP:
        raise ValueError("RENDER_OUTPUT_EXCEEDS_2MIB")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
