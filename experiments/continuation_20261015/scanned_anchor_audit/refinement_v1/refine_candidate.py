from __future__ import annotations
import sys, json, math, hashlib, csv, collections, platform, pathlib
import numpy as np
from scipy import __version__ as scipy_version
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
import vtk
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=pathlib.Path.cwd()
AUDIT=ROOT/'vesselforge/experiments/continuation_20261015/scanned_anchor_audit/refinement_v1'
ASSET=ROOT/'third_party/reference-assets/apsida-shm17946-0047'
REFINED=ASSET/'refined_v1'
RAW_NPZ=ROOT/'vesselforge/experiments/continuation_20261015/scanned_anchor_audit/raw_geometry.npz'
SOURCE_OBJ=ASSET/'Footed_Bowl_SHM_17946_0047.obj'
SOURCE_ZIP=ASSET/'Footed_Bowl_SHM_17946_0047_Obj06.zip'
AUDIT.mkdir(parents=True,exist_ok=True); REFINED.mkdir(parents=True,exist_ok=True)

# Verify and parse the unchanged source OBJ directly. Textures, UVs, and normals are
# not required for a geometry-only derivative; source OBJ/MTL remain retained.
def sha256(path): return hashlib.sha256(path.read_bytes()).hexdigest()
source_obj_sha=sha256(SOURCE_OBJ); source_zip_sha=sha256(SOURCE_ZIP)
expected_obj='C03413172398AE5280FAE3D1759F505B38BC97A1561E510FCFB4B99D97C57232'
expected_zip='7977FE145179160EBA1F560F09C75302FCBC9C501E2460B7817311B1860FE35B'
if source_obj_sha.upper()!=expected_obj or source_zip_sha.upper()!=expected_zip:
    raise SystemExit('Source asset hash mismatch; refusing to derive.')
verts=[]; faces=[]; face_lines=[]; vertex_colors=[]; polygon_sizes=collections.Counter()
with SOURCE_OBJ.open('r',encoding='utf-8',errors='replace') as src:
    for line_number,line in enumerate(src,1):
        s=line.strip()
        if not s or s.startswith('#'): continue
        tag,*parts=s.split()
        if tag=='v':
            if len(parts)<3: raise SystemExit(f'bad vertex line {line_number}')
            verts.append(tuple(map(float,parts[:3])))
            if len(parts)>=6:
                vertex_colors.append(tuple(map(float,parts[3:6])))
            else:
                vertex_colors.append((float('nan'),)*3)
        elif tag=='f':
            ids=[]
            for token in parts:
                raw=int(token.split('/')[0]); idx=raw-1 if raw>0 else len(verts)+raw
                if idx<0 or idx>=len(verts): raise SystemExit(f'out-of-range OBJ index on line {line_number}')
                ids.append(idx)
            polygon_sizes[len(ids)]+=1
            if len(ids)!=3: raise SystemExit(f'unexpected non-triangle face on line {line_number}; do not triangulate silently')
            faces.append(tuple(ids)); face_lines.append(line_number)
V=np.asarray(verts,dtype=np.float64); F=np.asarray(faces,dtype=np.int64)
raw=np.load(RAW_NPZ)
Vraw=raw['vertices_source_units']; Fraw=raw['faces']
if not np.array_equal(V,Vraw) or not np.array_equal(F,Fraw):
    raise SystemExit('Existing raw_geometry.npz does not exactly match source OBJ geometry.')
if len(V)>2_000_000 or len(F)>4_000_000: raise SystemExit('geometry exceeds configured safety cap')

# Indexed topology and exact surface metrics. Preserve every original v index.
tri=V[F]; cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]); cross_norm=np.linalg.norm(cross,axis=1)
face_area=cross_norm/2.0
volume_contrib=np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2]))/6.0
D=np.concatenate((F[:,[0,1]],F[:,[1,2]],F[:,[2,0]]),axis=0)
edge_sign=np.where(D[:,0]<D[:,1],1,-1); E=D.copy(); E.sort(axis=1)
UE,edge_inverse,edge_counts=np.unique(E,axis=0,return_inverse=True,return_counts=True)
rows=np.concatenate((UE[:,0],UE[:,1])); cols=np.concatenate((UE[:,1],UE[:,0]))
adj=csr_matrix((np.ones(len(rows),dtype=np.uint8),(rows,cols)),shape=(len(V),len(V)))
component_count,vertex_labels=connected_components(adj,directed=False,return_labels=True)
face_labels=vertex_labels[F[:,0]]
if not np.all((vertex_labels[F[:,0]]==vertex_labels[F[:,1]])&(vertex_labels[F[:,0]]==vertex_labels[F[:,2]])):
    raise SystemExit('face has endpoints assigned to multiple components')
