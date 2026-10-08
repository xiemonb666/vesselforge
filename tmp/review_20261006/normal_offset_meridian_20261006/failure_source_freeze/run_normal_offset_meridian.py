from __future__ import annotations
import hashlib, importlib.util, json, os, subprocess, sys, time
from decimal import Decimal; from fractions import Fraction as F
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]; REVIEW=ROOT/"vesselforge/tmp/review_20261006/normal_offset_meridian_20261006"
PINS=REVIEW/"source_pins.json"; LOCK=REVIEW/"normal_offset_meridian_once.lock"; OUT=REVIEW/"normal_offset_meridian_result.json"
RECEIPT=REVIEW/"normal_offset_meridian_run_receipt.json"; STDOUT=REVIEW/"normal_offset_meridian_stdout.bin"; STDERR=REVIEW/"normal_offset_meridian_stderr.bin"
MAX_SECONDS=15.0; MAX_BYTES=4*1024*1024; MAX_RESULT_BYTES=MAX_BYTES-65536
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def sha_bytes(b): return hashlib.sha256(b).hexdigest()
def raw_bytes(x): return x if isinstance(x,bytes) else (x or "").encode("utf-8",errors="replace")
readpins=lambda:json.loads(PINS.read_text(encoding="utf-8"))
def files(p):
    return {k:ROOT/v["path"] for k,v in p["files"].items() if k in ("source","readme","false_case","runner")} | {k:ROOT/v["path"] for k,v in p["inputs"].items()}
def checkpins(p):
    paths=files(p)
    for k,v in p["files"].items():
        if k in paths and sha(paths[k])!=v["sha256"]: raise RuntimeError("PIN_MISMATCH_"+k)
    for k,v in p["inputs"].items():
        if sha(paths[k])!=v["sha256"]: raise RuntimeError("PIN_MISMATCH_"+k)
    return paths
def input_hash(audit, target):
    return next((v for k,v in audit["input_sha256"].items() if Path(k).resolve()==target.resolve()),None)
def need(ok, label):
    if not ok: raise RuntimeError("UPSTREAM_EVIDENCE_MISMATCH_"+label)
def evidence(r,a):
    c=r["families"]["jar"]["exact_geometry_certificate"]; s=c["spans"]; j=a["families"]["jar"]; q=j["spans"]
    side=lambda x:not x["semantic_base_flat"] and not x["semantic_neck_cylindrical"]
    need(r["status"]=="GEOMETRY_ENGINEERING_CANDIDATE_ONLY" and len(s)==len(q)==12,"result_identity")
    need(sum(side(x) for x in s)==10 and sum(x["semantic_base_flat"] for x in s)==1 and sum(x["semantic_neck_cylindrical"] for x in s)==1,"span_kinds")
    need(c["all_spans_regular_proved"] and all(x["open_span_regular"] and x["endpoint_tangents_nonzero"] for x in s),"saved_regular"); need(all(x["z_derivative_poles_nonnegative"] and x["z_monotonicity_status"]=="PROVED_BY_POLE_SIGNS" for x in s),"saved_monotonicity")
    need(c["all_C4"] and len(c["joins"])==11 and all(x["exact_C4"] and all(x["derivative_orders_0_to_4_equal"]) for x in c["joins"]),"saved_C4"); need(c["all_features_exact"] and len(c["feature_checks"])==5 and all(x["exact"] for x in c["feature_checks"]),"saved_features")
    r9={i:x["radius_9mm_status"] for i,x in enumerate(s)}
    side_r9=sum(r9[i]=="PROVED_R9_ON_CLOSED_NONFLAT_SPAN" for i in r9 if side(s[i]))
    need(side_r9==10 and all(r9[i]=="EXCLUDED_STRAIGHT_MERIDIAN_BASE_OR_NECK" for i in r9 if not side(s[i])),"saved_R9")
    need(j["engineering_screens_all_pass"] and j["saved_reconstruction_matches"],"audit_identity"); need(all(x["open_regular_poles"] and x["endpoint_tangents_nonzero"] and x["radial_direction_poles"] and x["z_monotone_poles"] and x["hull"] and x["matches_saved"] for x in q),"audit_regular")
    need(sum(x["R9_status"]=="PROVED_R9_ON_CLOSED_NONFLAT_SPAN" for x in q)==10 and sum(x["R9_status"]=="EXCLUDED_STRAIGHT_MERIDIAN_BASE_OR_NECK" for x in q)==2,"audit_R9"); need(len(j["joins"])==11 and all(x["matches_saved"] and all(x["D0_to_D4"]) for x in j["joins"]),"audit_C4")
    need(len(j["features"])==5 and all(x["exact"] and x["matches_saved"] for x in j["features"]),"audit_features"); need(len(j["reference_speed"])==12 and all(x["all_at_least_1"] and x["matches_saved"] for x in j["reference_speed"]),"audit_reference_speed")
    need(all(s[i]["semantic_base_flat"]==q[i]["flat_base"] and s[i]["semantic_neck_cylindrical"]==q[i]["cylindrical_neck"] for i in range(12)),"span_kind_crosscheck")
    return {"sides_R9_pass":side_r9,"spans_regular_pass":12,"C4_joins_pass":11,"features_pass":5,"straight_exclusions":2,"upstream_r9_all_side_spans_pass":True,"upstream_regular_all_spans_pass":True}
