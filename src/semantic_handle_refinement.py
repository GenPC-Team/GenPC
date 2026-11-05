"""Experimental semantic 2D handles lifted to visible 3D, with local ARAP.

The MLLM supplies corresponding observed/prior surface landmarks and two
part windows. It never predicts a numeric 3D transform. No category rules.
"""
import numpy as np
from scipy import sparse
from scipy.spatial import cKDTree
from scipy.sparse.linalg import splu
from matplotlib.path import Path as Polygon
from PIL import Image, ImageDraw
from src.zbuffer import zbuffer_depth_with_indices
from src.deformation_graph import local_surface_graph, edge_strain

INSTRUCTIONS = '''You control geometric refinement of a complete generated prior against an incomplete physical scan. Attached images are paired 512x512 panels: LEFT BLUE is observed partial, RIGHT RED is complete prior. Both use the same camera. Each image is one view numbered consecutively from zero; the supplied payload gives the view count. Grid coordinates are percentages of each individual panel, not of the whole image. Unobserved prior surfaces must remain complete. First distinguish common global misalignment from a specific corresponding part with different pose/shape. Choose DEFORM_REGION only when the SAME physical part and its attachment are identifiable in both clouds. Choose REFINE_ALIGNMENT if several reliable parts share a common pose/scale offset; choose KEEP_CURRENT if ambiguous. For DEFORM_REGION, name the part, and outline its entire prior extent using a tight polygon in TWO different views; include its attachment boundary, exclude adjacent unrelated parts. Give 3 to 5 physically corresponding visible SURFACE landmarks along attachment, middle and extremity; never click empty space, a hidden centreline, or different sides of a part. Landmarks may use different views; select the clearest visible surface. Keep the first attachment landmark near its current location when attachment is already correct. Explain correspondence and intended deformation using multi-view depth and contour evidence. Do not use ground truth or invent numeric 3D coordinates or transforms. Do not force deformation just to improve overlap. Return uncertainty explicitly. Prioritize the largest coherent unresolved semantic mismatch, not tiny surface noise.'''

def schema():
    number={'type':'number'}; xy={'type':'array','items':number,'minItems':2,'maxItems':2}
    loc={'type':'object','properties':{'view':{'type':'integer'},'xy':xy},'required':['view','xy'],'additionalProperties':False}
    handle={'type':'object','properties':{'name':{'type':'string'},'source':loc,'target':loc},'required':['name','source','target'],'additionalProperties':False}
    window={'type':'object','properties':{'view':{'type':'integer'},'polygon':{'type':'array','items':xy}},'required':['view','polygon'],'additionalProperties':False}
    props={'action':{'type':'string','enum':['DEFORM_REGION','REFINE_ALIGNMENT','KEEP_CURRENT']},'part':{'type':'string'},'evidence':{'type':'array','items':{'type':'string'}},'uncertainty':{'type':'string'},'windows':{'type':'array','items':window},'target_windows':{'type':'array','items':window},'handles':{'type':'array','items':handle}}
    return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}


def render_handle_views(partial,prior,views,directory):
    directory.mkdir(parents=True,exist_ok=True);paths=[]
    for i,v in enumerate(views):
        image=Image.new('RGB',(1024,548),'white');draw=ImageDraw.Draw(image)
        for panel,points,color in [(0,partial,(35,100,220)),(1,prior,(220,55,50))]:
            uv,dep=v.project(points);depth,mask,_=zbuffer_depth_with_indices(uv,dep,v.image_shape,1)
            combined=np.r_[v.project(partial)[1],v.project(prior)[1]]
            near,far=np.quantile(combined,[.01,.99]);shade=np.clip((depth-near)/max(far-near,1e-8),0,1)
            pixels=np.full((512,512,3),250,dtype=np.uint8)
            rgb=np.array(color)[None,None,:]*(.65+.35*shade[:,:,None])+255*(.35-.35*shade[:,:,None])
            pixels[mask]=rgb[mask].astype(np.uint8);image.paste(Image.fromarray(pixels),(panel*512,36))
            draw=ImageDraw.Draw(image)
            draw.text((panel*512+5,4),f'VIEW {i}: '+('OBSERVED PARTIAL' if panel==0 else 'COMPLETE PRIOR'),fill='black')
            for j in range(0,101,10):
                at=min(511,round(j*5.12));x=panel*512+at
                draw.line((x,36,x,547),fill=(195,195,195),width=1)
                draw.line((panel*512,36+at,panel*512+511,36+at),fill=(195,195,195),width=1)
                draw.text((x+1,20),str(j),fill='black')
                draw.text((panel*512+1,36+at),str(j),fill='black')
        path=directory/f'view_{i}.png';image.save(path);paths.append(path)
    return paths


