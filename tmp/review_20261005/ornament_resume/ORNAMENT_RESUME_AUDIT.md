# VesselForge ornament route audit — 2026-10-05

## Finding

Run02 proves that the saved result is a real displaced, closed triangle mesh with a working relief and color mapping on one analytic cylinder. Its original outer mesh was too coarse for a quality claim. The draft-only local refinement path is now implemented in an isolated experiment and was run once on the same fixture at two local resolutions. Both candidates pass the fixed fixture gates, with finite sampled geometry error below `0.02 mm`; this qualifies a local mapping refinement experiment only. It does not establish a high-quality real-vessel style.

The independent NumPy recomputation of the frozen run02 NPZ gave 6,402 vertices, 12,800 faces, 19,200 edges, Euler characteristic 2, signed volume `10200.291910056922 mm³`, maximum outer chart edge `1.4013666739272455 mm`, and maximum displaced outer edge `1.4414763440066487 mm`. Those edges were about 3.1 and 3.2 times the `0.45 mm` relief amplitude. The run02 arrays SHA is `b44bb78176e690d8bc92ab2fc10f0803e142a0311acee8ff3944d4e324b9b974`.

## Frozen run02 pins and image

| Artifact | SHA-256 |
| --- | --- |
| `surface_mapping_prototype.py` | `0f624f8482d4d6540a0594ca1cbebebf1d02179d15a1e9fa05d3924107b12177` |
| `fixture_once_check_run02.py` | `e0f185d01ffa7b7f9239ece90617852aebc418693cef46dcdebb6121f37b75ae` |
| fixture parameter digest | `702285e2b311ea3ad7a17e6212d06ab8041faf58cca76e8e4a8a016d7e42c66e` |
| `fixture_arrays.npz` | `b44bb78176e690d8bc92ab2fc10f0803e142a0311acee8ff3944d4e324b9b974` |
| `surface_ornament_fixture.png` | `3cf1026178613a74cecc5d177139c6ec25e0134deb682ad61d312eed6bd5ac17` |

![Original run02 mapping preview](C:/Users/xiemo/Desktop/ShardForge/vesselforge/tmp/review_20261004/surface_ornament_route/run02/surface_ornament_fixture.png)

The original PNG shows actual surface displacement and a closed hollow fixture. Its full-cup view makes the shallow motifs hard to read; the close-up exposes coarse polygon facets, and the section exposes the piecewise-linear outline. The 3 mm wall value remains a concentric-cylinder radial proxy, not a global minimum or a changing-radius-vessel result.

## Frozen local refinement and measured results

The new source preserves every run02 vertex ID and coordinate as an unchanged prefix. It adds shared-edge red/green splits with per-face barycentric ancestry, places new rest points on the same analytic cylinder, and evaluates the same relief and linear-RGB field. It measures actual local and overall edge lengths, geometry error at every outer-triangle barycenter and edge midpoint against continuous `X1`, analytic normal angle error, seam uniqueness, lineage, and complete boundary topology.

| Candidate | Mesh V/F/E | Outer triangles | Max chart / displaced 3D edge in support + transition | Max finite geometry probe error | Max normal angle, report only | Volume | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Local A, `0.50 mm` | 9,490 / 18,976 / 28,464 | 12,320 | `0.5000 / 0.52255 mm` | `0.0145773 mm` (49,280 probes) | `5.8261°` | `10202.01418 mm³` | PASS |
| Local B, `0.25 mm` | 18,546 / 37,088 / 55,632 | 30,432 | `0.2500 / 0.26236 mm` | `0.00602363 mm` (121,728 probes) | `3.2769°` | `10202.17515 mm³` | PASS |

Both meshes have Euler characteristic 2, zero boundary/non-two-incidence/inconsistent-winding/duplicate/repeated/zero-area failures, one connected component, positive signed volume, unchanged baseline coordinate arrays, no duplicate seam coordinates, and successful source-triangle lineage reconstruction. The largest lineage chart residual is `1.78e-14 mm`. The standard sRGB transfer and linear-RGB baseline comparisons pass. The `0.02 mm` result is a finite probe gate, not a certified supremum, Hausdorff bound, or error bound everywhere.

The overall outer surface still has chart edges up to `1.40137 mm` outside the local support and transition band, about 3.11 times the relief amplitude. The refinement is intentionally local. Neither local density was selected as a production setting.

## Actual candidate PNG review

![Local A saved flat-triangle mesh](C:/Users/xiemo/Desktop/ShardForge/vesselforge/tmp/review_20261005/ornament_resume/local_refinement_run/local_a_0p50mm/flat_triangle_visual.png)

![Local B saved flat-triangle mesh](C:/Users/xiemo/Desktop/ShardForge/vesselforge/tmp/review_20261005/ornament_resume/local_refinement_run/local_b_0p25mm/flat_triangle_visual.png)

Both images render the saved candidate coordinates with flat faces. The relief reads more clearly at full-cup scale than in run02, and the detail shows the actual denser triangles. The transition band has visible fan-shaped triangles where it meets the coarse region. The detail panel's `x` axis label crowds the lower-right edge and overlaps, which weakens presentation. The silhouette and mesh data remain the scientific evidence; these previews still show simple repeated oval motifs rather than a validated real-vessel ornament style.

The color values come from the frozen linear-RGB blend and standard sRGB encoding. Pigment reflectance, glaze, BRDF/PBR, lighting, and display calibration remain unknown. This experiment does not qualify material appearance, physical behavior, real-vessel resemblance, curved-profile behavior, self-intersection, global normal wall thickness, or fracture labels.

## Execution and preservation record

The configured VesselForge Python runtime ran the isolated prototype once with `-B`; no CAD, OCC, STEP, solver, or Git operation ran. The run completed in `21.945 s` with exit code `0`. The driver generated both candidates because Local A passed every required gate. Its failure rule marks the candidate `FAIL` and stops before the next density; its 200,000-face/32-round budget reports `UNKNOWN` and also stops without changing density or tolerances.

An independent read-only NumPy pass reloaded both candidate NPZ files and reproduced their mesh counts, Euler characteristic, volumes, full outer finite geometry and normal-angle metrics, exact unchanged run02 coordinate prefixes, and NPZ/PNG hashes. Pre-run and post-run SHA manifests show all 17 explicitly pinned old inputs, old source files, old raw outputs, and frozen refinement sources were unchanged. No recursive inventory or Git command was used.

Run evidence and hashes are in `vesselforge/tmp/review_20261005/ornament_resume/local_refinement_run/`, with aggregate pins in [RESULT_SHA256.json](C:/Users/xiemo/Desktop/ShardForge/vesselforge/tmp/review_20261005/ornament_resume/RESULT_SHA256.json), and preservation pins in [PRE_RUN_SHA256.json](C:/Users/xiemo/Desktop/ShardForge/vesselforge/tmp/review_20261005/ornament_resume/PRE_RUN_SHA256.json) and [POST_RUN_SHA256.json](C:/Users/xiemo/Desktop/ShardForge/vesselforge/tmp/review_20261005/ornament_resume/POST_RUN_SHA256.json).

The frozen source SHA-256 is `5e946c205fb233e9354dfdde10d562597484ee38193e7930f93ce999f5840f74`; the candidate case freeze SHA-256 is `ab89a0832366d0391b9539248cfbfab62e7ea770f3cf9b1499ee6b39b0b533c1`. The experiment source, case freeze, check plan, and freeze manifest are under `vesselforge/experiments/surface_ornament_refinement_20261005/`.
