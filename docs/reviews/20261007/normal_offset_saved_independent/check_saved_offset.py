from __future__ import annotations
import hashlib, json, math, sys, time
from decimal import Decimal
from fractions import Fraction as F
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PINS = ROOT / "vesselforge/tmp/review_20261006/normal_offset_saved_independent/case_falsepins.json"; PINS_SHA256 = "d2be178a0af9a7a0e3b1083d662da768922879630247eb29bad4268671f753c9"
def need(ok, tag):
    if not ok: raise ValueError("CHECK_FAILED_" + tag)
def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""): h.update(block)
    return h.hexdigest()
def load(path): return json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
def frac(x): return x if isinstance(x, F) else F(str(x))
def qs(x): return f"{x.numerator}/{x.denominator}"
def deriv(a):
    n = len(a) - 1
    return [F(n) * (a[i + 1] - a[i]) for i in range(n)] if n else [F(0)]
def prod(a, b):
    m, n = len(a) - 1, len(b) - 1
    return [sum((a[i] * b[k-i] * F(comb(m,i)*comb(n,k-i), comb(m+n,k))
                 for i in range(max(0,k-n), min(m,k)+1)), F(0)) for k in range(m+n+1)]
def elevate(a, target):
    out = list(a)
    while len(out)-1 < target:
        n = len(out)-1
        out = [out[0]] + [F(i,n+1)*out[i-1] + F(n+1-i,n+1)*out[i]
                          for i in range(1,n+1)] + [out[-1]]
    need(len(out)-1 == target, "degree_elevation")
    return out
def qcoeff(r, zp):
    speed2 = [x+y for x,y in zip(prod(deriv(r),deriv(r)), prod(zp,zp))]
    radial = prod(prod(r,r), speed2)
    axial = elevate(prod(zp,zp), len(radial)-1)
    return [x-9*y for x,y in zip(radial,axial)]
def split(a):
    row=list(a); left=[row[0]]; right=[row[-1]]
    while len(row)>1:
        row=[(row[i]+row[i+1])/2 for i in range(len(row)-1)]
        left.append(row[0]); right.append(row[-1])
    return left, list(reversed(right))
def nonnegative(c, budget, depth=0):
    if budget["nodes"] >= budget["limit"]: return "UNKNOWN_NODE_BUDGET"
    budget["nodes"] += 1
    if c[0] < 0 or c[-1] < 0: return "EXACT_COUNTEREXAMPLE"
    if all(x >= 0 for x in c): return "PASS"
    if depth >= budget["depth"]: return "UNKNOWN_DEPTH_LIMIT"
    a,b=split(c); x=nonnegative(a,budget,depth+1)
    if x == "EXACT_COUNTEREXAMPLE": return x
    y=nonnegative(b,budget,depth+1)
    if y == "EXACT_COUNTEREXAMPLE": return y
    return "PASS" if x == y == "PASS" else "UNKNOWN"
def evalb(a,u):
    row=list(a)
    while len(row)>1: row=[(1-u)*row[i]+u*row[i+1] for i in range(len(row)-1)]
    return row[0]
