"""Command-line interface for the independent VF prototype."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .asset import create_asset_package
from .geometry import VesselSpec
from .schema import validate_asset


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vesselforge", description="Build or validate a forge.asset.v1 prototype")
    sub = parser.add_subparsers(dest="command", required=True)
    generate = sub.add_parser("generate", help="generate one small swept-handle vessel package")
    generate.add_argument("--out", required=True, type=Path)
    generate.add_argument("--pattern", choices=("four_bands", "three_bands"), default="four_bands")
    generate.add_argument("--seed", type=int, default=20261003)
    generate.add_argument("--body-width-mm", type=float, default=41.0)
    generate.add_argument("--body-height-mm", type=float, default=56.0)
    generate.add_argument("--wall-mm", type=float, default=4.0)
    generate.add_argument("--handle-radius-mm", type=float, default=2.6)
    generate.add_argument("--handle-outreach-mm", type=float, default=30.0)
    generate.add_argument("--handle-low-z-mm", type=float, default=12.0)
    generate.add_argument("--handle-high-z-mm", type=float, default=44.0)
    validate = sub.add_parser("validate", help="validate a forge.asset.v1 asset directory")
    validate.add_argument("asset_dir", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "generate":
        spec = VesselSpec(
            body_width_mm=args.body_width_mm,
            body_height_mm=args.body_height_mm,
            wall_mm=args.wall_mm,
            handle_radius_mm=args.handle_radius_mm,
            handle_outreach_mm=args.handle_outreach_mm,
            handle_low_z_mm=args.handle_low_z_mm,
            handle_high_z_mm=args.handle_high_z_mm,
        )
        result = create_asset_package(args.out, pattern=args.pattern, seed=args.seed, spec=spec)
    else:
        result = validate_asset(args.asset_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

