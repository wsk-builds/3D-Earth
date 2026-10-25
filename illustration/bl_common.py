"""通用插画风 Blender 公共工具（Blender 3.6 内运行）：场景重置 / 渲染设置 / 相机 / 灯 / 程序化网格 / 节点小工具。
用法：blender -b --python scene.py -- [--preview] [--frames A-B] [--still F] [--pct 50] [--samples 8]
帧号 = 绝对帧号（30fps）；整段输出 $ILLU_OUT/<SHOT>/######.png（缺省为本目录 out/）。"""
import bpy, bmesh, sys, os, math, time
import numpy as np
from mathutils import Vector, Euler, Matrix

FPS = 30
ROOT = os.environ.get('ILLU_OUT', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out'))

def args():
    a = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    o = dict(preview=('--preview' in a), frames=None, still=None, samples=None, pct=None)
    for i, x in enumerate(a):
        if x == '--frames': s, e = a[i+1].split('-'); o['frames'] = (int(s), int(e))
        if x == '--still': o['still'] = int(a[i+1])
        if x == '--samples': o['samples'] = int(a[i+1])
        if x == '--pct': o['pct'] = int(a[i+1])
        if x == '--step': o['step'] = int(a[i+1])
    return o

def F(t):  # 秒 -> 绝对帧号
    return int(round(t*FPS))

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = FPS
    return sc

def setup_render(sc, samples=24, exposure=0.0, look='Medium High Contrast', bloom=True, ssr=True, vol=True,
                 gtao_dist=0.6, shadow_size='2048', film_transparent=False):
    sc.render.engine = 'BLENDER_EEVEE'
    e = sc.eevee
    e.taa_render_samples = samples
    e.use_soft_shadows = True
    e.shadow_cube_size = '1024'; e.shadow_cascade_size = shadow_size
    e.use_shadow_high_bitdepth = True
    e.use_gtao = True; e.gtao_distance = gtao_dist; e.gtao_factor = 1.0
    e.use_bloom = bloom; e.bloom_threshold = 1.0; e.bloom_intensity = 0.04; e.bloom_radius = 5.0
    e.use_ssr = ssr; e.use_ssr_refraction = ssr; e.ssr_quality = 0.5; e.ssr_thickness = 0.3; e.use_ssr_halfres = False
    e.volumetric_start = 0.1; e.volumetric_end = 200; e.volumetric_tile_size = '4'; e.volumetric_samples = 64
    e.use_volumetric_lights = vol; e.use_volumetric_shadows = vol
    e.gi_diffuse_bounces = 2
    sc.render.resolution_x = 1920; sc.render.resolution_y = 1080; sc.render.resolution_percentage = 100
    sc.render.film_transparent = film_transparent
    sc.render.filter_size = 1.2
    sc.view_settings.view_transform = 'Filmic'; sc.view_settings.look = look; sc.view_settings.exposure = exposure
    sc.render.image_settings.file_format = 'PNG'; sc.render.image_settings.color_mode = 'RGB'
    sc.render.image_settings.compression = 15

def world_color(sc, col, strength=1.0, top=None):
    w = bpy.data.worlds.new('W'); sc.world = w; w.use_nodes = True
    nt = w.node_tree; bg = nt.nodes['Background']
    if top is None:
        bg.inputs[0].default_value = (*col, 1); bg.inputs[1].default_value = strength
    else:   # 竖直渐变天空
        tc = nt.nodes.new('ShaderNodeTexCoord'); sep = nt.nodes.new('ShaderNodeSeparateXYZ')
        nt.links.new(tc.outputs['Generated'], sep.inputs[0])
        mr = nt.nodes.new('ShaderNodeMapRange'); mr.inputs[1].default_value = -0.2; mr.inputs[2].default_value = 0.8
        nt.links.new(sep.outputs['Z'], mr.inputs[0])
        mx = nt.nodes.new('ShaderNodeMixRGB'); mx.inputs[1].default_value = (*col, 1); mx.inputs[2].default_value = (*top, 1)
        nt.links.new(mr.outputs[0], mx.inputs[0]); nt.links.new(mx.outputs[0], bg.inputs[0]); bg.inputs[1].default_value = strength
    return w

# ---------------------------------------------------------------- 材质
class M:
    """材质节点构建小助手：m = M('name'); m.bsdf(...); 用 m.n(type) 加节点、m.l(a,b) 连线。"""
    def __init__(self, name):
        self.mat = bpy.data.materials.new(name); self.mat.use_nodes = True
        self.nt = self.mat.node_tree; self.N = self.nt.nodes; self.P = self.N['Principled BSDF']
        self.out = self.N['Material Output']
    def n(self, t, **kw):
        nd = self.N.new(t)
        for k, v in kw.items():
            if k.startswith('in_'):
                key = k[3:]; key = int(key) if key.isdigit() else key.replace('__', ' ')
                nd.inputs[key].default_value = v
            else: setattr(nd, k, v)
        return nd
    def l(self, a, b): self.nt.links.new(a, b)
    def set(self, **kw):
        for k, v in kw.items():
            key = k.replace('__', ' ')
            if isinstance(v, (tuple, list)) and len(v) == 3: v = (*v, 1)
            self.P.inputs[key].default_value = v
        return self
    def attr(self, name):
        a = self.n('ShaderNodeAttribute'); a.attribute_name = name; return a

def assign(obj, mat):
    obj.data.materials.clear(); obj.data.materials.append(mat.mat if isinstance(mat, M) else mat)

def noise(m, scale=5., detail=6., rough=.6, vec=None, dim='3D'):
    nz = m.n('ShaderNodeTexNoise'); nz.noise_dimensions = dim
    nz.inputs['Scale'].default_value = scale; nz.inputs['Detail'].default_value = detail; nz.inputs['Roughness'].default_value = rough
    if vec is not None: m.l(vec, nz.inputs['Vector'])
    return nz

def ramp(m, fac, stops):
    r = m.n('ShaderNodeValToRGB'); cr = r.color_ramp
    while len(cr.elements) > 1: cr.elements.remove(cr.elements[-1])
    cr.elements[0].position = stops[0][0]; cr.elements[0].color = (*stops[0][1], 1) if len(stops[0][1]) == 3 else stops[0][1]
    for p, c in stops[1:]:
        e = cr.elements.new(p); e.color = (*c, 1) if len(c) == 3 else c
    m.l(fac, r.inputs['Fac']); return r

def bump(m, height, strength=.5, dist=.1, normal=None):
    b = m.n('ShaderNodeBump'); b.inputs['Strength'].default_value = strength; b.inputs['Distance'].default_value = dist
    m.l(height, b.inputs['Height'])
    if normal is not None: m.l(normal, b.inputs['Normal'])
    return b

# ---------------------------------------------------------------- 网格
def grid_mesh(name, nx, ny, sx, sy, z=None, cols=None):
    """规则网格（numpy 一次性写入）。z: (ny,nx)；cols: dict 名称->(ny,nx,4) 颜色属性"""
    xs = np.linspace(-sx/2, sx/2, nx); ys = np.linspace(-sy/2, sy/2, ny)
    X, Y = np.meshgrid(xs, ys); Z = np.zeros_like(X) if z is None else z
    V = np.stack([X, Y, Z], -1).reshape(-1, 3)
    i = np.arange(nx*ny).reshape(ny, nx)
    q = np.stack([i[:-1, :-1], i[:-1, 1:], i[1:, 1:], i[1:, :-1]], -1).reshape(-1, 4)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(V)); me.vertices.foreach_set('co', V.astype(np.float32).ravel())
    me.loops.add(q.size); me.loops.foreach_set('vertex_index', q.ravel().astype(np.int32))
    me.polygons.add(len(q)); me.polygons.foreach_set('loop_start', np.arange(0, q.size, 4, dtype=np.int32))
    me.polygons.foreach_set('loop_total', np.full(len(q), 4, np.int32))
    me.update(); me.validate()
    me.polygons.foreach_set('use_smooth', np.ones(len(q), bool))
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob)
    # UV = 归一化 xy
    uv = me.uv_layers.new(name='UVMap'); lu = np.stack([(X.ravel()+sx/2)/sx, (Y.ravel()+sy/2)/sy], -1)[q.ravel()]
    uv.data.foreach_set('uv', lu.astype(np.float32).ravel())
    if cols:
        for nm, c in cols.items(): set_point_color(me, nm, c.reshape(-1, c.shape[-1]))
    return ob

