from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from vesselforge.tetra_audit import MeshAuditError, audit_tetra_mesh


MESH_PATH = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "continuation_20261015"
    / "bowl_tetra"
    / "run02"
    / "mesh"
    / "mesh.npz"
)


def _load_mesh() -> dict[str, np.ndarray]:
    with np.load(MESH_PATH, allow_pickle=False) as archive:
        return {key: archive[key] for key in archive.files}


def _audit(mesh: dict[str, np.ndarray], **overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "stored_volume_m3": mesh["volume_m3"],
        "center_m": (0.0, 0.0, 0.012),
        "inner_radius_m": 0.008,
        "outer_radius_m": 0.012,
        "interface_plane_x_m": 0.0,
        "expected_volume_m3": 2.0 * np.pi / 3.0 * (0.012**3 - 0.008**3),
        "expected_interface_area_m2": np.pi / 2.0 * (0.012**2 - 0.008**2),
    }
    defaults.update(overrides)
    interface_triangles = defaults.pop("interface_triangles", mesh["interface_triangles"])
    interface_parents = defaults.pop("interface_parents", mesh["interface_parents"])
    return audit_tetra_mesh(
        mesh["nodes_m"],
        mesh["tets"],
        mesh["source_partition_volume"],
        interface_triangles,
        interface_parents,
        **defaults,
    )


def test_run02_actual_mesh_passes_independent_topology_and_volume_audit() -> None:
    mesh = _load_mesh()
    report = _audit(mesh)

    assert report["status"] == "PASS"
    assert report["counts"]["nodes"] == 1212
    assert report["counts"]["tetrahedra"] == 4342
    assert report["counts"]["two_parent_internal_faces"] == 7738
    assert report["counts"]["cross_partition_faces"] == 158
    assert report["exterior_surface"]["closed_oriented_vertex_manifold"]
    assert report["exterior_surface"]["edges_with_incidence_other_than_two"] == 0
    assert report["interface"]["parent_pairs_exact"]
    assert report["interface"]["parents_from_distinct_partitions"]
    assert report["interface"]["relative_area_error"] < 0.01
    assert report["volume"]["exterior_boundary_relative_error"] < 1e-9
    assert report["volume"]["partition_balance_relative_error"] < 0.01
    assert all(
        part["analytic_half_volume_relative_error"] < 0.01
        for part in report["volume"]["partitions"].values()
    )
    assert report["quality"]["minimum_altitude_m"]["min"] > 0.0
    assert report["quality"]["worst_vertex_edge_matrix_condition"]["max"] < 100.0

    geometry = report["geometry_sampling"]
    assert geometry["tetrahedron_centroids_outside_material"] == 0
    chord_samples = geometry["inner_spherical_boundary_chord_sampling"]
    assert chord_samples["inner_radius_boundary_triangles"] > 0
    assert chord_samples["samples_inside_analytic_cavity"] > 0
    assert 0.0 < chord_samples["maximum_sampled_radial_intrusion_mm"] < 0.1
    assert geometry["continuous_global_containment_certified"] is False


def test_missing_partition_interface_face_is_detected() -> None:
    mesh = _load_mesh()

    with pytest.raises(MeshAuditError, match="do not exactly match cross-partition faces"):
        _audit(
            mesh,
            interface_triangles=mesh["interface_triangles"][:-1],
            interface_parents=mesh["interface_parents"][:-1],
        )


def test_duplicate_tetrahedron_is_detected_before_it_can_fake_face_incidence() -> None:
    mesh = _load_mesh()
    duplicated = dict(mesh)
    duplicated["tets"] = np.concatenate((mesh["tets"], mesh["tets"][:1]), axis=0)
    duplicated["source_partition_volume"] = np.concatenate(
        (mesh["source_partition_volume"], mesh["source_partition_volume"][:1])
    )
    duplicated["volume_m3"] = np.concatenate((mesh["volume_m3"], mesh["volume_m3"][:1]))

    with pytest.raises(MeshAuditError, match="duplicate tetrahedron"):
        _audit(duplicated)


def test_three_tetrahedra_on_one_face_are_rejected_as_non_manifold() -> None:
    nodes = np.asarray(
        [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (0.0, 0.0, -1.0),
            (1.0, 1.0, 1.0),
        ]
    )
    tets = np.asarray(((0, 1, 2, 3), (0, 2, 1, 4), (0, 1, 2, 5)), dtype=np.int64)

    with pytest.raises(MeshAuditError, match="more than two parents"):
        audit_tetra_mesh(nodes, tets, np.ones(3, dtype=np.int64))


def test_reversed_tetrahedron_orientation_is_rejected() -> None:
    mesh = _load_mesh()
    reversed_tets = mesh["tets"].copy()
    reversed_tets[0, [0, 1]] = reversed_tets[0, [1, 0]]

    with pytest.raises(MeshAuditError, match="positive orientation"):
        audit_tetra_mesh(
            mesh["nodes_m"],
            reversed_tets,
            mesh["source_partition_volume"],
        )
