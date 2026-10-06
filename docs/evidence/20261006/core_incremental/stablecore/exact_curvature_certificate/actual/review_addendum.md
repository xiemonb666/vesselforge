# Exact curvature certificate review addendum

The one authorized run completed with return code `0` in `0.235 s`, using 82 checked nodes. The certificate is 191,724 bytes, below the 8 MiB cap, with SHA-256 `b08a550d14e59ed9945408bafc42a921692f1ef7f9c4540dc77f8a364ede8bde`. The stdout, stderr, and machine-readable attempt receipt are preserved beside it. Source, fixed-case, and both prior-input pins were identical before and after the run: source `bf6838f11ac4cb9422236242431ebcf0c4237c37a9329937da9322615092d97d`; case `e1e9c3cf659dbc59d99a18c4b70694201518be4f3aba09a57806402e732cf95a`; prior profile source `057233b930a2b8e0e3ef43a3568f1cb0e6e972baed97eeeeceb6459d9de8c951`; prior diagnostic `eb60138fc559d5a06ab2b4febf82fdc6654e6bbeab84f05f847c65934ffbbd4f`.

All 16 spans have strict positive derivative-projection proofs over four exact quarter intervals. Across the 12 spans with radius targets, 8 are `FAIL_CERTIFIED` and 4 are `PASS`. The four lip spans have no new radius certificate. `NO_NEW_LIP_RADIUS_CERTIFICATE; finite curvature prior rational bounds in pinned original diagnostic` — both lip quadrants of each vessel retain four `RATIONAL_BOUND` intervals in the pinned prior diagnostic.

| Family | Span | Radius target | Radius result | 3 mm absolute-curvature screen |
|---|---|---:|---|---|
| bowl | outer_base_round | 9 mm | FAIL_CERTIFIED | N/A |
| bowl | outer_base_to_lower_body | 9 mm | FAIL_CERTIFIED | N/A |
| bowl | outer_lower_body | 9 mm | PASS | PASS |
| bowl | outer_mid_body | 9 mm | PASS | PASS |
| bowl | outer_apex_in | 9 mm | PASS | PASS |
| bowl | outer_apex_out_to_mouth | 9 mm | FAIL_CERTIFIED | PASS |
| bowl | rim_outer_quadrant | none | report only | N/A |
| bowl | rim_inner_quadrant | none | report only | N/A |
| jar | outer_base_round | 8.25 mm | FAIL_CERTIFIED | N/A |
| jar | outer_base_to_body | 8.25 mm | FAIL_CERTIFIED | N/A |
| jar | outer_body_to_apex | 9 mm | FAIL_CERTIFIED | PASS |
| jar | outer_apex_to_shoulder | 9 mm | FAIL_CERTIFIED | PASS |
| jar | outer_shoulder | 9 mm | FAIL_CERTIFIED | `SUFFICIENT_ABS_CURVATURE_BOUND_FAIL_ACTUAL_SIGNED_REGULARITY_UNKNOWN` |
| jar | outer_neck | 9 mm | PASS | PASS |
| jar | rim_outer_quadrant | none | report only | N/A |
| jar | rim_inner_quadrant | none | report only | N/A |

The exact negative radius-polynomial witnesses are `P_R(t)=S(t)^3-R^2 D(t)^2` at rational local parameters:

| Family | Span | R | t | Exact `P_R(t)` |
|---|---|---:|---:|---:|
| bowl | outer_base_round | 9 | 3/4 | `-13292533187702179868331/281474976710656` |
| bowl | outer_base_to_lower_body | 9 | 1/4 | `-533049128826330173945270743/73786976294838206464` |
| bowl | outer_apex_out_to_mouth | 9 | 1/8 | `-1771672562265769444294032438584983/9903520314283042199192993792` |
| jar | outer_base_round | 33/4 | 3/4 | `-43160560924131489228519779623431/1152921504606846976000000` |
| jar | outer_base_to_body | 33/4 | 1/4 | `-3432411342041698435811629549231/1152921504606846976000000` |
| jar | outer_body_to_apex | 9 | 1/8 | `-55357053270434764255543995158199983660107/1237940039285380274899124224000000` |
| jar | outer_apex_to_shoulder | 9 | 1/4 | `-4247986242178025797177078451/68719476736000000000000` |
| jar | outer_shoulder | 9 | 1/8 | `-5798497569650583919498496507125422521647/590295810358705651712000000000000` |

The jar shoulder 3 mm polynomial also has the exact negative witness `P_3(7/8)=-334695922022012195968375682904615484543/590295810358705651712000000000000`. This proves that the sufficient screen `|3κ|<1` fails there. At this same witness, the signed-curvature review gives `D<0`, `κ≈−0.35874139/mm`, and the inward-offset tangent factor `1−3κ≈2.076>0`. Therefore the screen failure does not prove an inward normal-offset cusp or a nonregular point. The seven `P_3` passes prove the sufficient absolute screen on those spans; the jar shoulder's actual signed regularity over its full span remains unknown. A future direct regularity proof must certify `1−3κ>0` with its sign, rather than treating failure of the absolute-curvature screen as physical failure.

Global minimum wall thickness and nonlocal self-intersection remain `UNKNOWN`. The run made no geometry, CAD, STEP, material, or physical-thickness claim.
