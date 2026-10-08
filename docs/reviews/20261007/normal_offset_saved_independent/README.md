# Saved normal-offset independent checker — source only

**SOURCE_READY, not executed.** `check_saved_offset.py` is a read-only standard-library/Fraction audit for the saved 12-span jar meridian result. It imports neither producer runner nor certificate kernel and creates no files. Only an explicit root authorization should invoke it with `--root-go` under the VF Python using `-B`.

The checker verifies the pinned result (`96ea35c4…9956a`), receipt (`768c771d…029d`), source pins, outer saved result (`839c461c…73185`), independent audit (`fe0c7c0f…dc0b`), frozen driver/inputs, and old failure manifest. It matches the receipt's result digest, before/after input hashes, raw stdout/stderr, fixed-point byte total, and all manifest snapshot hashes. It checks the recorded `PASS` status on all spans, 37 saved certificate nodes, and the pinned R9/regularity factor premise without recalculating curvature.

After GO, it reads only saved Bezier span coordinates and recomputes exact degree-18 Bernstein coefficients for `Q = r²(r′²+z′²)−9z′²`, along with nonnegative r/z′ controls and shape monotonicity gates: side z′ controls are nonnegative with at least one positive; the flat base has z′=0 and nonnegative, nonzero r′; the straight neck has r′=0 and nonnegative, nonzero z′. It checks exact adjacent endpoint joins and independently evaluates 25 true-unit-normal display points per span, comparing them with saved samples and requiring finite, nonnegative sampled inner radii. The samples are comparison data, not proof.

The false fixture checks must retain an exact `Q=-8` witness at `u=0`; the second fixture must remain `UNKNOWN` at its separate 8-node/depth-6 limit, never be relabeled as a counterexample. The checker keeps global wall thickness, normal-strip injectivity, lip closure, revolved-surface self-intersection, B-rep, material, and physics `UNKNOWN`. It reports a local meridian audit only and never promotes the upstream engineering candidate.

`case_falsepins.json` SHA-256: `d2be178a0af9a7a0e3b1083d662da768922879630247eb29bad4268671f753c9`.

`check_saved_offset.py` SHA-256: `fdd95596fa76aa5f8d431cbd0efde3a1d4907a3af5fb1b45eb62453fbe7e9a70` (160 lines). The checker enforces a 15-second runtime and 4 MiB stdout cap. No saved controls were evaluated during source preparation.
