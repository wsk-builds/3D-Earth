"""通用插画风 toon 工具（Blender 3.6 Eevee）：3 档色阶平涂 + 暖紫暗部 + 合成器墨线 + 平涂天 + 难建模元素的现成做法。
默认风格 vivid 1.0（明艳）；换档：use_style('vivid', 1.25) / use_style('fresh')，或环境变量 ILLU_STYLE / ILLU_VIVID。
必须在搭材质之前选档（色阶节点在创建时写死参数）。

调用顺序：reset → setup_render → toon_setup → sky_world/key_light → 建模(toon/flat/…) → comp_outline → render_still（动画：打关键帧 → render_anim，见 SPEC §11）
"""
import bpy, math, os, sys, subprocess
import numpy as np
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0, HERE)
import style
from bl_common import M, mth, ramp, noise, assign, tube, sun, area

INK = style.INK
P = {}; PAL = {}                      # 当前预设参数 / 色板（线性）；use_style 原地更新，from toon import PAL 也能看到

def use_style(name='vivid', strength=1.0):
    P.clear(); P.update(style.preset(name, strength)); PAL.clear(); PAL.update(style.palette(P)); return P
use_style(os.environ.get('ILLU_STYLE', 'vivid'), float(os.environ.get('ILLU_VIVID', '1.0')))
def paper_kw(): return dict(P['paper'])

# ---------------------------------------------------------------- 渲染参数
def toon_setup(sc, samples=8, ssr=False):
    """Standard 视图变换（Filmic 会发灰）、无 AO / 泛光 / 软阴影、filter 1.0。必须在 setup_render 之后调用。"""
    e = sc.eevee
    e.taa_render_samples = samples
    e.use_gtao = False; e.use_bloom = False; e.use_ssr = ssr; e.use_ssr_refraction = False
    e.use_soft_shadows = False; e.shadow_cascade_size = '4096'; e.shadow_cube_size = '2048'
    e.use_volumetric_lights = False
    sc.view_settings.view_transform = 'Standard'; sc.view_settings.look = 'None'; sc.view_settings.exposure = 0
    sc.render.filter_size = 1.0; sc.render.use_freestyle = False

def noline(*objs):
    """放进 NoLine 集合。注意：只有 comp_outline(noline_mask=True) 时才真的不描线（Eevee 不出 IndexOB）。"""
    nol = bpy.data.collections.get('NoLine') or bpy.data.collections.new('NoLine')
    if nol.name not in bpy.context.scene.collection.children: bpy.context.scene.collection.children.link(nol)
    for o in objs:
        for c in list(o.users_collection): c.objects.unlink(o)
        nol.objects.link(o)

# ---------------------------------------------------------------- 天、环境光、主光
def sky_world(sc, horizon=None, top=None, ambient=None, amb_col=None, z_range=(-.05, .6)):
    """相机看到平涂/渐变天空；物体只吃均匀环境光（色阶暗部的底）。缺省颜色随预设：vivid 下天向暖雾色靠。"""
    horizon = horizon or P['sky_h']; top = P['sky_t'] if top is None else top
    ambient = P['ambient'] if ambient is None else ambient; amb_col = amb_col or P['amb_col']
    w = bpy.data.worlds.new('TW'); sc.world = w; w.use_nodes = True; nt = w.node_tree; N = nt.nodes
    bg = N['Background']; lp = N.new('ShaderNodeLightPath')
    cam_bg = N.new('ShaderNodeBackground'); amb = N.new('ShaderNodeBackground')
    amb.inputs[0].default_value = (*amb_col, 1); amb.inputs[1].default_value = ambient
    if not top:
        cam_bg.inputs[0].default_value = (*horizon, 1)
    else:
        tc = N.new('ShaderNodeTexCoord'); sep = N.new('ShaderNodeSeparateXYZ'); nt.links.new(tc.outputs['Generated'], sep.inputs[0])
        mr = N.new('ShaderNodeMapRange'); mr.inputs[1].default_value = z_range[0]; mr.inputs[2].default_value = z_range[1]; nt.links.new(sep.outputs['Z'], mr.inputs[0])
        mx = N.new('ShaderNodeMixRGB'); mx.inputs[1].default_value = (*horizon, 1); mx.inputs[2].default_value = (*top, 1)
        nt.links.new(mr.outputs[0], mx.inputs[0]); nt.links.new(mx.outputs[0], cam_bg.inputs[0])
    mix = N.new('ShaderNodeMixShader'); nt.links.new(lp.outputs['Is Camera Ray'], mix.inputs[0])
    nt.links.new(amb.outputs[0], mix.inputs[1]); nt.links.new(cam_bg.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], N['World Output'].inputs[0])
    N.remove(bg); return w

