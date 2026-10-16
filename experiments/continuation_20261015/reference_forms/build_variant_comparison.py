"""Create a generated-geometry-only side-elevation comparison matrix."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "outputs" / "family_variant_matrix_v1"
VARIANTS = (
    ("family_daily_deep_v1", "DEEPER BODY · H 62 mm"),
    ("family_daily_full_belly_v1", "FULLER BELLY · H 53 mm"),
    ("family_daily_broad_foot_v2", "WIDER FOOT · H 53 mm"),
)
PANEL_SIZE = (520, 520)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to overwrite comparison output: {OUTPUT}")
    output_dir = OUTPUT
    output_dir.mkdir(parents=True, exist_ok=False)

    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 19)
    except OSError:
        font = ImageFont.load_default()

    caption_height = 48
    canvas = Image.new("RGB", (PANEL_SIZE[0] * len(VARIANTS), PANEL_SIZE[1] + caption_height), (251, 250, 247))
    draw = ImageDraw.Draw(canvas)
    manifest_rows: list[dict[str, object]] = []
    for index, (directory_name, label) in enumerate(VARIANTS):
        candidate_dir = HERE / "outputs" / directory_name
        preview_path = candidate_dir / "preview.png"
        report_path = candidate_dir / "geometry_report.json"
        provenance_path = candidate_dir / "provenance.json"
        if not all(path.is_file() for path in (preview_path, report_path, provenance_path)):
            raise FileNotFoundError(f"variant output is incomplete: {candidate_dir}")
        with Image.open(preview_path) as preview:
            if preview.size != (1560, 1040):
                raise ValueError(f"unexpected preview dimensions in {preview_path}: {preview.size}")
            panel = preview.crop((0, 0, PANEL_SIZE[0], PANEL_SIZE[1])).convert("RGB")
        x = index * PANEL_SIZE[0]
        canvas.paste(panel, (x, caption_height))
        draw.text((x + 14, 12), label, fill=(34, 44, 51), font=font)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        manifest_rows.append(
            {
                "candidate_directory": directory_name,
                "label": label,
                "design_assumptions": provenance["design_assumptions"],
                "candidate_dimensions_mm": report["measurements"]["candidate_dimensions_mm"],
                "structural_geometry_status": report["candidate_geometry_status"],
                "artifact_sha256": report["measurements"]["artifact_sha256"],
                "preview_sha256": sha256(preview_path),
                "matrix_view": "crop of the candidate's own VTK orthographic side elevation; no source photographs included",
            }
        )

    matrix_path = output_dir / "family_side_elevation_matrix.png"
    canvas.save(matrix_path, format="PNG", optimize=True)
    manifest = {
        "schema": "vf.revolved_profile_family_variant_matrix.v1",
        "interpretation": "Three independently controlled geometry variations around the daily-use candidate family; not measured specimen profiles.",
        "source_images_included": False,
        "panels": manifest_rows,
        "matrix_sha256": sha256(matrix_path),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    total_bytes = sum(path.stat().st_size for path in output_dir.rglob("*") if path.is_file())
    if total_bytes > 64 * 1024 * 1024:
        raise RuntimeError(f"comparison output exceeds 64 MiB: {total_bytes} bytes")
    print(json.dumps({"output": str(output_dir), "matrix_sha256": manifest["matrix_sha256"], "output_bytes": total_bytes}, indent=2))


if __name__ == "__main__":
    main()
