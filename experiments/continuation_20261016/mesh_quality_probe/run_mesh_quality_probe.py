from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

sys.dont_write_bytecode = True

import numpy as np


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SOURCE_DIR = (
    REPO
    / "vesselforge"
    / "experiments"
    / "continuation_20261015"
    / "reference_tetra"
    / "daily_aberdeen_v5_diagnostic"
)
SOURCE_MSH = SOURCE_DIR / "mesh.msh"
SOURCE_NPZ = SOURCE_DIR / "mesh.npz"
SOURCE_REPORT = SOURCE_DIR / "result.json"
OUTPUT_JSON = HERE / "mesh_quality_probe.json"
CANDIDATE_DIR = HERE / "candidates"
GMSH_LIB = (
    REPO
    / "third_party"
    / "pgfrag-geometry-runtime"
    / "sdk"
    / "gmsh-4.15.2-Windows64-sdk"
    / "lib"
)
VF_SOURCE = REPO / "vesselforge" / "src"

MAX_TETRAHEDRA = 100_000
MAX_MEMORY_BYTES = 2 * 1024**3
MAX_RUN_SECONDS = 75.0
MAX_TOTAL_SECONDS = 285.0
OPTIMIZERS = {
    "gmsh_default": {"method": "", "force": True},
    "gmsh_default_unforced": {"method": "", "force": False},
    "netgen": {"method": "Netgen", "force": True},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def summary(values: np.ndarray) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "min": float(np.min(array)),
        "p1": float(np.percentile(array, 1)),
        "p5": float(np.percentile(array, 5)),
        "median": float(np.median(array)),
        "p95": float(np.percentile(array, 95)),
        "max": float(np.max(array)),
    }


def load_gmsh() -> tuple[Any, Any]:
    if not GMSH_LIB.is_dir():
        raise FileNotFoundError(f"Gmsh SDK library not found: {GMSH_LIB}")
    dll_handle = os.add_dll_directory(str(GMSH_LIB)) if hasattr(os, "add_dll_directory") else None
    sys.path.insert(0, str(GMSH_LIB))
    import gmsh  # type: ignore[import-not-found]

    return gmsh, dll_handle


def source_inputs() -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    report = json.loads(SOURCE_REPORT.read_text(encoding="utf-8"))
    with np.load(SOURCE_NPZ) as source:
        arrays = {name: source[name].copy() for name in source.files}
    return report, arrays


def _physical_entities(gmsh: Any, dimension: int, wanted_name: str) -> tuple[int, ...]:
    for group_dimension, group_tag in gmsh.model.getPhysicalGroups(dimension):
        if gmsh.model.getPhysicalName(group_dimension, group_tag) == wanted_name:
            return tuple(
                sorted(
                    int(tag)
                    for tag in gmsh.model.getEntitiesForPhysicalGroup(group_dimension, group_tag)
                )
            )
    raise ValueError(f"physical group {wanted_name!r} is missing in the source MSH")


def _elements_for_entity(gmsh: Any, dimension: int, entity_tag: int, expected_type: int) -> tuple[np.ndarray, np.ndarray]:
    types, element_tag_groups, node_tag_groups = gmsh.model.mesh.getElements(dimension, entity_tag)
    element_tags: list[np.ndarray] = []
    connectivity: list[np.ndarray] = []
    for element_type, tags, nodes in zip(types, element_tag_groups, node_tag_groups, strict=True):
        properties = gmsh.model.mesh.getElementProperties(int(element_type))
        if int(element_type) != expected_type:
            raise ValueError(
                f"entity ({dimension}, {entity_tag}) contains {properties[0]}, expected MSH type {expected_type}"
            )
        element_tags.append(np.asarray(tags, dtype=np.int64))
        connectivity.append(np.asarray(nodes, dtype=np.int64).reshape(-1, int(properties[3])))
    if not element_tags:
        return np.empty((0,), dtype=np.int64), np.empty((0, 3 if dimension == 2 else 4), dtype=np.int64)
    return np.concatenate(element_tags), np.concatenate(connectivity)