def key_light(name='Key', rot_deg=(52, 0, 35), energy=1.0, color=(1., .96, .88), angle=.5):
    """主光（太阳）：能量 × sun_k、颜色向 (1,.80,.55) 偏 sun_warm。平涂下光色不进最终颜色，
    它只决定明暗分界；『暖光』真正落在画面上的是亮档倍率 P['lit']。"""
    c = style._lerp(color, (1., .80, .55), P['sun_warm'])
    return sun(name, rot_deg, energy=energy*P['sun_k'], color=c, angle=angle)

def fill_light(name='Fill', loc=(-6, -4, 6), target=(0, 0, 0), energy=260., size=6., color=(.55, .8, .75)):
    """冷色补光：只把背光面从暗档抬到中档，不产生渐变。"""
    return area(name, loc, target, energy=energy, size=size, color=color)

# ---------------------------------------------------------------- 色阶着色
def _col(m, c):
    if callable(c): return c(m)
    if isinstance(c, (tuple, list)):
        r = m.n('ShaderNodeRGB'); r.outputs[0].default_value = (*c, 1) if len(c) == 3 else c; return r.outputs[0]
    return c

def toon_shade(m, base, steps=(.22, .62), levels=(.50, .80, 1.0), tint=None, normal=None):
    """Diffuse → ShaderToRGB → 灰度 → 3 段 CONSTANT 色阶 × 固有色。
    暗档 = levels0·tint；中档 = levels1·((1-mid_k)+mid_k·tint)；亮档 = levels2·lit。
    vivid 下暗档/中档再按固有色加饱和（shadow_sat），暗部是『更深的本色』而不是灰。"""
    tint = P['tint'] if tint is None else tint
    d = m.n('ShaderNodeBsdfDiffuse'); d.inputs['Color'].default_value = (1, 1, 1, 1)
    if normal is not None: m.l(normal, d.inputs['Normal'])
    s2r = m.n('ShaderNodeShaderToRGB'); m.l(d.outputs[0], s2r.inputs[0])
    bw = m.n('ShaderNodeRGBToBW'); m.l(s2r.outputs['Color'], bw.inputs[0])
    mk = P['mid_k']
    t0 = tuple(levels[0]*x for x in tint); t1 = tuple(levels[1]*((1-mk)+mk*x) for x in tint)
    t2 = tuple(levels[2]*x for x in P['lit'])
    r = ramp(m, bw.outputs[0], [(0., t0), (steps[0], t1), (steps[1], t2)]); r.color_ramp.interpolation = 'CONSTANT'; r.label = 'TOON'
    bc = _col(m, base)
    if P['shadow_sat']:
        sr = ramp(m, bw.outputs[0], [(0., (1.,)*3), (steps[0], (.5,)*3), (steps[1], (0.,)*3)])
        sr.color_ramp.interpolation = 'CONSTANT'; sr.label = 'TOON'
        hs = m.n('ShaderNodeHueSaturation'); m.l(bc, hs.inputs['Color'])
        m.l(mth(m, 'ADD', mth(m, 'MULTIPLY', sr.outputs[0], P['shadow_sat']), 1.), hs.inputs['Saturation']); bc = hs.outputs[0]
    mul = m.n('ShaderNodeMixRGB', blend_type='MULTIPLY'); mul.inputs[0].default_value = 1.
    m.l(bc, mul.inputs[1]); m.l(r.outputs[0], mul.inputs[2])
    return mul.outputs[0]

