# Whole-body C3 meridian proposal

Status: source/design proposal only. Nothing in this directory has been executed. No CAD, OCC, STEP, solver, curve sampler, or geometry constructor was run.

## Decision and failure being addressed

The catalog defaults are two fixed engineering examples, bowl and jar. The prior corner-fairing experiment moved selected vertices only 12% and protected the bowl maximum-radius apex; it therefore retained the artificial apex corner. It also faired the inside and outside independently. Its own bounded section-pair sample distances were 1.025229189 mm for bowl and 1.390641235 mm for jar while the catalog declared 3 mm radial offset. Those are finite section distances, not normal-wall or global minimum-wall proofs.

The proposed replacement uses degree-seven Hermite Beziers for the entire positive-radius meridian. Each semantic connection shares position and derivatives 1, 2, and 3 with its neighbor. The selected source jets have zero second and third derivatives at stations. Exact shared jets produce C3 continuity; where the curve is regular, signed curvature and its arc-length derivative are continuous. This C3 upgrade is required because a C2 outer curve alone does not generally give a C2 exact normal offset: the offset second derivative depends on the curvature derivative.

This is a new bounded geometry proposal, not an unconstrained fit. The source contains only fixed station data, rational endpoint jets, span parameter lengths, and the exact degree-seven Hermite pole formula. No parameters are searched or tuned.

## Fixed geometry

The bowl keeps its catalog stations through the upper body and fixes the radius apex at (60, 77.4). Two adjacent septic spans meet there with a shared vertical tangent. Their common second and third jets are zero, so the radius is stationary with zero curvature and zero curvature derivative at the apex. Their exact pole convex hulls are designed to stay at or inside r=60.

The jar keeps max radius 54 and the body-top apex at z=62. The old vertical max-radius segment’s lower artificial station (54, 40.8) is removed. One septic span reaches the fixed apex from the lower-body station (34.56, 16.8); a second leaves toward the shoulder station (49.68, 74). Both use the same vertical apex tangent and zero second/third jets. The pole hulls are designed to satisfy r≤54 while preserving the exact maximum radius.

The bowl clear mouth stays 108 mm and the jar clear mouth stays 46 mm. Their side-wall mouth points remain (54, 90) and (23, 120) on the inside, with outer mouth points (57, 90) and (26, 120). Each has a separate two-span degree-seven lip bridge with a fixed crest at (55.5, 92) for bowl and (24.5, 122) for jar. The catalog values 90 and 120 mm are mouth/body junction datums only; candidate total bounding-box heights are the fixed crest heights 92 and 122 mm.

The old catalog’s 3 mm declaration means radial meridian offset. The proposal reuses 3 mm only as a candidate Euclidean normal offset on the designated body/shoulder/neck spans. It makes no material-thickness or whole-section minimum-wall claim. The basal transition and lip bridge are outside this side-wall offset region.

## Section and offset API

The source API is intentionally small:

- Jet3 stores an exact RZ point and global-parameter derivatives d1, d2, d3.
- SpanJet3 stores one semantic name, positive parameter length h, and two endpoint Jet3 values.
- degree7_controls(span) returns eight exact rational Bezier poles using the endpoint position/1-2-3 derivative Hermite formulas. Its Fraction-only implementation covers the fixed rational outer spans.
- A later, separately reviewed build_outer_case(case) may join only the fixed spans in fixed_cases.json and must reject any mismatch between adjacent station jets.
- A later normal_offset_side(outer, distance_mm, inward) may exist only for the listed side-wall spans. It must return a per-span regularity status and the exact offset curve; it must not silently substitute radial offset or refit the result.

The inner-base-fairing endpoint is currently recorded as an exact expression containing sqrt(41) for bowl and sqrt(569) for jar. The current Fraction-only constructor does not construct those spans, and no inner-offset or inner-fairing pole builder exists in this source proposal. The ten inner spans are case/API design only, not executable source or a frozen run input.