def set_point_color(me, name, c):
    if c.shape[1] == 3: c = np.concatenate([c, np.ones((len(c), 1))], 1)
    a = me.color_attributes.get(name) or me.color_attributes.new(name, 'FLOAT_COLOR', 'POINT')
    a.data.foreach_set('color', c.astype(np.float32).ravel())

def set_point_float(me, name, v):
    a = me.attributes.get(name) or me.attributes.new(name, 'FLOAT', 'POINT')
    a.data.foreach_set('value', np.asarray(v, np.float32).ravel())

def shape_sequence(ob, frames, coords_fn):
    """逐帧网格动画：对每个帧 f 建一个 shape key（绝对坐标 coords_fn(f)->(N,3)），只在 f 帧权重为 1。"""
    if ob.data.shape_keys is None: ob.shape_key_add(name='Basis', from_mix=False)
    keys = []
    for f in frames:
        k = ob.shape_key_add(name=f'f{f}', from_mix=False)
        k.data.foreach_set('co', np.asarray(coords_fn(f), np.float32).ravel())
        keys.append((f, k))
    for i, (f, k) in enumerate(keys):
        for ff, v in ((f-1, 0.), (f, 1.), (f+1, 0.)):
            k.value = v; k.keyframe_insert('value', frame=ff)
    # 线性插值，避免贝塞尔过冲
    act = ob.data.shape_keys.animation_data.action
    for fc in act.fcurves:
        for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
    return keys