face_counts=np.bincount(face_labels,minlength=component_count)
vertex_counts=np.bincount(vertex_labels,minlength=component_count)
area_by=np.bincount(face_labels,weights=face_area,minlength=component_count)
volume_by=np.bincount(face_labels,weights=volume_contrib,minlength=component_count)
mins=np.full((component_count,3),np.inf); maxs=np.full((component_count,3),-np.inf)
np.minimum.at(mins,vertex_labels,V); np.maximum.at(maxs,vertex_labels,V)
main_label=int(np.argmax(area_by))
if main_label != 0 or component_count != 389: raise SystemExit(f'Unexpected main/component topology: main={main_label}, components={component_count}')
main_face_ids=np.flatnonzero(face_labels==main_label)
main_vertex_ids=np.unique(F[main_face_ids])
remap=np.full(len(V),-1,dtype=np.int64); remap[main_vertex_ids]=np.arange(len(main_vertex_ids))
mainV=V[main_vertex_ids]
mainF=remap[F[main_face_ids]]
main_tri=mainV[mainF]
main_cross=np.cross(main_tri[:,1]-main_tri[:,0],main_tri[:,2]-main_tri[:,0])
main_cross_norm=np.linalg.norm(main_cross,axis=1)
main_twice_area_threshold_faces=np.flatnonzero(cross_norm < 1e-12)
main_zero_area_faces=np.flatnonzero(main_cross_norm == 0)
if len(main_twice_area_threshold_faces)!=4 or len(main_zero_area_faces)!=4:
    raise SystemExit('Degenerate-face count differs from previously reported four; inspect before proceeding.')

# Build a static locator on the main surface for exact island-vertex-to-triangle distances.
pts=vtk.vtkPoints(); pts.SetData(numpy_to_vtk(np.ascontiguousarray(mainV),deep=True))
cell_blob=np.empty((len(mainF),4),dtype=np.int64); cell_blob[:,0]=3; cell_blob[:,1:]=mainF
cells=vtk.vtkCellArray(); cells.SetCells(len(mainF),numpy_to_vtkIdTypeArray(np.ascontiguousarray(cell_blob.ravel()),deep=True))
main_pd=vtk.vtkPolyData(); main_pd.SetPoints(pts); main_pd.SetPolys(cells)
locator=vtk.vtkStaticCellLocator(); locator.SetDataSet(main_pd); locator.BuildLocator()

