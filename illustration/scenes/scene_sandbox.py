"""验证场景 2：桌面地形沙盘（科学示意主题）——等高台阶地形 + 河流/湖 + 水循环示意（蒸发箭头、云、雨）+ 台灯光束。
blender -b --python scenes/scene_sandbox.py [-- --pct 50 --vivid 1.0]   → out/sandbox.png"""
import sys, os, math
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, HERE)
import bpy, numpy as np
from mathutils import Vector
from bl_common import reset, setup_render, camera, look_at, assign, grid_mesh, tube
import toon as T, style

a = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
opt = lambda k, d: type(d)(a[a.index(k)+1]) if k in a else d
T.use_style('vivid', opt('--vivid', 1.0)); PAL = T.PAL
th = style.theme('science'); WHITE, LAKE, GRASS, GOLD = th['main']; RED, COBALT = th['accent']

sc = reset(); setup_render(sc); T.toon_setup(sc)
T.sky_world(sc, horizon=style.hex2lin('#EDE6DA'), top=None)            # 室内：背景就是暖白墙色
T.key_light('Sun', (50, 0, 28), energy=2.6, color=(1, .92, .80))       # 窗光从右前方来
T.fill_light('Fill', (-5, -3, 5), energy=150)

def cube(name, loc, scale, mat, rot=0.):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc); o = bpy.context.object; o.name = name; o.scale = scale; o.rotation_euler[2] = rot
    assign(o, mat); return o

# ---- 桌面 + 墙
WOOD_L = tuple(.75*a + .25*b for a, b in zip(PAL['wood'], PAL['sand']))
OAK, OAK_L = [tuple(k*a + (1-k)*b for a, b in zip(PAL['wood'], PAL['paper'])) for k in (.55, .38)]   # 大面积桌面：浅橡木，别用纯木色
def grain(m):                                                          # 木纹：沿 x 拉长的噪声切两色硬边
    mp = m.n('ShaderNodeMapping'); m.l(T.wpos(m), mp.inputs['Vector']); mp.inputs['Scale'].default_value = (.15, 3., 1.)
    return T.posterize(m, T.noise(m, 1.5, 2., .5, vec=mp.outputs[0]).outputs['Fac'], [(0., OAK), (.5, OAK_L)])
desk = T.toon('desk', grain, levels=(.55, .80, .92))
d = cube('Desk', (0, .3, -.06), (9., 5.5, .12), desk)
wall = cube('Wall', (0, 3.2, 2.0), (60, .1, 12), T.toon('wall', WHITE, levels=(.6, .8, .88)))
cube('Skirting', (0, 3.12, .1), (60, .08, .2), T.toon('skirt', PAL['stone']))

# ---- 沙盘：等高台阶地形
SX, SY, STEP = 4.0, 2.6, .095
nx, ny = 520, 338
X, Y = np.meshgrid(np.linspace(-SX/2, SX/2, nx), np.linspace(-SY/2, SY/2, ny))
H = (.56*np.exp(-((X - .9)**2/.75 + (Y - .55)**2/.42)) + .36*np.exp(-((X + .35)**2/.45 + (Y - .75)**2/.30))
     + .26*np.exp(-((X - 1.55)**2/.22 + (Y + .35)**2/.32)) + .10*np.sin(2.3*X + 1)*np.cos(1.9*Y) + .12)
riv = np.array([(1.25, .95), (.95, .25), (.55, -.05), (.05, -.15), (-.45, -.35), (-.95, -.55)])    # 河道中心线（山 → 湖）
def dist_poly(px, py, P):
    best = np.full(px.shape, 1e9)
    for (x0, y0), (x1, y1) in zip(P[:-1], P[1:]):
        vx, vy = x1 - x0, y1 - y0; t = np.clip(((px - x0)*vx + (py - y0)*vy)/(vx*vx + vy*vy), 0, 1)
        best = np.minimum(best, np.hypot(px - x0 - t*vx, py - y0 - t*vy))
    return best