def toon(name, base, emit=0., alpha=1., gloss=0., gloss_rough=.06, steps=(.22, .62), levels=(.50, .80, 1.0),
         tint=None, normal=None, blend='BLEND', backface=True, shadow=True):
    """完整插画材质。base：颜色 / socket / callable(m)->socket。alpha、gloss 可为数值或 callable。"""
    m = M(name); m.N.remove(m.P)
    c = toon_shade(m, base, steps, levels, tint, normal)
    if emit:
        add = m.n('ShaderNodeMixRGB', blend_type='ADD'); add.inputs[0].default_value = 1.
        m.l(c, add.inputs[1]); ce = m.n('ShaderNodeMixRGB', blend_type='MULTIPLY'); ce.inputs[0].default_value = 1.
        m.l(_col(m, base), ce.inputs[1]); ce.inputs[2].default_value = (emit, emit, emit, 1); m.l(ce.outputs[0], add.inputs[2]); c = add.outputs[0]
    em = m.n('ShaderNodeEmission'); m.l(c, em.inputs['Color']); sh = em.outputs[0]
    if gloss:
        g = m.n('ShaderNodeBsdfGlossy'); g.inputs['Roughness'].default_value = gloss_rough
        if normal is not None: m.l(normal, g.inputs['Normal'])
        mx = m.n('ShaderNodeMixShader')
        if callable(gloss): m.l(gloss(m), mx.inputs[0])
        else: mx.inputs[0].default_value = gloss
        m.l(sh, mx.inputs[1]); m.l(g.outputs[0], mx.inputs[2]); sh = mx.outputs[0]
    if callable(alpha) or alpha < 1:
        tr = m.n('ShaderNodeBsdfTransparent'); mx = m.n('ShaderNodeMixShader')
        if callable(alpha): m.l(alpha(m), mx.inputs[0])
        else: mx.inputs[0].default_value = alpha
        m.l(tr.outputs[0], mx.inputs[1]); m.l(sh, mx.inputs[2]); sh = mx.outputs[0]
        m.mat.blend_method = blend; m.mat.shadow_method = 'HASHED' if shadow else 'NONE'; m.mat.show_transparent_back = backface
    elif not shadow: m.mat.shadow_method = 'NONE'
    m.l(sh, m.out.inputs['Surface'])
    return m

def flat(name, col, alpha=1., strength=1.):
    """不受光的平涂（发光体、雨丝、雾片、流线、光束）。alpha 可为 callable。"""
    m = M(name); m.N.remove(m.P)
    em = m.n('ShaderNodeEmission'); m.l(_col(m, col), em.inputs['Color']); em.inputs['Strength'].default_value = strength; sh = em.outputs[0]
    if callable(alpha) or alpha < 1:
        tr = m.n('ShaderNodeBsdfTransparent'); mx = m.n('ShaderNodeMixShader')
        if callable(alpha): m.l(alpha(m), mx.inputs[0])
        else: mx.inputs[0].default_value = alpha
        m.l(tr.outputs[0], mx.inputs[1]); m.l(sh, mx.inputs[2]); sh = mx.outputs[0]
        m.mat.blend_method = 'BLEND'; m.mat.shadow_method = 'NONE'; m.mat.show_transparent_back = False
    else: m.mat.shadow_method = 'NONE'
    m.l(sh, m.out.inputs['Surface']); return m

def img_tex(m, path, vec=None, ext='REPEAT', interp='Linear', colorspace='sRGB'):
    t = m.n('ShaderNodeTexImage'); t.image = bpy.data.images.load(path, check_existing=True); t.extension = ext; t.interpolation = interp
    t.image.colorspace_settings.name = colorspace
    if vec is not None: m.l(vec, t.inputs['Vector'])
    return t

def posterize(m, fac, stops):
    """把连续量切成硬边平色块：stops=[(pos, col)...]。表面纹理一律这样做，不要连续噪声。"""
    r = ramp(m, fac, stops); r.color_ramp.interpolation = 'CONSTANT'; return r.outputs[0]

def obj_coord(m, attr='Object'):
    return m.n('ShaderNodeTexCoord').outputs[attr]

def wpos(m):
    """世界坐标（大物体缩放过时，Object/Generated 坐标只有 -1..1，噪声会几乎不变，用这个）。"""
    return m.n('ShaderNodeNewGeometry').outputs['Position']

def band_by_z(m, stops, attr='Object'):
    """按高度切色带（地形等高、树冠上下、建筑墙脚、灯塔红白环）。stops=[(z, col)...]；attr='World' 用世界高度。"""
    sp = m.n('ShaderNodeSeparateXYZ'); m.l(wpos(m) if attr == 'World' else obj_coord(m, attr), sp.inputs[0])
    return posterize(m, sp.outputs['Z'], stops)

def band_by_normal_z(m, stops):
    """按法线朝上程度切色：stops=[(nz, col)...]，例：岩石 侧面灰 → 顶面苔绿。"""
    g = m.n('ShaderNodeNewGeometry'); sp = m.n('ShaderNodeSeparateXYZ'); m.l(g.outputs['Normal'], sp.inputs[0])
    return posterize(m, sp.outputs['Z'], stops)