def lift(point,points,views):
    vi=int(point['view']);xy=np.asarray(point['xy'],float)
    if not 0<=vi<len(views) or xy.shape!=(2,) or not np.isfinite(xy).all() or np.any((xy<0)|(xy>100)):
        raise ValueError('invalid landmark image coordinates')
    view=views[vi];uv,d=view.project(points)
    _,_,idx=zbuffer_depth_with_indices(uv,d,view.image_shape,0)
    visible=np.unique(idx[idx>=0]);wanted=xy/100*np.array([view.image_shape[1],view.image_shape[0]])
    dist=np.linalg.norm(uv[visible]-wanted,axis=1);best=int(np.argmin(dist))
    if dist[best]>15:
        raise ValueError('landmark is not on an observed visible surface')
    return int(visible[best]),float(dist[best])


def local_arap_candidate(prior,partial,views,decision,fraction=1.):
    if len(decision['windows'])!=2 or len({w['view'] for w in decision['windows']})!=2:
        raise ValueError('two independent part windows required')
    if not 3<=len(decision['handles'])<=5:raise ValueError('three to five surface handles required')
    mask=np.ones(len(prior),bool)
    for window in decision['windows']:
        vi=int(window['view']);poly=np.asarray(window['polygon'],float)
        if not 0<=vi<len(views) or poly.ndim!=2 or poly.shape[1]!=2 or len(poly)<3 or not np.isfinite(poly).all() or np.any((poly<0)|(poly>100)):
            raise ValueError('invalid part window')
        uv,_=views[vi].project(prior)
        mask &= Polygon(poly/100*512).contains_points(uv,radius=3)
    if mask.sum()<50:raise ValueError(f'part contains only {mask.sum()} points; insufficient surface support')
    if mask.all():raise ValueError('part covers the whole carrier; retain an external attachment or use a global tool')
    sources=[];targets=[];snap=[]
    for h in decision['handles']:
        a,da=lift(h['source'],prior,views);b,db=lift(h['target'],partial,views)
        if not mask[a]:raise ValueError('source handle lies outside the selected part')
        sources.append(a);targets.append(partial[b]);snap.append([da,db])
    sources=np.asarray(sources);targets=np.asarray(targets)
    if len(np.unique(sources))!=len(sources):raise ValueError('duplicate source handles')
    diag=np.linalg.norm(np.ptp(prior,axis=0))
    if np.linalg.norm(targets-prior[sources],axis=1).max()>.25*diag:raise ValueError('handle displacement exceeds local bound')
    # Spatially uniform graph nodes plus exact control slots, preserving all output slots.
    cell=np.floor((prior-prior.min(axis=0))/(diag/65)).astype(int)
    _,ids=np.unique(cell,axis=0,return_index=True)
    if len(ids)>7000:ids=ids[np.linspace(0,len(ids)-1,7000,dtype=int)]
    ids=np.unique(np.r_[ids,sources]);rest=prior[ids];active=mask[ids]
    graph,_,_=local_surface_graph(rest,neighbours=12,edge_ratio=2.5)
    # Keep every disconnected unconstrained node well posed.
    rows,cols=graph.nonzero();weights=graph.data
    lap=sparse.diags(np.asarray(graph.sum(axis=1)).ravel())-graph
    anchor=np.where(active,.02,100.)
    hi=np.searchsorted(ids,sources);anchor[hi]=100.
    goals=rest.copy();goals[hi]=rest[hi]+fraction*(targets-rest[hi])
    solver=splu((lap+sparse.diags(anchor)).tocsc());x=rest.copy()
    edges=rest[rows]-rest[cols];rotations=np.tile(np.eye(3),(len(rest),1,1))
    for _ in range(15):
        covariance=np.zeros((len(rest),3,3))
        np.add.at(covariance,rows,weights[:,None,None]*(x[rows]-x[cols])[:,:,None]*edges[:,None,:])
        u,_,vt=np.linalg.svd(covariance);sign=np.ones((len(rest),3));sign[:,-1]=np.sign(np.linalg.det(u@vt))
        rotations=(u*sign[:,None,:])@vt
        edge_rhs=.5*np.einsum('nij,nj->ni',rotations[rows]+rotations[cols],edges)*weights[:,None]
        rhs=np.zeros_like(rest);np.add.at(rhs,rows,edge_rhs)
        x=solver.solve(rhs+anchor[:,None]*goals)
    # Blend local rigid transforms, not a raw displacement field. Outside stays exact.
    dist,nn=cKDTree(rest).query(prior[mask],k=4)
    w=1/np.maximum(dist,diag*1e-5)**2;w/=w.sum(axis=1,keepdims=True)
    transformed=np.einsum('nkij,nkj->nki',rotations[nn],prior[mask,None]-rest[nn])+x[nn]
    result=prior.copy();result[mask]=np.sum(w[:,:,None]*transformed,axis=1)
    fullgraph,_,_=local_surface_graph(prior,neighbours=12,edge_ratio=1.85)
    activegraph=fullgraph.multiply(mask[:,None]).maximum(fullgraph.multiply(mask[None,:]))
    strain=edge_strain(prior,result,activegraph)
    return result,{'source_ids':sources.tolist(),'target_positions':targets.tolist(),'snap_pixels':snap,'part_points':int(mask.sum()),'fraction':fraction,'strain':strain,'handle_error_before':np.linalg.norm(prior[sources]-targets,axis=1).tolist(),'handle_error_after':np.linalg.norm(result[sources]-targets,axis=1).tolist(),'maximum_motion_ratio':float(np.linalg.norm(result-prior,axis=1).max()/diag)},mask