dr = dist_poly(X, Y, riv); w = .10 + .09*np.clip((1.2 - X)/2.2, 0, 1)
cv = np.exp(-(dr/(2.4*w))**2)                                            # 宽 V 形河谷：坡缓，台阶间距才拉得开
H = H*(1 - .95*cv) - .05*cv                                     # 刻出河谷
H = H - .32*np.exp(-((X + 1.25)**2/.22 + (Y + .7)**2/.12))             # 左前方湖盆
H = np.where(dr < w*.5, np.minimum(H, 0), H)                               # 河床压到水面以下
H = np.clip(H, 0, None)
edge = np.minimum(np.minimum(X + SX/2, SX/2 - X), np.minimum(Y + SY/2, SY/2 - Y))
H = H*np.clip(edge/.12, 0, 1)**.5
q = np.clip(H, 0, None)/STEP; f = q - np.floor(q); ss = np.clip((f - .78)/.22, 0, 1); ss = ss*ss*(3 - 2*ss)
Hq = (np.floor(q) + ss)*STEP + .02                                    # 等高台阶：平台 + 窄陡坎（用 smoothstep，不用硬 floor，否则网格锯齿全被描线）
terr = grid_mesh('Terrain', nx, ny, SX, SY, z=Hq); terr.location = (0, .2, .12)
Zb = .12 + .02 - .3*STEP                                                # 每级台阶一个色带：沙 → 嫩绿 → 绿 → 金 → 暖白（高程编码）
bands = [(-1, PAL['sand']), (Zb + STEP, GRASS), (Zb + 3*STEP, PAL['green']), (Zb + 5*STEP, GOLD), (Zb + 6*STEP, WHITE)]
assign(terr, T.toon('terrain', lambda m: T.band_by_z(m, bands, attr='World'), levels=(.58, .84, 1.0)))
# 水面：一整块平涂水面卡在第一级台阶之上，河谷和湖盆里自然露出
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, .2, .12 + .02 + .6*STEP)); wt = bpy.context.object; wt.name = 'Water'; wt.scale = (SX - .02, SY - .02, 1)
assign(wt, T.toon('water', lambda m: T.posterize(m, T.noise(m, 6., 2., .5, vec=T.wpos(m)).outputs['Fac'], [(0., LAKE), (.62, PAL['teal_l'])]),
                  levels=(.62, .86, 1.0), gloss=.15))
# 沙盘木框
FW, FH = .09, .32
for nm, loc, sc_ in [('fN', (0, .2 + SY/2 + FW/2, FH/2), (SX + 2*FW, FW, FH)), ('fS', (0, .2 - SY/2 - FW/2, FH/2), (SX + 2*FW, FW, FH)),
                     ('fE', (SX/2 + FW/2, .2, FH/2), (FW, SY, FH)), ('fW', (-SX/2 - FW/2, .2, FH/2), (FW, SY, FH))]:
    cube(nm, loc, sc_, T.toon('frame', OAK_L, levels=(.55, .82, .95)))
cube('base', (0, .2, .06), (SX, SY, .12), T.toon('frame', WOOD_L))

# ---- 小树：圆锥 + 球冠两种，只种在 2~5 级台阶
rng = np.random.default_rng(5); n_tree = 0
leaf = T.toon('leaf', lambda m: T.band_by_z(m, [(-1, PAL['green']), (0., GRASS)]), levels=(.55, .84, 1.0))
trunk = T.toon('trunk', PAL['wood'])
while n_tree < 34:
    i, j = rng.integers(10, ny - 10), rng.integers(10, nx - 10); h = Hq[i, j]
    if not (.02 + 2*STEP <= h <= .02 + 5*STEP) or dr[i, j] < .16: continue
    x, y, z = X[i, j], Y[i, j] + .2, h + .12; s = rng.uniform(.75, 1.15)
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=.008*s, depth=.05*s, location=(x, y, z + .025*s)); assign(bpy.context.object, trunk)
    if n_tree % 3:
        bpy.ops.mesh.primitive_cone_add(vertices=12, radius1=.045*s, depth=.13*s, location=(x, y, z + .11*s))
    else:
        bpy.ops.mesh.primitive_uv_sphere_add(radius=.045*s, location=(x, y, z + .09*s), segments=16, ring_count=8)
    bpy.ops.object.shade_smooth(); assign(bpy.context.object, leaf); n_tree += 1
# 湖边小屋两栋（尺度参照）
for k, (x, y) in enumerate([(-.55, -.62), (-.40, -.78)]):
    zz = .12 + Hq[np.argmin(abs(np.linspace(-SY/2, SY/2, ny) - (y - .2))), np.argmin(abs(np.linspace(-SX/2, SX/2, nx) - x))]
    cube(f'hut{k}', (x, y, zz + .035), (.08, .06, .07), T.toon('hut', PAL['wall']))
    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=.068, depth=.06, location=(x, y, zz + .1)); r = bpy.context.object
    r.rotation_euler[2] = math.pi/4; r.scale = (1.15, .85, 1); assign(r, T.toon('hutroof', RED))

# ---- 示意层：河流箭头（红）、蒸发箭头（钴蓝）、云 + 雨
Z0 = .12 + .02 + .6*STEP + .015
rp = np.array([(1.10, .62), (.95, .25), (.55, -.05), (.05, -.15), (-.45, -.35), (-.85, -.52)])
t = np.linspace(0, 1, 60); cs = np.cumsum(np.r_[0, np.hypot(*np.diff(rp, axis=0).T)]); cs /= cs[-1]
px, py = np.interp(t, cs, rp[:, 0]), np.interp(t, cs, rp[:, 1])
pts = [(x, y + .2, Z0 + .01) for x, y in zip(px, py)]
T.flowline('riverflow', pts[:-3], radius=.013, color=RED, alpha=.95)
T.arrow_head('riverhead', pts[-1], np.subtract(pts[-1], pts[-4]), size=.09, color=RED)
for k, (x0, y0) in enumerate([(-1.35, -.45), (-1.1, -.62), (-.85, -.40)]):         # 蒸发：湖面上升的 S 形箭头
    ev = [(x0 + .05*math.sin(q*4.), y0 + .2 + .1*q, Z0 + q*1.05) for q in np.linspace(0, 1, 30)]
    T.flowline(f'evap{k}', ev[:-2], radius=.011, color=COBALT, alpha=.95)
    T.arrow_head(f'evaph{k}', ev[-1], np.subtract(ev[-1], ev[-3]), size=.07, color=COBALT)
