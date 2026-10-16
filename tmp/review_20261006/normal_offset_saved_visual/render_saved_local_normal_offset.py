"""Render pinned outer jar controls and already-saved local normal-offset samples only."""
from __future__ import annotations
import hashlib, importlib.metadata, io, json, math, runpy, textwrap, time
from fractions import Fraction as F
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
PINS = HERE / "false_pins.json"
OUTER = ROOT / "vesselforge/tmp/review_20261006/curvature_constrained_meridian_20261006/curvature_constrained_meridian_result.json"
OFFSET = ROOT / "vesselforge/tmp/review_20261006/normal_offset_meridian_20261006/retry01_after_zprime_fix/normal_offset_meridian_result.json"
DRIVER = ROOT / "vesselforge/experiments/semantic_base_neck_bspline_20261006/semantic_base_neck_driver.py"
OUTPUT = HERE / "normal_offset_local_2d_preview.png"
RENDERER = Path(__file__).resolve()
LIMIT = 2 * 1024 * 1024


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bezier(poles: tuple[tuple[F, F], ...], t: F) -> tuple[F, F]:
    work = list(poles)
    while len(work) > 1:
        work = [tuple((1-t)*a+t*b for a,b in zip(work[i],work[i+1],strict=True)) for i in range(len(work)-1)]
    return work[0]


def main() -> None:
    started = time.monotonic()
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    if sha(RENDERER) != pins["renderer"]["sha256"]: raise ValueError("RENDERER_SOURCE_PIN_MISMATCH")
    if pins["render_authorization"]["root_render_only_go_received"] is not True:
        raise PermissionError("ROOT_RENDER_ONLY_GO_REQUIRED")
    if OUTPUT.exists() or pins["inputs"]["normal_offset_result"]["sha256"] is None:
        raise ValueError("ROOT_MUST_PIN_RESULT_SHA_AND_OUTPUT_MUST_BE_NEW")
    hashes = {"normal_offset_result":sha(OFFSET), "curvature_result":sha(OUTER), "frozen_driver":sha(DRIVER)}
    for name, digest in hashes.items():
        if digest != pins["inputs"][name]["sha256"]: raise ValueError("INPUT_PIN_MISMATCH_"+name)
    if hashes["curvature_result"] != "839c461cdf0dcae93f362ee7d80d0446cf52b6b1e1f04ed18842e17527673185":
        raise ValueError("CURVATURE_RESULT_PIN_MISMATCH")
    outer = json.loads(OUTER.read_text(encoding="utf-8")); result = json.loads(OFFSET.read_text(encoding="utf-8"))
    if outer["source_pins"]["frozen_inputs"]["driver_sha256"] != hashes["frozen_driver"]:
        raise ValueError("CURVATURE_DRIVER_PIN_MISMATCH")
    if result["status"] != "INNER_MERIDIAN_LOCAL_OFFSET_CANDIDATE" or result["scope"] != "jar_meridian_2d_only":
        raise ValueError("SAVED_RESULT_NOT_LOCAL_OFFSET_CANDIDATE")
    controls = tuple(tuple(F(str(v)) for v in p) for p in outer["families"]["jar"]["control_points_rz_mm"])
    extraction = runpy.run_path(str(DRIVER))["exact_bezier_extraction"]()
    if len(controls) != 17 or len(extraction) != 12 or len(result["spans"]) != 12:
        raise ValueError("SAVED_JAR_SPAN_SHAPE_MISMATCH")
    outer_xy, inner_xy = [], []
    for i, (block, row) in enumerate(zip(extraction, result["spans"], strict=True)):
        poles = tuple(tuple(sum((w[j]*controls[j][a] for j in range(17)), F(0)) for a in range(2)) for w in block)
        saved = tuple(tuple(F(str(v)) for v in p) for p in row["exact_bezier_controls_rz_mm"])
        if poles != saved: raise ValueError(f"SPAN_OUTER_CONTROLS_MISMATCH_{i}")
        outer_xy.extend(tuple(float(v) for v in bezier(poles, F(j,24))) for j in range(25))
        samples = row["true_normal_display_25"]
        if len(samples) != 25: raise ValueError(f"OFFSET_SAMPLE_COUNT_MISMATCH_{i}")
        for j, sample in enumerate(samples):
            if F(sample["u"]) != F(j,24) or sample["status"] != "FINITE_TRUE_NORMAL_OFFSET_SAMPLE":
                raise ValueError(f"OFFSET_DISPLAY_STATUS_MISMATCH_{i}_{j}")
            point = (float(sample["r_inner_mm"]), float(sample["z_inner_mm"]))
            if not all(math.isfinite(v) for v in point): raise ValueError("NONFINITE_OFFSET_DISPLAY")
            inner_xy.append(point)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(12,10), layout="constrained")
    grid = fig.add_gridspec(3,1,height_ratios=(.85,6,1.35))
    header = fig.add_subplot(grid[0]); header.axis("off")
    header.text(0,.95,textwrap.fill("LOCAL 2D TRUE-NORMAL INNER-MERIDIAN CANDIDATE — JAR, t=3 mm",58),va="top",fontsize=14,weight="bold")
    header.text(0,.28,textwrap.fill("Saved local result: "+result["status"]+"; inner trace is display-only.",60),va="top",fontsize=10)
    ax = fig.add_subplot(grid[1])
    ax.plot([p[0] for p in outer_xy],[p[1] for p in outer_xy],color="#245b91",lw=2,label="Saved outer meridian")
    ax.plot([p[0] for p in inner_xy],[p[1] for p in inner_xy],color="#cf6b2d",lw=1.8,label="Saved 3 mm inward-normal samples")
    all_xy = outer_xy + inner_xy; r=[p[0] for p in all_xy]; z=[p[1] for p in all_xy]
    pad=max(max(r)-min(r),max(z)-min(z))*.04
    ax.set(xlim=(min(0,min(r))-pad,max(r)+pad),ylim=(min(z)-pad,max(z)+pad),xlabel="radius r (mm)",ylabel="height z (mm)")
    ax.set_aspect("equal",adjustable="box"); ax.grid(alpha=.2); ax.legend(loc="upper right")
    footer = fig.add_subplot(grid[2]); footer.axis("off")
    note="\n".join(("GLOBAL WALL THICKNESS: UNKNOWN · NORMAL-STRIP GLOBAL INJECTIVITY: UNKNOWN",
                    "LIP CLOSURE: UNKNOWN · NATIVE B-REP: UNKNOWN · 3D / PHYSICS: UNKNOWN",
                    "12 spans × 25 saved inner samples; visualization only, not a certificate."))
    footer.text(0,1,note,va="top",fontsize=10,linespacing=1.4)
    buffer=io.BytesIO(); fig.savefig(buffer,format="png",dpi=130,metadata={"Title":"Local 2D normal-offset candidate only","Description":json.dumps(hashes)})
    plt.close(fig); image=buffer.getvalue()
    if len(image)>=LIMIT or time.monotonic()-started>=15: raise RuntimeError("RENDER_BUDGET_EXCEEDED")
    with OUTPUT.open("xb") as stream: stream.write(image)
    print(json.dumps({"png":str(OUTPUT),"bytes":len(image),"sha256":hashlib.sha256(image).hexdigest(),"pins":hashes},sort_keys=True))


if __name__ == "__main__": main()
