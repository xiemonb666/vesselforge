"""Independent exact audit of one pinned saved candidate; import is inert."""
from __future__ import annotations
import ast, hashlib, json, math, sys, time
from fractions import Fraction as F
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RESULT = ROOT / "vesselforge/tmp/review_20261006/curvature_constrained_meridian_20261006/curvature_constrained_meridian_result.json"
IMPLEMENTATION = ROOT / "vesselforge/experiments/curvature_constrained_meridian_20261006/curvature_constrained_meridian.py"
DRIVER = ROOT / "vesselforge/experiments/semantic_base_neck_bspline_20261006/semantic_base_neck_driver.py"
FIXED = DRIVER.with_name("fixed_cases.json")
DESIGN = ROOT / "vesselforge/experiments/curvature_constrained_meridian_20261006/design_cases.json"
OUT = HERE / "independent_audit.json"
RUN = HERE / "run.txt"
REVIEW = HERE / "independent_review.md"
PINS = ("839c461cdf0dcae93f362ee7d80d0446cf52b6b1e1f04ed18842e17527673185",
        "96875bb6592a6fd57ceef4dc326c35faeb3f96de16607faa816c7d3fed1e08ce",
        "038974cbbe3965f7f03f1ad0199d0aba00b56294840e411ca9a21fbde42466a3",
        "4e18dbeaecbf13a54a87b3f1409e1c0f7fe54c3606122a01880689d9e3a6a83c",
        "d1bb74bfc90de5937884854fd4e5e62c4dbf01f33e2f1f7be5dbf931ee35c8eb")
MAX_SECONDS, MAX_BYTES = 15.0, 2 * 1024 * 1024

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def vec(p): return tuple(F(x) for x in p)
def add(a,b): return tuple(x+y for x,y in zip(a,b))
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def scale(a,s): return tuple(s*x for x in a)
def dot(a,b): return sum((x*y for x,y in zip(a,b)), F(0))

def basis_fns(U):
    @lru_cache(None)
    def N(i,p,u):
        if u == 1: return F(i == len(U)-p-2)
        if p == 0: return F(U[i] <= u < U[i+1])
        a,b=U[i+p]-U[i],U[i+p+1]-U[i+1]
        return ((u-U[i])/a*N(i,p-1,u) if a else F(0))+((U[i+p+1]-u)/b*N(i+1,p-1,u) if b else F(0))
    @lru_cache(None)
    def Nd(i,p,q,u):
        if q == 0: return N(i,p,u)
        if q > p: return F(0)
        a,b=U[i+p]-U[i],U[i+p+1]-U[i+1]
        return (F(p)/a*Nd(i,p-1,q-1,u) if a else F(0))-(F(p)/b*Nd(i+1,p-1,q-1,u) if b else F(0))
    return N,Nd

def find_span(U,p,n,u):
    for k in range(p,n):
        if U[k] <= u < U[k+1]: return k
    raise ValueError("NO_INSERTION_SPAN")

def insert_once(P,U,p,u):
    n,s=len(P)-1,sum(x==u for x in U); k=find_span(U,p,len(P),u); Q=[None]*(n+2)
    for i in range(k-p+1): Q[i]=P[i]
    for i in range(k-s,n+1): Q[i+1]=P[i]
    for i in range(k-p+1,k-s+1):
        den=U[i+p]-U[i]
        if den<=0: raise ValueError("BAD_BOEHM_DENOMINATOR")
        t=(u-U[i])/den; Q[i]=tuple(t*x+(1-t)*y for x,y in zip(P[i],P[i-1]))
    if any(x is None for x in Q): raise ValueError("UNFILLED_BEZIER_POLE")
    return tuple(Q),U[:k+1]+(u,)+U[k+1:]

def extract(P,U,p,breaks,tick):
    P,U=tuple(P),tuple(U)
    for u in breaks[1:-1]:
        while sum(x==u for x in U)<p: tick(); P,U=insert_once(P,U,p,u)
    if len(P)!=1+(len(breaks)-1)*p: raise ValueError("BAD_EXTRACTION_COUNT")
    return tuple(tuple(P[i*p:i*p+p+1]) for i in range(len(breaks)-1))

def eval_bezier(P,t):
    p=len(P)-1
    return tuple(sum((F(math.comb(p,j))*(1-t)**(p-j)*t**j*P[j][a] for j in range(p+1)),F(0)) for a in range(2))