T.puffs('cloud', [(-.3, .9, 1.55, .26), (.05, .9, 1.68, .32), (.42, .95, 1.6, .27), (.7, 1.0, 1.52, .2)], squash=.75, color=(.93, .93, .91))
rain = T.flat('rain', style.vivid_rgb((.55, .78, .95), T.P), alpha=.9)
for k in range(16):                                                    # 雨：短斜线段，平涂半透明，不描线
    x, y = rng.uniform(-.25, .85), rng.uniform(.75, 1.15); z = rng.uniform(.75, 1.25)
    assign(tube(f'rain{k}', [(x, y, z), (x - .025, y, z - .16)], radius=.006), rain)

# ---- 桌面道具：台灯（光束）、尺子、铅笔、笔记本、杯子
LB = (2.75, 1.85, 0.)
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=.32, depth=.06, location=(LB[0], LB[1], .03)); bpy.ops.object.shade_smooth(); assign(bpy.context.object, T.toon('lampbase', GOLD))
arm = [(LB[0], LB[1], .05), (LB[0] - .1, LB[1] - .05, 1.15), (LB[0] - .65, LB[1] - .45, 1.75)]
assign(tube('arm1', [arm[0], arm[1]], radius=.03), T.toon('arm', PAL['black'])); assign(tube('arm2', [arm[1], arm[2]], radius=.03), T.toon('arm', PAL['black']))
SH = Vector(arm[2]); dl = (Vector((1.2, .55, .12)) - SH).normalized()
bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=.30, radius2=.07, depth=.42, end_fill_type='NOTHING', location=SH + dl*.12)
sh = bpy.context.object; sh.rotation_mode = 'QUATERNION'; sh.rotation_quaternion = (-dl).to_track_quat('Z', 'Y'); bpy.ops.object.shade_smooth()
mt = T.toon('shade', GOLD, levels=(.55, .82, 1.0)); mt.mat.use_backface_culling = False; assign(sh, mt)
bpy.ops.mesh.primitive_uv_sphere_add(radius=.07, location=SH + dl*.2); assign(bpy.context.object, T.flat('bulb', (1., .95, .78), strength=1.1))
T.beam('lampbeam', SH + dl*.3, dl, 1.7, r0=.28, r1=.95, color=(1., .92, .66), alpha=.26)
cube('ruler', (-.4, -1.55, .015), (2.2, .22, .03), T.toon('ruler', GOLD, levels=(.6, .85, 1.0)), rot=.06)
for k in range(23):
    cube(f'tick{k}', (-1.45 + k*.095, -1.48 + k*.095*.06, .032), (.008, .07 if k % 5 else .11, .004), T.flat('tick', style.INK), rot=.06)
pen = [(1.2, -1.45, .03), (2.25, -1.15, .03)]
assign(tube('pencil', pen, radius=.035, nseg=6), T.toon('pencil', RED))
bpy.ops.mesh.primitive_cone_add(vertices=6, radius1=.035, depth=.12, location=(2.31, -1.133, .03)); c = bpy.context.object
c.rotation_euler = (0, math.pi/2, math.atan2(.3, 1.05)); assign(c, T.toon('pencil_tip', PAL['sand']))
nb = cube('notebook', (-3.05, -.55, .03), (1.3, 1.7, .06), T.toon('nb', COBALT, levels=(.58, .84, 1.0)), rot=-.18)
cube('nbpage', (-3.05, -.55, .065), (1.2, 1.62, .012), T.toon('nbp', WHITE, levels=(.6, .84, .93)), rot=-.18)
for k in range(8):
    cube(f'line{k}', (-3.05 + .02*k*math.sin(.18) + .0, -1.15 + k*.17, .078), (1.0, .012, .004), T.flat('nbline', style.vivid_rgb((.55, .75, .85), T.P)), rot=-.18)
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=.22, depth=.5, location=(-2.6, 1.6, .25)); bpy.ops.object.shade_smooth(); assign(bpy.context.object, T.toon('mug', LAKE))
bpy.ops.mesh.primitive_torus_add(major_radius=.12, minor_radius=.03, location=(-2.84, 1.6, .27), rotation=(math.pi/2, 0, 0)); assign(bpy.context.object, T.toon('mug', LAKE))
T.flowline('steam1', [(-2.6 + .04*math.sin(q*6), 1.6, .52 + q*.45) for q in np.linspace(0, 1, 20)], radius=.012, color=(.97, .97, .95), alpha=.8)

cam = camera(sc, lens=30.); cam.location = (-1.9, -4.9, 3.5); look_at(cam, (.15, .3, .5), up=(0, 0, 1))
T.comp_outline(sc, nthr=(.8, 1.4), zthr=(.05, .12), fade=(14., 40.))
T.render_still(sc, os.path.join(HERE, 'out', 'sandbox.png'), pct=opt('--pct', 50))
