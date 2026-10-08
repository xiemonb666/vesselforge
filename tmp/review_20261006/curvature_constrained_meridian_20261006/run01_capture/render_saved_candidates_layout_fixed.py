"""Render only the pinned saved controls as a geometry-only PNG; never optimize or certify."""
from __future__ import annotations
import hashlib, io, json, runpy, time
import importlib.metadata
import textwrap
from fractions import Fraction as F
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
REVIEW = Path(__file__).resolve().parents[1]
RESULT = REVIEW / "curvature_constrained_meridian_result.json"
DRIVER = ROOT / "vesselforge" / "experiments" / "semantic_base_neck_bspline_20261006" / "semantic_base_neck_driver.py"
SOURCE = ROOT / "vesselforge" / "experiments" / "curvature_constrained_meridian_20261006" / "curvature_constrained_meridian.py"
OUTDIR = REVIEW / "run01_capture" / "render_only_saved_layout_fixed_01"
PNG, MANIFEST = OUTDIR / "saved_meridian_geometry_preview.png", OUTDIR / "render_manifest.json"
RESULT_SHA256 = "839c461cdf0dcae93f362ee7d80d0446cf52b6b1e1f04ed18842e17527673185"; LIMIT = 2 * 1024 * 1024


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bezier_point(poles: tuple[tuple[F, F], ...], t: F) -> tuple[F, F]:
    work = list(poles)
    while len(work) > 1:
        work = [tuple((1-t)*a+t*b for a,b in zip(work[i],work[i+1],strict=True)) for i in range(len(work)-1)]
    return work[0]


def summarize(row: dict) -> str:
    cert = row["exact_geometry_certificate"]
    spans = cert["spans"]; statuses = [s["radius_9mm_status"] for s in spans]
    coeffs = [c for s in spans for c in s["P_R_degree24_coefficients"]]
    codes = {"proved":"PROVED_R9_ON_CLOSED_NONFLAT_SPAN", "endpoint":"POINT_COUNTEREXAMPLE_AT_SPAN_ENDPOINT",
             "unknown":"UNKNOWN_NOT_CERTIFIED", "excluded":"EXCLUDED_STRAIGHT_MERIDIAN_BASE_OR_NECK"}
    count = {k: statuses.count(v) for k, v in codes.items()}
    negative = sum(F(str(c)) < 0 for c in coeffs)
    lines = [f"CURVATURE — R9 proved {count['proved']}; endpoint counterexamples {count['endpoint']}; "
             f"unknown {count['unknown']}; straight exclusions {count['excluded']}.",
             f"P_R degree-24 Bernstein: {len(coeffs)} exact coefficients; {negative} negative.",
             f"C4 joins {sum(all(j['derivative_orders_0_to_4_equal']) for j in cert['joins'])}/11; "
             f"features exact {sum(x['exact'] for x in cert['feature_checks'])}/5; "
             f"hulls {sum(s['hull_poles_within_bbox'] for s in spans)}/12; "
             f"regular spans {sum(s['open_span_regular'] for s in spans)}/12.",
             f"UNKNOWN inner profile: {cert['inner_profile']}.",
             f"UNKNOWN global normal wall: {cert['global_normal_wall']}."]
    return "\n".join(textwrap.fill(line, width=74, break_long_words=False) for line in lines)


