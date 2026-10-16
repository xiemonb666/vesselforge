from __future__ import annotations
import json, math, sys, pathlib, hashlib, collections
import numpy as np
import vtk
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OBJ=pathlib.Path(sys.argv[1]).resolve()
OUT=pathlib.Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
MAX_V=2_000_000; MAX_F=4_000_000
verts=[]; faces=[]; vt=vn=0; mtllib=[]; material=[]; obj_names=[]; groups=[]; polygon_sizes=collections.Counter()
with OBJ.open('r', encoding='utf-8', errors='replace') as f:
    for lineno,line in enumerate(f,1):
        s=line.strip()
        if not s or s.startswith('#'): continue
        tag, *rest=s.split()
        if tag=='v':
            if len(verts)>=MAX_V: raise SystemExit(f'vertex limit exceeded at line {lineno}')
            if len(rest)<3: raise SystemExit(f'invalid v at line {lineno}')
            # Source OBJ includes optional RGB after XYZ; preserve XYZ only for geometry.
            verts.append((float(rest[0]),float(rest[1]),float(rest[2])))
        elif tag=='vt': vt+=1
        elif tag=='vn': vn+=1
        elif tag=='mtllib': mtllib.extend(rest)
        elif tag=='usemtl': material.extend(rest)
        elif tag=='o': obj_names.append(' '.join(rest))
        elif tag=='g': groups.append(' '.join(rest))
        elif tag=='f':
            if len(faces)>=MAX_F: raise SystemExit(f'face limit exceeded at line {lineno}')
            ids=[]
            for entry in rest:
                raw=int(entry.split('/')[0])
                ix=(raw-1) if raw>0 else (len(verts)+raw)
                if ix<0 or ix>=len(verts): raise SystemExit(f'face index out of range line {lineno}')
                ids.append(ix)
            polygon_sizes[len(ids)]+=1
            if len(ids)<3: raise SystemExit(f'face < 3 vertices line {lineno}')
            # Original is retained unchanged. Triangulate n-gons only in audit view/statistics.
            if len(ids)==3: faces.append(tuple(ids))
            else:
                for j in range(1,len(ids)-1): faces.append((ids[0],ids[j],ids[j+1]))
            if len(faces)>MAX_F: raise SystemExit(f'triangulated face limit exceeded at line {lineno}')