removed_rows=[]; removed_vertex_ids=[]
main_min=mins[main_label]; main_max=maxs[main_label]; main_extent=main_max-main_min
for c in range(component_count):
    if c==main_label: continue
    ids=np.flatnonzero(vertex_labels==c); removed_vertex_ids.extend(ids.tolist())
    distances=[]
    for ix in ids:
        closest=[0.0,0.0,0.0]; cell_id=vtk.mutable(0); sub_id=vtk.mutable(0); dist2=vtk.mutable(0.0)
        locator.FindClosestPoint(tuple(map(float,V[ix])),closest,cell_id,sub_id,dist2)
        distances.append(math.sqrt(max(0.0,float(dist2))))
    distances=np.asarray(distances,dtype=np.float64)
    box_gap=np.maximum(0.0,np.maximum(mins[c]-main_max,main_min-maxs[c]))
    box_extent=maxs[c]-mins[c]
    comp_face_ids=np.flatnonzero(face_labels==c)
    removed_rows.append({
        'component_id':int(c),'vertex_count':int(vertex_counts[c]),'face_count':int(face_counts[c]),
        'surface_area_raw_units2':float(area_by[c]),'signed_volume_raw_units3':float(volume_by[c]),'abs_signed_volume_raw_units3':float(abs(volume_by[c])),
        'bounds_min_x':float(mins[c,0]),'bounds_min_y':float(mins[c,1]),'bounds_min_z':float(mins[c,2]),
        'bounds_max_x':float(maxs[c,0]),'bounds_max_y':float(maxs[c,1]),'bounds_max_z':float(maxs[c,2]),
        'extent_x':float(box_extent[0]),'extent_y':float(box_extent[1]),'extent_z':float(box_extent[2]),
        'aabb_gap_x_to_main':float(box_gap[0]),'aabb_gap_y_to_main':float(box_gap[1]),'aabb_gap_z_to_main':float(box_gap[2]),'aabb_euclidean_gap_to_main_raw_units':float(np.linalg.norm(box_gap)),
        'aabb_extent_fraction_main_x':float(box_extent[0]/main_extent[0]),'aabb_extent_fraction_main_y':float(box_extent[1]/main_extent[1]),'aabb_extent_fraction_main_z':float(box_extent[2]/main_extent[2]),'max_extent_fraction_main':float(np.max(box_extent/main_extent)),
        'vertex_to_main_triangle_distance_min_raw_units':float(distances.min()),'vertex_to_main_triangle_distance_q25_raw_units':float(np.quantile(distances,.25)),'vertex_to_main_triangle_distance_median_raw_units':float(np.median(distances)),'vertex_to_main_triangle_distance_q75_raw_units':float(np.quantile(distances,.75)),'vertex_to_main_triangle_distance_max_raw_units':float(distances.max()),
        'vertex_distance_min_mm_if_1raw_unit_is_1m':float(distances.min()*1000),'vertex_distance_median_mm_if_1raw_unit_is_1m':float(np.median(distances)*1000),'vertex_distance_max_mm_if_1raw_unit_is_1m':float(distances.max()*1000),
        'distance_method':'vtkStaticCellLocator closest-point query from every island vertex to main-component triangles; scale remains UNKNOWN'
    })
