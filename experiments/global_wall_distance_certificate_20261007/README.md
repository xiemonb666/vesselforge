# Global meridian curve-pair distance certificate

This is a bounded exact source-only verifier for one pinned jar. It reconstructs the twelve degree-5 Bezier spans from the pinned actual B-spline controls, binds them to the frozen local-offset spans, checks all ten exact R9 polynomials and eleven global-u C4 joins, and certifies the two inner-offset endpoint distances by exact degree-10 Bernstein subdivision.

The proof extends `F(u,s)` to `0<=s<=6`. R9 gives `lambda>=1/3`; exact derivative signs give one strictly rising side/neck height branch and one flat base. The fixed-height identity then proves the extended 2D strip injective. If both endpoint certificates pass, interior nearest-footpoint stationarity and extended injectivity prove `min |c(u)-F(v,3)|=3`.

Full surfaces of revolution inherit that curve-pair minimum because differing azimuth adds a nonnegative squared-distance term. The claim excludes the CAD lip, caps, seam patches, native B-rep validity, and production wall qualification; those remain `UNKNOWN`.

The driver is inert by default. Its module entry point always stops; a future separately authorized caller must pass `root_ready=True`. This task did not execute it or perform numeric, CAD, provider, solver, renderer, or test work. A certificate run returns `UNKNOWN` if any pin, premise, endpoint bound, or fixed subdivision budget is unresolved.
