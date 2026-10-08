#!/usr/bin/env python3
"""One-shot, read-only visual review of the frozen STEP geometry."""
from __future__ import annotations
import hashlib, json, math, os, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
RUN = ROOT / "vesselforge/experiments/smooth_surface_native_adapter_20261005/tmp/runs/single_inner_native_01"
STEP = RUN / "candidate.step"
RUN_RECEIPT = RUN / "run_receipt.json"
STEP_SHA = "9a6ac86efb2d714e5d2d737263307014487fe2e45979c4181f6071c6f0cf6c71"
RECEIPT_SHA = "4c17fe03c74a6fe4474d98b3de9305916572910247c64bd144189ca2c3f711c8"
MAX_VERTICES, MAX_FACES, WALL_SECONDS = 100_000, 200_000, 60
PNG = OUT / "native_cad_visual_2panel.png"
WORKER_DATA = OUT / "native_cad_visual_data.json"
MANIFEST = OUT / "native_cad_visual_run_manifest.json"
ATTEMPT_LOCK = OUT / "native_cad_visual_attempt.lock"

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def checked_receipt() -> tuple[str, dict]:
    step_sha, receipt_sha = sha256(STEP), sha256(RUN_RECEIPT)
    if step_sha != STEP_SHA or receipt_sha != RECEIPT_SHA:
        raise RuntimeError(f"frozen input hash mismatch: step={step_sha}, receipt={receipt_sha}")
    receipt = json.loads(RUN_RECEIPT.read_text(encoding="utf-8"))
    if receipt["native_step"]["step_sha256"] != STEP_SHA or receipt["run_id"] != "single_inner_native_01":
        raise RuntimeError("run receipt does not identify the frozen STEP/run")
    if receipt["budget"]["step_imports"] != 1 or receipt["budget"]["solver_runs"] != 0 or receipt["budget"]["normal_rays"] != 0:
        raise RuntimeError("source run receipt has unexpected import/solver/ray budget")
    return step_sha, receipt

def sample_actual_section(shape) -> tuple[list[dict], int]:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
    section = BRepAlgoAPI_Section(shape.wrapped, gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0)), True)
    section.Build()
    if not section.IsDone():
        raise RuntimeError("OCCT BRepAlgoAPI_Section(y=0) did not complete")
    explorer, curves = TopExp_Explorer(section.Shape(), TopAbs_EDGE), []
    while explorer.More():
        edge = TopoDS.Edge_s(explorer.Current())
        curve = BRepAdaptor_Curve(edge)
        first, last = float(curve.FirstParameter()), float(curve.LastParameter())
        if not math.isfinite(first) or not math.isfinite(last) or first == last:
            raise RuntimeError("section edge has non-finite or zero parameter interval")
        coords = []
        for i in range(101):
            p = curve.Value(first + (last - first) * i / 100)
            coords.append([float(p.X()), float(p.Y()), float(p.Z())])
        curves.append({"edge_index": len(curves), "sample_count": len(coords), "xyz_mm": coords})
        explorer.Next()
    if not curves:
        raise RuntimeError("OCCT y=0 section contains no actual B-rep edges")
    return curves, len(curves)