# ---------------------------------------------------------------- 难建模元素（现成做法）
def fog_card(name, loc, size, rot=(math.pi/2, 0, 0), alpha_max=.4, color=None, scale=1.2):
    """竖直雾片：平涂 + 带状噪声 alpha，越远的片 alpha_max 越大。颜色/浓度随预设（vivid 更淡更暖）。"""
    color = color or P['fog_col']; a_max = alpha_max*P['fog_a']
    def alpha(m):
        n = noise(m, scale, 2., .5)
        sp = m.n('ShaderNodeSeparateXYZ'); m.l(m.n('ShaderNodeTexCoord').outputs['Generated'], sp.inputs[0])
        v = m.n('ShaderNodeMapRange'); m.l(sp.outputs['Y'], v.inputs['Value']); v.inputs[1].default_value = 1.; v.inputs[2].default_value = .35   # 上淡下浓
        a = mth(m, 'MULTIPLY', mth(m, 'ADD', mth(m, 'MULTIPLY', n.outputs['Fac'], .8), .4), v.outputs[0])
        return mth(m, 'MULTIPLY', mth(m, 'MINIMUM', a, 1.), a_max)
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc, rotation=rot); o = bpy.context.object; o.name = name
    o.scale = (size[0], size[1], 1); assign(o, flat('mist_' + name, color, alpha=alpha)); o.visible_shadow = False
    return o

def puffs(name, balls, color=(.97, .97, .95), alpha=1., squash=.8, levels=(.84, .93, 1.0), mat=None):
    """云 / 烟 / 蒸汽：扁平白球叠成团（不用体积）。balls=[(x,y,z,r)...]。高 levels 让暗部只剩一道浅色。"""
    mat = mat or toon(name + '_m', color, steps=(.2, .55), levels=levels, alpha=alpha, shadow=False)
    obs = []
    for i, (x, y, z, r) in enumerate(balls):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=(x, y, z), segments=32, ring_count=16); o = bpy.context.object
        o.name = f'{name}{i}'; o.scale[2] = squash; bpy.ops.object.shade_smooth(); assign(o, mat); obs.append(o)
    return obs

def flowline(name, pts, radius=.012, color=(.98, .96, .88), alpha=.85, strength=1.):
    """气流 / 水流 / 示意箭头的线：细管 + 平涂（BLEND，不会被描框）。路径按真实流场或示意路径给。"""
    o = tube(name, pts, radius=radius); assign(o, flat(name + '_m', color, alpha=alpha, strength=strength)); return o

def arrow_head(name, tip, direction, size=.08, color=(.98, .96, .88), alpha=.97):
    d = Vector(direction).normalized()
    bpy.ops.mesh.primitive_cone_add(vertices=12, radius1=size*.55, depth=size, location=Vector(tip) - d*size*.5)
    o = bpy.context.object; o.name = name; o.rotation_mode = 'QUATERNION'; o.rotation_quaternion = d.to_track_quat('Z', 'Y')
    bpy.ops.object.shade_smooth(); assign(o, flat(name + '_m', color, alpha=alpha)); return o   # alpha<1 → BLEND → 不描线

def beam(name, apex, direction, length, r0=.05, r1=1., color=(1., .93, .70), alpha=.38, bands=3):
    """光束（灯塔、探照灯、窗光）：圆锥 + 平涂，alpha 沿长度分 bands 档硬边递减（不是渐变）。"""
    d = Vector(direction).normalized()
    bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=r1, radius2=r0, depth=length, end_fill_type='NOTHING',
                                    location=Vector(apex) + d*length/2)
    o = bpy.context.object; o.name = name; o.rotation_mode = 'QUATERNION'; o.rotation_quaternion = (-d).to_track_quat('Z', 'Y')
    bpy.ops.object.shade_smooth()
    def a(m):
        sp = m.n('ShaderNodeSeparateXYZ'); m.l(m.n('ShaderNodeTexCoord').outputs['Generated'], sp.inputs[0])
        st = [(0., (.35,)*3)] + [((i+1)/(bands+1), ((i+2)/(bands+1),)*3) for i in range(bands)]   # Generated.z：0 远端 → 1 光源
        lw = m.n('ShaderNodeLayerWeight'); lw.inputs['Blend'].default_value = .35
        edge = posterize(m, lw.outputs['Facing'], [(0., (1.,)*3), (.55, (.55,)*3), (.8, (0.,)*3)])  # 侧缘硬边变淡
        s = m.n('ShaderNodeSeparateRGB'); m.l(posterize(m, sp.outputs['Z'], st), s.inputs[0])
        e = m.n('ShaderNodeSeparateRGB'); m.l(edge, e.inputs[0])
        return mth(m, 'MULTIPLY', mth(m, 'MULTIPLY', s.outputs[0], e.outputs[0]), alpha)
    mt = flat(name + '_m', color, alpha=a); mt.mat.show_transparent_back = True
    assign(o, mt); o.visible_shadow = False; return o

