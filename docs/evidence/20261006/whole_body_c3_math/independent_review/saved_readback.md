# Saved output independent readback

Status: **PASS for the saved-array arithmetic/count review, with one pointwise radius-target counterexample.** This readback consumed the frozen JSON, fixed-case source, execution receipt and existing PNG only. It did not call the candidate, construct controls, evaluate a curve, resample, run CAD, or run a solver.

## Verified saved structure

- The diagnostic JSON and PNG match their supplied SHA-256 pins. The author receipt records rc=0, 2.147634 s, empty stdout/stderr, and identical pre/post hashes for all seven frozen inputs.
- The saved result contains 16/16 feature-hull passes and 64/64 exact rational curvature-bound interval records (four per span). The interval statuses and rational values parse consistently.
- The saved target counts are 2 `BOUND_PROVES_TARGET`, 10 `UNKNOWN_BOUND_TOO_LOOSE_OR_TARGET_NOT_PROVED`, and 4 lip `REPORT_ONLY_NO_RADIUS_TARGET`. On the eight designated side spans, 3 bounds prove local 3 mm offset regularity and 5 remain UNKNOWN.
- There are 128 outer profile sites and 16 designated point probes. Each of the 16 saved probes uses a 3 mm offset, has a unit normal and positive tangent factor, and satisfies the independent arithmetic identity `factor = 1 − 3κ` within roundoff. Each stored offset point agrees with `outer point + 3 normal` within roundoff. This verifies internal saved-value consistency, not the unrecorded curve derivatives independently.

## Pointwise counterexample to the 9 mm target

The saved jar `outer_apex_to_shoulder` probe at `t=1/4` has `κ = 0.11222216144789537 mm⁻¹`, which exceeds `1/9 mm⁻¹`; the corresponding local radius is about 8.91 mm. This is a **pointwise counterexample** to the 9 mm minimum-radius target, even though the saved span-level status is the broad `UNKNOWN_BOUND_TOO_LOOSE_OR_TARGET_NOT_PROVED`. The record should be read as target not satisfied at this probe, while the full-span curvature maximum and exact violation extent remain unknown. Its saved offset tangent factor is positive (~0.66333), a point value only.

The existing PNG was visually checked. It shows the two fixed outer meridian profiles with equal radial/height scale and readable labels. It is a plot of the sampled mathematical source, not a CAD render; no inner wall is drawn.

Global minimum wall, section nonintersection, inner profile, material/physical suitability, and full-span qualification remain UNKNOWN. The original diagnostic JSON and PNG were not modified.

## Readback execution history

The reviewer’s first two attempts failed in reviewer-owned bookkeeping: run01’s side-span count gate included the eight non-offset spans, and run02 completed all arithmetic assertions but the JSON writer did not serialize Decimal receipt metadata. Both failure receipts are retained. Run03 completed with actual rc=0 in 94.796 ms, stdout 626 bytes and stderr 0 bytes. These reviewer-tooling failures do not change the saved candidate data or its conclusions.