def worker() -> int:
    started = time.monotonic()
    data = {"status": "failure", "step_sha256": None, "run_receipt_sha256": None,
            "step_import_started": False, "step_import_completed": False,
            "brep_counts": {}, "tessellation": {"deflection_mm": 0.25, "angle_rad": 0.25},
            "section": {"plane": "y=0", "normal": [0, 1, 0], "sampling": "101 uniform parameter samples per actual OCCT section edge"}}
    rc = 2
    try:
        data["step_sha256"], receipt = checked_receipt()
        data["run_receipt_sha256"] = RECEIPT_SHA
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        import cadquery as cq
        from cadquery import importers

        data["step_import_started"] = True
        imported = importers.importStep(str(STEP))  # exactly one STEP import in this task
        data["step_import_completed"] = True
        shape = imported.val() if hasattr(imported, "val") else imported
        if shape is None or shape.wrapped.IsNull():
            raise RuntimeError("STEP import yielded a null shape")
        box = shape.BoundingBox()
        data["brep_counts"] = {"solids": len(shape.Solids()), "shells": len(shape.Shells()),
                               "faces": len(shape.Faces()), "edges": len(shape.Edges())}
        data["bbox_mm"] = {"xmin": box.xmin, "xmax": box.xmax, "ymin": box.ymin,
                           "ymax": box.ymax, "zmin": box.zmin, "zmax": box.zmax}
        data["source_run"] = {"run_id": receipt["run_id"], "source_receipt_status": receipt["status"],
                              "source_face_count": receipt["native_step"]["step_face_count"],
                              "normal_wall_status": receipt["normal_wall_status"],
                              "global_self_intersection_status": receipt["native_step"]["global_self_intersection_status"],
                              "physics_status": receipt["native_step"]["physics_status"]}
        curves, edge_count = sample_actual_section(shape)
        data["section"].update({"edge_count": edge_count, "curves": curves,
                                "sample_count": sum(c["sample_count"] for c in curves)})

        vertices, triangles = shape.tessellate(0.25, 0.25)
        nv, nf = len(vertices), len(triangles)
        data["tessellation"].update({"vertices": nv, "triangles": nf, "visualization_only": True})
        if nv > MAX_VERTICES or nf > MAX_FACES:
            data["status"] = "failure_cap_exceeded_no_retry"
            data["failure"] = f"tessellation cap exceeded: {nv} vertices / {nf} faces"
            rc = 3
        elif not nv or not nf:
            raise RuntimeError("OCCT tessellation returned an empty visualization proxy")
        else:
            xyz = np.asarray([[v.x, v.y, v.z] for v in vertices], dtype=np.float64)
            faces = np.asarray(triangles, dtype=np.int32)
            fig = plt.figure(figsize=(16, 8), dpi=120)
            ax = fig.add_subplot(1, 2, 1)
            for c in curves:
                pts = np.asarray(c["xyz_mm"], dtype=np.float64)
                ax.plot(pts[:, 0], pts[:, 2], color="#183b52", linewidth=1.15)
            ax.set_xlim(box.xmin, box.xmax); ax.set_ylim(box.zmin, box.zmax)
            ax.set_aspect("equal", adjustable="box")
            ax.set_xlabel("x (mm)"); ax.set_ylabel("z (mm)")
            ax.set_title("Actual B-rep section at y=0 · equal mm scale")
            ax.grid(True, linewidth=0.35, alpha=0.35)
            ax3 = fig.add_subplot(1, 2, 2, projection="3d")
            mesh = Poly3DCollection(xyz[faces], facecolor="#9fc4d3", edgecolor="#375563",
                                    linewidth=0.025, antialiased=True)
            ax3.add_collection3d(mesh)
            ax3.set_xlim(box.xmin, box.xmax); ax3.set_ylim(box.ymin, box.ymax)
            ax3.set_zlim(box.zmin, box.zmax)
            ax3.set_box_aspect((box.xlen, box.ylen, box.zlen))
            ax3.view_init(elev=28, azim=38)
            ax3.set_xlabel("x (mm)"); ax3.set_ylabel("y (mm)"); ax3.set_zlabel("z (mm)")
            ax3.set_title("Tessellated visualization proxy · 0.25 mm / 0.25 rad")
            fig.suptitle("VISUALIZATION ONLY — B-rep geometry, not a fracture/solver mesh", fontsize=15)
            fig.tight_layout(rect=(0, 0, 1, 0.95))
            fig.savefig(PNG, dpi=120, facecolor="white")
            plt.close(fig)
            data["status"], data["png"] = "success", PNG.name
            rc = 0
    except Exception as e:
        data["failure"] = f"{type(e).__name__}: {e}"
        rc = 2
    data["worker_elapsed_seconds"] = round(time.monotonic() - started, 3)
    WORKER_DATA.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"worker_status": data["status"], "failure": data.get("failure"),
                      "brep_counts": data.get("brep_counts"), "tessellation": data.get("tessellation")}, ensure_ascii=False))
    return rc

def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--worker":
        return worker()
    actual_argv = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]
    worker_argv = [sys.executable, str(Path(__file__).resolve()), "--worker"]
    rc, status, stdout, stderr = 2, "failure", "", ""
    try:
        with ATTEMPT_LOCK.open("x", encoding="utf-8") as lock:
            lock.write("single attempt consumed; no retries\n")
    except FileExistsError:
        print("one-shot visual review already attempted; refusing rerun", file=sys.stderr)
        return 5
    try:
        checked_receipt()
        if len(sys.argv) != 1:
            raise RuntimeError("no user arguments are accepted; all review inputs and budgets are frozen")
        proc = subprocess.run(worker_argv, cwd=str(ROOT), capture_output=True, text=True,
                              timeout=WALL_SECONDS, check=False)
        rc, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
        status = "success" if rc == 0 else ("failure_cap_exceeded_no_retry" if rc == 3 else "failure")
    except subprocess.TimeoutExpired as e:
        rc, status = 124, "failure_timeout_no_retry"
        stdout = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        stderr += f"\nworker exceeded hard {WALL_SECONDS}s wall-time limit; no retry"
    except Exception as e:
        rc, status, stderr = 2, "failure", f"{type(e).__name__}: {e}"
    worker_data = json.loads(WORKER_DATA.read_text(encoding="utf-8")) if WORKER_DATA.exists() else None
    manifest = {"status": status, "actual_argv": actual_argv, "worker_argv": worker_argv,
                "actual_rc": rc, "source_step": str(STEP), "source_step_sha256": STEP_SHA,
                "run_receipt": str(RUN_RECEIPT), "run_receipt_sha256": RECEIPT_SHA,
                "wall_time_limit_seconds": WALL_SECONDS, "proxy_limits": {"max_vertices": MAX_VERTICES,
                "max_faces": MAX_FACES, "deflection_mm": 0.25, "angle_rad": 0.25},
                "step_import_started_this_review": worker_data.get("step_import_started") if worker_data else None,
                "step_import_completed_this_review": worker_data.get("step_import_completed") if worker_data else None,
                "solver_runs": 0, "normal_rays": 0, "worker_data": worker_data,
                "stdout": stdout, "stderr": stderr,
                "png_sha256": sha256(PNG) if PNG.exists() else None,
                "completed_utc": datetime.now(timezone.utc).isoformat()}
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if stdout: print(stdout, end="")
    if stderr: print(stderr, file=sys.stderr, end="")
    return rc

if __name__ == "__main__":
    raise SystemExit(main())