V=np.asarray(verts,dtype=np.float64); F=np.asarray(faces,dtype=np.int64)
if len(V)>MAX_V or len(F)>MAX_F: raise SystemExit('configured geometry safety limit exceeded')
if not len(V) or not len(F): raise SystemExit('no geometry parsed')
low=V.min(axis=0); high=V.max(axis=0); ext=high-low
# Simple exact topology counts on indexed triangle edges.
directed_edges=np.concatenate((F[:,[0,1]],F[:,[1,2]],F[:,[2,0]]),axis=0)
edge_sign=np.where(directed_edges[:,0]<directed_edges[:,1],1,-1)
E=directed_edges.copy(); E.sort(axis=1)
UE, edge_inverse, EC=np.unique(E,axis=0,return_inverse=True,return_counts=True)
boundary=UE[EC==1]; nonmanifold=UE[EC>2]
orientation_sum=np.bincount(edge_inverse,weights=edge_sign)
inconsistent_oriented_edges=np.flatnonzero((EC==2)&(orientation_sum!=0))
# Boundary graph components, degree spectrum; degree-2 components are closed loops.
adj=collections.defaultdict(list)
for a,b in boundary.tolist(): adj[a].append(b); adj[b].append(a)
seen=set(); boundary_components=[]
for start in adj:
    if start in seen: continue
    stack=[start]; seen.add(start); nodes=[]
    while stack:
        x=stack.pop(); nodes.append(x)
        for y in adj[x]:
            if y not in seen: seen.add(y); stack.append(y)
    degs=[len(adj[x]) for x in nodes]
    boundary_components.append({'vertices':len(nodes),'edges':sum(degs)//2,'degree_histogram':dict(sorted(collections.Counter(degs).items())),'closed_loop_if_all_degree2':bool(degs) and all(d==2 for d in degs)})
# Degenerate triangle count and used vertices.
tri=V[F]
areas2=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)
degenerate=int(np.count_nonzero(areas2<1e-12))
used=np.unique(F)
# Independent graph connectivity on the original OBJ vertex indices. OBJ uv/normal
# seams are intentionally not welded; each `v` index remains distinct.
rows=np.concatenate((UE[:,0],UE[:,1])); cols=np.concatenate((UE[:,1],UE[:,0]))
adjacency=csr_matrix((np.ones(len(rows),dtype=np.uint8),(rows,cols)),shape=(len(V),len(V)))
component_count, component_labels=connected_components(adjacency,directed=False,return_labels=True)
face_component=component_labels[F[:,0]]
if not (np.all(component_labels[F[:,0]]==component_labels[F[:,1]]) and np.all(component_labels[F[:,0]]==component_labels[F[:,2]])):
    raise SystemExit('face spans inconsistent graph component labels')
face_count_by_component=np.bincount(face_component,minlength=component_count)
vertex_count_by_component=np.bincount(component_labels,minlength=component_count)
face_area=areas2/2.0
area_by_component=np.bincount(face_component,weights=face_area,minlength=component_count)
volume_contrib=np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2]))/6.0
signed_volume_by_component=np.bincount(face_component,weights=volume_contrib,minlength=component_count)
edge_component=component_labels[UE[:,0]]
inconsistent_by_component=np.bincount(edge_component[inconsistent_oriented_edges],minlength=component_count)
component_min=np.full((component_count,3),np.inf); component_max=np.full((component_count,3),-np.inf)
np.minimum.at(component_min,component_labels,V); np.maximum.at(component_max,component_labels,V)
area_order=np.lexsort((-face_count_by_component,-np.abs(signed_volume_by_component),-area_by_component))
component_rows=[]
for rank,label in enumerate(area_order,1):
    component_rows.append({'area_rank':rank,'component_label':int(label),'vertex_count':int(vertex_count_by_component[label]),'face_count':int(face_count_by_component[label]),'surface_area_raw_units2':float(area_by_component[label]),'signed_volume_raw_units3':float(signed_volume_by_component[label]),'abs_signed_volume_raw_units3':float(abs(signed_volume_by_component[label])),'inconsistent_oriented_edge_count':int(inconsistent_by_component[label]),'bounds_min_x':float(component_min[label,0]),'bounds_min_y':float(component_min[label,1]),'bounds_min_z':float(component_min[label,2]),'bounds_max_x':float(component_max[label,0]),'bounds_max_y':float(component_max[label,1]),'bounds_max_z':float(component_max[label,2]),'extent_x':float(component_max[label,0]-component_min[label,0]),'extent_y':float(component_max[label,1]-component_min[label,1]),'extent_z':float(component_max[label,2]-component_min[label,2])})
