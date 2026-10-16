"""Small fail-closed validator for the agreed forge.asset.v1 package contract."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np


class AssetValidationError(ValueError):
    """Raised when a forge.asset.v1 package is incomplete or unsafe."""


def _fail(message: str) -> None:
    raise AssetValidationError(message)


def package_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        _fail(f"invalid package-relative path: {relative!r}")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        _fail(f"unsafe package-relative path: {relative!r}")
    root_real = root.resolve(strict=True)
    candidate = root.joinpath(*pure.parts)
    cursor = root
    for part in pure.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            _fail(f"symlink is not permitted in asset packages: {relative!r}")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root_real)
    except ValueError:
        _fail(f"path escapes asset package: {relative!r}")
    if not resolved.is_file():
        _fail(f"asset entry is not a regular file: {relative!r}")
    return resolved


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(root: Path) -> dict[str, Any]:
    path = package_file(root, "manifest.json")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"manifest.json is not valid UTF-8 JSON: {exc}")
    if not isinstance(value, dict):
        _fail("manifest root must be a JSON object")
    return value


def validate_asset(root_path: str | os.PathLike[str]) -> dict[str, Any]:
    root = Path(root_path)
    if not root.is_dir():
        _fail(f"asset package directory does not exist: {root}")
    manifest = load_manifest(root)
    if manifest.get("schema") != "forge.asset.v1":
        _fail("schema must be forge.asset.v1")
    if manifest.get("units") != {"length": "mm", "time": "s", "mass": "kg"}:
        _fail("units do not match forge.asset.v1 canonical units")
    if manifest.get("frame") != "right_handed_z_up":
        _fail("frame must be right_handed_z_up")
    for field in ("geometry", "fields", "material", "ornament", "files", "provenance", "validation"):
        if not isinstance(manifest.get(field), dict):
            _fail(f"manifest.{field} must be an object")

    files = manifest["files"]
    if "manifest.json" in files or not files:
        _fail("files must enumerate package payloads and exclude manifest.json")
    for relative, expected in files.items():
        if not isinstance(expected, dict) or set(("sha256", "bytes")) - expected.keys():
            _fail(f"files[{relative!r}] must provide sha256 and bytes")
        path = package_file(root, relative)
        stat = path.stat()
        if stat.st_size != expected["bytes"]:
            _fail(f"byte count mismatch for {relative!r}")
        if sha256_file(path) != expected["sha256"]:
            _fail(f"sha256 mismatch for {relative!r}")

    geometry = manifest["geometry"]
    fields = manifest["fields"]
    surface_path = geometry.get("surface_npz")
    fields_path = fields.get("surface_fields_npz")
    report_path = manifest["validation"].get("report")
    provenance_spec = manifest.get("provenance", {}).get("spec")
    if not isinstance(provenance_spec, dict):
        _fail("manifest.provenance.spec must be an object")
    lineage_path = provenance_spec.get("mesh_lineage_npz")
    face_semantics_path = provenance_spec.get("face_semantics_report")
    for relative in (surface_path, fields_path, report_path, lineage_path, face_semantics_path):
        if relative not in files:
            _fail(f"manifest references a payload not enumerated in files: {relative!r}")
    step_path = geometry.get("solid_step")
    if step_path is not None and step_path not in files:
        _fail("geometry.solid_step must reference a hashed file")
    if manifest["validation"].get("scope") != "geometry_only":
        _fail("prototype validation scope must be geometry_only")
    if manifest["validation"].get("status") not in {"PASS", "FAIL", "PENDING"}:
        _fail("validation status is invalid")
    try:
        report = json.loads(package_file(root, report_path).read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"geometry validation report is not valid UTF-8 JSON: {exc}")
    if report.get("scope") != "geometry_only":
        _fail("geometry validation report must declare geometry_only scope")
    if report.get("status") != manifest["validation"].get("status"):
        _fail("manifest validation status disagrees with the referenced report")

    try:
        face_semantics = json.loads(package_file(root, face_semantics_path).read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"face semantics report is not valid UTF-8 JSON: {exc}")
    if not isinstance(face_semantics, dict):
        _fail("face semantics report root must be an object")
    step_path = geometry.get("solid_step")
    step_entry = files.get(step_path) if isinstance(step_path, str) else None
    if not isinstance(step_entry, dict):
        _fail("geometry.solid_step must reference a hashed canonical STEP file")
    if face_semantics.get("schema") != "vf.brep-face-semantics.v1" or face_semantics.get("status") != "PASS":
        _fail("canonical B-rep face semantics must be complete and PASS")
    if face_semantics.get("canonical_step_sha256") != step_entry.get("sha256"):
        _fail("face semantics report does not identify the hashed canonical STEP payload")
    if provenance_spec.get("canonical_step_sha256") != step_entry.get("sha256"):
        _fail("manifest provenance does not identify the hashed canonical STEP payload")
    classifier = face_semantics.get("classifier")
    if not isinstance(classifier, str) or not classifier.startswith("vf.canonical-step-face-semantics/"):
        _fail("face semantics report has no recognized classifier version")
    if provenance_spec.get("face_semantics_classifier") != classifier:
        _fail("manifest provenance classifier version disagrees with the face semantics report")
    backend = face_semantics.get("backend")
    if not isinstance(backend, dict) or not all(isinstance(backend.get(name), str) and backend.get(name) for name in ("cadquery_version", "ocp_module_version", "ocp_distribution_version")):
        _fail("face semantics report must identify CadQuery and OpenCascade backend versions")
    semantic_faces = face_semantics.get("faces")
    face_count = face_semantics.get("canonical_step_face_count")
    if not isinstance(semantic_faces, list) or not isinstance(face_count, int) or face_count != len(semantic_faces) or face_count < 1:
        _fail("face semantics report must enumerate every canonical B-rep face")
    code_by_brep_face: list[int] = []
    region_names = {1: "body_outer", 2: "body_inner", 3: "natural_rim", 4: "base", 5: "handle"}
    for expected_index, row in enumerate(semantic_faces):
        if not isinstance(row, dict) or row.get("face_index_zero_based") != expected_index:
            _fail("face semantics rows must be contiguous and ordered by canonical STEP face index")
        if row.get("status") != "CLASSIFIED" or row.get("classifier_version") != classifier:
            _fail(f"canonical B-rep face {expected_index} is UNKNOWN/PENDING or has inconsistent classifier version")
        if row.get("canonical_step_sha256") != step_entry.get("sha256"):
            _fail(f"canonical B-rep face {expected_index} has a stale STEP source hash")
        code = row.get("region_code")
        if isinstance(code, bool) or not isinstance(code, int) or code not in region_names or row.get("region_name") != region_names[code]:
            _fail(f"canonical B-rep face {expected_index} has an unknown or reserved region code")
        if not isinstance(row.get("classification_basis"), str) or not isinstance(row.get("classification_evidence"), dict):
            _fail(f"canonical B-rep face {expected_index} lacks auditable classification evidence")
        code_by_brep_face.append(int(code))

    try:
        with np.load(package_file(root, surface_path), allow_pickle=False) as arrays:
            vertices = arrays["vertices_mm"]
            faces = arrays["faces"]
        with np.load(package_file(root, fields_path), allow_pickle=False) as arrays:
            region = arrays["face_region"]
            albedo = arrays["albedo_linear_rgb"]
            roughness = arrays["roughness"]
            material_xyz = arrays["vertices_material_xyz_mm"]
        with np.load(package_file(root, lineage_path), allow_pickle=False) as arrays:
            triangle_source_faces = arrays["face_source_brep_index"]
    except (KeyError, ValueError, OSError) as exc:
        _fail(f"surface or fields NPZ is incomplete/invalid: {exc}")
    if vertices.dtype.kind != "f" or vertices.shape != (len(vertices), 3) or len(vertices) < 4:
        _fail("vertices_mm must be a floating point N×3 array")
    if not np.isfinite(vertices).all():
        _fail("vertices_mm contains a non-finite value")
    if faces.dtype.kind not in "iu" or faces.ndim != 2 or faces.shape[1] != 3 or len(faces) < 4:
        _fail("faces must be an integer F×3 array")
    if int(faces.min()) < 0 or int(faces.max()) >= len(vertices):
        _fail("faces contains an out-of-range vertex index")
    if region.shape != (len(faces),) or region.dtype.kind not in "iu":
        _fail("face_region must be an integer array with one value per face")
    if albedo.shape != (len(faces), 3) or albedo.dtype.kind != "f" or not np.isfinite(albedo).all():
        _fail("albedo_linear_rgb must be a finite floating F×3 array")
    if np.any(albedo < 0) or np.any(albedo > 1):
        _fail("albedo_linear_rgb values must lie in [0,1]")
    if roughness.shape != (len(faces),) or roughness.dtype.kind != "f" or not np.isfinite(roughness).all():
        _fail("roughness must be a finite floating F array")
    if np.any(roughness < 0) or np.any(roughness > 1):
        _fail("roughness values must lie in [0,1]")
    if material_xyz.shape != vertices.shape or material_xyz.dtype.kind != "f" or not np.isfinite(material_xyz).all():
        _fail("vertices_material_xyz_mm must be finite floating point N×3")
    if not np.array_equal(material_xyz, vertices):
        _fail("initial asset material coordinates must exactly equal canonical vertices")

    material = manifest["material"]
    material_id = material.get("id")
    if not isinstance(material_id, str) or not material_id.strip():
        _fail("material.id is required")
    mechanics = material.get("mechanics")
    if not isinstance(mechanics, dict) or set(("rho_kg_m3", "E_pa", "nu", "Gc_j_m2")) - mechanics.keys():
        _fail("material.mechanics must use canonical SI-named values")
    for name in ("rho_kg_m3", "E_pa", "Gc_j_m2"):
        value = mechanics.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            _fail(f"material.mechanics.{name} must be finite and positive")
    poisson = mechanics.get("nu")
    if isinstance(poisson, bool) or not isinstance(poisson, (int, float)) or not math.isfinite(poisson) or not (-1.0 < poisson < 0.5):
        _fail("material.mechanics.nu must be finite and in (-1, 0.5)")
    if material.get("calibration_status") != "UNVALIDATED_PROTOTYPE":
        _fail("prototype mechanics must remain UNVALIDATED_PROTOTYPE")
    recipe = manifest["ornament"].get("recipe")
    if manifest["ornament"].get("kind") != "painted" or not isinstance(recipe, dict):
        _fail("prototype ornament must be a painted rule recipe")
    if recipe.get("material_binding_id") != material_id:
        _fail("ornament material binding does not match material.id")
    if recipe.get("geometry_relief_mm") != 0.0:
        _fail("this painted-only prototype must declare zero geometric relief")
    if recipe.get("historical_style_validation") != "NOT_VALIDATED":
        _fail("historical style status must remain NOT_VALIDATED")
    allowed_regions = set(region_names)
    if not set(np.unique(region).astype(int)).issubset(allowed_regions):
        _fail("face_region contains an undeclared, UNKNOWN or reserved semantic code")
    if triangle_source_faces.shape != (len(faces),) or triangle_source_faces.dtype.kind not in "iu":
        _fail("face_source_brep_index must provide one integer canonical B-rep index per triangle")
    if len(triangle_source_faces) and (
        int(triangle_source_faces.min()) < 0 or int(triangle_source_faces.max()) >= len(code_by_brep_face)
    ):
        _fail("face_source_brep_index contains an out-of-range canonical B-rep index")
    if not np.array_equal(region, np.asarray(code_by_brep_face, dtype=region.dtype)[triangle_source_faces.astype(np.int64, copy=False)]):
        _fail("face_region does not follow canonical STEP triangle-to-B-rep lineage")
    if set(recipe.get("target_region_codes", [])) - allowed_regions:
        _fail("ornament targets contain an unknown semantic region")
    return {
        "schema": "forge.asset.v1",
        "contract_status": "PASS",
        "geometry_status": report["status"],
        "file_count": len(files),
        "vertex_count": int(len(vertices)),
        "triangle_count": int(len(faces)),
        "canonical_brep_face_count": int(face_count),
        "region_codes": sorted(int(value) for value in np.unique(region)),
        "mechanics_calibration_status": material["calibration_status"],
        "historical_style_validation": recipe["historical_style_validation"],
    }

