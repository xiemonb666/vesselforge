from __future__ import annotations

from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "vesselforge" / "src"))

from vesselforge.ornament_fields import (  # noqa: E402
    GeometricRingBand,
    RepeatedMotif,
    WavingBand,
    evaluate_ornament_stack,
)


def main() -> None:
    out = Path(__file__).resolve().parent
    theta = np.linspace(-np.pi, np.pi, 721)
    z_mm = np.linspace(8.0, 49.0, 520)
    theta_grid, z_grid = np.meshgrid(theta, z_mm)
    radius_mm = 18.0
    xyz = np.stack(
        [radius_mm * np.cos(theta_grid), radius_mm * np.sin(theta_grid), z_grid], axis=-1
    )
    base = (0.72, 0.57, 0.40)
    fields = (
        GeometricRingBand(field_id="level-ring", center_z_mm=18.0, width_mm=2.2,
                          pigment_color_linear_rgb=(0.18, 0.045, 0.025),
                          base_material_color_linear_rgb=base),
        WavingBand(field_id="wave-band", center_z_mm=31.0, width_mm=2.0,
                   path_amplitude_mm=4.0, repeat_count=6, phase_rad=0.35,
                   pigment_color_linear_rgb=(0.78, 0.20, 0.06),
                   base_material_color_linear_rgb=base),
        RepeatedMotif(field_id="repeated-motifs", center_z_mm=16.0, z_pitch_mm=8.0,
                      angular_repeats=16, angular_phase_rad=0.12,
                      angular_half_width_fraction=0.29, z_half_height_fraction=0.33,
                      pigment_color_linear_rgb=(0.055, 0.045, 0.035),
                      base_material_color_linear_rgb=base),
        GeometricRingBand(field_id="raised-ring", effect="raised", relief_amplitude_mm=0.65,
                          center_z_mm=43.0, width_mm=2.6,
                          pigment_color_linear_rgb=(0.47, 0.23, 0.08),
                          base_material_color_linear_rgb=base),
    )
    result = evaluate_ornament_stack(xyz, fields)
    base_image = result.base_material_color_linear_rgb
    alpha = result.pigment_opacity[..., None]
    preview_rgb = base_image * (1.0 - alpha) + result.pigment_color_linear_rgb * alpha

    figure, axes = plt.subplots(2, 1, figsize=(13, 7.5), sharex=True, constrained_layout=True)
    axes[0].imshow(preview_rgb, origin="lower", aspect="auto",
                   extent=(-180, 180, z_mm[0], z_mm[-1]), interpolation="nearest")
    axes[0].set_ylabel("Rest-coordinate z (mm)")
    axes[0].set_title("Procedural ornament layers evaluated on a cylindrical rest-coordinate grid")
    image = axes[1].imshow(result.relief_height_mm, origin="lower", aspect="auto",
                           extent=(-180, 180, z_mm[0], z_mm[-1]), interpolation="nearest",
                           cmap="coolwarm", vmin=-0.7, vmax=0.7)
    axes[1].set_xlabel("Rest-coordinate theta (degrees)")
    axes[1].set_ylabel("Rest-coordinate z (mm)")
    figure.colorbar(image, ax=axes[1], label="Signed scalar relief suggestion (mm)")
    for axis in axes:
        axis.grid(False)
        axis.set_xlim(-180, 180)
    figure.savefig(out / "ornament_fields_preview.png", dpi=160)
    plt.close(figure)


if __name__ == "__main__":
    main()