def main() -> None:
    started = time.monotonic()
    if sha(RESULT) != RESULT_SHA256 or PNG.exists() or MANIFEST.exists():
        raise ValueError("RESULT_HASH_MISMATCH_OR_RENDER_OUTPUT_ALREADY_EXISTS")
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    pins = result["source_pins"]
    driver_sha, source_sha = sha(DRIVER), sha(SOURCE)
    if driver_sha != pins["frozen_inputs"]["driver_sha256"] or source_sha != pins["implementation"]["sha256"]:
        raise ValueError("FROZEN_DRIVER_OR_IMPLEMENTATION_HASH_MISMATCH")
    if result["families"]["bowl"]["promotion_status"] != "EXACTFAIL_NOT_PROMOTED":
        raise ValueError("SAVED_BOWL_STATUS_DIFFERS_FROM_REVIEWED_RESULT")
    jar = result["families"]["jar"]
    if jar["optimizer_status"]["success"] or not all(jar["exact_geometry_certificate"][k] for k in ("all_C4","all_features_exact","all_hulls_proved","all_spans_regular_proved")):
        raise ValueError("SAVED_JAR_STATUS_DIFFERS_FROM_REVIEWED_RESULT")
    ns = runpy.run_path(str(DRIVER)); extraction = ns["exact_bezier_extraction"]()
    if len(extraction) != 12:
        raise ValueError("EXPECTED_12_FROZEN_SPANS")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(15.5, 10.5), layout="constrained")
    fig.suptitle("GEOMETRY-ONLY SAVED-CONTROLS PREVIEW — not physics-ready or style-calibrated", fontsize=14)
    grid = fig.add_gridspec(1, 2, wspace=.12)
    for col, family in enumerate(("bowl", "jar")):
        row = result["families"][family]
        controls = tuple(tuple(F(str(v)) for v in p) for p in row["control_points_rz_mm"])
        if len(controls) != 17 or len(row["alpha_exact_decimal_fraction"]) != 15: raise ValueError(f"INCOMPLETE_SAVED_CONTROLS:{family}")
        points = []
        for block in extraction:
            poles = tuple(tuple(sum((w[i]*controls[i][a] for i in range(17)), F(0)) for a in range(2)) for w in block)
            points.extend(bezier_point(poles, F(j,24)) for j in range(25))
        cell = grid[0, col].subgridspec(3, 1, height_ratios=(.8, 5, 2.1), hspace=.05)
        header = fig.add_subplot(cell[0]); header.axis("off")
        title = "BOWL — GEOMETRY FAIL" if family == "bowl" else "JAR — EXACT GEOMETRY GATES TRUE"
        status = ("Exact R9, hull, and open-span regularity gates fail; saved controls remain unpromoted."
                  if family == "bowl" else "SLSQP did not converge; exact saved-curve gates pass; geometry-only candidate.")
        header.text(0, .95, title, va="top", fontsize=12, weight="bold")
        header.text(0, .38, textwrap.fill(status, width=60), va="top", fontsize=10)
        ax = fig.add_subplot(cell[1])
        ax.plot([float(p[0]) for p in points], [float(p[1]) for p in points], color="#245b91", lw=2)
        ax.axvline(0, color="#888", lw=.8, ls="--")
        ax.set(xlim=(0, max(float(p[0]) for p in points)*1.05),
               ylim=(min(float(p[1]) for p in points), max(float(p[1]) for p in points)*1.04),
               xlabel="radius r (mm)", ylabel="height z (mm)")
        ax.set_aspect("equal", adjustable="box")
        ax.grid(alpha=.2)
        box = fig.add_subplot(cell[2]); box.axis("off")
        box.text(0, 1, summarize(row), va="top", fontsize=9, family="monospace", linespacing=1.35)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=130, metadata={"Title":"Geometry-only meridian preview"})
    plt.close(fig)
    png = buffer.getvalue()
    metadata = {"schema":"geometry_only_render.v1", "result_sha256":sha(RESULT),
                "driver_sha256":driver_sha, "implementation_sha256":source_sha,
                "matplotlib_version":importlib.metadata.version("matplotlib"),
                "families":["bowl", "jar"], "spans_per_family":12, "display_points_per_span":25,
                "claim":"saved-controls geometry preview only; no optimizer, CAD, field, or physical claim"}
    encoded = (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode()
    if len(png) + len(encoded) >= LIMIT or time.monotonic() - started >= 20:
        raise RuntimeError("RENDER_OUTPUT_OR_TIME_BUDGET_EXCEEDED")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    with PNG.open("xb") as stream:
        stream.write(png)
    with MANIFEST.open("xb") as stream:
        stream.write(encoded)
    print(json.dumps({"png":str(PNG), "manifest":str(MANIFEST), "png_bytes":len(png), "pins":metadata}, sort_keys=True))


if __name__ == "__main__": main()
