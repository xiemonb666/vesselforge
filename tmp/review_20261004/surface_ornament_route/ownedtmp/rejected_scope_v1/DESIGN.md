# Surface ornament route for RelicWeave

**State: design proposal and unexecuted mapping prototype.** No CAD, Python, test, solver, or GPU work was run for this note. The Python file is a source artifact only.

## Decision

Treat an ornament as two linked products on a measured parent surface: a color/material field and, only when supported by evidence, an outer-surface displacement that changes the solid boundary. The field is sampled in the parent's immutable rest frame. A fragment carries the original parent-surface samples and pattern attributes through fracture, rigid motion, tessellation, and export. It never evaluates a new pattern from its current fragment-local coordinates.

RelicWeave owns the observation and candidate problem: record what a shard actually shows, retrieve historical adjacency candidates with explicit confidence and provenance, and preserve verified edge relationships separately from inferred pattern continuity. VesselForge can provide a conditional parent-surface prior and a way to preview a proposed reconstruction. A generated vessel, its ornamental design, and its surface tessellation are not fracture ground truth. Pattern resemblance alone cannot establish adjacency.

The first acceptance artifact should be one tiny, controlled visual fixture: a hollow analytic cylinder with a closed boundary mesh, a repeated raised motif sampled on its outer wall, and a correctly encoded color preview. This is a mapping and geometry plumbing fixture, not an archaeological model or a validation of the existing field library. Keep its output small enough for local inspection. Only after that review should the same data path be batched on RTX 5090.

## Service boundary for the candidate route

RelicWeave provides the observed shard record and the historical vessel/fragment index. PG-Frag should accept that observation with its source, scan frame, measured boundary, surface patch, ornament evidence, and uncertainty intact, then return ranked historical adjacency candidates with separate evidence fields. Candidate evidence may include broken-edge fit, catalog/object provenance, surface continuity, and ornament phase. Keep each cue and its confidence visible so decoration similarity cannot hide a poor edge match or be mistaken for verified adjacency.

VesselForge supplies a proposed parent surface and its immutable rest-coordinate map only when a candidate needs a reconstruction preview. PG-Frag's retrieval result remains a candidate; a generated profile, field sample, displaced mesh, or render cannot upgrade it into ground truth. The rendering path carries fragment attributes through the selected candidate mapping without changing the retrieval label.

## What the current implementation establishes

- `ornament_fields.py` evaluates ring, wave, and repeated-motif coverage from asset-local XYZ. It returns linear-RGB channels and a signed scalar height array; it expressly does not construct displaced vertices or a solid mesh.
- Its cylindrical angle is paired with world Z. Circumferential physical distance is radius times angular change, so a fixed angular feature changes width as the parent radius changes. A theta/Z image therefore does not have a uniform millimeter metric on a curved vessel.
- The reference renderer composites the declared linear channels and sends those values directly to `imshow`. The preview needs linear-to-sRGB encoding at the display boundary. The RGB values still lack measured pigment reflectance, glaze, roughness, illumination, camera, and display calibration.
- `profile_catalog.py` says its inside profile is a constant radial offset and explicitly does not claim a global minimum wall. The current geometry builder offsets the side profile in the meridian normal direction, with mitered corners. Those construction rules are useful inputs, not a substitute for checking wall thickness after a relief operation.

## Parent surface coordinates and local metric

Every parent geometry revision gets a stable `parent_surface_id`, coordinate-frame ID, and a surface-to-rest-coordinate correspondence. Keep each source rest point `X_rest` immutable in millimeters. A triangle fragment stores its source parent triangle and barycentric coordinates, or an equivalent stable CAD face/parameter correspondence, so its rest point and sampled attributes can be recovered without guessing from the moved fragment. Store a compact provenance record for observation source, parent candidate, field revision, and any manual correction.

For a surface of revolution with meridian arc length `s`, radius `r(s)`, angle `theta`, and profile `X(s,theta) = (r(s) cos(theta), r(s) sin(theta), z(s))`, use the first fundamental form `dL^2 = ds^2 + r(s)^2 dtheta^2`. At an anchor `s0`, a local tangent chart uses `v = s - s0` and `u = r(s0) * wrapped_delta_theta`. This gives distances in millimeters at the anchor. The cylinder fixture has constant radius and can be unwrapped exactly, apart from the periodic seam. A general curved vessel cannot use one globally distance-preserving flat chart when its Gaussian curvature is nonzero; the metric changes with position and charts have seams or other distortion. Record the chart and its valid patch. For motifs wider than the accepted local patch, use surface geodesic distances or subdivide into overlapping charts and bound the distortion. Do not silently reuse one reference radius across a vessel with a changing radius.

For a CAD face or measured triangle surface, derive the local metric from its surface derivatives or triangle tangents and preserve the mapping to `X_rest`. Pattern dimensions are stated in millimeters on the surface. The chart helps measure and construct the pattern; it does not replace the immutable rest-coordinate identity.

## Color and actual relief

Evaluate color at the saved outer-surface rest samples. Composite pigment and base in linear RGB. Convert the final linear result to sRGB only when writing a display image or an sRGB texture. The standard channel transfer is `12.92 * c` for `c <= 0.0031308`; otherwise it is `1.055 * c^(1/2.4) - 0.055`, after clamping the display input to `[0,1]`. Keep linear values for lighting and material calculations.

A scalar `height_mm` array is only a displacement request. To claim a molded relief, orient a material outward normal `n_out` on the parent exterior and construct actual boundary positions `X_relief = X_rest + height_mm * n_out`. Keep the inner surface and material core, make the relief transition compatible with the surrounding faces, and emit a new closed boundary representation. Color and height remain functions of the original `X_rest`; later fragment cuts inherit those samples and do not regenerate a motif.

Every geometry-changing relief requires new geometry checks on the displaced result: shell closure and validity, triangle self-intersections, outer-to-inner clearance and minimum residual wall, local collision with other parts, normal orientation, and curvature/offset singularity risk. Compare wall thickness by a defined geometric distance over the resulting solid or its corresponding interior surface, not by subtracting radial coordinates. A curvature bound such as `abs(height) * max(abs(principal_curvatures)) < 1` is a useful early warning only; it is not a collision or validity proof. The analytic cylinder can report exact radial separation for its own fixture, but that result does not qualify a vessel profile.

## Fracture and representation labels

A fracture target must come from the observed fragment or a separately identified physical/simulated fracture process with its own provenance. A CAD parent surface and a mesh rendered at a finer or coarser tessellation are different representation/precision layers of the same proposed geometry. They are not independent fracture examples and must never be promoted to fracture ground truth. Keep parent, object, and scan provenance in train/evaluation grouping to prevent sibling fragments or mesh resolutions leaking across splits.

## Evidence and scope boundary

The supplied real-vessel catalog distinguishes observed painted/incised decoration from molded relief and leaves relief dimensions and several material properties unknown. Use it to phrase priors and uncertainty, not to invent a relief height, wall value, color calibration, or adjacency label. See `vesselforge/docs/references/REAL_VESSEL_REFERENCE_CATALOG_20261004.md`, especially its notes separating directly reported relief from visual inference.

The use of a local surface chart and normal displacement is standard engineering plumbing here, not a claimed research contribution. This proposal does not claim that the existing three fields reconstruct historical ornament, that RGB is calibrated to ceramic appearance, or that a generated surface is an observed fracture. It adds no source-package API and no training set.