def blend(a,b,t): return tuple(t*x+(1-t)*y for x,y in zip(a,b))
def insert_once(c,uvec,p,u):
    n=len(c)-1; mult=sum(x==u for x in uvec)
    if mult>=p: raise RuntimeError("UNEXPECTED_KNOT_MULTIPLICITY")
    k=next((k for k in range(p,n+1) if uvec[k]<=u<uvec[k+1]),None)
    if k is None: raise RuntimeError("KNOT_SPAN_NOT_FOUND")
    out=[None]*(n+2)
    for i in range(k-p+1): out[i]=c[i]
    for i in range(k-mult,n+1): out[i+1]=c[i]
    for i in range(k-p+1,k-mult+1):
        den=uvec[i+p]-uvec[i]
        if den<=0: raise RuntimeError("NONPOSITIVE_BOEHM_DENOMINATOR")
        out[i]=blend(c[i],c[i-1],(u-uvec[i])/den)
    if any(x is None for x in out): raise RuntimeError("BOEHM_UNFILLED_CONTROL")
    return tuple(out),tuple(uvec[:k+1])+(u,)+tuple(uvec[k+1:])
def extract(points):
    p=5; c=tuple(tuple(F(str(v)) for v in xy) for xy in points)
    if len(c)!=17 or any(len(x)!=2 for x in c): raise RuntimeError("SAVED_CONTROL_FORMAT_UNEXPECTED")
    u=tuple([F(0)]*6+[F(k,12) for k in range(1,12)]+[F(1)]*6); calls=0
    for k in range(1,12):
        knot=F(k,12)
        while sum(x==knot for x in u)<p:
            c,u=insert_once(c,u,p,knot); calls+=1
    if len(c)!=61: raise RuntimeError("BEZIER_EXTRACTION_COUNT_NOT_61")
    return [c[i*p:i*p+p+1] for i in range(12)],calls
