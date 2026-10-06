# Preserved bowl apex 10/12 infeasibility

This note belongs to the unchanged source-only freeze whose manifest and inputs are preserved beside it. Its failed case is not overwritten by the replacement candidate.

At u=10/12, the degree-5 B-spline active support is Q10 through Q15. The bowl radial poles Q11 through Q16 are fixed to 57 mm, leaving only Q10.r free among the active controls. The exact Fraction precheck gives the fixed-pole-reduced radial matrix rank 2 and augmented rank 3 for the three rows (foot radius, apex radius, apex vertical tangent). The explicit reduced apex rows are Q10 coefficient 1/120 with RHS 139/40, and Q10 coefficient -1/2 with RHS -57/2; their incompatible required values certify infeasibility.

The replacement moves only the bowl apex parameter to u=8/12. The apex point (60,77.4) mm, foot, neck, mouth, and R>=9 mm screen are unchanged. This is an engineering parameterization correction, not a relaxed geometry threshold.