def _capture(gmsh: Any, partition_entity_tags: np.ndarray) -> dict[str, Any]:
    node_tags_raw, coords_raw, _ = gmsh.model.mesh.getNodes()
    node_tags_raw = np.asarray(node_tags_raw, dtype=np.int64)
    xyz_raw = np.asarray(coords_raw, dtype=np.float64).reshape(-1, 3)
    node_order = np.argsort(node_tags_raw, kind="stable")
    node_tags = node_tags_raw[node_order]
    nodes_m = xyz_raw[node_order]
    if len(np.unique(node_tags)) != len(node_tags):
        raise ValueError("Gmsh returned duplicate node tags")
    node_row = {int(tag): row for row, tag in enumerate(node_tags)}

    tetra_rows: list[np.ndarray] = []
    cell_tag_rows: list[np.ndarray] = []
    partition_rows: list[np.ndarray] = []
    cell_entity_rows: list[np.ndarray] = []
    for label, raw_entity_tag in enumerate(partition_entity_tags):
        entity_tag = int(raw_entity_tag)
        cell_tags, tag_connectivity = _elements_for_entity(gmsh, 3, entity_tag, 4)
        tetra_rows.append(tag_connectivity)
        cell_tag_rows.append(cell_tags)
        partition_rows.append(np.full(len(cell_tags), label, dtype=np.int32))
        cell_entity_rows.append(np.full(len(cell_tags), entity_tag, dtype=np.int32))
    cell_tags = np.concatenate(cell_tag_rows)
    tag_connectivity = np.concatenate(tetra_rows)
    partitions = np.concatenate(partition_rows)
    cell_entities = np.concatenate(cell_entity_rows)
    cell_order = np.argsort(cell_tags, kind="stable")
    cell_tags = cell_tags[cell_order]
    tag_connectivity = tag_connectivity[cell_order]
    partitions = partitions[cell_order]
    cell_entities = cell_entities[cell_order]
    gmsh_volumes_m3 = np.asarray(
        gmsh.model.mesh.getElementQualities(cell_tags.tolist(), "volume"), dtype=np.float64
    )
    try:
        tets = np.asarray(
            [[node_row[int(tag)] for tag in row] for row in tag_connectivity], dtype=np.int32
        )
    except KeyError as exc:
        raise ValueError(f"tetrahedron references missing node tag {exc.args[0]}") from exc

    interface_entities = _physical_entities(gmsh, 2, "cut_interface")
    exterior_entities = _physical_entities(gmsh, 2, "source_exterior")
    interface_tag_rows: list[np.ndarray] = []
    interface_conn_rows: list[np.ndarray] = []
    exterior_surface_tag_rows: list[np.ndarray] = []
    exterior_tag_rows: list[np.ndarray] = []
    exterior_conn_rows: list[np.ndarray] = []
    surface_entities: dict[int, dict[str, Any]] = {}
    for _, surface_tag_raw in gmsh.model.getEntities(2):
        surface_tag = int(surface_tag_raw)
        triangle_tags, triangle_node_tags = _elements_for_entity(gmsh, 2, surface_tag, 2)
        if not len(triangle_tags):
            continue
        surface_entities[surface_tag] = {
            "element_tags": triangle_tags.copy(),
            "node_tags": triangle_node_tags.copy(),
        }
        if surface_tag in interface_entities:
            interface_tag_rows.append(triangle_tags)
            interface_conn_rows.append(triangle_node_tags)
        elif surface_tag in exterior_entities:
            exterior_surface_tag_rows.append(np.full(len(triangle_tags), surface_tag, dtype=np.int32))
            exterior_tag_rows.append(triangle_tags)
            exterior_conn_rows.append(triangle_node_tags)
        else:
            raise ValueError(f"surface entity {surface_tag} is not in the interface or exterior physical group")

    interface_element_tags = np.concatenate(interface_tag_rows) if interface_tag_rows else np.empty(0, dtype=np.int64)
    interface_node_tags = np.concatenate(interface_conn_rows) if interface_conn_rows else np.empty((0, 3), dtype=np.int64)
    exterior_element_tags = np.concatenate(exterior_tag_rows) if exterior_tag_rows else np.empty(0, dtype=np.int64)
    exterior_surface_tags = np.concatenate(exterior_surface_tag_rows) if exterior_surface_tag_rows else np.empty(0, dtype=np.int32)
    exterior_node_tags = np.concatenate(exterior_conn_rows) if exterior_conn_rows else np.empty((0, 3), dtype=np.int64)
    interface_triangles = np.asarray(
        [[node_row[int(tag)] for tag in row] for row in interface_node_tags], dtype=np.int32
    )
    exterior_triangles = np.asarray(
        [[node_row[int(tag)] for tag in row] for row in exterior_node_tags], dtype=np.int32
    )

    face_owners: dict[tuple[int, int, int], list[int]] = {}
    for row_index, row in enumerate(tag_connectivity):
        for opposite in range(4):
            key = tuple(sorted(int(tag) for corner, tag in enumerate(row) if corner != opposite))
            face_owners.setdefault(key, []).append(row_index)
    interface_parents = np.empty((len(interface_node_tags), 2), dtype=np.int32)
    for row_index, triangle in enumerate(interface_node_tags):
        owners = face_owners.get(tuple(sorted(int(tag) for tag in triangle)), [])
        if len(owners) != 2:
            raise ValueError(
                f"interface triangle tag row {row_index} has {len(owners)} tetrahedral parents"
            )
        interface_parents[row_index] = owners
    interface_parent_partition = partitions[interface_parents].astype(np.int8)

    return {
        "node_tags": node_tags,
        "nodes_m": nodes_m,
        "tets": tets,
        "cell_tags": cell_tags,
        "cell_node_tags": tag_connectivity,
        "partition": partitions,
        "cell_entity_tags": cell_entities,
        "gmsh_volumes_m3": gmsh_volumes_m3,
        "partition_entity_tags": np.asarray(partition_entity_tags, dtype=np.int32),
        "interface_element_tags": interface_element_tags,
        "interface_node_tags": interface_node_tags,
        "interface_triangles": interface_triangles,
        "interface_parents": interface_parents,
        "interface_parent_partition": interface_parent_partition,
        "interface_surface_tags": np.concatenate(
            [np.full(len(tags), tag, dtype=np.int32) for tag, data in surface_entities.items() if tag in interface_entities for tags in [data["element_tags"]]]
        ) if interface_entities else np.empty(0, dtype=np.int32),
        "interface_surface_entity_tags": interface_entities,
        "exterior_surface_entity_tags": exterior_entities,
        "exterior_element_tags": exterior_element_tags,
        "exterior_node_tags": exterior_node_tags,
        "exterior_triangles": exterior_triangles,
        "exterior_surface_tags": exterior_surface_tags,
        "surface_entities": surface_entities,
    }