def check():
    start=time.monotonic(); need(sha(PINS)==PINS_SHA256, "pins_file_sha"); pins=load(PINS); files=pins["files"]
    paths={k:ROOT/v["path"] for k,v in files.items()}
    for k,v in files.items(): need(paths[k].is_file() and sha(paths[k]) == v["sha256"], "pin_"+k)
    sp=load(paths["source_pins"])
    for k,alias in (("source","kernel"),("readme","normal_offset_readme"),
                    ("false_case","false_case"),("runner","runner")):
        e=sp["files"][k]; v=files[alias]
        need(e["sha256"]==v["sha256"] and e["path"].replace("\\","/")==v["path"], "source_pin_"+k)
    for k,alias in (("saved_result","outer_result"),("frozen_driver","semantic_driver"),
                    ("independent_audit","independent_audit"),("failed_attempt_manifest","failed_attempt_manifest")):
        e=sp["inputs"][k]; v=files[alias]
        need(e["sha256"]==v["sha256"] and e["path"].replace("\\","/")==v["path"], "input_pin_"+k)
    rec=load(paths["receipt"]); rh=files["offset_result"]["sha256"]
    need(rec["status"]=="COMPLETE" and rec["actual_rc"]==0 and rec["inputs_unchanged"] and not rec["retry_permitted"], "receipt_status")
    need(rec["result_sha256"]==rh and rec["total_persisted_bytes_status"]=="EXACT_FIXED_POINT" and rec["budget_status"]=="WITHIN_LIMIT", "receipt_result")
    stdout=paths["run_stdout"].read_bytes(); stderr=paths["run_stderr"].read_bytes()
    need(len(stdout)==rec["captured_stdout"]["bytes"] and hashlib.sha256(stdout).hexdigest()==rec["captured_stdout"]["sha256"], "receipt_stdout")
    need(len(stderr)==rec["captured_stderr"]["bytes"] and hashlib.sha256(stderr).hexdigest()==rec["captured_stderr"]["sha256"] and not stderr, "receipt_stderr")
    summary=json.loads(stdout.decode("utf-8")); need(summary["status"]=="INNER_MERIDIAN_LOCAL_OFFSET_CANDIDATE" and summary["spans"]==12 and summary["bytes"]==paths["offset_result"].stat().st_size, "worker_summary")
    expected={"source":files["kernel"]["sha256"],"readme":files["normal_offset_readme"]["sha256"],
              "false_case":files["false_case"]["sha256"],"runner":files["runner"]["sha256"],
              "saved_result":files["outer_result"]["sha256"],"frozen_driver":files["semantic_driver"]["sha256"],
              "independent_audit":files["independent_audit"]["sha256"],"failed_attempt_manifest":files["failed_attempt_manifest"]["sha256"],
              "source_pins":files["source_pins"]["sha256"]}
    need(rec["hashes_before"]==expected and rec["hashes_after"]==expected, "receipt_input_hashes")
    audit=load(paths["independent_audit"])
    for key in pins["audit_input_links"]:
        target=paths[key].resolve(); got=next((v for k,v in audit["input_sha256"].items() if Path(k).resolve()==target),None)
        need(got==files[key]["sha256"], "audit_input_"+key)
    outer=load(paths["outer_result"])
    need(outer["status"]==pins["upstream_semantics"]["outer_result_status"] and audit["status"]==pins["upstream_semantics"]["audit_status"], "upstream_identity")
    need(outer["families"]["jar"]["promotion_status"]==pins["upstream_semantics"]["outer_promotion_status"], "no_upstream_promotion")
    r=load(paths["offset_result"]); c=pins["contract"]
    need(r["status"]==c["expected_local_status"] and r["study_certificate_status"]==c["expected_local_status"], "local_status")
    need(r["scope"]=="jar_meridian_2d_only" and r["global_wall_status"]=="UNKNOWN" and r["normal_strip_global_injectivity"]=="UNKNOWN", "scope_limits")
    need(len(r["spans"])==c["span_count"] and r["study"]["nodes_used"]==c["expected_saved_primitive_nodes"] and r["study"]["node_limit"]==c["expected_saved_node_limit"] and r["study"]["depth_limit"]==c["expected_saved_depth_limit"], "saved_certificate_shape")
    need(r["calls"]["jar_nonnegative_primitive_calls"]==37 and r["calls"]["jar_certify_study"]==1 and r["calls"]["jar_display_25_calls"]==12 and r["calls"]["false_fixture_certificate_calls"]==2 and r["calls"]["false_fixture_budgets_independent"] and r["false_fixture_checks"]=="PASS", "saved_call_contract")
    ue=r["upstream_evidence"]
    need(ue["upstream_r9_all_side_spans_pass"] and ue["upstream_regular_all_spans_pass"] and r["study"]["upstream_r9_all_side_spans_pass"], "pinned_R9_regularity_premise")
    need([ue[k] for k in ("sides_R9_pass","spans_regular_pass","C4_joins_pass","features_pass","straight_exclusions")] == [10,12,11,5,2], "saved_upstream_counts")
    report=[]; maxerr=0.0; minri=float("inf"); samples=0; spans=[]
    for s in r["spans"]:
        controls=[[frac(x),frac(y)] for x,y in s["exact_bezier_controls_rz_mm"]]
        need(len(controls)==6 and len(s["certificate"]["checks"])>0, "bezier_controls")
        rr=[p[0] for p in controls]; zz=[p[1] for p in controls]; rp=deriv(rr); zp=deriv(zz)
        need([qs(x) for x in rr]==s["r_bernstein_mm"] and [qs(x) for x in zz]==s["z_bernstein_mm"], "saved_controls_match")
        qc=qcoeff(rr,zp)
        need(len(qc)==19 and [qs(x) for x in qc]==s["Q_bernstein_degree18"], "Q_exact_coefficients")
        kind=s["kind"]; mono={"side":all(x>=0 for x in zp) and any(x>0 for x in zp),"flat_base":all(x==0 for x in zp) and all(x>=0 for x in rp) and any(x>0 for x in rp),"straight_neck":all(x==0 for x in rp) and all(x>=0 for x in zp) and any(x>0 for x in zp)}; need(kind in mono and mono[kind] and all(x>=0 for x in rr) and all(x>=0 for x in zp) and all(x>=0 for x in qc), "exact_bernstein_nonnegative_and_monotone")
        need(s["certificate"]["status"]=="PASS", "saved_span_PASS")
        check=s["certificate"]["checks"]
        if s["kind"]=="side": need(check["curvature_factor_lower_bound"]=="2/3_FROM_PINNED_R9", "saved_R9_factor_premise")
        else: need(check["straight_curvature_factor"]=="1", "saved_straight_factor")
        display=s["true_normal_display_25"]; need(len(display)==25, "display_count")
        span_max=0.0
        for j,d in enumerate(display):
            u=F(j,24); need(d["u"]==qs(u) and d["display_only"] and d["status"]=="FINITE_TRUE_NORMAL_OFFSET_SAMPLE", "display_metadata")
            x,z,dx,dz=evalb(rr,u),evalb(zz,u),evalb(rp,u),evalb(zp,u); speed2=dx*dx+dz*dz
            need(speed2>0, "sample_speed")
            v=math.sqrt(float(speed2)); ri=float(x)-3.0*float(dz)/v; zi=float(z)+3.0*float(dx)/v
            need(math.isfinite(ri) and math.isfinite(zi) and ri>=-1e-9, "finite_nonnegative_sample")
            err=max(abs(ri-float(d["r_inner_mm"])),abs(zi-float(d["z_inner_mm"])))
            need(err<=float(c["display_error_tolerance_mm"]), "normal_display_formula")
            span_max=max(span_max,err); maxerr=max(maxerr,err); minri=min(minri,ri); samples+=1
        spans.append({"span_index":s["span_index"],"kind":s["kind"],"r_zprime_Q_coeff_nonnegative":True,"saved_status":"PASS","max_display_error_mm":span_max})
    kinds=[x["kind"] for x in spans]; need(samples==c["span_count"]*c["display_points_per_span"] and kinds.count("side")==10 and kinds.count("flat_base")==1 and kinds.count("straight_neck")==1, "sample_total_and_kinds")
    for a,b in zip(r["spans"],r["spans"][1:]):
        ca=a["exact_bezier_controls_rz_mm"][-1]; cb=b["exact_bezier_controls_rz_mm"][0]
        need([frac(x) for x in ca]==[frac(x) for x in cb], "join_endpoint")
    fc=load(paths["false_case"])["fixtures"]; f1,f2=fc
    q1=qcoeff([frac(x) for x in f1["r_bernstein_mm"]],deriv([frac(x) for x in f1["z_bernstein_mm"]]))
    need(f1["node_limit"]==c["false_fixture_node_limit_each"] and f1["depth_limit"]==c["false_fixture_depth_limit_each"] and len(q1)==19 and all(x==-8 for x in q1) and evalb(q1,F(0))==-8, "false1_exact_endpoint_witness")
    budget={"nodes":0,"limit":c["false_fixture_node_limit_each"],"depth":c["false_fixture_depth_limit_each"]}
    need(f2["node_limit"]==c["false_fixture_node_limit_each"] and f2["depth_limit"]==c["false_fixture_depth_limit_each"], "false2_budget")
    f2=[frac(x) for x in f2["bernstein_coefficients"]]; f2status=nonnegative(f2,budget)
    need(f2status.startswith("UNKNOWN") and budget["nodes"]==budget["limit"], "false2_unknown_not_fail")
    savedf=r["false_fixtures"]; need(savedf[0]["result"]["status"]=="EXACT_COUNTEREXAMPLE" and savedf[0]["result"]["witness_u"]=="0/1" and savedf[0]["result"]["exact_value"]=="-8/1" and savedf[1]["result"]["status"]=="UNKNOWN" and savedf[1]["budget_nodes"]==budget["limit"], "saved_false_fixtures")
    manifest=load(paths["failed_attempt_manifest"])
    for v in manifest["snapshot_files"].values():
        p=ROOT/v["snapshot_path"]; need(p.is_file() and p.stat().st_size==v["bytes"] and sha(p)==v["sha256"], "old_failure_snapshot")
    persisted=sum(paths[k].stat().st_size for k in ("offset_result","receipt","run_lock","run_stdout","run_stderr"))
    need(persisted==rec["total_persisted_bytes"] and persisted<=rec["output_limit_bytes_total"], "receipt_total_bytes")
    elapsed=time.monotonic()-start; need(elapsed<=c["max_runtime_seconds"], "runtime_budget")
    out={"status":"INDEPENDENT_SAVED_OFFSET_AUDIT_PASS","scope":r["scope"],"result_sha256":sha(paths["offset_result"]),
         "receipt_sha256":sha(paths["receipt"]),"outer_result_sha256":files["outer_result"]["sha256"],"audit_sha256":files["independent_audit"]["sha256"],
         "inputs_unchanged":rec["inputs_unchanged"],"upstream_R9_factor":"PINNED_PREMISE_NOT_RECALCULATED","span_count":len(spans),"joins_checked":11,
         "sample_count":samples,"sampled_min_inner_radius_mm":minri,"max_saved_display_error_mm":maxerr,"spans":spans,
         "false_fixture_1":{"status":"EXACT_COUNTEREXAMPLE","Q_all":"-8","witness_u":"0/1"},
         "false_fixture_2":{"status":f2status,"nodes":budget["nodes"],"limit":budget["limit"]},
         "global_wall":"UNKNOWN","normal_strip_global_injectivity":"UNKNOWN","physics":"UNKNOWN","elapsed_seconds":round(elapsed,3)}
    raw=(json.dumps(out,indent=2,allow_nan=False)+"\n").encode("utf-8")
    need(len(raw)<=c["max_stdout_bytes"] and time.monotonic()-start<=c["max_runtime_seconds"], "output_budget")
    return raw
def main():
    if sys.argv[1:] != ["--root-go"]:
        print("SOURCE_ONLY: root GO required"); return 4
    try: sys.stdout.buffer.write(check()); return 0
    except Exception as e:
        sys.stderr.write(json.dumps({"status":"FAIL","error":type(e).__name__,"detail":str(e)[:256]})+"\n"); return 2
if __name__ == "__main__": raise SystemExit(main())