For an arbitrary regular parameter s, let v=|C'|, T=C'/v, and N=(-T_z,T_r) for the inward normal convention used here. Signed curvature is κ=det(C',C'')/|C'|^3. In general C''=v'T+κv²N; the shorter identity C''=κ|C'|²N applies only when s is arc length. The normal derivative is N'=-κC', so the exact offset C_t=C+tN has tangent C_t'=(1−tκ)C'. A whole-span local regularity statement therefore needs a certified bound proving 1−tκ>0; the conservative acceptance condition is |tκ|<1. Body/shoulder radius target 9 mm would imply |3κ|≤1/3 only if that radius bound is itself proved over the complete spans. Sampling alone cannot prove it.

Even when |tκ|<1, global self-intersection and minimum separation from other section spans remain UNKNOWN until separately bounded. The lip bridge is a section closure, not a 3 mm normal-offset curve. The inner base fairing meets the offset side at the fixed lower-body station with a shared C2 jet; the section is not called uniform-wall below that station. Axis endpoints are rotational singularities and are excluded from wall regularity claims.

## Fixed geometry targets

The engineering screen for body and shoulder is minimum curvature radius at least 9 mm, three times the catalog’s 3 mm radial reference. The separate base and inner-base-fairing screens are 9 mm for bowl and 8.25 mm for jar, 1.5 times each catalog base-thickness declaration. These are geometric design screens only; they are not material or archaeological calibration.

The lip bridge is reported separately. If a fixed pole hull cannot preserve semantic bounds or if regularity/curvature targets fail, the result remains FAIL or UNKNOWN with the fixed case unchanged. No tolerance increase, local trim, or parameter search is allowed in this proposal.

## Exact control-hull checks and limits

For zero second and third endpoint jets, a span’s poles reduce to:

P0=p0
P1=p0+(h/7)v0
P2=p0+(2h/7)v0
P3=p0+(3h/7)v0
P4=p1-(3h/7)v1
P5=p1-(2h/7)v1
P6=p1-(h/7)v1
P7=p1

All input positions, derivatives, and lengths are decimal rationals in fixed_cases.json. The central design constraints were chosen so adjacent pole coordinates are monotone on each body span. At the fixed bowl apex, the incoming pole radii are at most 60 and the outgoing pole radii are at most 60. At the fixed jar apex, they are at most 54 on both sides. The Bezier convex-hull property then bounds radial overshoot without relying on samples. These are source-level design expectations to review against exact generated poles; the constructor has not been run and no curvature bound is claimed.

For monotonicity and a no-overshoot certificate, a future source review may check every exact degree-six derivative pole coordinate. For regularity it must also prove a strict positive lower bound on a common tangent projection across the complete span. If any of those exact checks fail, report the offending span and poles rather than modifying the case.

## Bounded next-stage plan

This proposal authorizes no run. The fixed case set is 16 outer spans: eight each for bowl and jar, including each rim closure split into two septic quadrants. This supersedes the earlier 14-span planning count. The ten inner spans remain unconstructed and must not be counted or attempted. No adaptive resampling or case change is allowed.

The next check, after a separate root READY, is limited to all 16 fixed outer spans (eight per family) and the exact data in fixed_cases.json. The source-only driver `diagnostic_driver_source_only.py` checks exact shared jets, control-pole bounds, strict tangent projections, and a determinant/speed-cubed curvature upper bound on four predeclared equal parameter subintervals. If a bound is too loose to prove a target, report UNKNOWN; do not subdivide further, alter a station, or retune h. Its entry point and PNG writer require an explicit `root_ready=True` argument, and it refuses to overwrite the fixed output files.

The fixed future sample budget is 144 evaluations: eight fixed parameters on each of 16 outer spans (128 total) and 16 fixed normal-offset point probes (eight per family). The exact four-piece interval bound is algebraic and is not an added sample grid. The inner wall and both inner-base fairings remain unconstructed and are excluded. One two-panel equal-scale RZ PNG will use the same 128 outer sample points, mark the fixed apex/mouth/crest, place legends outside the axes, and label units. It will be an actual plot of this mathematical source profile, not a CAD render or real-vessel image. No run has been performed or is authorized by this document.

## Provenance read during proposal

- Catalog default source SHA-256: e9d4bc1458a107208e537449d6526f1c0077d6d3afc6953a6200d86512f9c26f
- Prior smooth native adapter SHA-256: 7d745f48111d24b38a288714b580c0eeefe55415b2998351bf6144fa1cf4dab76
- Prior local corner fairing source SHA-256: 6c1e94150d769158c757469141aab23796b005421d3878b150271d375086d534
- Prior corner-fairing design audit SHA-256: e36bb07ea07469671babda8e35c11fcf5a4a15b1d624ed2a16eaf44a3f57cf7e

The prior smooth native adapter remains pinned to the beaker candidate and is not reused or edited here. No production or catalog source is changed by this proposal.
