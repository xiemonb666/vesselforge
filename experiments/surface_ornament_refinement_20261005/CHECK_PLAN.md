# Local analytic ornament refinement: source review and later check plan

**State: source frozen after main-agent review; one bounded local comparison is authorized.** No candidate arrays, CAD, rendering, or execution have been generated yet. This folder is isolated from production code and the frozen run02 experiment. The source reads run02's saved NPZ as its coarse baseline and proposes two resolutions of that same analytic sample.

## Fixed comparison

- Fixture: coaxial cylinder, `R=20 mm`, `H=24 mm`, declared radial wall `3 mm`, floor `2 mm`, baseline `128 x 25` outer samples.
- Field: eight repeated motifs at `z=13 mm`, half-widths `2.7 x 2.1 mm`, height `0.45 mm`, and the frozen linear-RGB base/pigment values.
- Candidates: local chart edge targets `0.50 mm` and `0.25 mm` in triangles intersecting a `1.5x` elliptical support/transition band. The field and analytic reference stay fixed.
- Source pins and case parameters are in `candidate_cases.json`. Baseline IDs and both baseline coordinate arrays must remain an unchanged prefix in every candidate.
- Refinement budget: at most 32 rounds and 200,000 faces. If the budget ends first, report `UNKNOWN` and stop without changing density or tolerances.

## What the source measures

`refinement_prototype.py` contains an isolated NumPy implementation. It uses shared midpoint IDs for marked edges and red/green face splits, so every incident triangle is subdivided together. New rest coordinates lie on the analytic cylinder; new relief, color, sRGB display samples, and displaced normals are evaluated from the same continuous field. Child faces carry source baseline triangle IDs and their corner barycentrics; new vertices carry a deterministic source-triangle owner and barycentrics.

For each saved candidate, the source is designed to record:

1. Source and parameter hashes, unchanged baseline vertex IDs/coordinates, analytic new-vertex coordinates, unchanged baseline field values, and barycentric lineage.
2. Maximum chart and displaced 3D edge lengths over the outer relief mesh and inside the support plus transition band, each divided by the `0.45 mm` amplitude.
3. Euclidean geometry error at every outer triangle barycenter and three edge midpoints against continuous `X1(theta,z)`, with RMS/p95/p99/max and separate barycenter/edge-midpoint maxima. The `0.02 mm` threshold is a finite-probe fixture gate, not a continuous error bound.
4. Oriented triangle-normal angle error at the same probes, reported without an acceptance threshold.
5. Full-boundary incidence, winding, duplicate/repeated/zero-area faces, connected components, Euler characteristic, and signed volume.
6. A flat-triangle view rendered from the just-saved NPZ coordinates. It does not use a smoothing shader.

The combined candidate gate requires all topology, baseline prefix/field/color, analytic point, barycentric lineage, unique seam, support-band edge, and finite `0.02 mm` geometry-probe checks to pass. A candidate failure is written as `FAIL`; the driver stops before attempting the next density. A budget exhaustion is `UNKNOWN` and follows the same stop rule.

The constant-radius chart, local metric, radial wall value, and analytic normals apply only to this cylinder. A pass would not validate changing-radius vessels, global minimum wall thickness, self-intersection, real-vessel resemblance, pigment reflectance, PBR, device calibration, manufacturing, or physics. The two meshes are resolution variants of one analytic sample, never independent samples or fracture ground truth.

## Authorized bounded command

```powershell
$vfPy = '.\third_party\vesselforge-runtime\venv\Scripts\python.exe'
& $vfPy .\vesselforge\experiments\surface_ornament_refinement_20261005\refinement_prototype.py `
  --output .\vesselforge\tmp\review_20261005\ornament_resume\local_refinement_run
```

The main agent authorized one execution after source and case freeze. Run it once with `-B` against a fresh output directory. It writes a candidate NPZ, checks, flat-triangle PNG, hash, timing, and process receipt for each attempted candidate. If a candidate fails, preserve the report and stop before the next density. Do not automatically increase density or relax a gate. The main agent will inspect the emitted NPZ, metrics, and flat-triangle PNG before deciding whether any implementation work should continue.

## Candidate acceptance record

A candidate is reviewable only if its source pins match; baseline arrays are byte-value unchanged; new samples follow the fixed analytic field; lineage is finite and reconstructs the chart coordinates; the support-band chart target passes; all finite geometry metrics are reported; the full closed mesh passes incidence/winding/connectivity/Euler/volume checks; and the flat-triangle PNG agrees with the saved geometry. Any failure is reported as a candidate failure, not repaired by changing the input field or threshold.
