"""Low-resolution, geometry-only OCC revolve check for new catalog profiles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cadquery as cq
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ROOT = Path(r"C:\Users\xiemo\Desktop\ShardForge")
REVIEW = ROOT / "vesselforge" / "tmp" / "review_20261004" / "profile_catalog"
MESH_DIR = REVIEW / "meshes"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def signed_mesh_volume(vertices: np.ndarray, faces: np.ndarray) -> float:
    a = vertices[faces[:, 0]]
    b = vertices[faces[:, 1]]
    c = vertices[faces[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def mesh_topology(vertices: np.ndarray, faces: np.ndarray, weld_tolerance_mm: float = 1e-5) -> dict[str, int | bool]:
    keys = np.rint(vertices / weld_tolerance_mm).astype(np.int64)
    remap_by_key: dict[tuple[int, int, int], int] = {}
    remap = np.empty(len(vertices), dtype=np.int64)
    for index, key_array in enumerate(keys):
        key = tuple(int(value) for value in key_array)
        mapped = remap_by_key.get(key)
        if mapped is None:
            mapped = len(remap_by_key)
            remap_by_key[key] = mapped
        remap[index] = mapped
    welded_faces = remap[faces]
    degenerate_triangles = int(sum(len(set(map(int, triangle))) != 3 for triangle in welded_faces))
    edge_counts: dict[tuple[int, int], int] = {}
    for a, b, c in welded_faces:
        for left, right in ((int(a), int(b)), (int(b), int(c)), (int(c), int(a))):
            edge = (min(left, right), max(left, right))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    boundary_edges = sum(count == 1 for count in edge_counts.values())
    nonmanifold_edges = sum(count != 2 for count in edge_counts.values())
    return {
        "welded_vertices": len(remap_by_key),
        "triangles": int(len(welded_faces)),
        "degenerate_triangles": degenerate_triangles,
        "boundary_edges": int(boundary_edges),
        "nonmanifold_edges": int(nonmanifold_edges),
        "watertight_edge_incidence": boundary_edges == 0 and nonmanifold_edges == 0 and degenerate_triangles == 0,
    }


def main() -> int:
    MESH_DIR.mkdir(parents=True, exist_ok=True)
    inputs_path = REVIEW / "mesh_inputs.json"
    receipt_path = REVIEW / "mesh_preflight_receipt.json"
    frozen_inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if sha256(inputs_path) != receipt["locked_inputs_sha256"]:
        raise ValueError("frozen mesh input hash mismatch; no OCC operation started")
    for relative, expected_hash in receipt["locked_source_sha256"].items():
        if sha256(ROOT / relative) != expected_hash:
            raise ValueError(f"locked source changed before OCC operation: {relative}")

    items: list[dict[str, object]] = []
    figure = plt.figure(figsize=(10, 4), constrained_layout=True)
    colors = {"bowl": "#bf8f55", "beaker": "#799eb5", "jar": "#a67e91"}

    for index, frozen_profile in enumerate(frozen_inputs["profiles"], start=1):
        family = frozen_profile["family"]
        params = frozen_profile["parameters"]
        outline = [tuple(point) for point in frozen_profile["closed_material_section_mm"]]
        solid = (
            cq.Workplane("XZ")
            .polyline(outline)
            .close()
            .revolve(360.0, (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), combine=False)
            .val()
        )
        solid_volume = float(solid.Volume())
        if not solid.isValid() or len(solid.Solids()) != 1 or len(solid.Shells()) != 1 or solid_volume <= 0.0:
            raise ValueError(f"{family} did not form one valid positive-volume OCC solid")

        vertices_raw, faces_raw = solid.tessellate(0.5, 0.2)
        vertices = np.asarray([point.toTuple() for point in vertices_raw], dtype=np.float64)
        faces = np.asarray(faces_raw, dtype=np.int64)
        if vertices.ndim != 2 or vertices.shape[1] != 3 or faces.ndim != 2 or faces.shape[1] != 3:
            raise ValueError(f"{family} OCC tessellation returned malformed arrays")
        mesh_volume = signed_mesh_volume(vertices, faces)
        if not np.isfinite(mesh_volume) or mesh_volume <= 0.0:
            raise ValueError(f"{family} mesh signed volume must be positive; received {mesh_volume}")
        topology = mesh_topology(vertices, faces)

        stl_path = MESH_DIR / f"{family}.stl"
        cq.exporters.export(
            solid,
            str(stl_path),
            exportType="STL",
            tolerance=0.5,
            angularTolerance=0.2,
        )
        bbox = solid.BoundingBox()
        item = {
            "family": family,
            "profile_parameters": params,
            "solid_valid": bool(solid.isValid()),
            "solid_count": len(solid.Solids()),
            "shell_count": len(solid.Shells()),
            "solid_volume_mm3": solid_volume,
            "bounds_mm": {
                "x": float(bbox.xlen),
                "y": float(bbox.ylen),
                "z": float(bbox.zlen),
            },
            "mesh_vertices": int(len(vertices)),
            "mesh_triangles": int(len(faces)),
            "mesh_signed_volume_mm3": mesh_volume,
            "mesh_signed_volume_relative_delta": (mesh_volume - solid_volume) / solid_volume,
            "mesh_signed_volume_matches_occ_within_1pct": bool(
                -0.01 <= (mesh_volume - solid_volume) / solid_volume <= 0.01
            ),
            "mesh_topology": topology,
            "mesh_tessellation_request": {"linear_deflection_mm": 0.5, "angular_tolerance_rad": 0.2},
            "stl": f"meshes/{stl_path.name}",
            "stl_sha256": sha256(stl_path),
        }
        if not item["mesh_signed_volume_matches_occ_within_1pct"]:
            raise ValueError(f"{family} mesh signed volume differs from OCC solid by more than 1 percent")
        items.append(item)

        axes = figure.add_subplot(1, 3, index, projection="3d")
        triangles = vertices[faces]
        axes.add_collection3d(
            Poly3DCollection(
                triangles,
                facecolors=colors[family],
                edgecolors="#333333",
                linewidths=0.12,
                alpha=1.0,
            )
        )
        radius = params["max_radius_mm"]
        height = params["height_mm"]
        axes.set_xlim(-radius * 1.08, radius * 1.08)
        axes.set_ylim(-radius * 1.08, radius * 1.08)
        axes.set_zlim(0.0, height)
        axes.set_box_aspect((1.0, 1.0, height / (2.0 * radius)))
        axes.view_init(elev=20, azim=35)
        axes.set_title(family.capitalize())
        axes.set_xlabel("x mm", labelpad=-2)
        axes.set_ylabel("y mm", labelpad=-2)
        axes.set_zlabel("z mm", labelpad=-2)
        axes.tick_params(labelsize=6, pad=0)

    figure.suptitle(
        "GEOMETRY-ONLY CANDIDATE PREVIEW · 0.5 mm coarse tessellation · no wall/curvature/solver qualification",
        fontsize=9,
        fontweight="bold",
    )
    png_path = REVIEW / "candidate_profiles_mesh.png"
    figure.savefig(png_path, dpi=140)
    plt.close(figure)
    report = {
        "schema": "vesselforge.profile_catalog.mesh_review/0.1.0",
        "profile_catalog_schema": frozen_inputs["profile_catalog_schema"],
        "status": "PASS_GEOMETRY_ONLY_CANDIDATE_MESHES",
        "backend": {"name": "CadQuery/OpenCascade", "cadquery_version": cq.__version__},
        "scope": "three frozen default profile meridians revolved once each and tessellated at low resolution",
        "frozen_input_sha256": receipt["locked_inputs_sha256"],
        "locked_source_sha256": receipt["locked_source_sha256"],
        "tessellation_notice": "0.5 mm linear deflection is for coarse vessel form preview; it does not qualify thin walls, curvature, or solver readiness.",
        "qualification": {
            "real_vessel_match": "NOT_VALIDATED",
            "material_or_physical_qualification": "NOT_VALIDATED",
            "historical_type_validation": "NOT_VALIDATED",
            "solver_used": False,
        },
        "mesh_plot": {"path": png_path.name, "sha256": sha256(png_path)},
        "items": items,
    }
    report_path = REVIEW / "candidate_meshes.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "items": items, "report": str(report_path), "plot": str(png_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