def obj_from_pydata(name, verts, faces, smooth=True):
    me = bpy.data.meshes.new(name); me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces]); me.update()
    if smooth: me.polygons.foreach_set('use_smooth', np.ones(len(me.polygons), bool))
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob); return ob

def add_mod(ob, typ, **kw):
    m = ob.modifiers.new(typ.lower(), typ)
    for k, v in kw.items(): setattr(m, k, v)
    return m

# ---------------------------------------------------------------- 灯光 / 相机
def sun(name, rot_deg, energy=3., color=(1, .9, .75), angle=2.):
    d = bpy.data.lights.new(name, 'SUN'); d.energy = energy; d.color = color; d.angle = math.radians(angle)
    o = bpy.data.objects.new(name, d); bpy.context.collection.objects.link(o)
    o.rotation_euler = Euler([math.radians(a) for a in rot_deg]); return o

def area(name, loc, target, energy=500., size=2., color=(1, 1, 1)):
    d = bpy.data.lights.new(name, 'AREA'); d.energy = energy; d.size = size; d.color = color
    o = bpy.data.objects.new(name, d); bpy.context.collection.objects.link(o); o.location = loc
    look_at(o, target); return o

def point(name, loc, energy=100., color=(1, .6, .3), radius=.1):
    d = bpy.data.lights.new(name, 'POINT'); d.energy = energy; d.color = color; d.shadow_soft_size = radius
    o = bpy.data.objects.new(name, d); bpy.context.collection.objects.link(o); o.location = loc; return o

UP_HINT = Vector((0, 0.35, 1)).normalized()
def look_at(o, target, roll=0., up=None):
    """相机/灯光朝向 target；up 为“屏幕上方”提示向量（默认偏 +Y 的天顶，正俯视时屏幕上方 = +Y，不会翻转）。"""
    f = (Vector(target) - o.location).normalized(); u0 = Vector(up) if up is not None else UP_HINT
    r = f.cross(u0)
    if r.length < 1e-6: r = f.cross(Vector((0, 1, 0)))
    r.normalize(); u = r.cross(f)
    if roll:
        a = math.radians(roll); r, u = r*math.cos(a)+u*math.sin(a), u*math.cos(a)-r*math.sin(a)
    m = Matrix((r, u, -f)).transposed()
    o.rotation_euler = m.to_euler()

def camera(sc, lens=35., sensor=36., clip=(0.05, 500)):
    c = bpy.data.cameras.new('Cam'); c.lens = lens; c.sensor_width = sensor; c.sensor_fit = 'HORIZONTAL'
    c.clip_start, c.clip_end = clip
    o = bpy.data.objects.new('Cam', c); bpy.context.collection.objects.link(o); sc.camera = o
    return o

def pchip(ts, vs):
    """单调三次插值（无过冲），返回 f(t)。vs 可为向量。"""
    ts = np.asarray(ts, float); vs = np.asarray(vs, float)
    if vs.ndim == 1: vs = vs[:, None]
    n = len(ts); h = np.diff(ts); dl = np.diff(vs, axis=0)/h[:, None]
    m = np.zeros_like(vs)
    for i in range(1, n-1):
        a, b = dl[i-1], dl[i]; w1 = 2*h[i]+h[i-1]; w2 = h[i]+2*h[i-1]
        m[i] = np.where(a*b > 0, (w1+w2)/(w1/np.where(a == 0, 1, a)+w2/np.where(b == 0, 1, b)), 0)
    def f(t):
        t = float(np.clip(t, ts[0], ts[-1])); i = min(np.searchsorted(ts, t, 'right')-1, n-2)
        s = (t-ts[i])/h[i]; h00 = 2*s**3-3*s**2+1; h10 = s**3-2*s**2+s; h01 = -2*s**3+3*s**2; h11 = s**3-s**2
        r = h00*vs[i]+h10*h[i]*m[i]+h01*vs[i+1]+h11*h[i]*m[i+1]
        return r if len(r) > 1 else float(r[0])
    return f