def coherent_semantic_candidate(prior,partial,views,decision,fraction=1.,protected_ids=None):
    """Fit one proper part motion from semantic surface pairs, taper intrinsically.

    Whole-part rigidity prevents isolated landmark spikes. Transition extent
    follows requested motion magnitude on the surface graph, not a category.
    """
    from scipy.sparse.csgraph import dijkstra
    from scipy.spatial.transform import Rotation
    from src.coherent_local_refinement import fit_rigid,geodesic_rigid_warp
    if len(decision['windows'])!=2 or len({w['view'] for w in decision['windows']})!=2:
        raise ValueError('two independent part windows required')
    if not 3<=len(decision['handles'])<=5:raise ValueError('three to five surface handles required')
    mask=np.ones(len(prior),bool)
    for window in decision['windows']:
        vi=int(window['view']);poly=np.asarray(window['polygon'],float)
        if not 0<=vi<len(views) or poly.ndim!=2 or poly.shape[1]!=2 or len(poly)<3 or not np.isfinite(poly).all():raise ValueError('invalid part window')
        uv,_=views[vi].project(prior);mask &= Polygon(poly/100*512).contains_points(uv,radius=3)
    if mask.sum()<50:raise ValueError(f'part contains only {mask.sum()} points; insufficient surface support')
    if mask.all():raise ValueError('part covers the whole carrier; retain an external attachment or use a global tool')
    sources=[];targets=[]
    for h in decision['handles']:
        a,_=lift(h['source'],prior,views);b,_=lift(h['target'],partial,views)
        if not mask[a]:raise ValueError('source handle outside part window')
        sources.append(a);targets.append(partial[b])
    sources=np.asarray(sources);targets=np.asarray(targets);diag=np.linalg.norm(np.ptp(prior,axis=0))
    rot,t=fit_rigid(prior[sources],targets)
    centre=prior[mask].mean(axis=0);shift=centre@rot.T+t-centre
    partial_rot=Rotation.from_rotvec(fraction*Rotation.from_matrix(rot).as_rotvec()).as_matrix()
    partial_t=centre+fraction*shift-centre@partial_rot.T
    graph,metric,_=local_surface_graph(prior,neighbours=12,edge_ratio=1.85)
    core=np.flatnonzero(mask)
    maximum=float(np.linalg.norm(prior[core]@partial_rot.T+partial_t-prior[core],axis=1).max())
    width=max(.06*diag,2.5*maximum)
    candidate,weight=geodesic_rigid_warp(prior,metric,core,partial_rot,partial_t,width)
    candidate=protect_displacement(prior,candidate,metric,protected_ids,.06*diag)
    edges=graph.multiply((weight>0)[:,None]).maximum(graph.multiply((weight>0)[None,:]))
    report={'operator':'semantic_part_rigid_with_intrinsic_transition','source_ids':sources.tolist(),'target_positions':targets.tolist(),'part_points':int(mask.sum()),'part_fraction':float(mask.mean()),'affected_fraction':float(np.mean(weight>0)),'affected_points':int(np.sum(weight>0)), 'fraction':fraction,'strain':edge_strain(prior,candidate,edges),'rotation_degrees':float(np.rad2deg(Rotation.from_matrix(partial_rot).magnitude())),'transition_width_ratio':width/diag,'handle_error_before':np.linalg.norm(prior[sources]-targets,axis=1).tolist(),'handle_error_after':np.linalg.norm(candidate[sources]-targets,axis=1).tolist(),'maximum_motion_ratio':float(np.linalg.norm(candidate-prior,axis=1).max()/diag)}
    return candidate,report,weight>0