import csv
with (OUT/'component_table.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(component_rows[0])); w.writeheader(); w.writerows(component_rows)
np.savez_compressed(OUT/'raw_geometry.npz',vertices_source_units=V,faces=F)
exact_xyz_count=int(len(np.unique(V,axis=0)))
# A least-squares circle on the topmost rim band is only a center/scale diagnostic;
# it does not claim an exact rotational reconstruction.
rim_band=V[V[:,2]>=high[2]-0.003]
circle_center=[float('nan'),float('nan')]; circle_radius=float('nan'); circle_rms=float('nan')
if len(rim_band)>=3:
    xy=rim_band[:,:2]; A=np.column_stack((2*xy[:,0],2*xy[:,1],np.ones(len(xy))))
    rhs=np.einsum('ij,ij->i',xy,xy)
    sol=np.linalg.lstsq(A,rhs,rcond=None)[0]
    circle_center=sol[:2].astype(float).tolist(); circle_radius=float(math.sqrt(max(0.0,sol[2]+sol[0]**2+sol[1]**2)))
    circle_rms=float(np.sqrt(np.mean((np.linalg.norm(xy-sol[:2],axis=1)-circle_radius)**2)))
base_band=V[V[:,2]<=low[2]+0.004]
base_radial_diameter=float(2*np.max(np.linalg.norm(base_band[:,:2]-np.asarray(circle_center),axis=1))) if len(base_band) else None
# Build correct indexed VTK surface: VTK's stock OBJ reader treats this file's xyzrgb v lines as malformed.
pts=vtk.vtkPoints(); pts.SetData(numpy_to_vtk(np.ascontiguousarray(V),deep=True))
cell_data=np.empty((len(F),4),dtype=np.int64); cell_data[:,0]=3; cell_data[:,1:]=F
cells=vtk.vtkCellArray(); cells.SetCells(len(F),numpy_to_vtkIdTypeArray(np.ascontiguousarray(cell_data.ravel()),deep=True))
pd=vtk.vtkPolyData(); pd.SetPoints(pts); pd.SetPolys(cells)
conn=vtk.vtkPolyDataConnectivityFilter(); conn.SetInputData(pd); conn.SetExtractionModeToAllRegions(); conn.Update()
# Raw model geometry only; no cleaning, hole fill, smoothing, decimation or scaling.
# Rendering applies temporary computed normals solely for lighting.
normals=vtk.vtkPolyDataNormals(); normals.SetInputData(pd); normals.ComputePointNormalsOn(); normals.ComputeCellNormalsOn(); normals.SplittingOff(); normals.ConsistencyOff(); normals.AutoOrientNormalsOff(); normals.Update()
render_data=normals.GetOutput()

# Render orthographic scan views as actual triangles.
def render_view(name, pos, up):
    ren=vtk.vtkRenderer(); ren.SetBackground(0.96,0.96,0.94)
    actor=vtk.vtkActor(); mapper=vtk.vtkPolyDataMapper(); mapper.SetInputData(render_data); actor.SetMapper(mapper)
    actor.GetProperty().SetColor(0.70,0.52,0.35); actor.GetProperty().SetAmbient(0.24); actor.GetProperty().SetDiffuse(0.76); actor.GetProperty().SetSpecular(0.12); actor.GetProperty().SetSpecularPower(20)
    ren.AddActor(actor); ren.ResetCamera()
    cam=ren.GetActiveCamera(); center=[float((low[i]+high[i])/2) for i in range(3)]; span=max(ext)
    cam.SetFocalPoint(*center); cam.SetPosition(*(center[i]+pos[i]*span for i in range(3))); cam.SetViewUp(*up); cam.ParallelProjectionOn(); cam.SetParallelScale(span*0.63)
    # Camera position changes after ResetCamera; refresh clip range or the foot
    # can be clipped from the image even though the source mesh is present.
    ren.ResetCameraClippingRange()
    win=vtk.vtkRenderWindow(); win.SetOffScreenRendering(1); win.SetSize(1400,1000); win.AddRenderer(ren); win.Render()
    w2i=vtk.vtkWindowToImageFilter(); w2i.SetInput(win); w2i.SetInputBufferTypeToRGB(); w2i.ReadFrontBufferOff(); w2i.Update()
    writer=vtk.vtkPNGWriter(); writer.SetFileName(str(OUT/f'{name}.png')); writer.SetInputConnection(w2i.GetOutputPort()); writer.Write()
    win.Finalize()

render_views={
 'scan_side': ((0,-3.5,0),(0,0,1)),
 'scan_oblique': ((2.6,-3.4,1.4),(0,0,1)),
 'scan_top': ((0,0,3.5),(0,1,0)),
 'scan_bottom': ((0,0,-3.5),(0,1,0)),
}
render_errors=[]
for name,(pos,up) in render_views.items():
    try: render_view(name,pos,up)
    except Exception as e: render_errors.append({'view':name,'error':repr(e)})

# Two orthogonal vertical cuts through the raw bounds center, rendered as raw-coordinate polylines.
def cut_plot(axis_idx, name):
    plane=vtk.vtkPlane(); origin=[float((low[i]+high[i])/2) for i in range(3)]; origin[axis_idx]=float(circle_center[axis_idx]); plane.SetOrigin(*origin)
    normal=[0.,0.,0.]; normal[axis_idx]=1.; plane.SetNormal(*normal)
    cutter=vtk.vtkCutter(); cutter.SetInputData(pd); cutter.SetCutFunction(plane); cutter.Update()
    stripper=vtk.vtkStripper(); stripper.SetInputConnection(cutter.GetOutputPort()); stripper.JoinContiguousSegmentsOn(); stripper.Update()
    cut=stripper.GetOutput(); ptsarr=vtk_to_numpy(cut.GetPoints().GetData()) if cut.GetPoints() else np.empty((0,3))
    lines=cut.GetLines(); ids=vtk.vtkIdList(); lines.InitTraversal(); polylines=[]
    while lines.GetNextCell(ids):
        ids_np=[ids.GetId(j) for j in range(ids.GetNumberOfIds())]
        if len(ids_np)>=2: polylines.append(ptsarr[ids_np])
    fig,ax=plt.subplots(figsize=(8,8),dpi=150)
    for line in polylines:
        u=1-axis_idx; ax.plot(line[:,u],line[:,2],color='#473a2f',lw=0.65,alpha=0.9)
    ax.set_aspect('equal',adjustable='box'); ax.grid(True,alpha=.22)
    ax.set_xlabel(('x','y','z')[1-axis_idx]+' (raw OBJ units)'); ax.set_ylabel('z (raw OBJ units)')
    ax.set_title(f'Actual mesh section: '+('x=top-band fitted center' if axis_idx==0 else 'y=top-band fitted center')+f'; {len(polylines)} joined polylines')
    fig.tight_layout(); fig.savefig(OUT/f'{name}.png'); plt.close(fig)
    if polylines:
        # Preserve every joined section polyline in raw coordinates as a diagnostic.
        # These are cuts from the scan, not fitted or repaired meridians.
        with (OUT/f'{name}.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.writer(f); w.writerow(['polyline_id','path_order','x_raw_obj_units','y_raw_obj_units','z_raw_obj_units'])
            for pid,line in enumerate(polylines):
                for j,point in enumerate(line): w.writerow([pid,j,*map(float,point)])
    polyline_summaries=[]
    for pid,line in enumerate(polylines):
        plow=line.min(axis=0); phigh=line.max(axis=0)
        polyline_summaries.append({'polyline_id':pid,'point_count':len(line),'bounds_min_xyz':plow.tolist(),'bounds_max_xyz':phigh.tolist(),'extent_xyz':(phigh-plow).tolist()})
    return {'section_axis':('x' if axis_idx==0 else 'y'),'plane_coordinate':origin[axis_idx],'plane_coordinate_source':'least-squares top rim band center; candidate axis only','point_count':len(ptsarr),'cut_segments':cutter.GetOutput().GetNumberOfLines(),'joined_polylines':len(polylines),'polyline_point_count_min':min((len(x) for x in polylines),default=0),'polyline_point_count_max':max((len(x) for x in polylines),default=0),'polylines':polyline_summaries}
section_stats=[]
try:
    section_stats=[cut_plot(0,'section_x_center'),cut_plot(1,'section_y_center')]
except Exception as e:
    render_errors.append({'view':'sections','error':repr(e)})

# SHA of the retained original technical file (not a derivative).
h=hashlib.sha256(OBJ.read_bytes()).hexdigest()
record={
 'source_model_file':OBJ.name,'source_model_sha256':h,'raw_vertex_count':int(len(V)),'raw_face_count_obj_polygons':int(sum(polygon_sizes.values())),'triangles_for_audit':int(len(F)),'raw_vt_count':int(vt),'raw_vn_count':int(vn),'face_polygon_size_histogram':dict(sorted(polygon_sizes.items())),'object_names':obj_names,'groups':groups,'materials':material,'mtllib':mtllib,
 'raw_bounds_xyz':{'min':low.tolist(),'max':high.tolist(),'extent':ext.tolist(),'units':'UNKNOWN in OBJ header; unit-scale candidates only'},'unused_vertex_count':int(len(V)-len(used)),'degenerate_triangle_count_area_lt_1e-12_raw_units2':degenerate,'unique_edges':int(len(UE)),'boundary_edge_count':int(len(boundary)),'boundary_graph_component_count':len(boundary_components),'boundary_components':boundary_components[:100],'boundary_components_truncated':len(boundary_components)>100,'nonmanifold_edge_count_incidence_gt2':int(len(nonmanifold)),'connected_face_regions_vtk':int(conn.GetNumberOfExtractedRegions()),'watertight_by_indexed_edge_incidence':bool(len(boundary)==0 and len(nonmanifold)==0),'surface_only_input':True,
 'source_record':{'item_url':'https://apsida.cut.ac.cy/items/show/49281','identifier':'SHM 17946:0047','title':'Footed bowl','period':'C.G. III (850–700 BC)','material':'Earthenware; Clay; Pottery','reported_height_mm':119.0,'reported_base_diameter_mm':70.0,'reported_rim_diameter_mm':160.0,'reported_dimension_ratios':{'height_over_rim_diameter':119/160,'base_over_rim_diameter':70/160},'obj_header':'Generated with Agisoft Metashape','coordinate_units_declared':False,'rights':'CC BY-SA 4.0'},
 'scale_candidates':{'meter_candidate':{'assumption':'1 raw OBJ unit = 1 m (1000 mm/raw unit); inferred from coordinate magnitude and reported H only, not declared in OBJ','bounds_extent_mm_if_assumed':[float(v*1000) for v in ext],'height_delta_from_report_mm':float(ext[2]*1000-119.0),'height_delta_percent':float((ext[2]*1000/119.0-1)*100),'top_band_fitted_circle_diameter_mm_if_assumed':float(circle_radius*2000),'top_band_diameter_delta_from_reported_rim_mm':float(circle_radius*2000-160.0),'top_band_diameter_delta_percent':float((circle_radius*2000/160.0-1)*100),'top_band_circle_fit_rms_mm_if_assumed':float(circle_rms*1000),'low_band_radial_diameter_mm_if_assumed':float(base_radial_diameter*1000),'low_band_diameter_delta_from_reported_base_mm':float(base_radial_diameter*1000-70.0),'low_band_diameter_delta_percent':float((base_radial_diameter*1000/70.0-1)*100),'warning':'Dimensions do not match all reported dimensions exactly; do not treat as calibrated physical unit scale.'}},
 'edge_graph_component_count':int(component_count),'largest_component':component_rows[0],'largest_component_face_fraction':float(face_count_by_component[area_order[0]]/len(F)),'largest_component_surface_area_fraction':float(area_by_component[area_order[0]]/area_by_component.sum()),'exact_duplicate_xyz_vertex_count':int(len(V)-exact_xyz_count),'inconsistent_oriented_edge_count':int(len(inconsistent_oriented_edges)),'component_table_file':'component_table.csv','raw_geometry_npz':'raw_geometry.npz','raw_geometry_npz_payload':'vertices_source_units and faces; preserves original parsed OBJ indexing, no weld/repair/rescale','top_rim_band_circle_fit_diagnostic':{'band_z_min':float(high[2]-0.003),'point_count':int(len(rim_band)),'center_xy_raw_units':circle_center,'radius_raw_units':circle_radius,'radial_rms_residual_raw_units':circle_rms},'bottom_band_diameter_candidate_raw_units':base_radial_diameter,
 'section_stats':section_stats,'render_errors':render_errors,
 'render_views':{k:{'camera_direction_relative_to_extent':list(v[0]),'image':f'{k}.png'} for k,v in render_views.items()},
 'processing_notes':['Parsed original OBJ xyz positions and indexed triangular faces directly.','VTK stock vtkOBJReader warned on the source xyzrgb vertex rows and duplicated corners; it was not used for final topology.','Edge-graph components use original OBJ v indices; no UV/normal seam welding.','No mesh repair, hole fill, smoothing, decimation, rescaling, or remeshing.','Computed temporary normals are only for visual shading.','Section cuts use the original indexed triangle surface.','A closed edge-incidence test only characterizes mesh topology; it does not establish physical solidity, acquisition completeness, or scan fidelity.']
}
(OUT/'mesh_audit.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(record,indent=2))