def deriv(P,h,q):
    V,d=tuple(P),len(P)-1
    for _ in range(q): V=tuple(tuple(F(d)*(V[i+1][a]-V[i][a])/h for a in range(2)) for i in range(d)); d-=1
    return V

def jet(P,h,q,end):
    V=deriv(P,h,q); return V[-1] if end else V[0]

def bprod(a,b):
    m,n=len(a)-1,len(b)-1
    return tuple(sum((F(math.comb(m,i)*math.comb(n,k-i),math.comb(m+n,k))*a[i]*b[k-i]
                      for i in range(max(0,k-n),min(m,k)+1)),F(0)) for k in range(m+n+1))

def bsum(a,b):
    if len(a)!=len(b): raise ValueError("BERNSTEIN_DEGREE_MISMATCH")
    return tuple(x+y for x,y in zip(a,b))

def elevate(a,target):
    V=tuple(a)
    while len(V)-1<target:
        d=len(V)-1; V=tuple((F(i,d+1)*V[i-1] if i else F(0))+(F(d+1-i,d+1)*V[i] if i<=d else F(0)) for i in range(d+2))
    if len(V)-1!=target: raise ValueError("BAD_ELEVATION")
    return V

def p_radius(P,h):
    a,b=deriv(P,h,1),deriv(P,h,2); r1,z1=tuple(x[0] for x in a),tuple(x[1] for x in a)
    r2,z2=tuple(x[0] for x in b),tuple(x[1] for x in b)
    s2=bsum(bprod(r1,r1),bprod(z1,z1)); d0,d1=bprod(r1,z2),bprod(z1,r2)
    det=tuple(x-y for x,y in zip(d0,d1)); s6=bprod(bprod(s2,s2),s2)
    d2=elevate(bprod(det,det),24)
    return tuple(x-81*y for x,y in zip(s6,d2))