def loadkernel(path):
    spec=importlib.util.spec_from_file_location("normal_offset_kernel",path)
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
def worker(paths,pins):
    for k,p in paths.items():
        expected=pins["files"][k]["sha256"] if k in pins["files"] else pins["inputs"][k]["sha256"]
        if sha(p)!=expected: raise RuntimeError("WORKER_PIN_CHANGED_"+k)
    result_path,audit_path=paths["saved_result"],paths["independent_audit"]
    r=json.loads(result_path.read_text(encoding="utf-8"),parse_float=Decimal); a=json.loads(audit_path.read_text(encoding="utf-8"),parse_float=Decimal)
    need(r["source_pins"]["frozen_inputs"]["driver_sha256"]==pins["inputs"]["frozen_driver"]["sha256"],"embedded_driver_pin")
    need(input_hash(a,result_path)==pins["inputs"]["saved_result"]["sha256"],"audit_result_pin")
    need(input_hash(a,paths["frozen_driver"])==pins["inputs"]["frozen_driver"]["sha256"],"audit_driver_pin")
    ev=evidence(r,a)  # Fail closed before control extraction or certificate arithmetic.
    jar=r["families"]["jar"]; kinds=jar["exact_geometry_certificate"]["spans"]; bezier,boehm_calls=extract(jar["control_points_rz_mm"])
    kernel=loadkernel(paths["source"]); spans=[]; exact=[]
    for i,(controls,meta) in enumerate(zip(bezier,kinds)):
        kind="flat_base" if meta["semantic_base_flat"] else "straight_neck" if meta["semantic_neck_cylindrical"] else "side"
        rr=[kernel.q(x[0]) for x in controls]; zz=[kernel.q(x[1]) for x in controls]
        row={"span_id":str(i),"kind":kind,"r_bernstein_mm":rr,"z_bernstein_mm":zz}; spans.append(row)
        exact.append({"span_index":i,"kind":kind,"exact_bezier_controls_rz_mm":[[kernel.qs(x),kernel.qs(y)] for x,y in controls],
                      "r_bernstein_mm":[kernel.qs(x) for x in rr],"z_bernstein_mm":[kernel.qs(x) for x in zz],
                      "Q_bernstein_degree18":[kernel.qs(x) for x in kernel.radius_numerator(rr,zz)]})
    study=kernel.certify_study(spans,upstream_r9_all_side_spans_pass=ev["upstream_r9_all_side_spans_pass"],
                               upstream_regular_all_spans_pass=ev["upstream_regular_all_spans_pass"])
    for i in range(12): exact[i]["certificate"]=study["spans"][i]; exact[i]["true_normal_display_25"]=kernel.true_offset_display_25(spans[i])
    case=json.loads(paths["false_case"].read_text(encoding="utf-8"))
    f1,f2=case["fixtures"]
    cr=[kernel.q(x) for x in f1["r_bernstein_mm"]]; cz=[kernel.q(x) for x in f1["z_bernstein_mm"]]
    need(not f1["budget_shared_with_jar_study"] and not f2["budget_shared_with_jar_study"],"fixture_budget_independence")
    fq=kernel.radius_numerator(cr,kernel.derivative(cz)); b1=kernel.StudyBudget(f1["node_limit"],f1["depth_limit"])
    false1=kernel.certify_nonnegative(fq,b1)
    b2=kernel.StudyBudget(f2["node_limit"],f2["depth_limit"])
    false2=kernel.certify_nonnegative([kernel.q(x) for x in f2["bernstein_coefficients"]],b2)
    false_ok=(false1["status"]=="EXACT_COUNTEREXAMPLE" and all(x==F(-8) for x in fq) and (false2["status"]=="UNKNOWN" or false2["status"].startswith("UNKNOWN_")))
    out={"status":study["status"] if false_ok else "UNKNOWN_NO_CANDIDATE",
         "study_certificate_status":study["status"],"scope":"jar_meridian_2d_only","global_wall_status":"UNKNOWN",
         "normal_strip_global_injectivity":"UNKNOWN","upstream_evidence":ev,"study":study,"spans":exact,
         "false_fixture_checks":"PASS" if false_ok else "FAIL",
         "false_fixtures":[{"id":f1["id"],"expected_status":f1["expected_status"],"budget_nodes":b1.nodes,"budget_depth":b1.depth_limit,"result":false1},
                            {"id":f2["id"],"expected_status":f2["expected_status"],"budget_nodes":b2.nodes,"budget_depth":b2.depth_limit,"result":false2}],
         "calls":{"evidence_validation":1,"saved_control_extraction":1,"boehm_insertions":boehm_calls,
                  "jar_certify_study":1,"jar_nonnegative_primitive_calls":37,"jar_display_25_calls":12,
                  "false_fixture_certificate_calls":2,"false_fixture_budgets_independent":True}}
    return out
