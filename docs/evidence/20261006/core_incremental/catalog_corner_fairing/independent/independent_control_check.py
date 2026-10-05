import json, math
from pathlib import Path

root = Path.cwd()
audit = json.loads((root / 'vesselforge/tmp/review_20261006/catalog_corner_fairing_20261006/DESIGN_AUDIT.json').read_text(encoding='utf-8'))
EPS = 2e-9

def sub(a,b): return (a[0]-b[0], a[1]-b[1])
def add(a,b): return (a[0]+b[0], a[1]+b[1])
def mul(a,s): return (a[0]*s, a[1]*s)
def dot(a,b): return a[0]*b[0]+a[1]*b[1]
def cross(a,b): return a[0]*b[1]-a[1]*b[0]
def norm(a): return math.hypot(a[0],a[1])
def unit(a):
    n=norm(a)
    if n<=0: raise ValueError('zero vector')
    return (a[0]/n,a[1]/n)
def on_seg(p,a,b,tol=EPS):
    ab=sub(b,a); ap=sub(p,a)
    return abs(cross(ab,ap)) <= tol*max(1.0,norm(ab)) and -tol <= dot(ap,ab) <= dot(ab,ab)+tol

def bezier_eval(P,t):
    omt=1.0-t
    p=[0.0,0.0]; d1=[0.0,0.0]; d2=[0.0,0.0]
    for i,pt in enumerate(P):
        w=math.comb(5,i)*omt**(5-i)*t**i
        p[0]+=w*pt[0]; p[1]+=w*pt[1]
    diffs=[sub(P[i+1],P[i]) for i in range(5)]
    for i,d in enumerate(diffs):
        w=5.0*math.comb(4,i)*omt**(4-i)*t**i
        d1[0]+=w*d[0]; d1[1]+=w*d[1]
    for i in range(4):
        d=add(sub(P[i+2],mul(P[i+1],2.0)),P[i])
        w=20.0*math.comb(3,i)*omt**(3-i)*t**i
        d2[0]+=w*d[0]; d2[1]+=w*d[1]
    speed=norm(d1)
    curvature=abs(cross(tuple(d1),tuple(d2)))/(speed**3) if speed>0 else math.inf
    return (tuple(p),speed,curvature)