def foam_disc(name, loc, radius, wobble=.18, z=.01, color=(.97, .97, .93), n=64, seed=0):
    """岸边 / 礁石周围的白浪花：不规则扁圆片贴在水面上（物体压在中间，露出的边就是一圈浪花）。"""
    rng = np.random.default_rng(seed); ph = rng.uniform(0, 6.28, 3)
    th = np.linspace(0, 2*np.pi, n, endpoint=False)
    rr = radius*(1 + wobble*(.6*np.sin(3*th+ph[0]) + .3*np.sin(5*th+ph[1]) + .2*np.sin(9*th+ph[2])))
    V = [(loc[0], loc[1], loc[2]+z)] + [(loc[0]+r*math.cos(t), loc[1]+r*math.sin(t), loc[2]+z) for r, t in zip(rr, th)]
    Fc = [(0, i+1, (i+1) % n + 1) for i in range(n)]
    me = bpy.data.meshes.new(name); me.from_pydata(V, [], Fc); o = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(o)
    assign(o, flat(name + '_m', color)); o.visible_shadow = False; return o

def sea_mat(name, deep=None, mid=None, light=None, foam=(.97, .97, .93), scale=.35, stretch=(1., 3.5), foam_thr=.74):
    """开阔水面（海、湖）：拉长噪声切 3 色硬边浪带 + 阈值白浪尖，少量光泽。全部平涂，不折射。"""
    deep = deep or PAL['water']; mid = mid or PAL['teal']; light = light or PAL['teal_l']
    def base(m):
        mp = m.n('ShaderNodeMapping'); m.l(wpos(m), mp.inputs['Vector'])
        mp.inputs['Scale'].default_value = (stretch[0], stretch[1], 1.)
        n = m.n('ShaderNodeTexNoise'); n.inputs['Scale'].default_value = scale; n.inputs['Detail'].default_value = 3.; m.l(mp.outputs[0], n.inputs['Vector'])
        return posterize(m, n.outputs['Fac'], [(0., deep), (.42, mid), (.6, light), (foam_thr, foam)])
    return toon(name, base, levels=(.62, .86, 1.0), gloss=.12)

def clear_water(name, tint=None, body=None, ripple=None, foam=(.96, .97, .93), body_a=.32):
    """浅水 / 溪流（能看见水底）：Transparent(tint) 透出底 + body_a 的平涂水色 + 阈值水纹/泡沫带（B6 做法）。
    只返回材质的基础两层；需要水纹/泡沫阈值时在返回的 m 上继续接 MixShader。"""
    tint = tint or PAL['teal_l']; body = body or PAL['teal']
    m = M(name); m.N.remove(m.P)
    tr = m.n('ShaderNodeBsdfTransparent'); tr.inputs['Color'].default_value = (*tint, 1)
    ew = m.n('ShaderNodeEmission'); ew.inputs['Color'].default_value = (*body, 1)
    m0 = m.n('ShaderNodeMixShader'); m0.inputs[0].default_value = body_a; m.l(tr.outputs[0], m0.inputs[1]); m.l(ew.outputs[0], m0.inputs[2])
    m.l(m0.outputs[0], m.out.inputs['Surface']); m.mat.blend_method = 'BLEND'; m.mat.shadow_method = 'NONE'; return m

# ---------------------------------------------------------------- 转换已有 Principled 场景
def _src(s): return s.links[0].from_socket if s.is_linked else None
def _mk(N, t, kw):
    n = N.new(t)
    for k, v in kw.items(): setattr(n, k, v)
    return n
def _has_surface(mat): return any(n.type == 'OUTPUT_MATERIAL' and n.inputs['Surface'].is_linked for n in mat.node_tree.nodes)

