from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def sample_packages(tmp_path_factory):
    from vesselforge.asset import create_asset_package

    root = tmp_path_factory.mktemp("vf-assets")
    first = root / "four_bands"
    second = root / "three_bands"
    create_asset_package(first, pattern="four_bands", seed=20261003)
    create_asset_package(second, pattern="three_bands", seed=20261003)
    return first, second