def main():
    if len(sys.argv)>1 and sys.argv[1]=="--worker":
        if os.environ.get("NORMAL_OFFSET_ONCE_CHILD")!="1": return 4
        try:
            p=readpins(); paths=checkpins(p); data=worker(paths,p)
            raw=(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+"\n").encode("utf-8")
            if len(raw)>MAX_RESULT_BYTES: raise RuntimeError("RESULT_RESERVE_LIMIT_EXCEEDED")
            OUT.write_bytes(raw); print(json.dumps({"status":data["status"],"spans":len(data["spans"]),"bytes":len(raw)})); return 0
        except BaseException as e:
            print(json.dumps({"error":type(e).__name__,"detail":str(e)[:512]}),file=sys.stderr); return 2
    if sys.argv[1:]!=["--root-go"]: print("SOURCE_ONLY: root review and --root-go required"); return 4
    start=time.monotonic(); p=readpins(); paths=checkpins(p)
    if any(x.exists() for x in (LOCK,OUT,RECEIPT,STDOUT,STDERR)): raise RuntimeError("ONE_SHOT_OUTPUT_ALREADY_EXISTS")
    with LOCK.open("x",encoding="utf-8") as f: f.write("consumed once; no retry\n")
    before={k:sha(v) for k,v in paths.items()}; before["source_pins"]=sha(PINS)
    argv=[sys.executable,"-B",str(Path(__file__).resolve()),"--worker"]
    status,rc,stdout,stderr="FAILURE",2,b"",b""; process_attempted=False; runner_error=None
    try:
        env=dict(os.environ,NORMAL_OFFSET_ONCE_CHILD="1"); process_attempted=True
        pr=subprocess.run(argv,cwd=ROOT,capture_output=True,text=False,timeout=max(0.1,MAX_SECONDS-(time.monotonic()-start)),env=env,check=False)
        rc,stdout,stderr=pr.returncode,pr.stdout,pr.stderr; status="COMPLETE" if rc==0 else "FAILURE"
    except subprocess.TimeoutExpired as e:
        rc,status=124,"TIMEOUT_NO_RETRY"; stdout,stderr=raw_bytes(e.stdout),raw_bytes(e.stderr)
    except Exception as e:
        rc,status,runner_error=127,"WORKER_LAUNCH_FAILURE",f"{type(e).__name__}: {str(e)[:512]}"
    stdout,stderr=raw_bytes(stdout),raw_bytes(stderr)
    if process_attempted: STDOUT.write_bytes(stdout); STDERR.write_bytes(stderr)
    after={k:sha(v) for k,v in paths.items()}; after["source_pins"]=sha(PINS)
    elapsed=round(time.monotonic()-start,3)
    if elapsed>MAX_SECONDS and rc==0: rc,status=124,"OUTER_LIMIT_EXCEEDED"
    inputs_unchanged=before==after
    if not inputs_unchanged:
        if rc==0: rc=125
        status="INPUT_CHANGED"
    receipt={"status":status,"actual_argv":argv,"user_argv":sys.argv,"actual_rc":rc,
             "elapsed_seconds":elapsed,"outer_limit_seconds":MAX_SECONDS,"output_limit_bytes_total":MAX_BYTES,
             "result_limit_bytes_reserved":MAX_RESULT_BYTES,"hashes_before":before,"hashes_after":after,
             "inputs_unchanged":inputs_unchanged,"result_sha256":sha(OUT) if OUT.exists() else None,
              "captured_stdout":{"file":STDOUT.name if process_attempted else None,"bytes":len(stdout),"sha256":sha_bytes(stdout),"summary":stdout.decode("utf-8",errors="replace")[:2048]},
              "captured_stderr":{"file":STDERR.name if process_attempted else None,"bytes":len(stderr),"sha256":sha_bytes(stderr),"summary":stderr.decode("utf-8",errors="replace")[:2048]},
             "runner_error":runner_error,"retry_permitted":False,"budget_status":"CHECKING"}
    base=(OUT.stat().st_size if OUT.exists() else 0)+(len(stdout)+len(stderr) if process_attempted else 0)+LOCK.stat().st_size
    def encode_receipt(): return (json.dumps(receipt,indent=2,ensure_ascii=False)+"\n").encode("utf-8")
    def fixed_receipt():
        for _ in range(10):
            receipt["total_persisted_bytes_status"]="EXACT_FIXED_POINT"; receipt["total_persisted_bytes"]=base+len(encode_receipt())
            encoded=encode_receipt(); actual=base+len(encoded)
            if receipt["total_persisted_bytes"]==actual: return encoded,actual,True
        receipt["total_persisted_bytes_status"]="UNKNOWN_FIXED_POINT_FAILED"
        receipt["total_persisted_bytes"]=None
        encoded=encode_receipt(); return encoded,base+len(encoded),False
    encoded,total,exact=fixed_receipt()
    if total>MAX_BYTES:
        status="OUTPUT_LIMIT_EXCEEDED"
        if rc==0: rc=126
        receipt.update(status=status,actual_rc=rc,budget_status="EXCEEDED")
        encoded,total,exact=fixed_receipt()
    else:
        receipt["budget_status"]="WITHIN_LIMIT"
        encoded,total,exact=fixed_receipt()
    if not exact:
        receipt.update(status="RECEIPT_COUNT_UNKNOWN",budget_status="UNKNOWN",
                       total_persisted_bytes_status="UNKNOWN_FIXED_POINT_FAILED",total_persisted_bytes=None)
        encoded=encode_receipt(); total=base+len(encoded)
    if total>MAX_BYTES: raise RuntimeError("TOTAL_OUTPUT_LIMIT_4MIB_EXCEEDED")
    RECEIPT.write_bytes(encoded)
    print(json.dumps({"status":receipt["status"],"actual_rc":rc,"elapsed_seconds":elapsed,"result_sha256":receipt["result_sha256"],"receipt_sha256":sha(RECEIPT),"retry_permitted":False})); return rc
if __name__=="__main__": raise SystemExit(main())
