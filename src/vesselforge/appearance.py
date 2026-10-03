"""Rule-based, painted-only appearance evaluated in asset-local rest coordinates."""

from __future__ import annotations

from typing import Any

import numpy as np



PALE_SLIP = (0.66, 0.49, 0.34)
DARK_PAINT = (0.095, 0.032, 0.018)
RED_PAINT = (0.48, 0.05, 0.025)

PATTERNS: dict[str, dict[str, Any]] = {
    "four_bands": {
        "bands": [
            {"center_z_mm": 15.0, "width_mm": 1.5, "color": "dark"},
            {"center_z_mm": 25.0, "width_mm": 1.2, "color": "dark"},
            {"center_z_mm": 34.0, "width_mm": 1.2, "color": "red"},
            {"center_z_mm": 43.0, "width_mm": 1.5, "color": "dark"},
        ]
    },
    "three_bands": {
        "bands": [
            {"center_z_mm": 18.0, "width_mm": 2.0, "color": "red"},
            {"center_z_mm": 29.0, "width_mm": 1.0, "color": "dark"},
            {"center_z_mm": 40.0, "width_mm": 2.0, "color": "red"},
        ]
    },
}


def make_recipe(pattern: str, material_id: str, spec: VesselSpec) -> dict[str, Any]:
    if pattern not in PATTERNS:
        raise ValueError(f"unsupported prototype pattern: {pattern}")
    scale_z = spec.body_height_mm / 56.0
    bands = [
        {**band, "center_z_mm": band["center_z_mm"] * scale_z, "width_mm": band["width_mm"] * scale_z}
        for band in PATTERNS[pattern]["bands"]
    ]
    return {
        "pattern_id": pattern,
        "material_binding_id": material_id,
        "coordinate_map": "cylindrical_z_up_mm",
        "target_region_codes": [1],
        "fracture_region_codes_excluded": [255],
        "bands": bands,
        "palette_linear_rgb": {
            "base": list(PALE_SLIP),
            "dark": list(DARK_PAINT),
            "red": list(RED_PAINT),
        },
        "surface_finish": {"model": "constant_lambertian_preview", "roughness": 0.78},
        "geometry_relief_mm": 0.0,
        "historical_style_validation": "NOT_VALIDATED",
        "source_note": "Deterministic workflow demonstration recipe; not matched to a dated or provenanced historical specimen.",
    }


def surface_fields(
    vertices_material_xyz_mm: np.ndarray,
    faces: np.ndarray,
    recipe: dict[str, Any],
    classified_face_regions: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Produce appearance fields using authoritative canonical B-rep regions.

    Colors are evaluated from triangle centroids in immutable rest/material
    coordinates. Region assignment itself comes from the same canonical STEP
    B-rep face that generated the triangle; centroid/normal guessing is not
    used. A downstream fragment renderer can repeat the color rule in rest
    coordinates; it must not use fragment world positions.
    """
    tri_xyz = vertices_material_xyz_mm[faces.astype(np.int64, copy=False)].astype(np.float64)
    centroids = tri_xyz.mean(axis=1)
    region = np.asarray(classified_face_regions, dtype=np.uint8)
    if region.shape != (len(faces),) or not set(np.unique(region).astype(int)).issubset({1, 2, 3, 4, 5}):
        raise ValueError("per-triangle regions must come from complete canonical B-rep face classification")
    albedo = np.tile(np.asarray(PALE_SLIP, dtype=np.float32), (len(faces), 1))
    roughness = np.full(len(faces), 0.78, dtype=np.float32)
    palette = recipe["palette_linear_rgb"]
    for band in recipe["bands"]:
        select = (
            np.isclose(region, 1)
            & (np.abs(centroids[:, 2] - band["center_z_mm"]) <= band["width_mm"] / 2)
        )
        color = palette[band["color"]]
        albedo[select] = np.asarray(color, dtype=np.float32)
        roughness[select] = np.float32(0.78)
    return region, albedo, roughness


def evaluate_continuous_albedo_at_z(z_mm: np.ndarray | float, recipe: dict[str, Any]) -> np.ndarray:
    """Evaluate the painted rule from immutable cylindrical rest height.

    This is a coordinate-space rule, independent of triangle centroids and mesh
    density. Renderers should interpolate ``vertices_material_xyz_mm`` and
    evaluate this recipe on the rest/material coordinates, never fragment world
    coordinates.
    """
    z = np.asarray(z_mm, dtype=np.float64)
    palette = recipe["palette_linear_rgb"]
    base = np.asarray(palette["base"], dtype=np.float64)
    result = np.broadcast_to(base, (*z.shape, 3)).copy()
    for band in recipe["bands"]:
        selected = np.abs(z - float(band["center_z_mm"])) <= float(band["width_mm"]) / 2
        result = np.where(
            np.expand_dims(selected, axis=-1),
            np.asarray(palette[band["color"]], dtype=np.float64),
            result,
        )
    return result


def per_face_band_coverage(
    vertices_material_xyz_mm: np.ndarray,
    faces: np.ndarray,
    face_region: np.ndarray,
    recipe: dict[str, Any],
) -> dict[str, Any]:
    """Audit how the low-resolution per-face approximation sampled each band."""
    triangles = vertices_material_xyz_mm[faces.astype(np.int64, copy=False)].astype(np.float64)
    centroids = triangles.mean(axis=1)
    areas = np.linalg.norm(
        np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1
    ) / 2
    outer = face_region == 1
    coverage = []
    for band in recipe["bands"]:
        within = outer & (
            np.abs(centroids[:, 2] - float(band["center_z_mm"])) <= float(band["width_mm"]) / 2
        )
        area_mm2 = float(areas[within].sum())
        count = int(np.count_nonzero(within))
        coverage.append(
            {
                "center_z_mm": float(band["center_z_mm"]),
                "width_mm": float(band["width_mm"]),
                "color": band["color"],
                "covered_face_count": count,
                "covered_triangle_area_mm2": area_mm2,
                "status": "PASS" if count else "FAIL",
                "reason": None if count else "no outer-body triangle centroid fell inside this narrow band",
            }
        )
    return {
        "per_face_approximation_status": "PASS" if all(item["status"] == "PASS" for item in coverage) else "FAIL",
        "method": "triangle-centroid coverage on outer-body faces; diagnostic approximation only",
        "bands": coverage,
    }

