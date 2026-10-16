"""Gmsh/OCC STEP partition and linear tetrahedra for controlled fracture cases.

This adapter produces geometry inputs. Volume tags are never fragment labels.
The caller supplies an initialized Gmsh module, keeping runtime installation and
process resource limits outside the reusable geometry API.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from .schema import package_file, validate_asset


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def partition_step_at_x(gmsh, asset_dir: str | Path, output_dir: str | Path, *,
                        mesh_size_m: float = .0015, max_tetrahedra: int = 150_000) -> dict:
    """Mesh a canonical STEP with a conformal x=center_x planar interface.

    The first application is a concentric hemispherical bowl. STEP import converts
    millimetres to solver metres while preserving analytic surfaces. A separate solver must
    subsequently establish interface damage and actual mechanical separation.
    """
    started = time.monotonic()
    root = Path(asset_dir).resolve(strict=True)
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    if not np.isfinite(mesh_size_m) or mesh_size_m <= 0 or max_tetrahedra <= 0:
        raise ValueError("mesh size and tetrahedron cap must be positive")
    validate_asset(root)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    spec = manifest["provenance"]["spec"]
    if spec.get("shape") != "concentric_lower_hemisphere":
        raise ValueError("this analytic audit currently supports concentric hemispherical bowls")
    ro, ri = float(spec["outer_radius_mm"]) / 1000, float(spec["inner_radius_mm"]) / 1000
    center = np.asarray(spec["center_xyz_mm"], dtype=float) / 1000
    exact_volume = 2 * np.pi / 3 * (ro**3 - ri**3)
    exact_area = np.pi / 2 * (ro**2 - ri**2)
    if 50 * exact_volume / mesh_size_m**3 > max_tetrahedra:
        raise ValueError("conservative mesh density forecast exceeds tetrahedron budget")
    source_step = package_file(root, manifest["geometry"]["solid_step"])
    gmsh.clear()
    gmsh.model.add("forge_conformal_bowl_partition")
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.option.setNumber("General.NumThreads", 1)
    # Import-unit conversion preserves spheres. A post-import OCC dilate can
    # replace analytic surfaces with B-splines and change numerical mass bounds.
    gmsh.option.setString("Geometry.OCCTargetUnit", "M")
    source = gmsh.model.occ.importShapes(str(source_step), highestDimOnly=True)
    volumes = [(dim, tag) for dim, tag in source if dim == 3]
    if len(volumes) != 1:
        raise ValueError("source STEP must contain one volume")
    source_volume = gmsh.model.occ.getMass(*volumes[0])
    span = 2 * ro
    # Rotate an XY rectangle into the YZ plane, then translate to the bowl center.
    plane = gmsh.model.occ.addRectangle(-span, -span, 0., 2 * span, 2 * span)
    gmsh.model.occ.rotate([(2, plane)], 0., 0., 0., 0., 1., 0., np.pi / 2)
    gmsh.model.occ.translate([(2, plane)], *center)
    _, parent_map = gmsh.model.occ.fragment(volumes, [(2, plane)])
    parts = sorted({tag for dim, tag in parent_map[0] if dim == 3})
    gmsh.model.occ.synchronize()
    if len(parts) != 2:
        raise ValueError(f"partition must create exactly two geometry volumes, got {len(parts)}")
    boundary_sets = [set(abs(tag) for dim, tag in gmsh.model.getBoundary([(3, part)], oriented=False)
                         if dim == 2) for part in parts]
    shared = sorted(boundary_sets[0] & boundary_sets[1])
    if not shared:
        raise ValueError("two source volumes have no conformal shared face")
    used_surfaces = set.union(*boundary_sets)
    orphan_surfaces = [(2, tag) for dim, tag in gmsh.model.getEntities(2) if tag not in used_surfaces]
    if orphan_surfaces:
        gmsh.model.occ.remove(orphan_surfaces, recursive=True)
        gmsh.model.occ.synchronize()
    part_volumes = [gmsh.model.occ.getMass(3, part) for part in parts]
    shared_area = sum(gmsh.model.occ.getMass(2, face) for face in shared)
    if not np.isclose(source_volume, exact_volume, rtol=1e-8, atol=1e-16):
        raise ValueError(f"imported OCC volume differs from analytic source: {source_volume} versus {exact_volume}")
    if not np.allclose(part_volumes, exact_volume / 2, rtol=1e-8, atol=1e-16):
        raise ValueError("partition volumes do not equal the analytic halves")
    if not np.isclose(shared_area, exact_area, rtol=1e-8, atol=1e-16):
        raise ValueError("conformal shared surface area differs from analytic half annulus")
    gmsh.model.addPhysicalGroup(3, parts, 1)
    gmsh.model.setPhysicalName(3, 1, "body")
    gmsh.model.addPhysicalGroup(2, shared, 2)
    gmsh.model.setPhysicalName(2, 2, "interface")
    exterior = sorted(used_surfaces - set(shared))
    gmsh.model.addPhysicalGroup(2, exterior, 3)
    gmsh.model.setPhysicalName(2, 3, "exterior")
    gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_size_m)
    gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_size_m)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
    gmsh.option.setNumber("Mesh.ElementOrder", 1)
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
    gmsh.option.setNumber("Mesh.Binary", 0)
    gmsh.model.mesh.generate(3)
    tags, coordinates, _ = gmsh.model.mesh.getNodes()
    xyz = np.asarray(coordinates, dtype=np.float64).reshape(-1, 3)
    node_tags = np.asarray(tags, dtype=np.int64)
    node_index = {int(tag): i for i, tag in enumerate(node_tags)}
    all_tets, cell_tags, owner = [], [], []
    for part in parts:
        types, element_tags, connectivity = gmsh.model.mesh.getElements(3, part)
        for kind, identifiers, nodes in zip(types, element_tags, connectivity, strict=True):
            if kind != 4:
                raise ValueError(f"expected linear tetrahedra only, got Gmsh type {kind}")
            local = np.asarray([[node_index[int(tag)] for tag in row]
                                for row in np.asarray(nodes).reshape(-1, 4)], dtype=np.int32)
            all_tets.append(local)
            cell_tags.extend(map(int, identifiers))
            owner.extend([part] * len(local))
    tets = np.concatenate(all_tets)
    if not 0 < len(tets) <= max_tetrahedra:
        raise ValueError(f"tetrahedron count outside budget: {len(tets)}")
    p = xyz[tets]
    determinant = np.einsum("ij,ij->i", p[:, 1] - p[:, 0], np.cross(p[:, 2] - p[:, 0], p[:, 3] - p[:, 0]))
    if np.any(determinant <= 0) or not np.isfinite(determinant).all():
        raise ValueError("mesh contains a nonpositive oriented tetrahedron")
    tet_volume = determinant / 6
    mesh_volume = float(tet_volume.sum())
    relative_error = abs(mesh_volume - exact_volume) / exact_volume
    if relative_error > .01:
        raise ValueError(f"tetrahedral volume differs from CAD by more than 1%: {relative_error}")
    faces_to_parents = defaultdict(list)
    for cell, row in enumerate(tets):
        for opposite in range(4):
            faces_to_parents[tuple(sorted(np.delete(row, opposite).tolist()))].append(cell)
    interface_triangles = []
    for face in shared:
        types, _, connectivity = gmsh.model.mesh.getElements(2, face)
        for kind, nodes in zip(types, connectivity, strict=True):
            if kind != 2:
                raise ValueError("interface must contain linear triangles")
            interface_triangles.extend([[node_index[int(tag)] for tag in row]
                                        for row in np.asarray(nodes).reshape(-1, 3)])
    triangles = np.asarray(interface_triangles, dtype=np.int32)
    parents = []
    owner = np.asarray(owner, dtype=np.int32)
    for row in triangles:
        adjacent = faces_to_parents[tuple(sorted(row.tolist()))]
        if len(adjacent) != 2 or owner[adjacent[0]] == owner[adjacent[1]]:
            raise ValueError("interface triangle lacks two distinct volume parents")
        parents.append(adjacent)
    tri_xyz = xyz[triangles]
    area = .5 * np.linalg.norm(np.cross(tri_xyz[:, 1] - tri_xyz[:, 0], tri_xyz[:, 2] - tri_xyz[:, 0]), axis=1)
    if not np.all(area > 0) or np.any(np.abs(tri_xyz[:, :, 0] - center[0]) > 1e-10):
        raise ValueError("interface triangles are degenerate or leave the declared plane")
    centroids = p.mean(axis=1)
    radius = np.linalg.norm(centroids - center, axis=1)
    inside = (radius >= ri) & (radius <= ro) & (centroids[:, 2] <= center[2] + 1e-12)
    if not inside.all():
        raise ValueError(f"{int((~inside).sum())} tetrahedron centroids leave analytic material")
    output.mkdir(parents=True, exist_ok=False)
    gmsh.write(str(output / "mesh.msh"))
    np.savez_compressed(output / "mesh.npz", nodes_m=xyz, tets=tets,
                        node_tags=node_tags, cell_tags=np.asarray(cell_tags),
                        source_partition_volume=owner, volume_m3=tet_volume,
                        interface_triangles=triangles, interface_parents=np.asarray(parents, dtype=np.int32))
    result = {
        "schema": "forge.conformal_tetra_partition.v1", "status": "GEOMETRY_DIAGNOSTIC_ONLY",
        "source_forge_manifest_sha256": _sha(manifest_path), "source_step_sha256": _sha(source_step),
        "units": "SI", "mesh_size_m": mesh_size_m, "nodes": len(xyz), "tetrahedra": len(tets),
        "step_unit_conversion": "Geometry.OCCTargetUnit=M at import; no post-import geometric dilation",
        "interface_triangles": len(triangles), "analytic_volume_m3": exact_volume,
        "occ_source_volume_m3": source_volume, "occ_partition_volumes_m3": part_volumes,
        "tetrahedral_volume_m3": mesh_volume, "tetrahedral_volume_relative_error": relative_error,
        "analytic_interface_area_m2": exact_area, "occ_interface_area_m2": shared_area,
        "triangular_interface_area_m2": float(area.sum()), "centroids_in_material": bool(inside.all()),
        "all_interface_triangles_have_two_distinct_volume_parents": True,
        "material_mass_kg": mesh_volume * manifest["material"]["mechanics"]["rho_kg_m3"],
        "elapsed_s": time.monotonic() - started,
        "limitations": ["linear boundary geometry is approximate; finite centroid checks are not a global containment certificate",
                        "predefined plane is geometry input, not a damage event or fragment partition",
                        "no material calibration, cohesive failure, dynamics, or R2 qualification"],
    }
    result["files"] = {name: {"sha256": _sha(output / name), "bytes": (output / name).stat().st_size}
                       for name in ("mesh.msh", "mesh.npz")}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