def toonify(steps=(.22, .62), levels=(.50, .80, 1.0), tint=None, skip=(), post=None, hide_volumes=True):
    """把场景里所有 Principled 材质换成色阶平涂（保留颜色逻辑和贴图），去掉体积；透射 → 半透明平涂 + 少量光泽。"""
    vol_objs = set()
    for mat in list(bpy.data.materials):
        if not mat.use_nodes or mat.name in skip: continue
        nt = mat.node_tree; N = nt.nodes; L = nt.links
        for o in [n for n in N if n.type == 'OUTPUT_MATERIAL']:
            if o.inputs['Volume'].is_linked:
                for l in list(o.inputs['Volume'].links): L.remove(l)
                vol_objs.add(mat.name)
        for Pn in [n for n in N if n.type == 'BSDF_PRINCIPLED']:
            m = type('MM', (), {})(); m.mat = mat; m.N = N
            m.n = lambda t, **kw: _mk(N, t, kw); m.l = lambda a, b: L.new(a, b)
            bc = Pn.inputs['Base Color']; base = _src(bc) or tuple(bc.default_value[:3])
            if post: base = post(mat.name, _col(m, base), m)
            c = toon_shade(m, base, steps, levels, tint)
            es = Pn.inputs['Emission Strength'].default_value; ec = Pn.inputs['Emission']
            if es > 0 and (ec.is_linked or max(ec.default_value[:3]) > 0):
                ce = m.n('ShaderNodeMixRGB', blend_type='MULTIPLY'); ce.inputs[0].default_value = 1.
                m.l(_src(ec) or _col(m, tuple(ec.default_value[:3])), ce.inputs[1]); ce.inputs[2].default_value = (es,)*3 + (1,)
                ad = m.n('ShaderNodeMixRGB', blend_type='ADD'); ad.inputs[0].default_value = 1.; m.l(c, ad.inputs[1]); m.l(ce.outputs[0], ad.inputs[2]); c = ad.outputs[0]
            em = m.n('ShaderNodeEmission'); m.l(c, em.inputs['Color']); sh = em.outputs[0]
            tr_ = Pn.inputs['Transmission'].default_value; a_in = Pn.inputs['Alpha']; a_src = _src(a_in); a_val = a_in.default_value
            if tr_ > .5:
                g = m.n('ShaderNodeBsdfGlossy'); g.inputs['Roughness'].default_value = .08
                mx = m.n('ShaderNodeMixShader'); mx.inputs[0].default_value = .25; m.l(sh, mx.inputs[1]); m.l(g.outputs[0], mx.inputs[2]); sh = mx.outputs[0]
                a_val = min(a_val, .55)
            if a_src is not None or a_val < 1:
                tr = m.n('ShaderNodeBsdfTransparent'); mx = m.n('ShaderNodeMixShader')
                if a_src is not None: m.l(a_src, mx.inputs[0])
                else: mx.inputs[0].default_value = a_val
                m.l(tr.outputs[0], mx.inputs[1]); m.l(sh, mx.inputs[2]); sh = mx.outputs[0]
                if mat.blend_method == 'OPAQUE': mat.blend_method = 'BLEND'
            for l in list(Pn.outputs[0].links): to = l.to_socket; L.remove(l); L.new(sh, to)
            N.remove(Pn)
    if hide_volumes:
        for ob in bpy.data.objects:
            if ob.type == 'MESH' and any(s.material and s.material.name in vol_objs and not _has_surface(s.material) for s in ob.material_slots):
                ob.hide_render = True
    return vol_objs

def port_fresh(sc):
    """把按『清新版』颜色写的旧场景整体推成当前预设：节点里的常量颜色走 vivid_rgb，名字以 mist 开头的雾片换色并变淡，
    太阳变亮变暖。新场景直接用 PAL / THEMES 取色，不要再调这个（会推两次）。"""
    def setc(sock): v = sock.default_value; sock.default_value = (*style.vivid_rgb(v[:3], P), v[3])
    for mat in bpy.data.materials:
        if not mat.use_nodes: continue
        nt = mat.node_tree
        if mat.name.startswith('mist'):
            for n in nt.nodes:
                if n.type == 'RGB': n.outputs[0].default_value = (*P['fog_col'], 1)
                if n.type == 'MIX_SHADER':
                    f = n.inputs[0]
                    if f.is_linked:
                        mm = nt.nodes.new('ShaderNodeMath'); mm.operation = 'MULTIPLY'; nt.links.new(f.links[0].from_socket, mm.inputs[0])
                        mm.inputs[1].default_value = P['fog_a']; nt.links.new(mm.outputs[0], f)
                    else: f.default_value *= P['fog_a']
            continue
        for n in nt.nodes:
            if n.label == 'TOON': continue
            if n.type == 'RGB': setc(n.outputs[0])
            elif n.type == 'VALTORGB':
                for el in n.color_ramp.elements: el.color = (*style.vivid_rgb(el.color[:3], P), el.color[3])
            elif n.type == 'MIX_RGB' and n.blend_type == 'MIX':
                for i in (1, 2):
                    if not n.inputs[i].is_linked: setc(n.inputs[i])
            elif n.type in ('EMISSION', 'BSDF_TRANSPARENT') and not n.inputs['Color'].is_linked:
                c = n.inputs['Color'].default_value
                if n.type == 'EMISSION' or max(c[:3]) - min(c[:3]) > .05: setc(n.inputs['Color'])
    for ob in bpy.data.objects:
        if ob.type == 'LIGHT' and ob.data.type == 'SUN':
            ob.data.energy *= P['sun_k']; ob.data.color = style._lerp(tuple(ob.data.color), (1., .80, .55), P['sun_warm'])

