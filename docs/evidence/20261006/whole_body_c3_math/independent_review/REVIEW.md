# Whole-body C3 source-only independent review

Review status for freeze `6233665f3aff3b38f646db6562bfca8bf1e24c26ee02d4afd9d7325f3bcb0ab2`: **BLOCKED pending one output-root correction**. No curve constructor, profile sampler, PNG, CAD/OCC, STEP, or solver was run.

The pinned formula and unit correction is sound. With global parameter `s` measured in mm, `C` has mm, `C'` is dimensionless, `C''` has 1/mm, and `C'''` has 1/mm². The degree-seven Hermite poles in `profile_design.py` correctly encode the endpoint position and first three derivatives after scaling by `h`, `h²`, and `h³`; equal shared jets therefore give parametric C3 at each listed join. C3 gives continuous curvature derivative only where the curve is regular.

For arbitrary regular `s`, the frozen design now correctly states `κ = det(C′, C″)/|C′|³`, `C″ = v′T + κv²N`, and `N′ = −κC′`. Therefore a constant normal offset has `C_t′ = (1−tκ)C′`; `|tκ|<1` is a sufficient local regularity condition, not a global nonintersection or wall-thickness certificate. If `κ′` also matches at a regular seam, the exact offset is C2 there. A proved radius floor of 9 mm would imply `|3κ|≤1/3`, but no such full-span bound exists yet.

The planned driver’s strict derivative-pole projection and exact Bernstein determinant/speed bound are mathematically appropriate sufficient checks: positive projection gives a speed lower bound, the Bernstein coefficient hull bounds the determinant, and the four fixed de Casteljau subnets can tighten that bound without adding sample sites. These are source-level algorithm findings only; no poles or curvature values were evaluated. The fixed budget is 16 outer spans, 128 profile sites, and 16 pointwise offset probes (144 total). The ten inner spans remain unconstructed; global minimum wall, section nonintersection, and physical qualification remain UNKNOWN. Catalog heights 90/120 mm are mouth/body datums; the proposed rim crests give total heights 92/122 mm.

## Blocking source finding

In `diagnostic_driver_source_only.py`, `HERE` is the experiment directory `ShardForge/vesselforge/experiments/whole_body_c2_profiles_20261006`. For that path, `HERE.parents[2]` is the workspace root `ShardForge`, while the frozen `HERE.parents[3]` is its parent `Desktop`. Consequently `OUTPUT_ROOT` resolves to `C:\Users\xiemo\Desktop\tmp\review_20261006\whole_body_c2_profiles_20261006\fixed_outer_trial`, outside the workspace and away from the output path in the pinned review plan. This must be corrected before any run or plot. The driver was not called, so no outside path was created by this review.

The `root_ready=True` argument is a fail-closed default guard, not an identity-bound authorization mechanism; the external runner must still require root approval and verify frozen pins. This is a boundary note, not a second blocker for the one-line path fix.

## Frozen pins

- `profile_design.py`: `057233b930a2b8e0e3ef43a3568f1cb0e6e972baed97eeeeceb6459d9de8c951`
- `fixed_cases.json`: `e1e9c3cf659dbc59d99a18c4b70694201518be4f3aba09a57806402e732cf95a`
- `DESIGN_PROPOSAL.md`: `8b5c8b7e78c8d2e245f9ade1498e3dd3c5f69b0a7a82eaf593e3ea49b1b7dbbf`
- `CONTROL_HULL_DESIGN.md`: `9fab758e2bc43926f6fe2e82b8ee6b65e4d3fdbaebbca8da84e29f5feb0f4a2b`
- `diagnostic_driver_source_only.py`: `1ef8df70e7f6a8de24f5149603481b63a2f085f948c22193a10ff4c01b5d45c8`
- `REVIEW_PLAN.md`: `734be4d98d9aabc3e30e3385506a64b28cf31a376dd34e91d1b1e6538376811e`
- `FREEZE_MANIFEST.json`: `6233665f3aff3b38f646db6562bfca8bf1e24c26ee02d4afd9d7325f3bcb0ab2`