def animate_camera(cam, frames, keys, dof_obj=None, roll_fn=None, up=None):
    """keys: [(t秒, loc, target, lens, focus_dist|None)] —— PCHIP 平滑，逐帧写关键帧（线性）。"""
    ts = [k[0] for k in keys]
    fl = pchip(ts, [k[1] for k in keys]); ft = pchip(ts, [k[2] for k in keys]); fn = pchip(ts, [k[3] for k in keys])
    ff = pchip(ts, [k[4] if k[4] is not None else 10. for k in keys]) if keys[0][4] is not None else None
    for f in frames:
        t = f/FPS; cam.location = Vector(fl(t)); look_at(cam, ft(t), roll_fn(t) if roll_fn else 0., up); cam.data.lens = fn(t)
        cam.keyframe_insert('location', frame=f); cam.keyframe_insert('rotation_euler', frame=f); cam.data.keyframe_insert('lens', frame=f)
        if ff is not None:
            cam.data.dof.focus_distance = ff(t); cam.data.dof.keyframe_insert('focus_distance', frame=f)
    for ad in (cam.animation_data, cam.data.animation_data):
        if ad and ad.action:
            for fc in ad.action.fcurves:
                for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'

def anim_value(sock_or_obj, path, frames, fn):
    for f in frames:
        v = fn(f/FPS)
        if path is None: sock_or_obj.default_value = v; sock_or_obj.keyframe_insert('default_value', frame=f)
        else: setattr(sock_or_obj, path, v); sock_or_obj.keyframe_insert(path, frame=f)

# ---------------------------------------------------------------- 渲染
def render(sc, shot, f0, f1, opts):
    out = f'{ROOT}/{shot}' + ('_prev' if opts['preview'] else '')
    os.makedirs(out, exist_ok=True)
    if opts['preview']:
        sc.render.resolution_percentage = opts['pct'] or 50
        sc.eevee.taa_render_samples = opts['samples'] or 8
    else:
        if opts['samples']: sc.eevee.taa_render_samples = opts['samples']
        if opts['pct']: sc.render.resolution_percentage = opts['pct']
    if opts['still'] is not None:
        sc.frame_set(opts['still']); sc.render.filepath = f'{out}/still_{opts["still"]:06d}.png'
        t = time.time(); bpy.ops.render.render(write_still=True); print('STILL', time.time()-t); return
    a, b = opts['frames'] or (f0, f1)
    sc.frame_start, sc.frame_end = a, b
    sc.frame_step = opts.get('step', 1) if opts['preview'] else 1
    sc.render.filepath = f'{out}/######'
    sc.render.use_overwrite = False if not opts['preview'] else True
    bpy.ops.render.render(animation=True)

def sock(sockets, name):
    """取第一个“可用”(enabled) 的同名 socket（Mix/NamedAttribute 等多类型节点会有同名隐藏 socket）。"""
    for x in sockets:
        if x.name == name and x.enabled: return x
    raise KeyError(name)

def tube(name, pts, radius=.01, nseg=8, cap=False):
    """沿折线扫出圆管网格，UV.x = 沿线弧长比例(0..1)，UV.y = 周向。radius 可为数组。"""
    pts = np.asarray(pts, float); n = len(pts)
    rad = np.broadcast_to(np.asarray(radius, float), (n,))
    T = np.gradient(pts, axis=0); T /= np.linalg.norm(T, axis=1, keepdims=True)+1e-12
    a = np.array([0, 0, 1.]) if abs(T[0, 2]) < .9 else np.array([1., 0, 0])
    Nn = np.cross(T[0], a); Nn /= np.linalg.norm(Nn); Ns = [Nn]
    for i in range(1, n):   # 平行移动标架，避免扭转
        v = Ns[-1] - np.dot(Ns[-1], T[i])*T[i]; v /= np.linalg.norm(v)+1e-12; Ns.append(v)
    Ns = np.array(Ns); Bs = np.cross(T, Ns)
    ang = np.linspace(0, 2*np.pi, nseg, endpoint=False)
    V = (pts[:, None, :] + rad[:, None, None]*(np.cos(ang)[None, :, None]*Ns[:, None, :]+np.sin(ang)[None, :, None]*Bs[:, None, :])).reshape(-1, 3)
    Fc = []
    for i in range(n-1):
        for j in range(nseg):
            Fc.append((i*nseg+j, i*nseg+(j+1) % nseg, (i+1)*nseg+(j+1) % nseg, (i+1)*nseg+j))
    ob = obj_from_pydata(name, V, Fc)
    seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]; u = seg/seg[-1]
    uv = ob.data.uv_layers.new(name='UVMap'); lu = []
    for f in Fc:
        for vi in f:
            i, j = divmod(vi, nseg); lu.append((u[i], j/nseg))
    uv.data.foreach_set('uv', np.array(lu, np.float32).ravel())
    return ob

