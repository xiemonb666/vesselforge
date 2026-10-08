# Independent static review: global two-cap candidate

**Static decision: no source-level blocker found after the SHA correction.** This review covers the frozen source and contract only; I did not generate a candidate, run focused checks, triangulate, call CAD, or call a solver. The root-authorized execution must retain its external 120 s hard limit and separate artifact-tree cap.

The earlier prewrite-audit pin error is resolved. The actual audit digest is `9aa9464977a3d551585182ab2b355b09f4b2f7db8843b9056fe0baf5cba9a5c1` (64 hex characters), and it now agrees in `candidate.py:43`, the contract, and the freeze. I independently hashed every freeze-listed source, the audit script/result, and all five pinned inputs; each matches the current declaration.

The cap selection is specific to the physical planar surfaces: 128 z=0, R=20 exterior triangles wound outward and 128 z=2, R=17 floor triangles wound inward. The selectors require distinct source-face sets, one center and 128 unique boundary vertices per cap, and map baseline source-face identities into local-B. Each patch keeps the center and exact 128-vertex boundary cycle. Frozen metadata gives 1,392 and 1,002 lattice vertices, 2,912 and 2,132 cap faces, 2,394 added vertices, and 41,876 total predicted faces. I read these as frozen preflight metadata; I did not recalculate or execute the triangulation.

The patch build replaces only those two cap face sets. It preserves noncap connectivity/order and existing vertex, lineage, outer-field and color arrays. Source-code guards enforce the fixed vertex/face caps, 15,000 cross-parent records, 60,000 patch vertices, and 128 parents per output face before NPZ save. The v2 output omits the standard v1 aliases; cross-parent rows use explicit v2 status plus the -1/NaN single-parent sentinel, with full CSR lineage authoritative and legacy compatibility marked UNKNOWN.

The readback checks cover CSR shapes and offsets, lineage reconstruction, per-output-face area coverage and overlap, cap boundary identity, colors, topology, and geometry-wide triangle metrics. They require each cap to meet Q >= 0.35 and aspect <= 5, preserve the noncap extrema, and require global minimum-Q gain and maximum-aspect reduction to exceed 64 scaled float64 epsilons. That rejects a floating-point tie. It is an all-relief-triangle geometric gate; it does not qualify solver mechanics, tetrahedron quality, or local sizing h. The actual result remains unknown until saved output is reviewed.

The outer color table stays byte-identical to the patterned baseline. The outer continuous field uses periodic theta unwrapping and corner, edge-midpoint and centroid samples. The planar caps retain the frozen base color. These are finite numerical checks, not an all-points proof of the continuous field or a visual/PBR qualification.

One reporting caveat remains: numeric checks are written before rendering, but the manifest is written only after rendering. A render failure can therefore leave numerical checks on disk but no manifest, with an UNKNOWN_OR_FAIL receipt. The parent runner's 20 MiB retention bound applies to child logs, not the complete run directory. Its child deadline and cleanup reserve also do not forcibly bound the runner's own hashing/receipt tail; retain the separately specified external hard 120 s limit and artifact-tree cap for the complete invocation. These bounds are part of the execution setup, not meshing blockers.

## Frozen snapshot

- Candidate: `9f09faf13fb423d1cbf6aeec0f41e4ece7533e648adf0e8b26762669a892c114`
- Focused checks: `e5e4f5cfecf7aa46b6c445083f11686bf5653975993b0e21cfad8c8a0e41c141`
- Contract: `302e0bc626dfb6d9fd62d279bd00c586f4657b187108d324dfdc65c1368eca97`
- Parent runner: `eddce6d5b1b8d8cd1b244c7380969e752e7633276aa577118ca9ab9e707d7757`
- Source freeze: `c4f209b32ae34c7affb7c8699320c9ba6f82665af8bc5777ad68b0f9cb0460a5`

Full hash verification and line-specific findings are in the accompanying JSON. A clean static review is not a quality pass; post-run conclusions require readback of the saved NPZ and checks.