def smooth_semantic_candidate(prior,partial,views,decision,fraction=1.,protected_ids=None):
    """Low-frequency semantic handle field, with intrinsic attachment taper.

    Regularized 3D linear RBFs distribute bending/length correction across the
    whole selected part rather than anchoring isolated graph vertices. Outside
    the intrinsic support the carrier remains exactly unchanged.
    """
    from scipy.interpolate import RBFInterpolator
    from scipy.spatial.distance import pdist
    from scipy.sparse.csgraph import dijkstra
    mask=np.ones(len(prior),bool)
    if len(decision['windows'])!=2 or len({w['view'] for w in decision['windows']})!=2:
        raise ValueError('two independent part windows required')
    if not 3<=len(decision['handles'])<=5:raise ValueError('three to five surface handles required')
    for window in decision['windows']:
        vi=int(window['view']);poly=np.asarray(window['polygon'],float)
        if not 0<=vi<len(views) or poly.ndim!=2 or poly.shape[1]!=2 or len(poly)<3 or not np.isfinite(poly).all():raise ValueError('invalid part window')
        uv,_=views[vi].project(prior);mask &= Polygon(poly/100*512).contains_points(uv,radius=3)
    if mask.sum()<50:raise ValueError(f'part contains only {mask.sum()} points; insufficient surface support')
    if mask.all():raise ValueError('part covers the whole carrier; retain an external attachment or use a global tool')
    source_ids=[];targets=[]
    for h in decision['handles']:
        a,_=lift(h['source'],prior,views);b,_=lift(h['target'],partial,views)
        if not mask[a]:raise ValueError('source handle outside part window')
        source_ids.append(a);targets.append(partial[b])
    source_ids=np.asarray(source_ids);targets=np.asarray(targets);source=prior[source_ids]
    diag=np.linalg.norm(np.ptp(prior,axis=0));length=max(float(np.median(pdist(source))),.02*diag)
    if len(np.unique(source_ids))!=len(source_ids):raise ValueError('duplicate source controls')
    field=RBFInterpolator(source/length,(targets-source)/length,kernel='linear',degree=0,smoothing=.05)
    graph,metric,_=local_surface_graph(prior,neighbours=12,edge_ratio=1.85)
    requested=field(prior[mask]/length)*length*fraction
    maximum=float(np.linalg.norm(requested,axis=1).max())
    if maximum>.3*diag:raise ValueError('semantic displacement exceeds local bound')
    width=max(.08*diag,3*maximum)
    distance=dijkstra(metric,directed=False,indices=np.flatnonzero(mask),min_only=True,limit=width)
    weight=np.clip(1-distance/width,0,1);weight=weight*weight*(3-2*weight)
    active=weight>0;movement=field(prior[active]/length)*length*fraction
    result=prior.copy();result[active]+=weight[active,None]*movement
    result=protect_displacement(prior,result,metric,protected_ids,.06*diag)
    edges=graph.multiply(active[:,None]).maximum(graph.multiply(active[None,:]))
    # Jacobian on supported samples detects folding that pair-distance summaries miss.
    ids=np.flatnonzero(active);ids=ids[np.linspace(0,len(ids)-1,min(512,len(ids)),dtype=int)]
    tree=cKDTree(prior);_,nn=tree.query(prior[ids],k=12)
    minimum_det=1.;singular=[]
    for i,neighbours in zip(ids,nn):
        a=prior[neighbours]-prior[i];b=result[neighbours]-result[i]
        _,s,_=np.linalg.svd(a,full_matrices=False)
        if s[-1]<s[0]*.05:continue
        jac=np.linalg.lstsq(a,b,rcond=None)[0];minimum_det=min(minimum_det,float(np.linalg.det(jac)));singular.extend(np.linalg.svd(jac,compute_uv=False).tolist())
    report={'operator':'semantic_smooth_rbf_with_intrinsic_transition','source_ids':source_ids.tolist(),'target_positions':targets.tolist(),'part_points':int(mask.sum()),'part_fraction':float(mask.mean()),'affected_fraction':float(np.mean(weight>0)),'affected_points':int(active.sum()),'fraction':fraction,'strain':edge_strain(prior,result,edges),'transition_width_ratio':width/diag,'handle_error_before':np.linalg.norm(source-targets,axis=1).tolist(),'handle_error_after':np.linalg.norm(result[source_ids]-targets,axis=1).tolist(),'maximum_motion_ratio':float(np.linalg.norm(result-prior,axis=1).max()/diag),'minimum_full_rank_jacobian_determinant':minimum_det,'full_rank_jacobians_checked':len(singular)//3}
    return result,report,active


def render_semantic_zooms(paths,decision,directory):
    """Same-window paired zooms with coordinates still in the original raster."""
    directory.mkdir(exist_ok=True);result=[]
    for window in decision.get('windows',[]):
        vi=int(window['view']);xy=list(window['polygon'])
        for h in decision.get('handles',[]):
            for role in ('source','target'):
                if h[role]['view']==vi:xy.append(h[role]['xy'])
        xy=np.asarray(xy);lo=np.maximum(0,xy.min(axis=0)-6);hi=np.minimum(100,xy.max(axis=0)+6)
        box=np.r_[lo/100*512,hi/100*512].astype(int);im=Image.open(paths[vi]);out=Image.new('RGB',(1024,560),'white');draw=ImageDraw.Draw(out)
        draw.text((8,8),f'ZOOM VIEW {vi}. Grid numbers remain ORIGINAL panel percentages. LEFT partial / RIGHT prior',fill='black')
        for side in range(2):
            crop=im.crop((side*512+box[0],36+box[1],side*512+box[2],36+box[3]))
            scale=min(512/crop.width,512/crop.height);crop=crop.resize((round(crop.width*scale),round(crop.height*scale)))
            out.paste(crop,(side*512,36))
        dest=directory/f'zoom_view_{vi}.png';out.save(dest);result.append(dest)
    return result


def protect_displacement(reference,candidate,metric,protected_ids,width):
    """A smooth intrinsic taper to exact fixed accepted surface slots."""
    if protected_ids is None or len(protected_ids)==0:return candidate
    from scipy.sparse.csgraph import dijkstra
    distance=dijkstra(metric,directed=False,indices=np.asarray(protected_ids,dtype=int),min_only=True,limit=width)
    freedom=np.clip(distance/width,0,1);freedom=freedom*freedom*(3-2*freedom)
    result=reference+freedom[:,None]*(candidate-reference)
    result[np.asarray(protected_ids,dtype=int)]=reference[np.asarray(protected_ids,dtype=int)]
    return result


def validate_semantic_plan(prior,partial,views,decision,images,directory,*,require_target_windows=False):
    """Expose exact lifted 3D handles in every selected view before solving."""
    directory.mkdir(exist_ok=True);issues=[];records=[];marked=[]
    source_windows=decision.get('windows',[]);target_windows=decision.get('target_windows',[])
    if require_target_windows or target_windows:
        if len(source_windows)!=2 or len(target_windows)!=2 or len({w['view'] for w in source_windows})!=2 or {w['view'] for w in source_windows}!={w['view'] for w in target_windows}:
            return {'valid':False,'issues':['Source and observed-target windows must identify the same part in the same TWO distinct views.'],'handles':[],'images':[]},[]
    for window in source_windows+target_windows:
        poly=np.asarray(window.get('polygon',[]),float);vi=window.get('view',-1)
        if not isinstance(vi,int) or not 0<=vi<len(views) or poly.ndim!=2 or poly.shape[1]!=2 or len(poly)<3 or not np.isfinite(poly).all() or np.any((poly<0)|(poly>100)):
            return {'valid':False,'issues':['Invalid part-window view or polygon coordinates.'],'handles':[],'images':[]},[]
    for i,h in enumerate(decision.get('handles',[])):
        try:
            a,sa=lift(h['source'],prior,views);b,sb=lift(h['target'],partial,views)
            record={'id':i,'name':h['name'],'source_id':a,'target_id':b,'snap_pixels':[sa,sb],'projections':[]}
            for w in decision.get('windows',[]):
                vi=int(w['view']);suv=views[vi].project(prior[a:a+1])[0][0];tuv=views[vi].project(partial[b:b+1])[0][0]
                poly=np.asarray(w['polygon'])/100*512
                inside=bool(Polygon(poly).contains_points(suv[None],radius=3)[0])
                projection={'view':vi,'source_xy_percent':(suv/512*100).tolist(),'target_xy_percent':(tuv/512*100).tolist(),'inside_source_window':inside}
                target_window=next((t for t in target_windows if t['view']==vi),None)
                if target_window:
                    target_inside=bool(Polygon(np.asarray(target_window['polygon'])/100*512).contains_points(tuv[None],radius=3)[0])
                    projection['inside_target_window']=target_inside
                    if not target_inside:issues.append(f'Handle {i} ({h["name"]}) target projects to {(tuv/512*100).round(2).tolist()} percent in view {vi}, OUTSIDE the observed part window. Recheck the SAME physical part across views; do not associate a neighbouring limb or tail surface.')
                record['projections'].append(projection)
                if not inside:issues.append(f'Handle {i} ({h["name"]}) lifts to source point {a}, which projects to {(suv/512*100).round(2).tolist()} percent in view {vi}, OUTSIDE its part window. Correct the window or surface association; do not expand onto an unrelated part.')
            records.append(record)
        except ValueError as exc:issues.append(f'Handle {i}: {exc}')
    for w in decision.get('windows',[]):
        vi=int(w['view']);im=Image.open(images[vi]).copy();draw=ImageDraw.Draw(im)
        poly=[(512+x/100*512,36+y/100*512) for x,y in w['polygon']];draw.line(poly+[poly[0]],fill=(0,150,0),width=3)
        target_window=next((t for t in target_windows if t['view']==vi),None)
        if target_window:
            target_poly=[(x/100*512,36+y/100*512) for x,y in target_window['polygon']]
            draw.line(target_poly+[target_poly[0]],fill=(0,150,150),width=3)
        for r in records:
            proj=next(x for x in r['projections'] if x['view']==vi)
            for side,key in [(0,'target_xy_percent'),(1,'source_xy_percent')]:
                x,y=proj[key];x=side*512+x/100*512;y=36+y/100*512
                draw.ellipse((x-7,y-7,x+7,y+7),outline='black',width=2);draw.text((x+7,y-7),str(r['id']),fill='black')
        path=directory/f'validated_view_{vi}.png';im.save(path);marked.append(path)
    return {'valid':not issues,'issues':issues,'handles':records,'images':[str(p.resolve()) for p in marked]},marked
