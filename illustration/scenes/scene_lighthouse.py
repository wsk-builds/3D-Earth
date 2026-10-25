"""验证场景 1：海边灯塔（海洋主题，冷主调 → check_frame --cool）。
blender -b --python scenes/scene_lighthouse.py [-- --pct 50 --vivid 1.0]   → out/lighthouse.png"""
import sys, os, math
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, HERE)
import bpy, numpy as np
from mathutils import Vector
from bl_common import reset, setup_render, camera, look_at, assign, grid_mesh, tube
import toon as T, style

a = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
opt = lambda k, d: type(d)(a[a.index(k)+1]) if k in a else d
T.use_style('vivid', opt('--vivid', 1.0)); PAL = T.PAL
th = style.theme('ocean'); SEA, SEA_L, FOAM = th['main']; RED, GOLD = th['accent']

sc = reset(); setup_render(sc); T.toon_setup(sc)
T.sky_world(sc, horizon=style.hex2lin('#E9EEE6'), top=style.hex2lin('#A9D5DA'), z_range=(0., .45))   # 海景：天顶带一点湖蓝
T.key_light('Sun', (55, 0, 30), energy=3.0, color=(1, .92, .80))     # 光从右后上方来：塔身左侧落中档，有体积
T.fill_light('Fill', (-8, -6, 7), energy=200)

def mesh_obj(name, loc, mat, smooth=True):
    o = bpy.context.object; o.name = name; o.location = loc
    if smooth: bpy.ops.object.shade_smooth()
    assign(o, mat); return o

# ---- 岬角：高度场，崖面按法线切石色、顶面切草色、贴海处切沙色
CX, CY = 4.5, 6.0
OCHRE = tuple(.55*a + .45*b for a, b in zip(PAL['stone'], PAL['sand'])); OCHRE_D = tuple(.55*a + .45*b for a, b in zip(PAL['stone'], PAL['wood']))
def coast_r(t): return 5.2 + .9*np.sin(3*t + .4) + .5*np.sin(5*t + 1.3) + .25*np.sin(11*t)
nx = ny = 220; S = 26.
xs = np.linspace(-S/2, S/2, nx); X, Y = np.meshgrid(xs, xs)
R = np.hypot(X, Y); TH = np.arctan2(Y, X); d = R/coast_r(TH)
cliff = 1/(1 + np.exp((d - .93)*42))                                   # 陡崖
dome = np.clip(1 - d**2, 0, 1)*.9
ledge = 1/(1 + np.exp((d - 1.02)*30))*.35                              # 崖脚一圈低矮礁台
rng0 = np.random.default_rng(7)
ridges = sum(rng0.uniform(.03, .08)*np.sin(f*TH + rng0.uniform(0, 6)) for f in (7, 13, 23, 31))   # 崖面竖向褶皱
d = d + ridges*(cliff*(1-cliff))*3
cliff = 1/(1 + np.exp((d - .93)*42))
Z = 1.7*cliff + dome*1.1*cliff + ledge - .4*(d > 1.06)
land = grid_mesh('Headland', nx, ny, S, S, z=Z); land.location = (CX, CY, 0)
def land_col(m):
    sp0 = m.n('ShaderNodeSeparateXYZ'); m.l(T.wpos(m), sp0.inputs[0])            # 崖面：暖赭岩层，按世界高度切 3 层
    strata = T.posterize(m, sp0.outputs['Z'], [(-9, OCHRE_D), (.55, OCHRE), (1.05, OCHRE_D), (1.25, OCHRE)])
    g = m.n('ShaderNodeNewGeometry'); spn = m.n('ShaderNodeSeparateXYZ'); m.l(g.outputs['Normal'], spn.inputs[0])
    top = T.posterize(m, spn.outputs['Z'], [(-1, PAL['green']), (.9, PAL['green_l'])])
    mt = m.n('ShaderNodeMixRGB'); m.l(T.mth(m, 'GREATER_THAN', spn.outputs['Z'], .72), mt.inputs[0]); m.l(strata, mt.inputs[1]); m.l(top, mt.inputs[2])
    byn = mt.outputs[0]
    sp = m.n('ShaderNodeSeparateXYZ'); m.l(T.wpos(m), sp.inputs[0])
    low = T.mth(m, 'LESS_THAN', sp.outputs['Z'], .30)
    mx = m.n('ShaderNodeMixRGB'); m.l(low, mx.inputs[0]); m.l(byn, mx.inputs[1]); mx.inputs[2].default_value = (*PAL['sand'], 1)
    return mx.outputs[0]
