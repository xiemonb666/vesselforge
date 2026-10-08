# Saved candidate completion review

Independent read-only review of the recovered saved NPZ and the actual saved PNGs. No generation, tests, source edits, CAD, or solver were run.

## Finding

The exterior z=0 floor quality improved substantially, but this candidate does **not** establish a meaningful global triangle-quality improvement. Independent recomputation over all 39,872 candidate triangles found the unchanged 128-face z=2 mm inner floor fan controls the global minimum Q and maximum aspect. The global differences are near floating-point tie scale. The 29/29 saved focused checks are numerical/structural results, not a global improvement qualification.

## Recomputed triangle quality

| Mesh / region | Faces | Minimum Q | Maximum aspect | Minimum altitude (mm) |
|---|---:|---:|---:|---:|
| Local-B all faces | 37088 | 0.0848854566941983 | 20.3800162470963 | 0.12271827051863 |
| Local-B exterior floor | 128 | 0.0848854566941983 | 20.3800162470963 | 0.981353486548353 |
| Candidate all faces | 39872 | 0.0848854566941984 | 20.3800162470962 | 0.12271827051863 |
| Candidate exterior floor | 2912 | 0.640740178348741 | 2.86881046251439 | 0.406581294001627 |
| Candidate nonfloor | 36960 | 0.0848854566941984 | 20.3800162470962 | 0.12271827051863 |

Global deltas (candidate minus local-B): ΔQmin=1.2490009027033e-16; Δmax-aspect=-2.8421709430404e-14. Exterior floor: 128 faces became 2,912, with Qmin 0.640740178349 and max aspect 2.86881046251.

## Worst region

The candidate top-ten Q and aspect faces are all in the unchanged planar inner-base fan. Every listed face is at z=2 mm, with corner radii 0, 17, 17 mm. The worst face (candidate face 36639) maps to frozen source face 12373. The exterior z=0 fan was repaired and no longer controls the global extrema.

| Candidate face | Source parent | Q | Aspect | z corners (mm) | radii corners (mm) |
|---:|---:|---:|---:|---|---|
| 36639 | 12373 | 0.0848854566941984 | 20.3800162470962 | 2, 2, 2 | 0, 17, 17 |
| 36915 | 12741 | 0.0848854566941984 | 20.3800162470962 | 2, 2, 2 | 0, 17, 17 |
| 36834 | 12633 | 0.0848854566941985 | 20.3800162470962 | 2, 2, 2 | 0, 17, 17 |
| 36897 | 12717 | 0.0848854566941985 | 20.3800162470962 | 2, 2, 2 | 0, 17, 17 |
| 36801 | 12589 | 0.0848854566941985 | 20.3800162470962 | 2, 2, 2 | 0, 17, 17 |
| 36879 | 12693 | 0.0848854566941986 | 20.3800162470962 | 2, 2, 2 | 0, 17, 17 |
| 36783 | 12565 | 0.0848854566941986 | 20.3800162470962 | 2, 2, 2 | 0, 17, 17 |
| 36744 | 12513 | 0.0848854566941986 | 20.3800162470962 | 2, 2, 2 | 0, 17, 17 |
| 36900 | 12721 | 0.0848854566941986 | 20.3800162470962 | 2, 2, 2 | 0, 17, 17 |
| 36702 | 12457 | 0.0848854566941986 | 20.3800162470962 | 2, 2, 2 | 0, 17, 17 |

If global improvement is desired, the narrow next target is that separate planar z=2 inner-floor fan. Keep its full 128-vertex boundary cycle and winding, represent it as a second explicit surface/chart patch, and retain v2 multi-parent area-coverage CSR lineage. The current next controlling side-wall region has Qmin 0.2384632727 and maximum aspect 8.0013721971. These remain geometric triangle metrics only.

## Recovery, lineage, and topology

Completion is labeled `RECOVERED_CANDIDATE_READBACK_FROM_FAILED_RUN`. The readback exited 0 after 6.131s and did not run candidate generation. The original run02 receipt remains `UNKNOWN_OR_FAIL` (`NameError: name 'COLOR_FINITE_SAMPLE_TOL' is not defined`) and its SHA stayed `5b8588696346fcb396c2c8eee36365ffccc30bf93c3e4bf36be5195713153184`. Saved focused checks report 29/29 passed.
The NPZ declares schema v2; standard v1 aliases are absent, explicit v2 parent keys are present, quarantine is `EXPERIMENT_ONLY_NOT_FOR_PRODUCTION`, and legacy-reader compatibility is `UNKNOWN; standard schema-v1 source_face_ids and face_corner_barycentric_to_source keys are omitted`. Independent comparison found all 36,960 non-floor faces preserve local-B connectivity, source parent IDs, corner-barycentric rows, vertex prefixes, and outer arrays exactly. Direct straight-chord interpolation in 3D has a 0.081236 mm maximum residual in both candidate and local-B; this is not an analytic curved-surface reprojection test, so chart-aware reprojection remains UNKNOWN here. The exterior-floor CSR contains 2912 output faces and 8200 parent patches, with a maximum of 22 parents per face against a cap of 128. Offsets are monotone, independently summed patch-area residual is 3.38e-14 mm², and saved checks report no overlap and a preserved boundary cycle.
Saved topology checks report one connected component, Euler characteristic 2, no boundary/non-two-incidence/winding conflict/duplicate/zero-area faces, and positive signed volume 10202.1751 mm³. This is topology evidence for the analytic fixture, not physical or mechanical validation.

## Actual saved images

Viewed [global vessel mesh PNG](C:/Users/xiemo/Desktop/ShardForge/vesselforge/tmp/review_20261005/global_mesh_quality_candidate/completion_review/global_equal_aspect_actual_mesh.png) (SHA `8278c09d4a49956df62680501a70efc3460e5813769b70c6812c2c21fef3bcbc`): the triangulated shell and opening are visible; the image does not isolate the z=2 inner fan. Viewed [z=0 exterior-floor PNG](C:/Users/xiemo/Desktop/ShardForge/vesselforge/tmp/review_20261005/global_mesh_quality_candidate/completion_review/floor_equal_aspect_actual_mesh.png) (SHA `3bf5ebbd4113f1a3a2238edf159a83ec6974566dae5160e5da4b6b9bf0a7f148`): the regular lattice and polygon boundary agree with the saved floor mesh, but say nothing about the unrepaired inner fan.

## Hashes

All source/input SHA-256 values at review start and end match; the full maps are in the accompanying JSON. Candidate NPZ: `11f3ddad24e8d8a1aa2d46d6e8be9b28049c87ad6226e47cf84eaff9eae167d9`; local-B: `8a2539dff0a05444951ecae6bd66ba2d849c753764dc635a4bacdf8382c6cfdf`; baseline: `b44bb78176e690d8bc92ab2fc10f0803e142a0311acee8ff3944d4e324b9b974`; source freeze: `47dbd74954126eecb648b3ee693cf1877150404f4db3aef06d9c338c194867e3`.
