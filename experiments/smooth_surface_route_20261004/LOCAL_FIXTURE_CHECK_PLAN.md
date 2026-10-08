# Post-review fixture check plan — smooth surface route v0.2

**Do not run before the main agent reviews and accepts the source and case data.** This file specifies the first two local executions only. It does not authorize batch generation, production integration, or a physical qualification claim.

## Exact fixed inputs

| Case | Height | Max radius | Clear mouth diameter | Radial setting | Base setting | Outside mouth radius | Inner mouth radius | Side stations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `beaker` | 110 mm | 42 mm | 70 mm | 2.5 mm | 4.5 mm | 37.5 mm | 35 mm | 6 |
| `bowl` | 90 mm | 60 mm | 108 mm | 3 mm | 6 mm | 57 mm | 54 mm | 6 |

Both use an underside radius of 12 mm, outside side root radius of 16 mm, side-root derivative `(4, 0)` in the shared parameter, zero station second derivatives, and rounded-lip tangent scale 8 mm per parameter. Full point/tangent station rows are in `fixed_cases.json` and are the complete fixture input. Do not rescale or interpolate these cases for the first run.

## Commands after review

Use the configured tiny VesselForge runtime. The following commands are examples of the authorized local checks after source review; they have **not** been run:

```powershell
$vfPy = '.\third_party\vesselforge-runtime\venv\Scripts\python.exe'
& $vfPy .\vesselforge\experiments\smooth_surface_route_20261004\route_source_draft.py `
  --family beaker `
  --output .\vesselforge\tmp\review_20261004\smooth_surface_route\run_beaker `
  --step-roundtrip

& $vfPy .\vesselforge\experiments\smooth_surface_route_20261004\route_source_draft.py `
  --family bowl `
  --output .\vesselforge\tmp\review_20261004\smooth_surface_route\run_bowl `
  --step-roundtrip
```

The explicit `--step-roundtrip` option belongs in the post-review run only. Each case must have its own fresh output directory. The source defaults do not export STEP when that flag is absent.

## Per-case acceptance record

Accept a local engineering sample only if each case reports all of the following:

1. **Meridian and section:** all non-axis C2 join rows pass position tolerance `1e-8 mm`, first derivative tolerance `1e-8 mm/parameter`, and second derivative tolerance `1e-8 mm/parameter²`; all 41 samples per curve span have finite point/curvature values and nondegenerate speed; the fixed-case Bernstein/control-polygon preflight passes, including monotone z and monotone r within each side span; one valid closed wire and one valid positive-area face are reported.
2. **Native solid and boundary:** native shape is valid, solid count is exactly 1, shell count exactly 1, the sole solid is valid, the sole shell reports closed, `open_boundary_shell_count=0`, and volume is finite and positive. A shape count or validity failure rejects the case. The report must distinguish the radial setting from all sampled normal-ray distances.
3. **All-hit sidewall probes:** at least one outer revolution-face probe below the rim with outward radial-normal dot above `0.25` exists; every selected candidate probe has a result, with `unknown_count=0`; each ray retains all tolerance-clustered hit distances and all classified intervals; the first three intervals are outside, material, outside, with a positive finite first material interval. The flat floor and rounded lip are excluded from this sidewall set and remain separately identified by their generator settings. Record min/max/mean and every sampled distance. Do not require equality to the radial setting and do not describe the sample as a global minimum.
4. **STEP round trip:** reloaded shape valid, exactly one solid and one closed shell, `reloaded_open_boundary_shell_count=0`; absolute volume delta at most `0.01 mm³`; absolute delta for every bounding-box bound at most `0.01 mm`. If STEP fails, preserve and report the native result separately, mark STEP as failed, and do not promote the asset.
5. **Visual review:** `*_native_body_and_section.png` contains a tessellation of the actual native solid and a non-empty planar section face produced by the actual `y >= 0` half-space cut. Inspect the vessel silhouette, base, rim, and wall section. Any CAD-invalid, empty, self-crossing-looking, or unexpectedly pinched sample is a rejection even if the counters pass.
6. **Candidate language:** report `candidate_scope=ANALYTIC_CANDIDATE_ONLY`, `real_vessel_match=NOT_VALIDATED`, `material_or_physical_qualification=NOT_VALIDATED`, and `global_minimum_normal_wall_thickness=UNKNOWN`. Keep each local measurement and refusal reason attached to its own case.

The first run is two finite, fixed cases. It does not establish behavior for other parameter values, all of a future family domain, material response, manufacturability, archaeological fidelity, batch quality, or physical eligibility for RelicWeave. RelicWeave may consume only the evidence-backed geometry candidate record with its global-unknown flags and candidate-only status intact.