def join(objs, name=None):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]; bpy.ops.object.join()
    if name: objs[0].name = name
    return objs[0]

def value_node(m, frames, fn):
    v = m.n('ShaderNodeValue')
    for f in frames:
        v.outputs[0].default_value = fn(f/FPS); v.outputs[0].keyframe_insert('default_value', frame=f)
    return v

def mth(m, op, a, b=None):
    nd = m.n('ShaderNodeMath', operation=op)
    for i, x in enumerate((a, b)):
        if x is None: continue
        if isinstance(x, (int, float)): nd.inputs[i].default_value = x
        else: m.l(x, nd.inputs[i])
    return nd.outputs[0]

def flow_material(name, frames, phase_fn, color=(1., .68, .30), strength=2.4, alpha=.55, on_fn=None, dash=3.0, sharp=5.):
    """流线材质：沿 UV.x 移动的亮段（phase_fn(t) 递增 → 向线的末端流动），两端淡出，透明混合。"""
    fm = M(name); fm.mat.blend_method = 'BLEND'; fm.mat.shadow_method = 'NONE'; fm.mat.show_transparent_back = False
    uvn = fm.n('ShaderNodeTexCoord').outputs['UV']; sepu = fm.n('ShaderNodeSeparateXYZ'); fm.l(uvn, sepu.inputs[0])
    ph = value_node(fm, frames, phase_fn)
    oi = fm.n('ShaderNodeObjectInfo')
    d = mth(fm, 'ADD', mth(fm, 'SUBTRACT', mth(fm, 'MULTIPLY', sepu.outputs['X'], dash), ph.outputs[0]), oi.outputs['Random'])
    pk = mth(fm, 'POWER', mth(fm, 'FRACT', d), sharp)
    e1 = fm.n('ShaderNodeMapRange'); fm.l(sepu.outputs['X'], e1.inputs['Value']); e1.inputs['From Min'].default_value = 1.0; e1.inputs['From Max'].default_value = .8
    e2 = fm.n('ShaderNodeMapRange'); fm.l(sepu.outputs['X'], e2.inputs['Value']); e2.inputs['From Min'].default_value = .0; e2.inputs['From Max'].default_value = .1
    a = mth(fm, 'MULTIPLY', mth(fm, 'MULTIPLY', pk, mth(fm, 'MULTIPLY', e1.outputs[0], e2.outputs[0])), alpha)
    if on_fn is not None:
        on = value_node(fm, frames, on_fn); a = mth(fm, 'MULTIPLY', a, on.outputs[0])
    em = fm.n('ShaderNodeEmission'); em.inputs['Color'].default_value = (*color, 1); em.inputs['Strength'].default_value = strength
    tr = fm.n('ShaderNodeBsdfTransparent'); mx = fm.n('ShaderNodeMixShader'); fm.l(a, mx.inputs[0]); fm.l(tr.outputs[0], mx.inputs[1]); fm.l(em.outputs[0], mx.inputs[2])
    fm.l(mx.outputs[0], fm.out.inputs['Surface'])
    return fm

def cyl_coords(m, P):
    """P(世界坐标向量) → (r, theta, z) 三个 socket"""
    s = m.n('ShaderNodeSeparateXYZ'); m.l(P, s.inputs[0])
    r = mth(m, 'SQRT', mth(m, 'ADD', mth(m, 'MULTIPLY', s.outputs['X'], s.outputs['X']), mth(m, 'MULTIPLY', s.outputs['Y'], s.outputs['Y'])))
    th = mth(m, 'ARCTAN2', s.outputs['Y'], s.outputs['X'])
    return r, th, s.outputs['Z']
