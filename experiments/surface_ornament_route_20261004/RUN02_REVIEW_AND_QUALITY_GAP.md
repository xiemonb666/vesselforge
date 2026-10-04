# run02 review: accepted mapping mechanism, unresolved mesh quality

**Status:** Root visually accepted this run as a 3D mapping-mechanism example only. It is not a high-quality ornament mesh, a real-vessel result, a material calibration, or a physical qualification.

## Frozen run identity

- Prototype: `surface_mapping_prototype.py`, SHA-256 `0f624f8482d4d6540a0594ca1cbebebf1d02179d15a1e9fa05d3924107b12177`.
- run02 checker: `fixture_once_check_run02.py`, SHA-256 `e0f185d01ffa7b7f9239ece90617852aebc418693cef46dcdebb6121f37b75ae`.
- Parameters: SHA-256 `702285e2b311ea3ad7a17e6212d06ab8041faf58cca76e8e4a8a016d7e42c66e`.
- Result directory: `vesselforge/tmp/review_20261004/surface_ornament_route/run02/`.
- Output artifact manifest SHA-256: `50deccebca5ca3a2e3b14a52aae7ab844f5ee288050f56e1e7faa4eab25ad6fb`.
- The prototype was unchanged. The checker was copied from its original SHA `bd4511b51b5ca4683825eca3f2b3e9e5fd51ca74563a8f361322b69bf30d084f`; the only code change was registering the module in `sys.modules` before `exec_module`. The original failed import and all run01 evidence remain in the separate run01 directory. run01 did not construct a fixture and is not counted as geometry validation.

## What this one fixture established

The saved data contains a closed hollow-cylinder boundary with 6,402 vertices and 12,800 triangles. Incidence, winding, duplicate-face, repeated-vertex, zero-area, connected-component, and signed-volume checks all passed: zero boundary edges, zero edges with incidence other than two, zero inconsistent-winding edges, one component, and positive signed volume `10200.291910056922 mm³`.

The outer color and relief were sampled on immutable rest coordinates. The largest requested height was `0.45 mm`; the largest actual vertex displacement was `0.4499999999999993 mm`, with maximum normal-projection and tangential-residual errors both about `1.59e-15 mm`. The inner wall, floor, lip, non-outer vertices, and outer end rings remained unchanged. The theta seam had incidence two, and the sampled height repeated exactly every 16 angular samples for the eight-motif field.

The `3.0 mm` result is only the radial-separation proxy for this coaxial analytic cylinder. It is not a measured global minimum wall thickness over the triangulated relief boundary, and it does not establish clearance for a curved vessel. Self-intersection, general offset validity, curved-profile wall, and collision remain `NOT_ASSESSED`.

Linear values were encoded with the standard linear-RGB-to-sRGB transfer before the swatch was displayed; the recorded transfer error was zero. The swatch is a color-mapping diagnostic. Pigment reflectance, glaze, BRDF/PBR, illumination, and display-device calibration remain `UNKNOWN` or `NOT_PERFORMED`. Physics qualification is `UNKNOWN`; the run creates no fracture labels, R2/R0 labels, or training data.

Root inspected [the data-driven PNG](../../tmp/review_20261004/surface_ornament_route/run02/surface_ornament_fixture.png) and accepted that it shows real displaced mesh geometry, a closed fixture, and a color field. The same review rejected the mesh as a high-quality relief result: the close-up and section expose coarse triangular/faceted geometry.

## Quality gap to carry forward

The run used 128 angular samples at `R = 20 mm` and 25 meridian rows over `24 mm`. The nominal chart pitches are approximately `0.982 mm` circumferentially and `1.000 mm` vertically; a cell diagonal is about `1.40 mm`. Relative to the `0.45 mm` relief amplitude, those nominal lengths are about `2.18`, `2.22`, and `3.11` times the amplitude, respectively. These are parameter-derived chart-spacing figures, not a measurement of the longest relieved triangle edge. A future checker must measure actual outer-mesh edge lengths from its saved arrays.

At this sampling density the geometric facets and section polyline are visible around the ornament. Do not hide this with smooth-shading or a shader: the next comparison must measure the saved triangle geometry against the continuous analytic field. Keep run02 as the coarse baseline, not as proof that the ornament is visually or physically finished.

The baseline and any later tessellation candidates are representations of the same analytic parent, material inputs, and eight-motif field. They are not independent samples, fracture examples, or ground truth. The constant-radius chart and its `R * delta_theta` metric apply only to this cylinder; they do not provide a globally equal-distance chart for a curved shoulder or changing-radius vessel.