assign(land, T.toon('land', land_col, levels=(.55, .80, .95)))

# ---- 海：世界坐标噪声切 3 档浪带 + 少量白浪尖
bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, .0)); sea = bpy.context.object; sea.name = 'Sea'
assign(sea, T.sea_mat('sea', deep=SEA, mid=PAL['teal'], light=SEA_L, scale=.18, stretch=(1., 4.), foam_thr=.80))
# 岸边白浪：沿海岸线外扩的一圈不规则平片（中间被岬角压住，只露出边）
t = np.linspace(0, 2*np.pi, 240, endpoint=False); rr = coast_r(t)*1.10 + .12*np.sin(17*t)
V = [(CX, CY, .03)] + [(CX + r*math.cos(q), CY + r*math.sin(q), .03) for r, q in zip(rr, t)]
me = bpy.data.meshes.new('surf'); me.from_pydata(V, [], [(0, i+1, (i+1) % 240 + 1) for i in range(240)])
o = bpy.data.objects.new('Surf', me); sc.collection.objects.link(o); assign(o, T.flat('surf', FOAM)); o.visible_shadow = False
rng = np.random.default_rng(3)
for i, (x, y, r) in enumerate([(-1.6, 3.2, .55), (-.6, 1.6, .38), (-2.6, 5.2, .32), (8.2, 0.6, .5), (9.3, 1.6, .3)]):   # 礁石 + 浪花
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=r, location=(x, y, r*.15))
    rk = mesh_obj(f'rock{i}', (x, y, r*.15), T.toon('rock', lambda m: T.band_by_normal_z(m, [(-1, PAL['stone']), (.6, OCHRE)]), levels=(.55, .80, .95)))
    rk.scale = (1.3, 1., .75); rk.rotation_euler[2] = rng.uniform(0, 3)
    T.foam_disc(f'rf{i}', (x, y, 0), r*1.75, wobble=.2, seed=i, color=FOAM)

# ---- 灯塔
LX, LY, LZ = CX + .4, CY - .6, 2.75
def lh(ob, name, mat): ob.name = name; bpy.ops.object.shade_smooth(); assign(ob, mat); return ob
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=1.0, depth=.55, location=(LX, LY, LZ + .1))
lh(bpy.context.object, 'plinth', T.toon('plinth', PAL['stone'], levels=(.55, .80, .95)))
H = 4.6
bpy.ops.mesh.primitive_cone_add(vertices=64, radius1=.66, radius2=.44, depth=H, location=(LX, LY, LZ + .35 + H/2))
stripes = [(-9, RED)] + sum([[(-H/2 + (k+.5)*H/5, PAL['wall']), (-H/2 + (k+1)*H/5, RED)] for k in range(4)], []) + [(H/2 - .1, PAL['wall'])]
tower = lh(bpy.context.object, 'tower', T.toon('tower', lambda m: T.band_by_z(m, stripes), levels=(.55, .80, 1.0)))
top = LZ + .35 + H
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=.72, depth=.12, location=(LX, LY, top + .06)); lh(bpy.context.object, 'gallery', T.toon('gal', PAL['tile']))
bpy.ops.mesh.primitive_torus_add(major_radius=.70, minor_radius=.025, location=(LX, LY, top + .42)); lh(bpy.context.object, 'rail', T.toon('rail', PAL['black']))
for k in range(16):
    q = k/16*2*math.pi; bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=.018, depth=.36, location=(LX + .70*math.cos(q), LY + .70*math.sin(q), top + .24))
    lh(bpy.context.object, f'post{k}', T.toon('rail', PAL['black']))
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=.40, depth=.62, location=(LX, LY, top + .43)); lh(bpy.context.object, 'lamp', T.flat('lamp', GOLD, strength=1.15))
for k in range(6):                                                    # 灯室窗棂
    q = k/6*2*math.pi + .3; bpy.ops.mesh.primitive_cube_add(size=1, location=(LX + .405*math.cos(q), LY + .405*math.sin(q), top + .43))
    o = lh(bpy.context.object, f'mul{k}', T.toon('mul', PAL['black'])); o.scale = (.03, .03, .31); o.rotation_euler[2] = q
bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=.52, depth=.5, location=(LX, LY, top + .99)); lh(bpy.context.object, 'cap', T.toon('cap', RED))
bpy.ops.mesh.primitive_uv_sphere_add(radius=.07, location=(LX, LY, top + 1.28)); lh(bpy.context.object, 'fin', T.toon('fin', PAL['black']))
for k, z in enumerate((LZ + 1.6, LZ + 3.0)):                         # 塔身小窗
    bpy.ops.mesh.primitive_cube_add(size=1, location=(LX - .55 + k*.02, LY - .32, z)); o = lh(bpy.context.object, f'win{k}', T.toon('win', PAL['tile']))
    o.scale = (.08, .16, .22); o.rotation_euler[2] = .52
# 光束：暖金、硬边分档透明
T.beam('beam', (LX - .3, LY - .2, top + .43), (-1., -.25, -.20), 10., r0=.32, r1=1.7, color=(1., .90, .62), alpha=.30)

# ---- 守塔人小屋 + 栅栏 + 灌木
def house(x, y, rot):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, LZ + .5)); o = bpy.context.object; o.scale = (1.7, 1.15, 1.0); o.rotation_euler[2] = rot
    assign(o, T.toon('hwall', PAL['wall'], levels=(.58, .84, 1.0)))
    gx, gy, gz = .85, .575, LZ + 1.0                                   # 山墙（白）+ 两片带出檐的屋面（红）
    G = [(-gx, -gy, gz - .02), (gx, -gy, gz - .02), (gx, gy, gz - .02), (-gx, gy, gz - .02), (-gx, 0, gz + .55), (gx, 0, gz + .55)]
    me = bpy.data.meshes.new('gable'); me.from_pydata(G, [], [(0, 3, 4), (1, 5, 2)]); gb = bpy.data.objects.new('gable', me); sc.collection.objects.link(gb)
    gb.location = (x, y, 0); gb.rotation_euler[2] = rot; assign(gb, T.toon('hwall', PAL['wall']))
    for sgn in (-1, 1):
        bpy.ops.mesh.primitive_cube_add(size=1); r = bpy.context.object
        r.scale = (2.0, .78, .07); r.rotation_euler = (sgn*-.76, 0, 0); r.location = (0, sgn*.30, gz + .27)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True); r.location = (x, y, 0); r.rotation_euler[2] = rot
        assign(r, T.toon('hroof', RED, levels=(.55, .82, 1.0)))
    for dx, w, h, c in [(-.35, .34, .62, PAL['wood']), (.4, .32, .3, PAL['tile'])]:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x + dx*math.cos(rot) + .58*math.sin(rot), y + dx*math.sin(rot) - .58*math.cos(rot), LZ + (.31 if h > .5 else .55)))
        o = bpy.context.object; o.scale = (w, .03, h); o.rotation_euler[2] = rot; assign(o, T.toon('hd', c))
house(CX - 2.0, CY + .9, -.25)
for k in range(9):
    q = -1.9 + k*.16; x, y = CX + 3.3*math.cos(q), CY + 3.3*math.sin(q) + .4
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=.035, depth=.42, location=(x, y, LZ + .17)); assign(bpy.context.object, T.toon('fence', PAL['wood']))
fx = [(CX + 3.3*math.cos(-1.9 + k*.02), CY + 3.3*math.sin(-1.9 + k*.02) + .4, LZ + .3) for k in range(66)]
assign(tube('rail1', fx, radius=.022), T.toon('fence', PAL['wood']))
leaf = T.toon('bush', lambda m: T.band_by_z(m, [(-1, PAL['green']), (.05, PAL['green_l'])]), levels=(.55, .84, 1.0))
for i, (x, y, r) in enumerate([(CX - 1.6, CY + .8, .45), (CX - 1.1, CY + 1.4, .35), (CX + 1.0, CY - 1.9, .35), (CX + 3.8, CY + 1.6, .5)]):
    T.puffs(f'bush{i}', [(x, y, LZ + r*.4, r), (x + r*.7, y + .1, LZ + r*.3, r*.7)], squash=.75, mat=leaf)