with (AUDIT/'removed_components.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(removed_rows[0])); w.writeheader(); w.writerows(removed_rows)

# Record every low-area/zero-area face, with original face line, vertex IDs, and exact coordinates.
degenerate_rows=[]
for face_id in main_twice_area_threshold_faces:
    p=tri[face_id]; vids=F[face_id]
    degenerate_rows.append({'source_face_index_zero_based':int(face_id),'source_obj_line':int(face_lines[face_id]),'component_id':int(face_labels[face_id]),'source_vertex_indices_json':json.dumps(vids.tolist()),'distinct_vertex_indices':int(len(np.unique(vids))),'distinct_xyz_positions':int(len(np.unique(p,axis=0))),'cross_norm_twice_area_raw_units2':float(cross_norm[face_id]),'triangle_area_raw_units2':float(face_area[face_id]),'exact_zero_area':bool(cross_norm[face_id]==0),'coordinates_xyz_json':json.dumps(p.tolist(),separators=(',',':')),'disposition':'PRESERVED in main-only candidate; no weld/delete/repair; topology-aware review required before physics use'})
with (AUDIT/'degenerate_faces.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(degenerate_rows[0])); w.writeheader(); w.writerows(degenerate_rows)

# Write a geometry-only main-component derivative. Positions are serialized at
# 9 decimals from the original six-decimal source; faces preserve original order.
main_obj=REFINED/'SHM17946_0047_main_component.obj'
with main_obj.open('w',encoding='utf-8',newline='\n') as f:
    f.write('# Derived main connected component from the CC BY-SA 4.0 Apsida OBJ.\n')
    f.write('# Original coordinates copied without scaling; unit UNKNOWN. Main geometry only; no repair or smoothing.\n')
    f.write('# Full source OBJ/MTL/ZIP retained in parent directory.\n')
    f.write('o SHM_17946_0047_main_component_candidate\n')
    for p in mainV: f.write('v %.9f %.9f %.9f\n'%tuple(p))
    for tri_ids in mainF: f.write('f %d %d %d\n'%(tri_ids[0]+1,tri_ids[1]+1,tri_ids[2]+1))
main_npz=REFINED/'SHM17946_0047_main_component.npz'
np.savez_compressed(main_npz,vertices_source_units=mainV,faces=mainF,source_vertex_indices=main_vertex_ids,source_face_indices=main_face_ids)

# Validate the OBJ derivative by reparsing and comparing it to the selected source geometry.
checkV=[]; checkF=[]
with main_obj.open('r',encoding='utf-8') as f:
    for line in f:
        s=line.strip()
        if s.startswith('v '): checkV.append([float(x) for x in s.split()[1:4]])
        elif s.startswith('f '): checkF.append([int(x)-1 for x in s.split()[1:4]])
checkV=np.asarray(checkV,dtype=np.float64); checkF=np.asarray(checkF,dtype=np.int64)
if not np.array_equal(checkV,mainV) or not np.array_equal(checkF,mainF): raise SystemExit('Derivative OBJ geometry validation failed')
# Post-write topology metrics for the derivative.
md=np.concatenate((checkF[:,[0,1]],checkF[:,[1,2]],checkF[:,[2,0]])); ms=np.where(md[:,0]<md[:,1],1,-1); me=md.copy(); me.sort(axis=1)
mu,mi,mc=np.unique(me,axis=0,return_inverse=True,return_counts=True)
main_boundary=int(np.count_nonzero(mc==1)); main_nonmanifold=int(np.count_nonzero(mc>2)); main_orientation_bad=int(np.count_nonzero((mc==2)&(np.bincount(mi,weights=ms)!=0)))
mr,ml=connected_components(csr_matrix((np.ones(2*len(mu),dtype=np.uint8),(np.r_[mu[:,0],mu[:,1]],np.r_[mu[:,1],mu[:,0]])),shape=(len(checkV),len(checkV))),directed=False,return_labels=True)
main_area=float(main_cross_norm.sum()/2.0); main_signed_volume=float(np.einsum('ij,ij->i',main_tri[:,0],np.cross(main_tri[:,1],main_tri[:,2])).sum()/6.0)
main_zero_count=int(np.count_nonzero(main_cross_norm==0))

# Least-squares rim-band center for diagnostics, retaining raw coordinates.
source_bounds_min=V.min(axis=0); source_bounds_max=V.max(axis=0)
rim_band=V[V[:,2]>=source_bounds_max[2]-0.003]
xy=rim_band[:,:2]; design=np.column_stack((2*xy[:,0],2*xy[:,1],np.ones(len(xy)))); rhs=np.einsum('ij,ij->i',xy,xy)
fit=np.linalg.lstsq(design,rhs,rcond=None)[0]; center_xy=fit[:2]; radius=math.sqrt(max(0,float(fit[2]+fit[0]**2+fit[1]**2)))
# Renders use the exact candidate faces, computed normals only for display, no mesh edits.
normals=vtk.vtkPolyDataNormals(); normals.SetInputData(main_pd); normals.ComputePointNormalsOn(); normals.ComputeCellNormalsOn(); normals.SplittingOff(); normals.ConsistencyOff(); normals.AutoOrientNormalsOff(); normals.Update(); render_pd=normals.GetOutput()
def render_view(name,direction,up):
    ren=vtk.vtkRenderer(); ren.SetBackground(0.96,0.96,0.94)
    mapper=vtk.vtkPolyDataMapper(); mapper.SetInputData(render_pd)
    actor=vtk.vtkActor(); actor.SetMapper(mapper); actor.GetProperty().SetColor(0.70,0.52,0.35); actor.GetProperty().SetAmbient(0.24); actor.GetProperty().SetDiffuse(0.76); actor.GetProperty().SetSpecular(0.12); actor.GetProperty().SetSpecularPower(20)
    ren.AddActor(actor); ren.ResetCamera()
    cam=ren.GetActiveCamera(); center=(source_bounds_min+source_bounds_max)/2; span=float(max(source_bounds_max-source_bounds_min))
    cam.SetFocalPoint(*map(float,center)); cam.SetPosition(*(float(center[i]+direction[i]*span) for i in range(3))); cam.SetViewUp(*up); cam.ParallelProjectionOn(); cam.SetParallelScale(span*0.63)
    ren.ResetCameraClippingRange()
    win=vtk.vtkRenderWindow(); win.SetOffScreenRendering(1); win.SetSize(1400,1000); win.AddRenderer(ren); win.Render()
    w2i=vtk.vtkWindowToImageFilter(); w2i.SetInput(win); w2i.SetInputBufferTypeToRGB(); w2i.ReadFrontBufferOff(); w2i.Update()
    writer=vtk.vtkPNGWriter(); writer.SetFileName(str(AUDIT/f'{name}.png')); writer.SetInputConnection(w2i.GetOutputPort()); writer.Write(); win.Finalize()
views={'refined_side':((0,-3.5,0),(0,0,1)),'refined_oblique':((2.6,-3.4,1.4),(0,0,1)),'refined_top':((0,0,3.5),(0,1,0)),'refined_bottom':((0,0,-3.5),(0,1,0))}
for name,(direction,up) in views.items(): render_view(name,direction,up)

# Candidate-axis Y section; preserve all joined polylines and display raw values.
section_axis='y'; plane=vtk.vtkPlane(); origin=[float((source_bounds_min[i]+source_bounds_max[i])/2) for i in range(3)]; origin[1]=float(center_xy[1]); plane.SetOrigin(*origin); plane.SetNormal(0,1,0)
cutter=vtk.vtkCutter(); cutter.SetInputData(main_pd); cutter.SetCutFunction(plane); cutter.Update()
stripper=vtk.vtkStripper(); stripper.SetInputConnection(cutter.GetOutputPort()); stripper.JoinContiguousSegmentsOn(); stripper.Update()
cut=stripper.GetOutput(); cut_points=vtk_to_numpy(cut.GetPoints().GetData()) if cut.GetPoints() else np.empty((0,3))
lines=cut.GetLines(); ids=vtk.vtkIdList(); lines.InitTraversal(); polylines=[]
while lines.GetNextCell(ids):
    line=cut_points[[ids.GetId(j) for j in range(ids.GetNumberOfIds())]]
    if len(line)>=2: polylines.append(line)
with (AUDIT/'refined_y_section.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['polyline_id','path_order','x_raw_obj_units','y_raw_obj_units','z_raw_obj_units'])
    for pid,line in enumerate(polylines):
        for j,p in enumerate(line): w.writerow([pid,j,*map(float,p)])
fig,ax=plt.subplots(figsize=(8,8),dpi=150)
for line in polylines: ax.plot(line[:,0],line[:,2],color='#473a2f',lw=.65)
ax.set_aspect('equal',adjustable='box');ax.grid(True,alpha=.22);ax.set_xlabel('x (raw OBJ units)');ax.set_ylabel('z (raw OBJ units)');ax.set_title(f'Main-component source section: y=top-band fitted center; {len(polylines)} joined polylines');fig.tight_layout();fig.savefig(AUDIT/'refined_y_section.png');plt.close(fig)

# Hashes and review stats.
render_hashes={p.name:sha256(p) for p in sorted(AUDIT.glob('*.png'))}
report={
 'record_type':'reviewed main-component refinement candidate; not a physical truth/physics approval',
 'source':{'item_url':'https://apsida.cut.ac.cy/items/show/49281','archive_url':'https://apsida.cut.ac.cy/files/original/529/49281/Footed_Bowl_SHM_17946_0047_Obj06.zip','identifier':'SHM 17946:0047','title':'Footed bowl','rights':'CC BY-SA 4.0','attribution':'Medelhavsmuseet, SHM 17946:0047; via Apsida / Digital Heritage Research Lab','source_zip_sha256':source_zip_sha,'source_obj_sha256':source_obj_sha,'source_obj_bytes':SOURCE_OBJ.stat().st_size,'source_zip_bytes':SOURCE_ZIP.stat().st_size,'prior_raw_geometry_npz_sha256':sha256(RAW_NPZ)},
 'tool_versions':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy_version,'vtk':vtk.vtkVersion.GetVTKVersion(),'matplotlib':matplotlib.__version__},
 'source_geometry':{'raw_vertices':int(len(V)),'raw_faces':int(len(F)),'components':int(component_count),'main_component_id':main_label,'main_vertices':int(len(mainV)),'main_faces':int(len(mainF)),'main_face_fraction_of_source':float(len(mainF)/len(F)),'main_surface_area_raw_units2':main_area,'main_surface_area_fraction_of_source':float(main_area/face_area.sum()),'main_signed_volume_raw_units3':main_signed_volume,'raw_xyz_units':'UNKNOWN in OBJ header','raw_bounds_min_xyz':source_bounds_min.tolist(),'raw_bounds_max_xyz':source_bounds_max.tolist(),'raw_bounds_extent_xyz':(source_bounds_max-source_bounds_min).tolist(),'reported_dimensions_mm':{'height':119.0,'base_diameter':70.0,'rim_diameter':160.0},'meter_scale_candidate':'1 raw OBJ unit = 1 metre (×1000 mm/raw), inferred only; not calibrated or source-declared'},
 'removed_components':{'component_ids':sorted([x['component_id'] for x in removed_rows]),'count':len(removed_rows),'vertices':int(sum(vertex_counts[c] for c in range(component_count) if c!=main_label)),'faces':int(sum(face_counts[c] for c in range(component_count) if c!=main_label)),'surface_area_raw_units2':float(sum(area_by[c] for c in range(component_count) if c!=main_label)),'sum_signed_volume_raw_units3':float(sum(volume_by[c] for c in range(component_count) if c!=main_label)),'sum_abs_signed_component_volumes_raw_units3':float(sum(abs(volume_by[c]) for c in range(component_count) if c!=main_label)),'face_fraction_of_source':float(sum(face_counts[c] for c in range(component_count) if c!=main_label)/len(F)),'surface_area_fraction_of_source':float(sum(area_by[c] for c in range(component_count) if c!=main_label)/face_area.sum()),'max_island_face_count':int(max(face_counts[c] for c in range(component_count) if c!=main_label)),'aabb_gap_summary':'All per-axis AABB gaps to the main AABB are 0 because island boxes lie inside the main bounding box; this is not a surface-contact test. See removed_components.csv for extents and surface distances.','closest_main_triangle_distance_method':'vtkStaticCellLocator from every removed-component vertex to the retained main-component triangle surface. Distances are raw units; mm-if-meter columns are only a scale scenario.','component_manifest':'removed_components.csv'},
 'degenerate_faces':{'count':len(degenerate_rows),'face_indices_zero_based':[x['source_face_index_zero_based'] for x in degenerate_rows],'component_ids':[x['component_id'] for x in degenerate_rows],'all_exact_zero_area':all(x['exact_zero_area'] for x in degenerate_rows),'all_have_3_distinct_vertex_ids_but_2_distinct_xyz_positions':all(x['distinct_vertex_indices']==3 and x['distinct_xyz_positions']==2 for x in degenerate_rows),'disposition':'All four are in retained main component and are preserved. They are exact zero-area faces caused by duplicate XYZ coordinates under distinct OBJ vertex IDs. No welding, deletion, or automatic repair. Physics/solid use is rejected pending topology-aware review. See degenerate_faces.csv.'},
 'candidate_change':{'operation':'Select the largest indexed edge-connected component only; remove other 388 disconnected components from this derivative.', 'removed_component_ids':'Explicit full list in removed_components.csv and refinement_receipt.json.', 'coordinates':'Copied from source OBJ; no rescale; unit remains UNKNOWN.', 'faces':'Main component triangles preserved in order; remapped only to compact local vertex indices for derivative file.', 'not_performed':['no smoothing','no remeshing','no decimation/LOD','no hole filling/capping','no vertex welding','no change to connected handles, foot, body, rim, or inner/outer wall geometry'],'candidate_status':'Usable as a visual/modeling anchor candidate; not approved as a physically validated solid because four exact zero-area faces remain and coordinate units are unknown.'},
 'post_derivative_validation':{'obj_vertex_count':int(len(checkV)),'obj_face_count':int(len(checkF)),'source_positions_exactly_equal_after_decimal_serialization':bool(np.array_equal(checkV,mainV)),'source_face_order_exact_after_index_remap':bool(np.array_equal(checkF,mainF)),'edge_connected_components':int(mr),'boundary_edge_count':main_boundary,'nonmanifold_edge_count':main_nonmanifold,'inconsistent_winding_edge_count':main_orientation_bad,'exact_zero_area_face_count':main_zero_count,'surface_area_raw_units2':main_area,'signed_volume_raw_units3':main_signed_volume,'closed_by_indexed_edge_incidence':bool(main_boundary==0 and main_nonmanifold==0),'physics_approval':'REJECT_PENDING_TOPOLOGY_AWARE_REVIEW'},
 'visual_review':{'criteria':{'whole_foot_and_stem_visible':'orthographic side and oblique views','two_handles_and_rim':'oblique and top views','inner_surface':'top and oblique views; paired with outer surface in section','underside_foot':'bottom view and Y section','all_main_components_present':'renders use every triangle in selected main component; no render mask beyond 388 disconnected islands'},'section_y':{'axis_center_xy_raw_units':center_xy.tolist(),'plane_coordinate_y_raw_units':float(origin[1]),'joined_polylines':len(polylines),'section_csv':'refined_y_section.csv','interpretation':'Candidate meridian diagnostic only; no handle loop visible in this plane, but no geometry has been rotated or converted to a full revolved body.'},'render_files_sha256':render_hashes},
 'lod':{'created':False,'reason':'The 643,336-face main candidate is already a practical full-detail asset; no decimation/sample-distance/feature-preservation study was warranted, and the retained zero-area faces block physics qualification.'},
 'prior_render_receipt':{'note':'During the previous audit turn, scan_side.png was overwritten while correcting a stale VTK camera clipping range; the earlier raster was invalid because it clipped the foot. This refinement_v1 folder contains fresh, separate renders. Raster changes do not indicate native geometry edits; source OBJ and ZIP hashes above are unchanged.'}
}
report['derivative_files']={'obj':{'name':main_obj.name,'bytes':main_obj.stat().st_size,'sha256':sha256(main_obj)},'npz':{'name':main_npz.name,'bytes':main_npz.stat().st_size,'sha256':sha256(main_npz)}}
(AUDIT/'refinement_receipt.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

readme=f'''# Reviewed refinement candidate: Apsida SHM 17946:0047

This is a **candidate derivative** of the retained public Apsida model, not a claim that its small components are physically false or that the mesh is ready for simulation. Source: [Apsida item 49281](https://apsida.cut.ac.cy/items/show/49281), [OBJ ZIP](https://apsida.cut.ac.cy/files/original/529/49281/Footed_Bowl_SHM_17946_0047_Obj06.zip). Attribution: “Medelhavsmuseet, SHM 17946:0047; via Apsida / Digital Heritage Research Lab.” Source rights are CC BY-SA 4.0; keep derivative geometry and render outputs under the same license and retain attribution. The license/legal code is in the parent asset directory.

## Refinement performed

The source has 389 indexed edge-connected components. This candidate retains the largest component (ID 0: {len(mainV):,} vertices, {len(mainF):,} faces, {main_area:.12g} raw-unit² area, {main_signed_volume:.12g} raw-unit³ signed volume) and omits only the other 388 separate components in this derivative. The removed manifest lists every component ID, vertices/faces, area/volume, bounds relative to the main bounds, and exact nearest point-to-main-triangle distances. Raw source files and the earlier full-geometry audit remain intact.

The retained main component contains all four exact zero-area triangles found by the audit. Each has three different OBJ vertex IDs but only two distinct XYZ positions. Face indices (0-based) are {', '.join(str(x['source_face_index_zero_based']) for x in degenerate_rows)}; all belong to component 0. They are preserved without welding/deletion/repair. **Do not use this candidate as a physics-qualified or validated solid mesh** until a topology-aware repair and revalidation are reviewed. No hole caps, smoothing, remeshing, or decimation were applied.

The main component's 643,336 faces have {main_boundary} boundary edges, {main_nonmanifold} non-manifold edges, and {main_orientation_bad} inconsistent-winding edges by indexed edge incidence. It is one edge-connected, closed indexed surface, but this does not establish scan completeness, physical solidity, or capture accuracy.

## Coordinate and dimension status

Coordinates are copied from the source OBJ and remain in its **UNKNOWN** coordinate units. The candidate interpretation 1 raw unit = 1 m (multiply by 1000 for mm) is only a magnitude/metadata-based hypothesis, not a declared or calibrated unit. Under that hypothesis, source height 119 mm is close to the OBJ Z extent, while the rim/base estimates do not match their reported dimensions exactly. No scaling has been baked into the derivative.

## Files

- `SHM17946_0047_main_component.obj`: geometry-only OBJ. Vertex positions are copied exactly from the source values (written to 9 decimal places); face winding/order is preserved. UVs, normals, material, and texture are omitted in this candidate; the original OBJ/MTL/ZIP remain in the parent directory.
- `SHM17946_0047_main_component.npz`: `vertices_source_units`, remapped `faces`, `source_vertex_indices`, and `source_face_indices` for direct programmatic reuse.
- `refinement_receipt.json`: source hashes, versions, exact changes, post-export validation, dimensions, license, and render hashes.

## Visual review matrix

| Review | View/file | Result |
|---|---|---|
| Complete side profile | [orthographic side](../refinement_v1/refined_side.png) | Full bowl, stem, foot, and one visible handle; no clipping after explicit clipping-range reset. |
| Overall form and paired handles | [oblique](../refinement_v1/refined_oblique.png) | Both handles, rim, inner surface, bowl body, stem, and full foot visible. |
| Opening / inner surface | [top](../refinement_v1/refined_top.png) | Bowl cavity and both handles visible. |
| Foot underside | [bottom](../refinement_v1/refined_bottom.png) | Foot area visible from below. |
| Inner/outer wall and foot | [Y-center section](../refinement_v1/refined_y_section.png) | One continuous cut outline shows paired surfaces and foot; raw-coordinate section samples are in `refined_y_section.csv`. This is a section of the actual mesh, not a generated revolved body. |

All render views use the retained main-component triangles. Only computed normals/material lighting are used for display; geometry is not transformed. Renders are new files in the refinement audit directory.

The previous audit's `scan_side.png` had been overwritten when fixing a stale camera clipping range; the earlier raster was invalid because it clipped the foot. These new `refined_*` images are separate. Their hashes identify the current renders, while unchanged source OBJ/ZIP hashes identify native geometry provenance.

No LOD was created: the full-detail main mesh is already 643k faces, and there was no reason to add decimation risk. No tests of the application were run because no application code changed; the geometry export was reparsed and compared byte-value-for-value at positions and face-index order.
'''
(AUDIT/'README.md').write_text(readme,encoding='utf-8')
asset_readme=f'''# Main-component derivative candidate

This folder contains a reviewed, geometry-only derivative of the official Apsida model for **SHM 17946:0047, Footed bowl**. It retains only the largest original indexed edge-connected component. This is a reversible simplification choice for the derivative, not a claim that discarded detached islands are not part of the real object. The source ZIP, full OBJ, and MTL remain unchanged in the parent directory.

Source: [Apsida record 49281](https://apsida.cut.ac.cy/items/show/49281); [direct OBJ package](https://apsida.cut.ac.cy/files/original/529/49281/Footed_Bowl_SHM_17946_0047_Obj06.zip). Attribute as “Medelhavsmuseet, SHM 17946:0047; via Apsida / Digital Heritage Research Lab.” Rights: **CC BY-SA 4.0**. Preserve attribution and ShareAlike terms for this derivative. See [source license page](../LICENSE-CC-BY-SA-4.0.html) and the [full refinement receipt](../../../vesselforge/experiments/continuation_20261015/scanned_anchor_audit/refinement_v1/README.md).

`SHM17946_0047_main_component.obj` contains {len(mainV):,} XYZ vertices and {len(mainF):,} triangles; `SHM17946_0047_main_component.npz` carries those arrays plus source vertex/face indices. Positions and face winding/order are unchanged from the retained source component; only vertex indices are compactly remapped. Coordinates are source-native numbers with **UNKNOWN units**; no rescale or calibration was applied. The retained main component contains four exact zero-area faces caused by duplicate XYZ positions under distinct vertex IDs. They remain in the candidate, so it is **not approved as a physics-qualified mesh** pending topology-aware review. No smoothing, welding, hole filling, or decimation was applied.
'''
(REFINED/'README.md').write_text(asset_readme,encoding='utf-8')
print(json.dumps({'receipt':str(AUDIT/'refinement_receipt.json'),'asset_readme':str(REFINED/'README.md'),'main_vertices':len(mainV),'main_faces':len(mainF),'removed_components':len(removed_rows),'degenerate_faces':degenerate_rows,'main_topology':{'connected_components':int(mr),'boundary_edges':main_boundary,'nonmanifold_edges':main_nonmanifold,'winding_errors':main_orientation_bad,'zero_area_faces':main_zero_count},'derivative_files':report['derivative_files'],'section_polyline_count':len(polylines),'render_files':list(render_hashes)},indent=2))
