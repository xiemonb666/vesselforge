from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
PROBE_DIR = HERE.parent
SOURCE_DIR = (
    REPO
    / "vesselforge"
    / "experiments"
    / "continuation_20261015"
    / "reference_tetra"
    / "daily_aberdeen_v5_diagnostic"
)
FROZEN_HELPERS = PROBE_DIR / "run_mesh_quality_probe.py"
REPORT_PATH = HERE / "mesh_quality_probe_v2.json"
STDOUT_PATH = HERE / "worker_stdout.log"
STDERR_PATH = HERE / "worker_stderr.log"
MAX_TETRAHEDRA = 100_000
MAX_DECLARED_MEMORY_BYTES = 2 * 1024**3
MAX_PROCESS_SECONDS = 110.0
MAX_LOG_BYTES = 256 * 1024**2
MIN_ALTITUDE_GAIN_FRACTION = 1.0e-3


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def capture_without_gmsh_volume_quality(gmsh: Any, partition_entities: Any) -> dict[str, Any]:
    """Capture current arrays without depending on Gmsh's element-tag quality lookup."""
    import numpy as np

    spec = importlib.util.spec_from_file_location(
        "frozen_mesh_probe_helpers", FROZEN_HELPERS
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load frozen probe helper module")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)

    raw_node_tags, raw_coordinates, _ = gmsh.model.mesh.getNodes()
    raw_node_tags = np.asarray(raw_node_tags, dtype=np.int64)
    raw_coordinates = np.asarray(raw_coordinates, dtype=np.float64).reshape(-1, 3)
    node_order = np.argsort(raw_node_tags, kind="stable")
    node_tags = raw_node_tags[node_order]
    nodes_m = raw_coordinates[node_order]
    node_row = {int(tag): row for row, tag in enumerate(node_tags)}

    cell_tags_by_partition: list[np.ndarray] = []
    cell_connectivity_by_partition: list[np.ndarray] = []
    partition_rows: list[np.ndarray] = []
    entity_rows: list[np.ndarray] = []
    for label, entity_tag_raw in enumerate(partition_entities):
        entity_tag = int(entity_tag_raw)
        tags, connectivity = helper._elements_for_entity(gmsh, 3, entity_tag, 4)
        cell_tags_by_partition.append(tags)
        cell_connectivity_by_partition.append(connectivity)
        partition_rows.append(np.full(len(tags), label, dtype=np.int32))
        entity_rows.append(np.full(len(tags), entity_tag, dtype=np.int32))
    cell_tags = np.concatenate(cell_tags_by_partition)
    cell_node_tags = np.concatenate(cell_connectivity_by_partition)
    partitions = np.concatenate(partition_rows)
    cell_entities = np.concatenate(entity_rows)
    cell_order = np.argsort(cell_tags, kind="stable")
    cell_tags = cell_tags[cell_order]
    cell_node_tags = cell_node_tags[cell_order]
    partitions = partitions[cell_order]
    cell_entities = cell_entities[cell_order]
    tets = np.asarray(
        [[node_row[int(tag)] for tag in row] for row in cell_node_tags], dtype=np.int32
    )

    interface_entities = helper._physical_entities(gmsh, 2, "cut_interface")
    exterior_entities = helper._physical_entities(gmsh, 2, "source_exterior")
    surface_entities: dict[int, dict[str, Any]] = {}
    interface_element_tags: list[np.ndarray] = []
    interface_node_tags: list[np.ndarray] = []
    interface_surface_tags: list[np.ndarray] = []
    exterior_element_tags: list[np.ndarray] = []
    exterior_node_tags: list[np.ndarray] = []
    exterior_surface_tags: list[np.ndarray] = []
    for _, entity_tag_raw in gmsh.model.getEntities(2):
        entity_tag = int(entity_tag_raw)
        tri_tags, tri_nodes = helper._elements_for_entity(gmsh, 2, entity_tag, 2)
        if not len(tri_tags):
            continue
        surface_entities[entity_tag] = {
            "element_tags": tri_tags.copy(),
            "node_tags": tri_nodes.copy(),
        }
        if entity_tag in interface_entities:
            interface_element_tags.append(tri_tags)
            interface_node_tags.append(tri_nodes)
            interface_surface_tags.append(np.full(len(tri_tags), entity_tag, dtype=np.int32))
        elif entity_tag in exterior_entities:
            exterior_element_tags.append(tri_tags)
            exterior_node_tags.append(tri_nodes)
            exterior_surface_tags.append(np.full(len(tri_tags), entity_tag, dtype=np.int32))
        else:
            raise ValueError(f"surface entity {entity_tag} lacks source-exterior/interface classification")

    interface_nodes = (
        np.concatenate(interface_node_tags)
        if interface_node_tags
        else np.empty((0, 3), dtype=np.int64)
    )
    exterior_nodes = (
        np.concatenate(exterior_node_tags)
        if exterior_node_tags
        else np.empty((0, 3), dtype=np.int64)
    )
    face_owners: dict[tuple[int, int, int], list[int]] = {}
    for row_index, row in enumerate(cell_node_tags):
        for opposite in range(4):
            face = tuple(sorted(int(tag) for index, tag in enumerate(row) if index != opposite))
            face_owners.setdefault(face, []).append(row_index)
    interface_parents = np.empty((len(interface_nodes), 2), dtype=np.int32)
    for row_index, tri in enumerate(interface_nodes):
        owners = face_owners.get(tuple(sorted(int(tag) for tag in tri)), [])
        if len(owners) != 2:
            raise ValueError(f"interface triangle {row_index} has {len(owners)} tetrahedral parents")
        interface_parents[row_index] = owners

    return {
        "node_tags": node_tags,
        "nodes_m": nodes_m,
        "tets": tets,
        "cell_tags": cell_tags,
        "cell_node_tags": cell_node_tags,
        "partition": partitions,
        "cell_entity_tags": cell_entities,
        "gmsh_volumes_m3": None,
        "partition_entity_tags": np.asarray(partition_entities, dtype=np.int32),
        "interface_element_tags": np.concatenate(interface_element_tags) if interface_element_tags else np.empty(0, dtype=np.int64),
        "interface_node_tags": interface_nodes,
        "interface_triangles": np.asarray([[node_row[int(tag)] for tag in row] for row in interface_nodes], dtype=np.int32),
        "interface_parents": interface_parents,
        "interface_parent_partition": partitions[interface_parents].astype(np.int8),
        "interface_surface_tags": np.concatenate(interface_surface_tags) if interface_surface_tags else np.empty(0, dtype=np.int32),
        "interface_surface_entity_tags": interface_entities,
        "exterior_surface_entity_tags": exterior_entities,
        "exterior_element_tags": np.concatenate(exterior_element_tags) if exterior_element_tags else np.empty(0, dtype=np.int64),
        "exterior_node_tags": exterior_nodes,
        "exterior_triangles": np.asarray([[node_row[int(tag)] for tag in row] for row in exterior_nodes], dtype=np.int32),
        "exterior_surface_tags": np.concatenate(exterior_surface_tags) if exterior_surface_tags else np.empty(0, dtype=np.int32),
        "surface_entities": surface_entities,
    }


def run_worker() -> dict[str, Any]:
    import numpy as np

    started = time.monotonic()
    if not FROZEN_HELPERS.is_file():
        raise FileNotFoundError(f"frozen helper script is missing: {FROZEN_HELPERS}")
    spec = importlib.util.spec_from_file_location("frozen_mesh_probe_helpers", FROZEN_HELPERS)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load frozen probe helper module")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)

    source_report, source = helper.source_inputs()
    partition_entities = source["partition_entity_tags"].astype("int32", copy=False)
    gmsh, dll_handle = helper.load_gmsh()
    initialized = False
    try:
        gmsh.initialize()
        initialized = True
        gmsh.option.setNumber("General.Terminal", 0)
        default_renumber = float(gmsh.option.getNumber("Mesh.Renumber"))
        gmsh.option.setNumber("Mesh.Renumber", 0)
        renumber_before_open = float(gmsh.option.getNumber("Mesh.Renumber"))
        gmsh.open(str(helper.SOURCE_MSH))
        renumber_after_open = float(gmsh.option.getNumber("Mesh.Renumber"))

        before = capture_without_gmsh_volume_quality(gmsh, partition_entities)
        source_alignment_before = helper._source_alignment(before, source, source_report)
        before_quality = helper._quality_metrics(gmsh, before, source_report)
        before_audit = helper._audit(gmsh, before, source_report)
        if not source_alignment_before["all_source_indexed_mesh_arrays_align"]:
            return {
                "status": "SOURCE_ALIGNMENT_FAILED",
                "source_alignment_before": source_alignment_before,
                "elapsed_s": time.monotonic() - started,
            }

        volume_tags = [int(tag) for tag in partition_entities]
        optimizer_start = time.monotonic()
        gmsh.model.mesh.optimize(
            "",
            force=True,
            niter=1,
            dimTags=[(3, tag) for tag in volume_tags],
        )
        optimize_wall_s = time.monotonic() - optimizer_start
        renumber_after_optimize = float(gmsh.option.getNumber("Mesh.Renumber"))
        after = capture_without_gmsh_volume_quality(gmsh, partition_entities)
        after_quality = helper._quality_metrics(gmsh, after, source_report)
        after_audit = helper._audit(gmsh, after, source_report)
        source_alignment_after = helper._source_alignment(after, source, source_report)

        # Exact-coordinate matching is only used to diagnose tag permutations. No
        # tolerance or nearest-point matching is permitted. Duplicate bit patterns
        # make the correspondence ambiguous and are reported as such.
        before_keys = [row.tobytes() for row in before["nodes_m"].astype("<f8", copy=False)]
        after_keys = [row.tobytes() for row in after["nodes_m"].astype("<f8", copy=False)]
        before_counts: dict[bytes, int] = {}
        after_counts: dict[bytes, int] = {}
        for key in before_keys:
            before_counts[key] = before_counts.get(key, 0) + 1
        for key in after_keys:
            after_counts[key] = after_counts.get(key, 0) + 1
        unique_before = all(count == 1 for count in before_counts.values())
        unique_after = all(count == 1 for count in after_counts.values())
        exact_key_sets_equal = set(before_counts) == set(after_counts)
        exact_bijection = unique_before and unique_after and exact_key_sets_equal
        after_tag_by_coordinate = (
            {key: int(tag) for key, tag in zip(after_keys, after["node_tags"], strict=True)}
            if exact_bijection
            else {}
        )
        exact_coordinate_tag_map = (
            {
                int(old_tag): after_tag_by_coordinate[key]
                for old_tag, key in zip(before["node_tags"], before_keys, strict=True)
            }
            if exact_bijection
            else {}
        )

        direct_node_tags_equal = bool(
            len(before["node_tags"]) == len(after["node_tags"])
            and (before["node_tags"] == after["node_tags"]).all()
        )
        direct_coordinates_bitwise_by_tag = bool(
            direct_node_tags_equal
            and (before["nodes_m"].view("uint64") == after["nodes_m"].view("uint64")).all()
        )
        coordinate_displacement_m = np.linalg.norm(after["nodes_m"] - before["nodes_m"], axis=1)
        coordinate_rows_bitwise_equal = (
            before["nodes_m"].view("uint64") == after["nodes_m"].view("uint64")
        ).all(axis=1)

        surface_maps_before: dict[int, dict[int, tuple[int, int, int]]] = {}
        surface_maps_after: dict[int, dict[int, tuple[int, int, int]]] = {}
        for target, snapshot in (
            (surface_maps_before, before),
            (surface_maps_after, after),
        ):
            for entity_tag, data in snapshot["surface_entities"].items():
                target[int(entity_tag)] = {
                    int(element_tag): tuple(int(node_tag) for node_tag in row)
                    for element_tag, row in zip(
                        data["element_tags"], data["node_tags"], strict=True
                    )
                }
        same_surface_entity_tags = set(surface_maps_before) == set(surface_maps_after)
        surface_element_tag_sets_equal = same_surface_entity_tags and all(
            set(surface_maps_before[entity]) == set(surface_maps_after[entity])
            for entity in surface_maps_before
        )
        surface_connectivity_equal_by_exact_element_tag = surface_element_tag_sets_equal and all(
            surface_maps_before[entity] == surface_maps_after[entity]
            for entity in surface_maps_before
        )
        mapped_surface_connectivity_equal = False
        if exact_bijection and same_surface_entity_tags:
            mapped_surface_connectivity_equal = all(
                {
                    element_tag: tuple(exact_coordinate_tag_map[tag] for tag in nodes)
                    for element_tag, nodes in surface_maps_before[entity].items()
                }
                == surface_maps_after[entity]
                for entity in surface_maps_before
                if entity in surface_maps_after
            ) and all(set(surface_maps_before[e]) == set(surface_maps_after[e]) for e in surface_maps_before)

        surface_direct = helper._surface_preservation(before, after)
        cell_connectivity_before = {
            int(tag): tuple(int(node) for node in row)
            for tag, row in zip(before["cell_tags"], before["cell_node_tags"], strict=True)
        }
        cell_connectivity_after = {
            int(tag): tuple(int(node) for node in row)
            for tag, row in zip(after["cell_tags"], after["cell_node_tags"], strict=True)
        }
        common_cell_tags = set(cell_connectivity_before) & set(cell_connectivity_after)
        cell_tag_sets_equal = set(cell_connectivity_before) == set(cell_connectivity_after)
        same_connectivity_for_common_cell_tags = all(
            cell_connectivity_before[tag] == cell_connectivity_after[tag]
            for tag in common_cell_tags
        )
        before_alt = before_quality["minimum_per_tetrahedron_altitude_mm"]["min"]
        after_alt = after_quality["minimum_per_tetrahedron_altitude_mm"]["min"]
        altitude_gain_fraction = (after_alt - before_alt) / before_alt if before_alt > 0 else None
        surface_preserved = bool(
            surface_direct["surface_preserved_exactly"]
            and surface_connectivity_equal_by_exact_element_tag
            and direct_node_tags_equal
        )
        audit_pass = after_audit.get("status") == "PASS"
        t4_within_limit = after_quality["tetrahedra"] <= MAX_TETRAHEDRA
        memory_forecast = int(source_report["resource_forecast"]["estimated_peak_memory_bytes"])
        memory_within_limit = memory_forecast <= MAX_DECLARED_MEMORY_BYTES
        substantive_gain = bool(
            altitude_gain_fraction is not None
            and altitude_gain_fraction > MIN_ALTITUDE_GAIN_FRACTION
        )
        candidate_qualified = bool(
            surface_preserved
            and audit_pass
            and after_quality["negative_oriented_tetrahedra"] == 0
            and after_quality["zero_or_nonfinite_determinants"] == 0
            and t4_within_limit
            and memory_within_limit
            and substantive_gain
        )

        candidate_artifact: dict[str, Any] | None = None
        if candidate_qualified:
            candidate_path = HERE / "candidate_default_optimizer.msh"
            gmsh.write(str(candidate_path))
            candidate_artifact = {
                "path": candidate_path.name,
                "bytes": candidate_path.stat().st_size,
                "sha256": sha256(candidate_path),
            }

        try:
            gmsh_version = str(gmsh.option.getString("General.Version"))
        except Exception:
            gmsh_version = str(getattr(gmsh, "__version__", "unknown"))

        run_report: dict[str, Any] = {
            "schema": "vesselforge.gmsh_mesh_quality_probe_v2.v1",
            "status": "COMPLETED",
            "outcome": "QUALIFIED_CANDIDATE" if candidate_qualified else "NO_QUALIFIED_CANDIDATE",
            "purpose": "Re-run one default Gmsh tetra optimizer pass with Mesh.Renumber set to 0 and exact tag capture to distinguish tag renumbering from actual coordinate/surface changes.",
            "input": {
                "source_mesh_path": str(helper.SOURCE_MSH.relative_to(REPO)),
                "source_mesh_sha256": sha256(helper.SOURCE_MSH),
                "source_npz_sha256": sha256(helper.SOURCE_NPZ),
                "source_report_sha256": sha256(helper.SOURCE_REPORT),
                "frozen_helper_script_sha256": sha256(FROZEN_HELPERS),
                "source_ancestry_status": source_report["source_face_ancestry"]["status"],
            },
            "gmsh": {
                "version": gmsh_version,
                "optimizer": "default (empty method string)",
                "force": True,
                "niter": 1,
                "dimTags": [[3, tag] for tag in volume_tags],
                "default_Mesh.Renumber_at_initialization": default_renumber,
                "Mesh.Renumber_set_before_open": renumber_before_open,
                "Mesh.Renumber_after_open_before_optimize": renumber_after_open,
                "Mesh.Renumber_after_optimize": renumber_after_optimize,
                "renumber_option_semantics_source": "Official Gmsh 4.15.2 manual defines Mesh.Renumber as renumbering nodes and elements in a continuous sequence after mesh generation (default 1); this experiment records and sets it to 0 before optimize without claiming that the option itself guarantees optimizer tag stability.",
            },
            "timing": {
                "optimizer_wall_s": optimize_wall_s,
                "process_wall_s": time.monotonic() - started,
                "process_wall_cap_s": MAX_PROCESS_SECONDS,
            },
            "resources": {
                "source_forecast_tetrahedra": int(source_report["resource_forecast"]["estimated_tetrahedra"]),
                "source_forecast_peak_memory_bytes": memory_forecast,
                "declared_tetrahedron_cap": MAX_TETRAHEDRA,
                "declared_peak_memory_cap_bytes": MAX_DECLARED_MEMORY_BYTES,
                "actual_before_tetrahedra": int(before_quality["tetrahedra"]),
                "actual_after_tetrahedra": int(after_quality["tetrahedra"]),
                "actual_process_peak_memory_sampled": False,
            },
            "baseline": {
                "source_alignment": source_alignment_before,
                "quality": before_quality,
                "tetra_audit": before_audit,
            },
            "optimized": {
                "source_index_alignment": source_alignment_after,
                "quality": after_quality,
                "tetra_audit": after_audit,
            },
            "tag_and_surface_diagnosis": {
                "node_count_before": int(len(before["node_tags"])),
                "node_count_after": int(len(after["node_tags"])),
                "direct_node_tags_equal": direct_node_tags_equal,
                "coordinates_bitwise_equal_by_same_node_tag": direct_coordinates_bitwise_by_tag,
                "exact_coordinate_key_bijection_available": exact_bijection,
                "exact_coordinate_keys_unique_before": unique_before,
                "exact_coordinate_keys_unique_after": unique_after,
                "coordinate_key_set_equal": exact_key_sets_equal,
                "duplicate_coordinate_key_count_before": int(sum(count > 1 for count in before_counts.values())),
                "duplicate_coordinate_key_count_after": int(sum(count > 1 for count in after_counts.values())),
                "same_tag_nodes_with_nonbitwise_coordinate_change": int(np.count_nonzero(~coordinate_rows_bitwise_equal)),
                "max_coordinate_displacement_by_same_node_tag_m": float(np.max(coordinate_displacement_m)),
                "exact_coordinate_tag_permutation_count": int(
                    sum(old_tag != new_tag for old_tag, new_tag in exact_coordinate_tag_map.items())
                ) if exact_bijection else None,
                "surface_entities_before": int(len(surface_maps_before)),
                "surface_entities_after": int(len(surface_maps_after)),
                "surface_element_tags_and_oriented_node_connectivity_equal_by_exact_element_tag": bool(surface_connectivity_equal_by_exact_element_tag),
                "surface_connectivity_equal_after_exact_coordinate_tag_mapping": bool(mapped_surface_connectivity_equal) if exact_bijection else None,
                "same_indexed_boundary_coordinates_bitwise_equal": bool(surface_direct["surface_coordinates_bitwise_equal_by_exact_node_tag"]),
                "surface_direct_same_tag_comparison": surface_direct,
                "tetrahedron_element_tag_sets_equal": bool(cell_tag_sets_equal),
                "tetrahedron_tags_only_before": int(len(set(cell_connectivity_before) - set(cell_connectivity_after))),
                "tetrahedron_tags_only_after": int(len(set(cell_connectivity_after) - set(cell_connectivity_before))),
                "oriented_tetra_connectivity_equal_for_common_exact_element_tags": bool(same_connectivity_for_common_cell_tags),
                "same_tag_tetra_connectivity_changes": int(sum(cell_connectivity_before[tag] != cell_connectivity_after[tag] for tag in common_cell_tags)),
                "actual_physical_boundary_change_diagnosed": bool(not surface_preserved),
                "interpretation": (
                    "Exact coordinate keys establish an unambiguous old-to-new node-tag permutation; geometry was unchanged while raw tags differed."
                    if exact_bijection and not direct_node_tags_equal and mapped_surface_connectivity_equal
                    else "In this Mesh.Renumber=0 run, boundary/interface coordinates and oriented triangle connectivity are exactly preserved under the same node and element tags. This does not retroactively prove the cause of the earlier run's raw-tag mismatch because its post-run arrays were not retained."
                    if surface_preserved
                    else "The same-tag boundary/interface comparison detects a change in this run; no renumber-only explanation is asserted."
                ),
            },
            "decision": {
                "surface_preserved_by_same_indexed_tags_and_bitwise_coordinates": surface_preserved,
                "tetra_audit_pass": audit_pass,
                "positive_orientation_pass": bool(
                    after_quality["negative_oriented_tetrahedra"] == 0
                    and after_quality["zero_or_nonfinite_determinants"] == 0
                ),
                "tetrahedron_cap_pass": t4_within_limit,
                "declared_memory_forecast_cap_pass": memory_within_limit,
                "minimum_altitude_gain_fraction": altitude_gain_fraction,
                "minimum_altitude_gain_threshold_fraction": MIN_ALTITUDE_GAIN_FRACTION,
                "substantive_altitude_gain_pass": substantive_gain,
                "candidate_written": candidate_artifact is not None,
                "candidate_artifact": candidate_artifact,
                "candidate_gate": "same indexed boundary/interface node tags, bitwise coordinates and exact element-tag triangle connectivity; tetra_audit PASS; all positive cells; resource caps; minimum tetra altitude improves by more than 0.1%",
            },
            "limitations": [
                "No STEP geometry, loading, constitutive model or discretization order was changed; no solver evolution was run.",
                "Source exterior face ancestry remains PRESENT_BUT_UNBOUND and was not inferred.",
                "The source reports a forecast rather than sampled peak memory; this process uses one fresh model and one optimizer call.",
                "This disposable v5 diagnostic is not the latest v6 mesh or an accepted physical mother.",
            ],
        }
        return run_report
    finally:
        if initialized:
            gmsh.finalize()
        _ = dll_handle


def controller() -> int:
    script = Path(__file__).resolve()
    command = [sys.executable, str(script), "--worker"]
    started = time.monotonic()
    with STDOUT_PATH.open("wb") as stdout, STDERR_PATH.open("wb") as stderr:
        child = subprocess.Popen(command, cwd=str(REPO), stdout=stdout, stderr=stderr)
        timeout_reason = None
        while child.poll() is None:
            elapsed = time.monotonic() - started
            log_bytes = (STDOUT_PATH.stat().st_size if STDOUT_PATH.exists() else 0) + (
                STDERR_PATH.stat().st_size if STDERR_PATH.exists() else 0
            )
            if elapsed > MAX_PROCESS_SECONDS:
                timeout_reason = "worker process exceeded 110 second wall cap"
                child.kill()
                break
            if log_bytes > MAX_LOG_BYTES:
                timeout_reason = "worker stdout/stderr exceeded 256 MiB output cap"
                child.kill()
                break
            time.sleep(0.1)
        child.wait(timeout=5)
    if timeout_reason:
        payload = {
            "schema": "vesselforge.gmsh_mesh_quality_probe_v2.v1",
            "status": "BOUNDED_ABORT",
            "outcome": "NO_CANDIDATE",
            "reason": timeout_reason,
            "controller_wall_s": time.monotonic() - started,
        }
    elif child.returncode != 0:
        payload = {
            "schema": "vesselforge.gmsh_mesh_quality_probe_v2.v1",
            "status": "WORKER_FAILED",
            "outcome": "NO_CANDIDATE",
            "worker_return_code": child.returncode,
            "controller_wall_s": time.monotonic() - started,
            "stderr_tail": STDERR_PATH.read_text(encoding="utf-8", errors="replace")[-8000:],
        }
    else:
        payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        payload["controller_wall_s"] = time.monotonic() - started
    payload["runner_sha256"] = sha256(script)
    payload["output_limits"] = {
        "worker_stdout_bytes": STDOUT_PATH.stat().st_size if STDOUT_PATH.exists() else 0,
        "worker_stderr_bytes": STDERR_PATH.stat().st_size if STDERR_PATH.exists() else 0,
        "worker_log_cap_bytes": MAX_LOG_BYTES,
        "run_v2_file_cap_bytes": MAX_LOG_BYTES,
    }
    REPORT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    generated_bytes = sum(path.stat().st_size for path in HERE.rglob("*") if path.is_file())
    payload["output_limits"]["run_v2_file_bytes_total"] = generated_bytes
    payload["output_limits"]["run_v2_files_under_cap"] = generated_bytes <= MAX_LOG_BYTES
    if generated_bytes > MAX_LOG_BYTES:
        payload["status"] = "OUTPUT_CAP_EXCEEDED"
        payload["outcome"] = "NO_CANDIDATE"
    REPORT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0 if payload.get("status") == "COMPLETED" else 1


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        result = run_worker()
        REPORT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return 0 if result.get("status") == "COMPLETED" else 2
    return controller()


if __name__ == "__main__":
    raise SystemExit(main())