def _source_alignment(snapshot: dict[str, Any], source: dict[str, np.ndarray], report: dict[str, Any]) -> dict[str, Any]:
    source_node_tags = np.asarray(source["original_node_tags"], dtype=np.int64)
    current_node_row = {int(tag): row for row, tag in enumerate(snapshot["node_tags"])}
    missing_nodes = [int(tag) for tag in source_node_tags if int(tag) not in current_node_row]
    source_coordinates = np.asarray(source["nodes_m"], dtype=np.float64)
    current_source_coordinates = (
        snapshot["nodes_m"][[current_node_row[int(tag)] for tag in source_node_tags]]
        if not missing_nodes
        else np.empty((0, 3), dtype=np.float64)
    )
    coordinate_delta = (
        np.abs(current_source_coordinates - source_coordinates)
        if not missing_nodes
        else np.asarray([math.inf])
    )
    max_coordinate_delta_m = float(np.max(coordinate_delta)) if coordinate_delta.size else None
    coordinate_match = not missing_nodes and bool(max_coordinate_delta_m <= 1e-17)

    expected_cell_tags = np.asarray(source["original_cell_tags"], dtype=np.int64)
    source_tets = np.asarray(source["tets"], dtype=np.int64)
    source_cells = {
        int(element_tag): tuple(int(source_node_tags[index]) for index in row)
        for element_tag, row in zip(expected_cell_tags, source_tets, strict=True)
    }
    current_cells = {
        int(element_tag): tuple(int(tag) for tag in row)
        for element_tag, row in zip(snapshot["cell_tags"], snapshot["cell_node_tags"], strict=True)
    }
    cells_equal = source_cells == current_cells

    expected_surfaces: dict[int, set[tuple[int, int, int]]] = {}
    for surface_tag in np.asarray(source["exterior_surface_tags"], dtype=np.int64):
        expected_surfaces.setdefault(int(surface_tag), set())
    for triangle, surface_tag in zip(
        np.asarray(source["exterior_triangles"], dtype=np.int64),
        np.asarray(source["exterior_surface_tags"], dtype=np.int64),
        strict=True,
    ):
        expected_surfaces[int(surface_tag)].add(
            tuple(sorted(int(source_node_tags[index]) for index in triangle))
        )
    interface_surface_tags = tuple(int(tag) for tag in report["cad"]["shared_surface_tags"])
    expected_surfaces.update({tag: set() for tag in interface_surface_tags})
    for triangle in np.asarray(source["interface_triangles"], dtype=np.int64):
        if len(interface_surface_tags) != 1:
            break
        expected_surfaces[interface_surface_tags[0]].add(
            tuple(sorted(int(source_node_tags[index]) for index in triangle))
        )
    current_surfaces = {
        entity_tag: {
            tuple(sorted(int(tag) for tag in row))
            for row in data["node_tags"]
        }
        for entity_tag, data in snapshot["surface_entities"].items()
    }
    surface_connectivity_equal = expected_surfaces == current_surfaces

    expected_partitions = {
        int(cell_tag): int(partition)
        for cell_tag, partition in zip(
            expected_cell_tags, np.asarray(source["source_partition_volume"], dtype=np.int64), strict=True
        )
    }
    current_partitions = {
        int(cell_tag): int(partition)
        for cell_tag, partition in zip(snapshot["cell_tags"], snapshot["partition"], strict=True)
    }
    partition_tags_equal = expected_partitions == current_partitions
    return {
        "source_node_count": int(len(source_node_tags)),
        "source_tetrahedron_count": int(len(expected_cell_tags)),
        "coordinate_match_for_exact_source_node_tags_with_1e-17_m_MSH_text_tolerance": bool(coordinate_match),
        "max_source_NPZ_vs_MSH_coordinate_delta_m": max_coordinate_delta_m,
        "missing_source_node_tags": missing_nodes[:20],
        "cell_tags_and_oriented_node_tag_connectivity_equal": bool(cells_equal),
        "partition_by_exact_cell_tag_equal": bool(partition_tags_equal),
        "source_surface_entity_count": int(len(expected_surfaces)),
        "surface_entities_exact_node_tag_connectivity_equal": bool(surface_connectivity_equal),
        "all_source_indexed_mesh_arrays_align": bool(
            coordinate_match and cells_equal and partition_tags_equal and surface_connectivity_equal
        ),
    }