def main():
    if "--root-go" not in sys.argv: raise SystemExit("ROOT_REVIEW_AND_GO_REQUIRED")
    if any(p.exists() for p in (OUT,RUN,REVIEW)): raise SystemExit("OUTPUT_EXISTS_REFUSING_RERUN")
    start=time.monotonic(); deadline=start+MAX_SECONDS
    def tick():
        if time.monotonic()>deadline: raise TimeoutError("15_SECOND_AUDIT_BUDGET_EXCEEDED")
    source=Path(__file__).read_text(encoding="utf-8"); tree=ast.parse(source)
    allowed={"__future__","ast","hashlib","json","math","sys","time","fractions","functools","pathlib"}; imports=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Import): imports.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node,ast.ImportFrom): imports.add(node.module.split('.')[0] if node.module else "")
        elif isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in {"eval","exec","__import__"}:
            raise ValueError("DYNAMIC_EXECUTION_IN_READER")
    if not imports<=allowed: raise ValueError("UNAPPROVED_IMPORT:"+repr(sorted(imports-allowed)))
    paths=(RESULT,IMPLEMENTATION,DRIVER,FIXED,DESIGN); hashes=tuple(sha(p) for p in paths)
    if hashes!=PINS: raise ValueError("PIN_MISMATCH:"+repr(hashes))
    if RESULT.stat().st_size>8*1024*1024: raise ValueError("SAVED_RESULT_TOO_LARGE")
    saved=json.loads(RESULT.read_text(encoding="utf-8")); frozen=json.loads(FIXED.read_text(encoding="utf-8"))
    design_doc=json.loads(DESIGN.read_text(encoding="utf-8")); design=saved["explicit_design_cases"]
    pin=saved["source_pins"]; frozen_pins=pin["frozen_inputs"]
    pinok=(pin["implementation"]["sha256"]==hashes[1] and frozen_pins["driver_sha256"]==hashes[2] and
           frozen_pins["fixed_cases_sha256"]==hashes[3] and frozen_pins["design_cases_sha256"]==hashes[4] and
           pin["output_root"]=="vesselforge/tmp/review_20261006/curvature_constrained_meridian_20261006" and
           design_doc["source_fixed_case_sha256"]==hashes[3])
    if saved.get("schema")!="vesselforge.curvature_constrained_meridian.result.v1" or design!=design_doc["cases"] or not pinok:
        raise ValueError("RESULT_SCHEMA_OR_CASE_MISMATCH")
    if set(saved["families"])!={"bowl","jar"}: raise ValueError("FAMILY_SET_MISMATCH")
    p,n=int(frozen["curve"]["degree"]),int(frozen["curve"]["control_count"])
    U=(F(0),)*(p+1)+tuple(F(x) for x in frozen["curve"]["internal_knots"])+(F(1),)*(p+1)
    breaks=tuple(F(i,12) for i in range(13))
    if (p,n,len(U),len(breaks))!=(5,17,23,13): raise ValueError("KNOT_SCHEMA_MISMATCH")
    N,Nd=basis_fns(U)
    audit={"status":"INDEPENDENT_RECONSTRUCTION","input_sha256":dict(zip(map(str,paths),hashes)),
           "reader_sha256":hashlib.sha256(source.encode()).hexdigest(),"methods":"stdlib Fraction Cox rows, Boehm extraction, exact Bernstein products",
           "claims_excluded":["objective optimality","inner/global wall","circumferential curvature","physics/style/CAD"],"families":{}}
    for fam in ("bowl","jar"):
        tick(); case,rec=design[fam],saved["families"][fam]; geom=rec["exact_geometry_certificate"]
        C=tuple(vec(x) for x in rec["control_points_rz_mm"]); Q0=tuple(vec(x) for x in rec["compatible_q0_control_points_rz_mm"])
        if len(C)!=n or len(Q0)!=n: raise ValueError(f"{fam}:CONTROL_COUNT")
        spans=extract(C,U,p,breaks,tick); qspans=extract(Q0,U,p,breaks,tick)
        def direct(u,order):
            row=tuple((N if order==0 else lambda i,d,x:Nd(i,d,order,x))(i,p,u) for i in range(n))
            return tuple(sum((row[i]*C[i][a] for i in range(n)),F(0)) for a in range(2))
        feats=[]
        for x in case["features"]:
            val=direct(F(x["u"]),0); expected=vec(x["rz_mm"]); old=next(y for y in geom["feature_checks"] if y["name"]==x["name"])
            feats.append({"name":x["name"],"value":tuple(map(str,val)),"exact":val==expected,
                          "matches_saved":val==tuple(F(y) for y in old["value_rz_mm"]) and expected==tuple(F(y) for y in old["expected_rz_mm"]) and (val==expected)==bool(old["exact"])})
        spots=[]
        for i,S in enumerate(spans):
            h=breaks[i+1]-breaks[i]
            for t in (F(1,3),F(2,3)):
                u=breaks[i]+h*t; a=direct(u,0); b=eval_bezier(S,t)
                spots.append({"span":i,"t":str(t),"match":a==b})
        equalities=[]
        for x in case["linear_equalities"]:
            coord=0 if x["coordinate"]=="r" else 1; row=tuple((Nd(i,p,int(x["order"]),F(x["u"])) if int(x["order"]) else N(i,p,F(x["u"]))) for i in range(n))
            val=sum((row[i]*C[i][coord] for i in range(n)),F(0)); equalities.append({"name":x["name"],"residual":str(val-F(x["rhs"]))})
        au=F(case["apex"]["u"]); apex=direct(au,1); apex2=direct(au,2); apex_dr=apex[0]
        joins=[]
        for i,(L,R) in enumerate(zip(spans,spans[1:])):
            hl,hr=breaks[i+1]-breaks[i],breaks[i+2]-breaks[i+1]
            flags=tuple(jet(L,hl,q,True)==jet(R,hr,q,False) for q in range(5)); old=geom["joins"][i]["derivative_orders_0_to_4_equal"]
            joins.append({"u":str(breaks[i+1]),"D0_to_D4":flags,"matches_saved":tuple(old)==flags})
        target=set(map(int,case["curvature_screen_span_indices_zero_based"])); ai=breaks.index(au)
        maxr,mouthz=F(case["max_outer_radius_mm"]),F(case["mouth_z_mm"]); rows=[]; speed=[]
        for i,S in enumerate(spans):
            tick(); h=breaks[i+1]-breaks[i]; d=deriv(S,h,1); P=p_radius(S,h)
            hull=all(0<=x[0]<=maxr and 0<=x[1]<=mouthz for x in S); zm=all(x[1]>=0 for x in d)
            rd=all(x[0]>=0 for x in d) if i<ai else all(x[0]<=0 for x in d)
            endnz=d[0]!=(F(0),F(0)) and d[-1]!=(F(0),F(0)); opreg=(all(x[0]>=0 for x in d) and any(x[0]>0 for x in d)) if i==0 else (all(x[1]>=0 for x in d) and any(x[1]>0 for x in d))
            flat=all(x[1]==0 for x in S); cyl=all(x[0]==F(case["mouth_r_mm"]) for x in S)
            stat=("POINT_COUNTEREXAMPLE_AT_SPAN_ENDPOINT" if i in target and (P[0]<0 or P[-1]<0) else
                  "PROVED_R9_ON_CLOSED_NONFLAT_SPAN" if i in target and all(x>=0 for x in P) and opreg and endnz else
                  "UNKNOWN_NOT_CERTIFIED" if i in target else
                  "EXCLUDED_STRAIGHT_MERIDIAN_BASE_OR_NECK" if (i==0 and flat) or (i==11 and cyl) else
                  "NOT_EXCLUDED_BASE_FLATNESS_NOT_PROVED" if i==0 else "NOT_EXCLUDED_NECK_CYLINDER_NOT_PROVED")
            old=geom["spans"][i]; oldp=tuple(F(x) for x in old["P_R_degree24_coefficients"])
            qd=deriv(qspans[i],F(1),1); rv=add(qd[0],qd[-1]); den=abs(rv[0])+abs(rv[1])
            if not den: raise ValueError(f"{fam}:{i}:ZERO_Q0_DIRECTION")
            ref=tuple(x/den for x in rv); dots=tuple(dot(x,ref) for x in d); os=rec["exact_reference_speed_gates"][i]
            speedok=all(x>=1 for x in dots); smatch=dots==tuple(F(x) for x in os["reference_direction_dot_mm_per_global_u"]) and speedok==os["all_at_least_1"]
            match=(hull==old["hull_poles_within_bbox"] and old["hull_status"]==("PROVED_BY_CONVEX_HULL" if hull else "NOT_CERTIFIED_BY_HULL") and zm==old["z_derivative_poles_nonnegative"] and old["z_monotonicity_status"]==("PROVED_BY_POLE_SIGNS" if zm else "NOT_CERTIFIED_BY_POLE_SIGNS") and rd==old["radial_direction_poles_match_apex"] and old["radial_direction_status"]==("PROVED_BY_POLE_SIGNS" if rd else "NOT_CERTIFIED_BY_POLE_SIGNS") and endnz==old["endpoint_tangents_nonzero"] and opreg==old["open_span_regular"] and flat==old["semantic_base_flat"] and cyl==old["semantic_neck_cylindrical"] and stat==old["radius_9mm_status"] and (P==oldp if i in target else not oldp))
            rows.append({"span":i,"hull":hull,"z_monotone_poles":zm,"radial_direction_poles":rd,"endpoint_tangents_nonzero":endnz,"open_regular_poles":opreg,"flat_base":flat,"cylindrical_neck":cyl,"R9_status":stat,"P_R_degree24":tuple(map(str,P)),"endpoint_P_negative":i in target and (P[0]<0 or P[-1]<0),"matches_saved":match})
            speed.append({"span":i,"reference":tuple(map(str,ref)),"dots":tuple(map(str,dots)),"all_at_least_1":speedok,"matches_saved":smatch})
        strict={"axis_radial_tangent_positive":deriv(spans[0],breaks[1],1)[0][0]>0,"apex_vertical_tangent_positive":apex[1]>0,"apex_strict_radial_maximum":apex2[0]<0,"mouth_vertical_tangent_positive":deriv(spans[-1],breaks[-1]-breaks[-2],1)[-1][1]>0}
        oldstrict={x["name"]:x["status"]=="PASS" for x in geom["strict_point_checks"]}
        featpass=all(x["exact"] for x in feats); featmatch=all(x["matches_saved"] for x in feats)
        eqok=all(F(x["residual"])==0 for x in equalities) and apex_dr==0
        c4pass=all(all(x["D0_to_D4"]) for x in joins); c4match=all(x["matches_saved"] for x in joins)
        strictpass=all(strict.values()); strictmatch=strict==oldstrict
        hullok=all(x["hull"] for x in rows); regular=all(x["open_regular_poles"] and x["endpoint_tangents_nonzero"] for x in rows)
        mono=all(x["z_monotone_poles"] and x["radial_direction_poles"] for x in rows); speedok=all(x["all_at_least_1"] for x in speed)
        r9=all(rows[i]["R9_status"]=="PROVED_R9_ON_CLOSED_NONFLAT_SPAN" for i in target); epfail=any(rows[i]["endpoint_P_negative"] for i in target)
        straight=rows[0]["flat_base"] and rows[-1]["cylindrical_neck"]
        cmpok=(featpass and featmatch and c4pass and c4match and strictpass and strictmatch and eqok and featpass==geom["all_features_exact"] and c4pass==geom["all_C4"] and strictpass==geom["all_strict_point_checks_pass"] and hullok==geom["all_hulls_proved"] and regular==geom["all_spans_regular_proved"] and straight==geom["straight_meridian_exclusions_proved"] and all(x["matches_saved"] for x in rows+speed) and all(x["match"] for x in spots))
        gpass=featpass and eqok and c4pass and strictpass and hullok and regular and mono and speedok and r9 and straight
        opt=rec["optimizer_status"]
        gstatus="EXACT_R9_COUNTEREXAMPLE" if epfail else "EXACT_EQUALITY_OR_JET_FAILURE" if not (featpass and eqok and c4pass and strictpass) else "GEOMETRY_SCREENS_PROVED" if gpass else "NOT_FULLY_PROVED"
        exact_fail=epfail or not (featpass and eqok and c4pass and strictpass and speedok)
        unknown=not (hullok and regular and mono and r9 and straight)
        derived_promotion=("EXACTFAIL_NOT_PROMOTED" if exact_fail else "EXACTUNKNOWN_NOT_PROMOTED" if unknown else
                           "GEOMETRY_ENGINEERING_CANDIDATE_NOT_PHYSICS_READY" if opt["success"] else "OPTIMIZER_UNSUCCESSFUL_NOT_PROMOTED")
        saved_match=cmpok and derived_promotion==rec["promotion_status"]
        audit["families"][fam]={"geometry_status":gstatus,"engineering_screens_all_pass":gpass,"exact_R9_endpoint_counterexample":epfail,"saved_reconstruction_matches":saved_match,"features":feats,"direct_Cox_vs_Bezier_spot_checks":spots,"linear_equalities":equalities,"apex_jet":{"dr":str(apex_dr),"dz":str(apex[1]),"d2r":str(apex2[0])},"strict_points":strict,"joins":joins,"spans":rows,"reference_speed":speed,"optimizer_success":opt["success"],"optimizer_status_code":opt["status"],"optimizer_iterations":opt["nit"],"optimization_claim":"SLSQP_SUCCESS" if opt["success"] else "NOT_CONVERGED_NO_OPTIMUM_CLAIM","saved_promotion_status":rec["promotion_status"],"independently_derived_promotion_status":derived_promotion,"physics_style_inner_global_wall":"UNKNOWN"}
    tick()
    if tuple(sha(p) for p in paths)!=PINS: raise ValueError("PIN_CHANGED_DURING_AUDIT")
    audit["elapsed_seconds"]=time.monotonic()-start; audit["argv"]=sys.argv; audit["python_executable"]=sys.executable
    audit["reader_sha256"]=sha(Path(__file__))
    ok=all(x["saved_reconstruction_matches"] for x in audit["families"].values())
    audit["status"]="PASS_RECONSTRUCTION" if ok else "FAIL_RECONSTRUCTION"; audit["exit_code"]=0 if ok else 1
    data=(json.dumps(audit,indent=2,sort_keys=True)+"\n").encode("utf-8")
    if len(data)>MAX_BYTES: raise ValueError("AUDIT_JSON_OVER_2MIB")
    tick()
    summary={k:(v["geometry_status"],v["optimization_claim"],v["saved_reconstruction_matches"]) for k,v in audit["families"].items()}
    with OUT.open("xb") as f: f.write(data)
    with RUN.open("x",encoding="utf-8") as f:
        f.write(f"argv={sys.argv!r}\npython={sys.executable}\nresult_sha256={PINS[0]}\nreader_sha256={audit['reader_sha256']}\nelapsed_seconds={audit['elapsed_seconds']}\nexit_code={audit['exit_code']}\nsummary={summary!r}\n")
    with REVIEW.open("x",encoding="utf-8") as f:
        f.write("# 保存候选独立复核\n\n")
        for name,item in audit["families"].items():
            f.write(f"- {name}: geometry `{item['geometry_status']}`; SLSQP `{item['optimization_claim']}` (status {item['optimizer_status_code']}, {item['optimizer_iterations']} iterations); saved reconstruction matches={item['saved_reconstruction_matches']}.\n")
        f.write("\n仅审子午线几何门；周向曲率、内壁、法向壁厚、物理与风格仍 UNKNOWN。几何可行与目标收敛分别报告。\n")
    print(json.dumps(summary,sort_keys=True))
    if any(not x[2] for x in summary.values()): raise SystemExit(1)

if __name__=="__main__": main()