# ---------------------------------------------------------------- 合成器描边
def comp_outline(sc, ink=INK, alpha=.85, nthr=(.35, .9), zthr=(.035, .09), fade=(18., 60.), far_k=.3, noline_mask=False):
    """法线 Sobel（折角/轮廓）与 log 深度 Sobel（遮挡边）取大 → 按距离淡出 → ×alpha 混向墨青。
    BLEND 材质设 show_transparent_back=True，不写深度预通道 → 雨、雾、流线、光束不会被描框。
    noline_mask=True：NoLine 集合里的物体用 Cryptomatte 擦线（会连带擦掉相邻 1px，别用在地面/水面）。"""
    sc.render.use_freestyle = False
    vl = sc.view_layers[0]; vl.use_pass_normal = True; vl.use_pass_z = True
    for m in bpy.data.materials:
        if m.blend_method == 'BLEND': m.show_transparent_back = True
    sc.use_nodes = True; nt = sc.node_tree; N = nt.nodes; L = nt.links
    for n in list(N): N.remove(n)
    rl = N.new('CompositorNodeRLayers'); out = N.new('CompositorNodeComposite')
    def node(t, **kw):
        n = N.new(t)
        for k, v in kw.items(): setattr(n, k, v)
        return n
    def math_(op, a, b=None, clamp=False):
        n = node('CompositorNodeMath', operation=op, use_clamp=clamp)
        for i, x in enumerate((a, b)):
            if x is None: continue
            if isinstance(x, (int, float)): n.inputs[i].default_value = x
            else: L.new(x, n.inputs[i])
        return n.outputs[0]
    def ramp01(s, lo, hi): return math_('MULTIPLY', math_('SUBTRACT', s, lo), 1./(hi-lo), clamp=True)
    sn = node('CompositorNodeFilter', filter_type='SOBEL'); L.new(rl.outputs['Normal'], sn.inputs['Image'])
    sp = node('CompositorNodeSepRGBA'); L.new(sn.outputs[0], sp.inputs[0])
    en = ramp01(math_('ADD', math_('ADD', sp.outputs[0], sp.outputs[1]), sp.outputs[2]), *nthr)
    lz = math_('LOGARITHM', math_('MAXIMUM', rl.outputs['Depth'], .01), 2.718)
    sz = node('CompositorNodeFilter', filter_type='SOBEL'); L.new(lz, sz.inputs['Image'])
    sp2 = node('CompositorNodeSepRGBA'); L.new(sz.outputs[0], sp2.inputs[0])
    e = math_('MAXIMUM', en, ramp01(sp2.outputs[0], *zthr))
    e = math_('MULTIPLY', e, math_('ADD', math_('MULTIPLY', math_('SUBTRACT', 1., ramp01(rl.outputs['Depth'], *fade)), 1-far_k), far_k))
    nol = bpy.data.collections.get('NoLine')
    names = [o.name for o in nol.all_objects] if (nol and noline_mask) else []
    if names:
        vl.use_pass_cryptomatte_object = True
        cm = node('CompositorNodeCryptomatteV2'); cm.source = 'RENDER'; cm.scene = sc; cm.layer_name = vl.name + '.CryptoObject'
        cm.matte_id = ','.join(names)
        dl = node('CompositorNodeDilateErode', distance=1); L.new(cm.outputs['Matte'], dl.inputs[0])
        e = math_('MULTIPLY', e, math_('SUBTRACT', 1., dl.outputs[0]))
    e = math_('MULTIPLY', e, alpha, clamp=True)
    mx = node('CompositorNodeMixRGB'); L.new(e, mx.inputs[0]); L.new(rl.outputs['Image'], mx.inputs[1]); mx.inputs[2].default_value = (*ink, 1)
    L.new(mx.outputs[0], out.inputs[0])
    return nt