# ---- 帆船
def boat(x, y, s, rot):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, .1*s)); h = bpy.context.object; h.scale = (1.2*s, .38*s, .26*s)
    me = h.data
    for v in me.vertices:
        if v.co.z < 0: v.co.x *= .72; v.co.y *= .55
        if v.co.x > 0: v.co.y *= .35 if v.co.z > 0 else .1
    h.rotation_euler[2] = rot; assign(h, T.toon('hull', lambda m: T.band_by_z(m, [(-1, RED), (.25, PAL['wall'])]), levels=(.55, .82, 1.0)))
    mx, my = x - .08*s*math.cos(rot), y - .08*s*math.sin(rot)
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=.025*s, depth=1.7*s, location=(mx, my, .95*s)); assign(bpy.context.object, T.toon('mast', PAL['wood']))
    c, s_ = math.cos(rot), math.sin(rot)
    for nm, pts, col in [('sail', [(.04, 0, .3), (.04, 0, 1.75), (.95, 0, .3)], PAL['wall']), ('jib', [(-.06, 0, .45), (-.06, 0, 1.5), (-.7, 0, .45)], GOLD)]:
        V = [(mx + (px*c)*s, my + (px*s_)*s, pz*s) for px, _, pz in pts]
        me = bpy.data.meshes.new(nm); me.from_pydata(V, [], [(0, 1, 2)]); o = bpy.data.objects.new(nm, me); sc.collection.objects.link(o)
        mt = T.toon(nm, col, levels=(.62, .86, 1.0)); mt.mat.use_backface_culling = False; assign(o, mt)
    wake = [(x - (1.2 + k*.25)*s*c, y - (1.2 + k*.25)*s*s_ + .05*math.sin(k*.9), .02) for k in range(8)]
    assign(tube('wake', wake, radius=np.linspace(.045, .01, 8)*s), T.flat('wake', FOAM, alpha=.9))
boat(-4.2, 3.4, 1.0, .25)

# ---- 远景：远岬 + 雾片 + 云 + 海鸥
for i, (x, y, r, sz) in enumerate([(-22, 46, 9., .32), (-9, 52, 11., .26), (30, 50, 12., .3)]):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=(x, y, -r*.5), segments=48, ring_count=24); o = bpy.context.object
    o.scale[2] = sz*2.4; o.scale[0] = 1.8; bpy.ops.object.shade_smooth(); assign(o, T.toon(f'far{i}', PAL['water'], levels=(.6, .82, .95)))
T.fog_card('fog1', (0, 40, 1.4), (500, 5.), alpha_max=.6)   # 雾片要比画面宽得多，否则侧边露出硬边
T.puffs('cloudA', [(-14, 34, 9.0, 1.6), (-12.2, 34, 9.6, 2.0), (-10.2, 34, 9.1, 1.5), (-8.8, 34, 8.8, 1.1)])
T.puffs('cloudB', [(10, 40, 12.0, 1.8), (12.2, 40, 12.6, 2.3), (14.6, 40, 12.0, 1.6)])
for i, (x, y, z, s) in enumerate([(-.5, 6, 7.6, .32), (1.0, 7, 8.3, .24), (-2.0, 9, 8.9, .2)]):
    pts = [(x - s, y, z + .25*s), (x - s*.5, y, z + .35*s), (x, y, z), (x + s*.5, y, z + .35*s), (x + s, y, z + .25*s)]
    assign(tube(f'gull{i}', pts, radius=.028*s/.3), T.flat('gull', style.INK))

cam = camera(sc, lens=30.); cam.location = (-9.0, -9.6, 4.6); look_at(cam, (2.4, 5.0, 3.9), up=(0, 0, 1))
T.comp_outline(sc, nthr=(.8, 1.4), zthr=(.06, .14), fade=(25., 80.))
T.render_still(sc, os.path.join(HERE, 'out', 'lighthouse.png'), pct=opt('--pct', 50), cool=True)