def _surface_preservation(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_entities = before["surface_entities"]
    after_entities = after["surface_entities"]
    before_surface_nodes = {
        int(tag)
        for data in before_entities.values()
        for tag in np.asarray(data["node_tags"], dtype=np.int64).reshape(-1)
    }
    after_surface_nodes = {
        int(tag)
        for data in after_entities.values()
        for tag in np.asarray(data["node_tags"], dtype=np.int64).reshape(-1)
    }
    entity_tag_sets_equal = set(before_entities) == set(after_entities)
    connectivity_changed: dict[str, dict[str, int]] = {}
    orientation_changed: dict[str, int] = {}
    for entity_tag in sorted(set(before_entities) | set(after_entities)):
        old = before_entities.get(entity_tag)
        new = after_entities.get(entity_tag)
        old_rows = np.asarray(old["node_tags"], dtype=np.int64) if old else np.empty((0, 3), dtype=np.int64)
        new_rows = np.asarray(new["node_tags"], dtype=np.int64) if new else np.empty((0, 3), dtype=np.int64)
        old_keys = {tuple(sorted(int(tag) for tag in row)) for row in old_rows}
        new_keys = {tuple(sorted(int(tag) for tag in row)) for row in new_rows}
        added = new_keys - old_keys
        removed = old_keys - new_keys
        if added or removed:
            connectivity_changed[str(entity_tag)] = {"added_triangles": len(added), "removed_triangles": len(removed)}

        old_orientation = {
            tuple(sorted(int(tag) for tag in row)): _orientation_sign(tuple(int(tag) for tag in row))
            for row in old_rows
        }
        new_orientation = {
            tuple(sorted(int(tag) for tag in row)): _orientation_sign(tuple(int(tag) for tag in row))
            for row in new_rows
        }
        flips = sum(old_orientation[key] != new_orientation[key] for key in old_orientation.keys() & new_orientation.keys())
        if flips:
            orientation_changed[str(entity_tag)] = int(flips)

    before_coords = {
        int(tag): before["nodes_m"][row]
        for row, tag in enumerate(before["node_tags"])
        if int(tag) in before_surface_nodes
    }
    after_node_row = {int(tag): row for row, tag in enumerate(after["node_tags"])}
    missing_surface_node_tags = sorted(before_surface_nodes - after_surface_nodes)
    new_surface_node_tags = sorted(after_surface_nodes - before_surface_nodes)
    moved_surface_nodes: list[int] = []
    node_displacements: dict[int, float] = {}
    for tag in sorted(before_surface_nodes & after_surface_nodes):
        row = after_node_row.get(tag)
        if row is None:
            moved_surface_nodes.append(tag)
            node_displacements[tag] = math.inf
        else:
            displacement = float(np.linalg.norm(before_coords[tag] - after["nodes_m"][row]))
            if displacement != 0.0:
                moved_surface_nodes.append(tag)
                node_displacements[tag] = displacement

    def displacement_for_entities(entity_tags: tuple[int, ...]) -> dict[str, Any]:
        entity_nodes = {
            int(tag)
            for entity_tag in entity_tags
            for snapshot in (before,)
            for tag in np.asarray(snapshot["surface_entities"].get(entity_tag, {}).get("node_tags", []), dtype=np.int64).reshape(-1)
        }
        changed = [tag for tag in moved_surface_nodes if tag in entity_nodes]
        values = [node_displacements[tag] for tag in changed]
        return {
            "source_surface_node_count": len(entity_nodes),
            "moved_node_count": len(changed),
            "max_node_displacement_m": max(values) if values else 0.0,
            "max_node_displacement_mm": max(values) * 1_000.0 if values else 0.0,
        }

    same = (
        entity_tag_sets_equal
        and before_surface_nodes == after_surface_nodes
        and not missing_surface_node_tags
        and not new_surface_node_tags
        and not moved_surface_nodes
        and not connectivity_changed
        and not orientation_changed
    )
    return {
        "exact_surface_entity_tags_equal": bool(entity_tag_sets_equal),
        "surface_node_tag_sets_equal": bool(before_surface_nodes == after_surface_nodes),
        "surface_coordinates_bitwise_equal_by_exact_node_tag": bool(not moved_surface_nodes),
        "missing_surface_node_tags": missing_surface_node_tags[:20],
        "new_surface_node_tags": new_surface_node_tags[:20],
        "moved_surface_node_tags": moved_surface_nodes[:20],
        "moved_surface_node_count": len(moved_surface_nodes),
        "max_surface_node_displacement_m": max(node_displacements.values()) if node_displacements else 0.0,
        "interface_surface_displacement": displacement_for_entities(before["interface_surface_entity_tags"]),
        "exterior_surface_displacement": displacement_for_entities(before["exterior_surface_entity_tags"]),
        "changed_connectivity_by_surface_entity": connectivity_changed,
        "changed_orientation_by_surface_entity": orientation_changed,
        "surface_preserved_exactly": bool(same),
    }


def _orientation_sign(row: tuple[int, int, int]) -> int:
    inversions = sum(row[i] > row[j] for i in range(3) for j in range(i + 1, 3))
    return -1 if inversions % 2 else 1


def _quality_metrics(gmsh: Any, snapshot: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    xyz = snapshot["nodes_m"][snapshot["tets"]]
    edge_matrix = np.stack(
        (xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0], xyz[:, 3] - xyz[:, 0]), axis=2
    )
    determinants = np.linalg.det(edge_matrix)
    signed_volumes = determinants / 6.0
    abs_volumes = np.abs(signed_volumes)
    face_areas = []
    for opposite in range(4):
        face_points = np.delete(xyz, opposite, axis=1)
        face_areas.append(
            0.5
            * np.linalg.norm(
                np.cross(face_points[:, 1] - face_points[:, 0], face_points[:, 2] - face_points[:, 0]),
                axis=1,
            )
        )
    face_areas_array = np.column_stack(face_areas)
    with np.errstate(divide="ignore", invalid="ignore"):
        minimum_altitude_m = np.min(3.0 * abs_volumes[:, None] / face_areas_array, axis=1)
    cell_volume = float(signed_volumes.sum())
    cad_volume = float(report["cad"]["source_volume_m3"])

    sicn_summary: dict[str, float] | None = None
    sicn_error: str | None = None
    try:
        qualities = gmsh.model.mesh.getElementQualities(
            snapshot["cell_tags"].tolist(), "minSICN"
        )
        sicn_summary = summary(np.asarray(qualities, dtype=np.float64))
    except Exception as exc:  # Preserve an unsupported metric as a recorded result.
        sicn_error = f"{type(exc).__name__}: {exc}"

    return {
        "tetrahedra": int(len(snapshot["tets"])),
        "nodes": int(len(snapshot["node_tags"])),
        "positive_oriented_tetrahedra": int(np.count_nonzero(determinants > 0.0)),
        "negative_oriented_tetrahedra": int(np.count_nonzero(determinants < 0.0)),
        "zero_or_nonfinite_determinants": int(np.count_nonzero(~np.isfinite(determinants) | (determinants == 0.0))),
        "minimum_per_tetrahedron_altitude_mm": summary(minimum_altitude_m * 1_000.0),
        "signed_tetrahedral_volume_m3": cell_volume,
        "cad_mesh_volume_relative_error": float(abs(cell_volume - cad_volume) / cad_volume),
        "gmsh_minSICN": sicn_summary,
        "gmsh_minSICN_error": sicn_error,
    }


def _audit(gmsh: Any, snapshot: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    sys.path.insert(0, str(VF_SOURCE))
    from vesselforge.tetra_audit import audit_tetra_mesh

    try:
        audited = audit_tetra_mesh(
            snapshot["nodes_m"],
            snapshot["tets"],
            snapshot["partition"],
            snapshot["interface_triangles"],
            snapshot["interface_parents"],
            stored_volume_m3=snapshot["gmsh_volumes_m3"],
            interface_plane_x_m=float(report["plane_x_m"]),
            expected_volume_m3=float(report["cad"]["source_volume_m3"]),
            expected_interface_area_m2=float(report["cad"]["shared_area_m2"]),
        )
        return {
            "status": audited["status"],
            "checks": audited["checks"],
            "counts": audited["counts"],
            "volume": {
                "tetrahedral_volume_m3": audited["volume"]["tetrahedral_volume_m3"],
                "analytic_relative_error": audited["volume"]["analytic_relative_error"],
                "partition_balance_relative_error": audited["volume"]["partition_balance_relative_error"],
                "partitions": {
                    label: {
                        "tetrahedra": part["tetrahedra"],
                        "tetrahedral_volume_m3": part["tetrahedral_volume_m3"],
                        "analytic_half_volume_relative_error": part["analytic_half_volume_relative_error"],
                    }
                    for label, part in audited["volume"]["partitions"].items()
                },
            },
            "interface": audited["interface"],
            "exterior_surface": audited["exterior_surface"],
        }
    except Exception as exc:
        return {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}


def _write_candidate(gmsh: Any, snapshot: dict[str, Any], variant: str) -> dict[str, Any]:
    CANDIDATE_DIR.mkdir(parents=True, exist_ok=True)
    mesh_path = CANDIDATE_DIR / f"{variant}.msh"
    npz_path = CANDIDATE_DIR / f"{variant}.npz"
    gmsh.write(str(mesh_path))
    exterior_count = len(snapshot["exterior_triangles"])
    np.savez_compressed(
        npz_path,
        nodes_m=snapshot["nodes_m"],
        tets=snapshot["tets"],
        original_node_tags=snapshot["node_tags"],
        original_cell_tags=snapshot["cell_tags"],
        source_partition_volume=snapshot["partition"],
        volume_m3=np.linalg.det(
            np.stack(
                (
                    snapshot["nodes_m"][snapshot["tets"]][:, 1] - snapshot["nodes_m"][snapshot["tets"]][:, 0],
                    snapshot["nodes_m"][snapshot["tets"]][:, 2] - snapshot["nodes_m"][snapshot["tets"]][:, 0],
                    snapshot["nodes_m"][snapshot["tets"]][:, 3] - snapshot["nodes_m"][snapshot["tets"]][:, 0],
                ),
                axis=2,
            )
        )
        / 6.0,
        interface_triangles=snapshot["interface_triangles"],
        interface_parents=snapshot["interface_parents"],
        interface_parent_partition=snapshot["interface_parent_partition"],
        exterior_triangles=snapshot["exterior_triangles"],
        exterior_surface_tags=snapshot["exterior_surface_tags"],
        exterior_source_face_ids=np.full(exterior_count, "", dtype="<U1"),
        exterior_roles=np.full(exterior_count, "unknown", dtype="<U7"),
        exterior_ancestry_exact=np.zeros(exterior_count, dtype=bool),
        partition_entity_tags=snapshot["partition_entity_tags"],
    )
    return {
        "mesh_msh": {"path": str(mesh_path.relative_to(HERE)), "bytes": mesh_path.stat().st_size, "sha256": sha256(mesh_path)},
        "mesh_npz": {"path": str(npz_path.relative_to(HERE)), "bytes": npz_path.stat().st_size, "sha256": sha256(npz_path)},
    }


def run_child(variant: str) -> dict[str, Any]:
    run_start = time.monotonic()
    report, source = source_inputs()
    if variant not in ("baseline", *OPTIMIZERS.keys()):
        raise ValueError(f"unknown run variant: {variant}")
    partition_entity_tags = np.asarray(source["partition_entity_tags"], dtype=np.int32)
    gmsh, dll_handle = load_gmsh()
    initialized = False
    try:
        gmsh.initialize()
        initialized = True
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(SOURCE_MSH))
        before = _capture(gmsh, partition_entity_tags)
        alignment = _source_alignment(before, source, report)
        if variant == "baseline" and not alignment["all_source_indexed_mesh_arrays_align"]:
            return {
                "variant": variant,
                "status": "BASELINE_SOURCE_ALIGNMENT_FAILED",
                "source_alignment": alignment,
                "elapsed_s": time.monotonic() - run_start,
            }
        optimize_wall_s = 0.0
        optimizer = None
        force_discrete_entities = False
        optimize_error = None
        before_metrics = _quality_metrics(gmsh, before, report)
        if variant != "baseline":
            optimizer = OPTIMIZERS[variant]["method"]
            force_discrete_entities = bool(OPTIMIZERS[variant]["force"])
            started = time.monotonic()
            try:
                # One bounded pass in a fresh model; explicit dimTags exclude all surfaces.
                gmsh.model.mesh.optimize(
                    optimizer,
                    force=force_discrete_entities,
                    niter=1,
                    dimTags=[(3, int(tag)) for tag in partition_entity_tags],
                )
            except Exception as exc:
                optimize_error = f"{type(exc).__name__}: {exc}"
            optimize_wall_s = time.monotonic() - started
        after = _capture(gmsh, partition_entity_tags)
        surfaces = _surface_preservation(before, after)
        metrics = _quality_metrics(gmsh, after, report)
        audit = _audit(gmsh, after, report)
        count_within_cap = metrics["tetrahedra"] <= MAX_TETRAHEDRA
        minimum_altitude_improved = (
            metrics["minimum_per_tetrahedron_altitude_mm"]["min"]
            > before_metrics["minimum_per_tetrahedron_altitude_mm"]["min"] * (1.0 + 1e-12)
        )
        eligible = (
            variant != "baseline"
            and optimize_error is None
            and count_within_cap
            and metrics["cad_mesh_volume_relative_error"] <= 0.01
            and surfaces["surface_preserved_exactly"]
            and audit.get("status") == "PASS"
            and minimum_altitude_improved
        )
        files = _write_candidate(gmsh, after, variant) if eligible else None
        baseline_metrics = metrics if variant == "baseline" else None
        return {
            "variant": variant,
            "status": "BASELINE" if variant == "baseline" else ("CANDIDATE_PRESERVED" if eligible else "REJECTED_OR_UNSUPPORTED"),
            "gmsh_version": str(gmsh.__version__),
            "optimizer_method": optimizer,
            "force_discrete_entities": force_discrete_entities,
            "niter": 0 if variant == "baseline" else 1,
            "optimizer_wall_s": optimize_wall_s,
            "optimizer_error": optimize_error,
            "source_alignment": alignment,
            "surface_preservation": surfaces,
            "quality": metrics,
            "audit": audit,
            "cell_count_within_100k_cap": bool(count_within_cap),
            "minimum_altitude_improved_vs_fresh_loaded_mesh": bool(minimum_altitude_improved),
            "cad_mesh_volume_relative_error_within_existing_1pct_gate": bool(
                metrics["cad_mesh_volume_relative_error"] <= 0.01
            ),
            "eligible_candidate": bool(eligible),
            "files": files,
            "elapsed_s": time.monotonic() - run_start,
            "baseline_metrics_internal": before_metrics,
        }
    finally:
        if initialized:
            gmsh.finalize()
        del dll_handle


def run_bounded_child(variant: str, timeout_s: float, started_at: float) -> dict[str, Any]:
    remaining = MAX_TOTAL_SECONDS - (time.monotonic() - started_at)
    if remaining <= 2.0:
        return {"variant": variant, "status": "SKIPPED_TOTAL_WALL_LIMIT", "wall_s": 0.0}
    timeout_s = min(timeout_s, remaining - 1.0)
    command = [sys.executable, str(Path(__file__).resolve()), "--child", variant]
    child_start = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raw_output = exc.stdout or ""
        output = raw_output.decode(errors="replace") if isinstance(raw_output, bytes) else raw_output
        return {
            "variant": variant,
            "status": "PROCESS_WALL_LIMIT_EXCEEDED",
            "wall_s": time.monotonic() - child_start,
            "peak_working_set_bytes": None,
            "output_tail": output[-2000:],
        }
    elapsed = time.monotonic() - child_start
    if completed.returncode != 0:
        return {
            "variant": variant,
            "status": "CHILD_PROCESS_FAILED",
            "wall_s": elapsed,
            "peak_working_set_bytes": None,
            "return_code": completed.returncode,
            "output_tail": completed.stdout[-3000:],
        }
    try:
        result = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        return {
            "variant": variant,
            "status": "CHILD_RESULT_PARSE_FAILED",
            "wall_s": elapsed,
            "peak_working_set_bytes": None,
            "parse_error": str(exc),
            "output_tail": completed.stdout[-3000:],
        }
    result["process_wall_s"] = elapsed
    result["peak_working_set_bytes"] = None
    return result


def _public_run(run: dict[str, Any]) -> dict[str, Any]:
    public = {key: value for key, value in run.items() if key != "baseline_metrics_internal"}
    return public


def _finalize_probe(runs: list[dict[str, Any]], total_wall_s: float, source_hashes: dict[str, Any]) -> dict[str, Any]:
    baseline = next((run for run in runs if run.get("variant") == "baseline" and run.get("quality")), None)
    baseline_quality = baseline["quality"] if baseline else None
    for run in runs:
        if not baseline_quality or not run.get("quality") or run.get("variant") == "baseline":
            continue
        base_altitude = baseline_quality["minimum_per_tetrahedron_altitude_mm"]["min"]
        run_altitude = run["quality"]["minimum_per_tetrahedron_altitude_mm"]["min"]
        run["comparison_to_baseline"] = {
            "minimum_altitude_change_mm": float(run_altitude - base_altitude),
            "minimum_altitude_factor": float(run_altitude / base_altitude) if base_altitude else None,
            "stable_step_ceiling_factor_if_proportional_to_minimum_altitude": (
                float(run_altitude / base_altitude) if base_altitude else None
            ),
            "estimated_steps_per_fixed_duration_factor_if_bottlenecked_by_that_altitude": (
                float(base_altitude / run_altitude) if run_altitude else None
            ),
            "minimum_SICN_change": (
                float(run["quality"]["gmsh_minSICN"]["min"] - baseline_quality["gmsh_minSICN"]["min"])
                if run["quality"].get("gmsh_minSICN") and baseline_quality.get("gmsh_minSICN")
                else None
            ),
            "median_SICN_change": (
                float(run["quality"]["gmsh_minSICN"]["median"] - baseline_quality["gmsh_minSICN"]["median"])
                if run["quality"].get("gmsh_minSICN") and baseline_quality.get("gmsh_minSICN")
                else None
            ),
        }
    source_report, _ = source_inputs()
    forecast = source_report["resource_forecast"]
    return {
        "schema": "vesselforge.mesh_quality_probe.v1",
        "status": "COMPLETED" if baseline_quality else "BASELINE_FAILED",
        "runner": {
            "path": str((HERE / "run_mesh_quality_probe.py").relative_to(REPO)),
            **source_hashes["runner_script"],
        },
        "source": {
            "mesh_msh": {"path": str(SOURCE_MSH.relative_to(REPO)), **source_hashes["mesh_msh"]},
            "mesh_npz": {"path": str(SOURCE_NPZ.relative_to(REPO)), **source_hashes["mesh_npz"]},
            "source_result_json": {"path": str(SOURCE_REPORT.relative_to(REPO)), **source_hashes["result_json"]},
            "source_mesh_schema_status": source_report["status"],
            "source_face_ancestry_status": source_report["source_face_ancestry"]["status"],
            "source_exterior_source_face_ids": "UNKNOWN; preserved as unknown; no spatial or nearest-face mapping was inferred",
            "source_step_sha256": source_report["source_step_sha256"],
            "cad_volume_m3": source_report["cad"]["source_volume_m3"],
            "original_cad_mesh_volume_relative_error": source_report["mesh"]["cad_mesh_volume_relative_error"],
        },
        "method": {
            "gmsh_version_expected": "4.15.2",
            "optimizer_runs": [
                {
                    "variant": key,
                    "method": value["method"] or "Gmsh default tetrahedral optimizer",
                    "niter": 1,
                    "fresh_model_load": True,
                    "dimTags": "only source partition volume entities",
                    "force": value["force"],
                }
                for key, value in OPTIMIZERS.items()
            ],
            "no CAD regeneration": True,
            "optimizer_entity_selection": "API dimTags selected only the two volume entities; the output comparison also checks indirect surface changes",
            "no separate vertex smoothing or node relocation API call": True,
            "boundary_gate": "bitwise equal coordinates and exact Gmsh node-tag triangle connectivity per original surface entity, including interface",
            "candidate_gate": "surface gate plus tetra_audit PASS plus <=100,000 T4 plus <=1% CAD-volume error plus improved global minimum tetrahedron altitude",
            "mesh_only_stable_step_proxy": "minimum tetrahedron altitude ratio; proportional estimate only, no material model or native solver was run",
            "quality_metric": "Gmsh getElementQualities(..., 'minSICN'): sampled minimum signed inverse condition number",
            "resource_limits": {
                "max_tetrahedra": MAX_TETRAHEDRA,
                "max_declared_forecast_memory_bytes": MAX_MEMORY_BYTES,
                "source_declared_forecast_tetrahedra": forecast["estimated_tetrahedra"],
                "source_declared_forecast_memory_bytes": forecast["estimated_peak_memory_bytes"],
                "actual_process_peak_working_set_sampled": False,
                "per_process_wall_limit_s": MAX_RUN_SECONDS,
                "total_probe_wall_limit_s": MAX_TOTAL_SECONDS,
            },
        },
        "runs": [_public_run(run) for run in runs],
        "outcome": {
            "status": "NO_QUALIFIED_CANDIDATE" if not any(run.get("eligible_candidate") for run in runs) else "CANDIDATE_FILES_WRITTEN",
            "qualified_variants": [run["variant"] for run in runs if run.get("eligible_candidate")],
            "interpretation": "No run passed exact surface preservation, the tetra audit, the 100,000-cell/1% CAD-volume gates, and a strictly improved minimum altitude.",
        },
        "total_process_wall_s": float(total_wall_s),
        "interpretation_limits": [
            "This is a disposable mesh-quality control on the existing daily Aberdeen v5 diagnostic, not latest v6 or an accepted physical mother.",
            "Only the existing mesh was loaded; true CAD geometry, loading, constitutive model, and element order were not changed.",
            "A minimum-altitude stable-step factor is a geometry-only proportional estimate and is not a measured solver time step or runtime reduction.",
            "The source exterior ancestry remains UNKNOWN because the existing source-face records lack exact imported Gmsh surface bindings.",
            "No native solver evolution, material calibration, physical qualification, or fracture calculation was performed.",
        ],
    }


def run_probe() -> dict[str, Any]:
    started_at = time.monotonic()
    source_hashes = {
        "mesh_msh": {"sha256": sha256(SOURCE_MSH), "bytes": SOURCE_MSH.stat().st_size},
        "mesh_npz": {"sha256": sha256(SOURCE_NPZ), "bytes": SOURCE_NPZ.stat().st_size},
        "result_json": {"sha256": sha256(SOURCE_REPORT), "bytes": SOURCE_REPORT.stat().st_size},
        "runner_script": {"sha256": sha256(HERE / "run_mesh_quality_probe.py"), "bytes": (HERE / "run_mesh_quality_probe.py").stat().st_size},
    }
    source_report, _ = source_inputs()
    forecast = source_report["resource_forecast"]
    if int(forecast["estimated_tetrahedra"]) > MAX_TETRAHEDRA:
        raise RuntimeError("the existing declared tetrahedron forecast exceeds the probe cap")
    if int(forecast["estimated_peak_memory_bytes"]) > MAX_MEMORY_BYTES:
        raise RuntimeError("the existing declared memory forecast exceeds the probe cap")
    runs: list[dict[str, Any]] = []
    baseline = run_bounded_child("baseline", timeout_s=45.0, started_at=started_at)
    runs.append(baseline)
    if baseline.get("status") != "BASELINE":
        return _finalize_probe(runs, time.monotonic() - started_at, source_hashes)
    for variant in OPTIMIZERS:
        run = run_bounded_child(variant, timeout_s=MAX_RUN_SECONDS, started_at=started_at)
        runs.append(run)
        if time.monotonic() - started_at >= MAX_TOTAL_SECONDS:
            break
    return _finalize_probe(runs, time.monotonic() - started_at, source_hashes)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded Gmsh tetra mesh quality probe")
    parser.add_argument("--child", choices=("baseline", *OPTIMIZERS.keys()))
    args = parser.parse_args()
    if args.child:
        try:
            print(json.dumps(run_child(args.child), separators=(",", ":")))
            return 0
        except Exception as exc:
            print(json.dumps({"variant": args.child, "status": "CHILD_EXCEPTION", "error": f"{type(exc).__name__}: {exc}"}, separators=(",", ":")))
            return 2
    probe = run_probe()
    OUTPUT_JSON.write_text(json.dumps(probe, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": probe["status"], "output": str(OUTPUT_JSON), "runs": [
        {"variant": run.get("variant"), "status": run.get("status"), "eligible_candidate": run.get("eligible_candidate")}
        for run in probe["runs"]
    ], "total_process_wall_s": probe["total_process_wall_s"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