# ---------------------------------------------------------------- 出单帧：渲染 → 纸纹 → 测量
def render_still(sc, out_png, pct=50, samples=8, frame=None, cool=False, check=True):
    """渲染一帧到 <out>_raw.png（未加纸纹的中间文件，运行时才生成，仓库不附带），用当前预设的纸纹参数出 out_png，再跑 check_frame.py。"""
    if frame is not None: sc.frame_set(frame)
    sc.render.resolution_percentage = pct; sc.eevee.taa_render_samples = samples
    raw = out_png[:-4] + '_raw.png'; os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
    sc.render.filepath = raw; bpy.ops.render.render(write_still=True)
    a = ['python3', os.path.join(HERE, 'paper.py'), raw, out_png, '--style', P['name'], '--vivid', str(P['strength'])]
    subprocess.run(a, check=True)
    if check: subprocess.run(['python3', os.path.join(HERE, 'check_frame.py'), out_png] + (['--cool'] if cool else []))
    print('STILL_OK', out_png)

# ---------------------------------------------------------------- 动画：交给 render_anim.py 分段并行渲染（§11）
def _anim_arg(k):
    a = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    return a[a.index(k)+1] if k in a else None

def render_anim(sc, preview_png=None, pct=50, cool=False):
    """动画场景脚本的最后一行（契约见 SPEC §11）：场景、相机/物体关键帧、sc.frame_start/frame_end 都设好之后调用。
    - 被 render_anim.py 启动（带 --anim-job job.json）：只渲 job 里列出的帧，写 Blender 原图（未加纸纹）到 raw_dir，原子写入；
    - 带 --anim-probe meta.json：只写帧范围 / fps / 分辨率，不渲染；
    - 直接用 blender 跑（都不带）：渲中间一帧当预览，走 render_still（纸纹 + 自检），输出 preview_png。"""
    import json, time
    probe = _anim_arg('--anim-probe')
    meta = dict(frame_start=sc.frame_start, frame_end=sc.frame_end, fps=sc.render.fps / sc.render.fps_base,
                res=(sc.render.resolution_x, sc.render.resolution_y), style=P['name'], vivid=P['strength'])
    if probe:
        with open(probe, 'w') as f: json.dump(meta, f)
        print('ANIM_PROBE', json.dumps(meta), flush=True); return
    job = _anim_arg('--anim-job')
    if not job:
        if preview_png is None: preview_png = os.path.join(HERE, 'out', 'anim_preview.png')
        render_still(sc, preview_png, pct=pct, frame=(sc.frame_start + sc.frame_end)//2, cool=cool); return
    J = json.load(open(job)); os.makedirs(J['raw_dir'], exist_ok=True)
    if J.get('meta_out'):
        with open(J['meta_out'], 'w') as f: json.dump(meta, f)
    sc.render.resolution_percentage = J['pct']; sc.eevee.taa_render_samples = J['samples']
    sc.render.image_settings.file_format = 'PNG'
    print('ANIM_READY', len(J['frames']), flush=True); ppid = os.getppid()
    for f in J['frames']:
        if os.getppid() != ppid: print('ANIM_ORPHAN render_anim.py 已退出，停止', flush=True); return   # 主进程被强杀时不留孤儿进程
        t = time.time(); dst = os.path.join(J['raw_dir'], f"{f:0{J['digits']}d}.png"); tmp = os.path.join(J['raw_dir'], f".tmp_{f}_{os.getpid()}.png")
        sc.frame_set(f); sc.render.filepath = tmp; bpy.ops.render.render(write_still=True)
        os.replace(tmp, dst)                                            # 原子：中断时只会留下 .tmp_*，不会留下半张帧
        print(f'ANIM_FRAME {f} {time.time()-t:.3f}', flush=True)
    print('ANIM_DONE', flush=True)

def build_scene(script):
    """复用现成的单帧场景脚本：执行它，但跳过末尾的 render_still，返回脚本的全局变量（sc、cam……）。
    动画脚本里 `G = T.build_scene('scenes/scene_xxx.py')` 之后只管加关键帧，不用复制搭场景的代码。"""
    import runpy
    global render_still
    keep = render_still; render_still = lambda *a, **k: None
    try: return runpy.run_path(script if os.path.isabs(script) else os.path.join(HERE, script), run_name='__scene__')
    finally: render_still = keep