checks=[]; total_samples=0; total_quintics=0
for fam in ('bowl','jar'):
    case=audit['cases'][fam]
    case_curve_rows=[]; case_samples=0
    for side in ('outer','inner'):
        original=case[f'original_{side}_profile_mm']
        fair=case[f'faired_{side}_sampled_profile_mm']
        assert fair[0] == original[0] and fair[-1] == original[-1]
        rows=case['corner_treatment'][f'{side}_profile']
        for row in rows:
            if row.get('status') != 'QUINTIC_FAIRING': continue
            P=[tuple(p) for p in row['control_points_rz_mm']]
            i=int(row['vertex_index']); V=tuple(original[i]); prev=tuple(original[i-1]); nex=tuple(original[i+1])
            tin=unit(sub(V,prev)); tout=unit(sub(nex,V)); trim=float(row['trim_distance_mm_each_side'])
            assert len(P)==6
            # Independent endpoint/tangent/zero-curvature identities from source vertices and frozen controls.
            assert norm(sub(P[0],sub(V,mul(tin,trim)))) < 1e-8
            assert norm(sub(P[5],add(V,mul(tout,trim)))) < 1e-8
            assert norm(sub(unit(sub(P[1],P[0])),tin)) < 1e-8
            assert norm(sub(unit(sub(P[5],P[4])),tout)) < 1e-8
            assert on_seg(P[0],sub(V,mul(tin,trim)),V)
            assert on_seg(P[1],sub(V,mul(tin,trim)),V)
            assert on_seg(P[2],sub(V,mul(tin,trim)),V)
            assert on_seg(P[3],V,add(V,mul(tout,trim)))
            assert on_seg(P[4],V,add(V,mul(tout,trim)))
            assert on_seg(P[5],V,add(V,mul(tout,trim)))
            assert min(p[0] for p in P) >= -1e-9
            bunit=unit(add(tin,tout)); d=[sub(P[j+1],P[j]) for j in range(5)]
            proj=[dot(v,bunit) for v in d]
            assert min(proj)>0.0
            speed_lb=5.0*min(proj)
            dd=[add(sub(P[j+2],mul(P[j+1],2.0)),P[j]) for j in range(4)]
            d2ub=20.0*max(norm(v) for v in dd)
            kub=d2ub/(speed_lb*speed_lb)
            assert abs(kub-float(row['global_curvature_upper_bound_per_mm'])) <= 1e-10*max(1.0,kub)
            # At endpoints the actual first and second derivative cross products vanish.
            start_cross=cross(sub(P[1],P[0]),add(sub(P[2],mul(P[1],2.0)),P[0]))
            end_cross=cross(sub(P[5],P[4]),add(sub(P[5],mul(P[4],2.0)),P[3]))
            assert abs(start_cross)<1e-8 and abs(end_cross)<1e-8
            curvs=[]; speeds=[]
            for k in range(9):
                _,v,c=bezier_eval(P,k/8.0); speeds.append(v); curvs.append(c); case_samples+=1
            assert min(speeds)>0.0 and max(curvs)<=kub*(1.0+1e-10)
            case_curve_rows.append({'side':side,'vertex_index':i,'turn_deg':row['signed_turn_deg'],'upper_bound_per_mm':kub,'sampled_max_per_mm':max(curvs),'sampled_min_radius_mm':1.0/max(curvs) if max(curvs)>0 else None,'bound_to_sampled_ratio':kub/max(curvs) if max(curvs)>0 else None,'minimum_control_projection_mm':min(proj),'endpoint_cross_max_mm2':max(abs(start_cross),abs(end_cross))})
            total_samples+=9; total_quintics+=1
    # Recomputed profile-target invariants from saved arrays, not source execution.
    params=case['catalog_parameters_unchanged']; outer=case['faired_outer_sampled_profile_mm']; inner=case['faired_inner_sampled_profile_mm']
    target={
        'outer_endpoints_unchanged': outer[0]==case['original_outer_profile_mm'][0] and outer[-1]==case['original_outer_profile_mm'][-1],
        'inner_endpoints_unchanged': inner[0]==case['original_inner_profile_mm'][0] and inner[-1]==case['original_inner_profile_mm'][-1],
        'outer_bottom_z_mm': min(p[1] for p in outer),
        'inner_floor_z_mm': inner[0][1],
        'clear_inside_mouth_diameter_mm': 2.0*inner[-1][0],
        'total_height_mm': max(p[1] for p in outer),
        'maximum_outer_radius_mm': max(p[0] for p in outer),
        'targets_expected': {'base':params['base_thickness_declaration_mm'],'mouth':params['mouth_diameter_mm'],'height':params['height_mm'],'radius':params['max_radius_mm']},
    }
    assert target['outer_endpoints_unchanged'] and target['inner_endpoints_unchanged']
    assert abs(target['outer_bottom_z_mm'])<1e-9
    assert abs(target['inner_floor_z_mm']-params['base_thickness_declaration_mm'])<1e-9
    assert abs(target['clear_inside_mouth_diameter_mm']-params['mouth_diameter_mm'])<1e-9
    assert abs(target['total_height_mm']-params['height_mm'])<1e-9
    assert abs(target['maximum_outer_radius_mm']-params['max_radius_mm'])<1e-9
    maxrow=max(case_curve_rows,key=lambda r:r['upper_bound_per_mm'])
    samplemax=max(r['sampled_max_per_mm'] for r in case_curve_rows)
    assert abs(maxrow['upper_bound_per_mm']-case['curvature_checks']['largest_quintic_curvature_upper_bound_per_mm']) < 1e-9
    assert abs(samplemax-case['curvature_checks']['maximum_sampled_curvature_per_mm']) < 1e-9
    checks.append({'family':fam,'quintic_count':len(case_curve_rows),'recomputed_curve_parameter_samples':case_samples,'semantic_targets':target,'largest_bound_corner':maxrow,'max_sampled_curvature_per_mm':samplemax,'all_sampled_curvatures_below_control_bound':True,'corners':case_curve_rows})
assert total_samples <=256
result={'input_audit_status':audit['status'],'saved_audit_curve_parameter_evaluations':audit['sample_cap']['curve_parameter_evaluations_used'],'saved_audit_contour_vertices':audit['sample_cap']['contour_sample_vertices_used'],'saved_audit_cap':audit['sample_cap']['limit'],'single_saved_audit_count_interpretation':'one source execution combined across bowl and jar; not per-case and not multiplied across separate reviews','independent_recheck':{'method':'pure Python direct evaluation of saved control points plus control-polygon algebra; no candidate module imported; no geometry rebuilt','quintics':total_quintics,'curve_parameter_samples':total_samples,'noncad_samples_cap':256,'cases':checks},'no_physical_stress_or_global_normal_wall_claim':True}
out=Path('vesselforge/tmp/review_20261006/catalog_corner_fairing_independent/INDEPENDENT_ALGEBRA_CHECK.json')
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS_CONTROL_POINT_ALGEBRA_RECHECK','quintics':total_quintics,'samples':total_samples,'cases':[{'family':x['family'],'quintics':x['quintic_count'],'samples':x['recomputed_curve_parameter_samples'],'worst_bound_corner':x['largest_bound_corner'],'max_sampled_curvature_per_mm':x['max_sampled_curvature_per_mm'],'semantics':x['semantic_targets']} for x in checks]},indent=2,allow_nan=False))


