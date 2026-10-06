# Exact control-pole design for the fixed features

The pole constructor in profile_design.py takes each listed station position and shared d1/d2/d3 jet with a positive h. The fixed station d2 and d3 values are zero. Therefore the eight poles use P0=p0, P1=p0+h*d1(start)/7, P2=p0+2h*d1(start)/7, P3=p0+3h*d1(start)/7, P4=p1-3h*d1(end)/7, P5=p1-2h*d1(end)/7, P6=p1-h*d1(end)/7, P7=p1.

The following apex and lip pole nets are expanded explicitly as exact rational coordinates. They are design evidence for feature preservation and convex-hull bounds, not evaluated curves.

## Bowl apex

outer_apex_in, h=8:

P0=(282/5,279/5)
P1=(2014/35,2053/35)
P2=(2054/35,2153/35)
P3=(2094/35,2253/35)
P4=(60,2589/35)
P5=(60,2629/35)
P6=(60,2669/35)
P7=(60,387/5)

outer_apex_out_to_mouth, h=8:

P0=(60,387/5)
P1=(60,2749/35)
P2=(60,2789/35)
P3=(60,2829/35)
P4=(57,606/7)
P5=(57,614/7)
P6=(57,622/7)
P7=(57,90)

Both spans share apex position (60,77.4), tangent (0,1), second jet (0,0), and third jet (0,0). The first net has radial poles no greater than 60; the second has radial poles no greater than 60. The shared vertical tangent preserves the fixed maximum radius without the prior protected corner.

## Jar apex

outer_body_to_apex, h=8:

P0=(864/25,84/5)
P1=(6248/175,614/35)
P2=(6448/175,128/7)
P3=(6648/175,666/35)
P4=(54,410/7)
P5=(54,418/7)
P6=(54,426/7)
P7=(54,62)

outer_apex_to_shoulder, h=8:

P0=(54,62)
P1=(54,442/7)
P2=(54,450/7)
P3=(54,458/7)
P4=(8910/175,494/7)
P5=(8838/175,502/7)
P6=(8766/175,510/7)
P7=(1242/25,74)

Both spans share apex position (54,62), tangent (0,1), second jet (0,0), and third jet (0,0). Their radial poles are all at or below 54. This removes the old lower endpoint (54,40.8) while retaining Rmax=54 at the fixed apex.

## Rounded lip bridges

Each lip uses two degree-seven spans, h=7/2, joined at a fixed crest with shared tangent (-1,0) and zero second/third jets. The endpoints use vertical side tangents. For bowl, the endpoints are (57,90) and (54,90), and the crest is (55.5,92). For jar, they are (26,120) and (23,120), and the crest is (24.5,122).

The bowl outer-to-crest poles are:

(57,90), (57,181/2), (57,91), (57,183/2), (57,92), (113/2,92), (56,92), (111/2,92).

The bowl crest-to-inner poles are:

(111/2,92), (55,92), (109/2,92), (54,92), (54,183/2), (54,91), (54,181/2), (54,90).

The jar nets are the same two pole sequences translated by (-31,30):

outer-to-crest: (26,120), (26,241/2), (26,121), (26,243/2), (26,122), (51/2,122), (25,122), (49/2,122).

crest-to-inner: (49/2,122), (24,122), (47/2,122), (23,122), (23,243/2), (23,121), (23,241/2), (23,120).

The control hulls keep each cap inside its radial endpoint interval and bound its crest at z=92 or z=122. For strict regularity of the outer-to-crest half, all degree-six derivative poles project positively onto (-1,1); for crest-to-inner they project positively onto (-1,-1). The fixed h=7/2 makes the minimum projection equal to 1 in the shared global-s parameter. These exact control-pole facts do not establish any normal-wall or material-thickness claim.

## Remaining exact checks before a math run

The other outer poles are uniquely specified by fixed_cases.json and the constructor formula. Before any sampling, a source-only review should confirm each complete pole sequence has the intended coordinate signs and strict common projection. The normal offset is not a polynomial Bezier pole set; its regularity needs a full-span curvature bound proving |3κ|<1, and its global self-intersection remains a separate UNKNOWN. The two inner-base-fairing endpoints contain square roots; the Fraction-only pole constructor does not construct them. They remain declarative symbolic inputs until root reviews a suitable exact-scalar implementation.
