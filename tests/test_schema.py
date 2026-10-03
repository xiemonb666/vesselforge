from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from vesselforge.schema import AssetValidationError, package_file, validate_asset


def test_package_paths_reject_escape_and_absolute(tmp_path: Path) -> None:
    root = tmp_path / "asset"
    root.mkdir()
    for unsafe in ("../secret", "/outside", "C:/outside", "..\\secret", "fields/../../secret"):
        with pytest.raises(AssetValidationError):
            package_file(root, unsafe)


def test_package_path_accepts_nested_file(tmp_path: Path) -> None:
    root = tmp_path / "asset"
    (root / "geometry").mkdir(parents=True)
    expected = root / "geometry" / "surface.npz"
    expected.write_bytes(b"asset")
    assert package_file(root, "geometry/surface.npz") == expected.resolve()


def test_validator_detects_manifest_material_binding_mismatch(sample_packages, tmp_path: Path) -> None:
    asset = sample_packages[0]
    isolated = tmp_path / "asset_copy"
    shutil.copytree(asset, isolated)
    manifest_path = isolated / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["ornament"]["recipe"]["material_binding_id"] = "other-material"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(AssetValidationError, match="material binding"):
        validate_asset(isolated)


def test_validator_separates_contract_and_geometry_status(sample_packages) -> None:
    result = validate_asset(sample_packages[0])
    assert result["contract_status"] == "PASS"
    assert result["geometry_status"] == "PASS"
    assert result["historical_style_validation"] == "NOT_VALIDATED"

