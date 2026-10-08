# Global mesh quality candidate — source review

This folder contains a source-only, one-candidate proposal. Nothing in the
candidate has been generated, tested, rendered, sent to CAD, or sent to a
solver. The review output folder remains empty until the parent agent approves
the generation step.

The proposal starts from the saved `local_b_0p25mm` arrays, whose ornament
support and transition already have the measured local refinement. It replaces
only the planar bottom exterior fan at `z=0`. The 128 original boundary points,
all existing vertex coordinates, the outer wall chart, relief, normals, and
color arrays remain unchanged. New floor points use a deterministic 1.0 mm
triangular lattice clipped at a fixed 0.40 mm margin inside the exact existing
polygon, followed by one Delaunay triangulation. No pitch change or retry is
allowed.

The old face-level lineage cannot describe triangles that cross the old radial
source sectors. The quarantined schema v2 uses explicitly named
`v2_legacy_single_parent_face_source_ids` and
`v2_legacy_single_parent_face_corner_barycentric_to_source` arrays only when
one old source triangle covers the entire child face. Cross-parent faces use
`-1`/NaN only in those explicitly named arrays and carry clipped parent
patches. Each patch records its old parent face, area, polygon vertices in the
source and output face barycentric coordinates, and color sampled from the
frozen base field. Patch coverage, source/output reconstruction, pairwise
overlap, and every appended vertex lineage are independently checked. The
standard schema-v1 `source_face_ids` and
`face_corner_barycentric_to_source` keys are omitted so a consumer that
requires them fails closed with `KeyError`. Compatibility with legacy
consumers remains **UNKNOWN**; metadata cannot enforce reader behavior. This
candidate is quarantined experiment output with no production integration.

The pinned inputs are the immutable run02 fixture (`b44bb781…b974`) and the
saved local-B candidate (`8a2539d…6cfdf`), with its saved focused checks and
prototype source also pinned. The full digests and anticipated outputs are in
[`candidate_contract.json`](candidate_contract.json).

The source expects roughly 1.3–1.5k new interior points and 2.6–3.2k bottom
triangles from the fixed lattice. These are planning estimates, not measured
outputs. Hard limits are 2,500 new points, 45,000 total faces, 15,000 patches,
at most 128 parent patches per output face, 60,000 patch vertices, and 120
seconds. One run would save the candidate NPZ,
focused checks, manifest, receipt, a global equal-physical-scale PNG, and a
floor equal-aspect PNG under
`vesselforge/tmp/review_20261005/global_mesh_quality_candidate/`.

The focused source checks preserve the closed interface and exact floor
polygon area, validate patch coverage and no-overlap, reconstruct every new
vertex, check floor linear-RGB/sRGB conversion, recompute whole-mesh topology,
compare finite outer color/relief samples against the frozen field, and report
actual displaced-surface triangle Q and aspect by floor/nonfloor region. The
outer relief-sample error delta against local-B is an explicit unchanged-value
gate. The Q/aspect results are geometric surface descriptors only; they say
nothing about tetrahedral quality, solver `h`, material response, or a real
fragment match. Review targets for this one experiment (`floor min Q >= 0.35`,
floor max aspect `<= 5`, with strict whole-mesh Q/aspect improvement over
local-B) are explicit in the contract and still need parent acceptance.

## Root review revision

This revision keeps the candidate quarantined. It removes the standard
schema-v1 `source_face_ids` and `face_corner_barycentric_to_source` keys from
the saved v2 NPZ and uses `v2_legacy_single_parent_*` names for the limited
single-parent rows. Legacy-reader compatibility is marked **UNKNOWN**; the
note does not claim that metadata can enforce a reader. The focused checks now
independently reconstruct every appended vertex, verify floor and patch sRGB
conversion, record the outer relief finite-sample error delta against local-B
as an explicit unchanged-value gate, and call the combined non-floor metric
`nonfloor` rather than labeling it body. The candidate remains source-only and
unrun pending root review.

## Per-face lineage bound revision

The per-output-face parent-patch ceiling now equals the complete frozen
128-triangle bottom fan. The retained center lies on the radial-sector fan;
a broad child triangle incident to it can geometrically cross about 21–22
source sectors over a 60-degree span when each of the 128 sectors is 2.8125
degrees wide. This is a geometry-based bookkeeping rationale, not a generated
output observation. The earlier limit of 12 parents could therefore reject a
valid triangulation for lineage bookkeeping alone. Global limits remain 15,000
patch records, 60,000 patch vertices, and 120 seconds, and the geometry,
triangulation settings, and quality targets are unchanged.
