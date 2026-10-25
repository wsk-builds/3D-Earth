"""最小示例：白墙黛瓦小屋 + 岩石 + 溪水 + 流线 + 云团 + 灯笼（照 SPEC 搭，40 行能看全套做法）。
运行：blender -b --python example_scene.py [-- --pct 50 --style vivid --vivid 1.0]
输出：out/example.png（已加纸纹的成品）+ out/example_raw.png（未加纸纹的中间文件，运行本脚本时才生成，仓库不附带），并打印 check_frame 结果。"""
import sys, os, math
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import bpy
from bl_common import reset, setup_render, camera, look_at, assign
import toon as T

a = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
opt = lambda k, d: type(d)(a[a.index(k)+1]) if k in a else d
T.use_style(opt('--style', 'vivid'), opt('--vivid', 1.0))           # ① 先选档，再搭材质
PAL = T.PAL
sc = reset(); setup_render(sc); T.toon_setup(sc)                   # ② 通用设置 → 插画参数（Standard / 无 AO / 8 采样）
T.sky_world(sc)                                                    # ③ 平涂渐变天 + 均匀环境光（颜色随预设）
T.key_light('Sun', (52, 0, 35), energy=3.0, color=(1, .92, .80))  #    暖主光定明暗分界
T.fill_light('Sky', (-6, -4, 6))                                  #    冷补光把背光面抬到中档

def box(name, loc, size, mat):
    bpy.ops.mesh.primitive_cube_add(location=loc); o = bpy.context.object; o.scale = size; o.name = name; assign(o, mat); return o
earth = tuple(.6*a + .4*b for a, b in zip(PAL['paper'], PAL['sand']))                    # 大地面：纸色与沙色各半，暖但不艳
ground = lambda m: T.posterize(m, T.noise(m, .09, 1., .4, vec=m.n('ShaderNodeNewGeometry').outputs['Position']).outputs['Fac'], [(0., PAL['green']), (.40, PAL['green_l']), (.53, earth)])
box('Ground', (0, 0, -.05), (40, 40, .05), T.toon('ground', ground, levels=(.55, .76, .84)))   # 大面积：浅色/中饱和、亮档压到 .84 防过曝，纹理切硬边色块
box('Wall', (-1.6, 1.2, .9), (1.2, .9, .9), T.toon('wall', PAL['wall'], levels=(.62, .86, 1.0)))
box('Door', (-1.0, .29, .45), (.28, .02, .45), T.toon('door', PAL['wood'], levels=(.62, .86, 1.0)))
bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=1.95, depth=.9, location=(-1.6, 1.2, 2.25)); roof = bpy.context.object
roof.rotation_euler[2] = math.pi/4; roof.scale = (1, .8, 1); assign(roof, T.toon('tile', PAL['tile'], levels=(.55, .85, 1.25)))
bpy.ops.mesh.primitive_plane_add(size=1, location=(.6, -.2, .02)); water = bpy.context.object; water.scale = (40, 2.0, 1)
assign(water, T.toon('water', PAL['teal'], levels=(.62, .86, 1.0), gloss=.25))
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=.55, location=(.9, -.2, .15)); rock = bpy.context.object
rock.scale = (1.3, 1, .8); bpy.ops.object.shade_smooth()          # 弧面必须平滑，否则每个面片都被描线
assign(rock, T.toon('stone', lambda m: T.band_by_normal_z(m, [(-1, PAL['stone']), (.55, PAL['green_l'])]), levels=(.62, .86, 1.0)))
T.foam_disc('foam', (.9, -.2, .02), .78, wobble=.12)
bpy.ops.mesh.primitive_uv_sphere_add(radius=.18, location=(-.2, .1, 1.25)); bpy.ops.object.shade_smooth()
assign(bpy.context.object, T.flat('lantern', (1, .42, .16), strength=2.1))   # 发光体 = 平涂，不受光
T.puffs('cloud', [(-7.5, 16, 4.4, 1.2), (-6.2, 16, 4.8, 1.5), (-4.8, 16, 4.4, 1.1), (5.0, 20, 5.4, 1.3), (6.5, 20, 5.6, 1.0)])   # 云 = 扁白球
for i, (x, y) in enumerate([(-3.4, 2.6), (-4.2, .6), (2.6, 2.8), (3.6, 1.6)]):     # 树 = 树干 + 两三个球冠，冠按高度切两色
    bpy.ops.mesh.primitive_cylinder_add(radius=.07, depth=.8, location=(x, y, .4)); assign(bpy.context.object, T.toon('trunk', PAL['wood']))
    T.puffs(f'tree{i}', [(x, y, 1.05, .5), (x+.2, y+.1, 1.4, .36)], squash=1.,
            mat=T.toon(f'leaf{i}', lambda m: T.band_by_z(m, [(-1, PAL['green']), (.1, PAL['green_l'])]), levels=(.55, .84, 1.0)))
for k in range(5):                                                 # 流线：绕石分流的示意路径
    yk = -.75 + k*.28
    T.flowline(f'flow{k}', [(x/10, yk + .45*math.exp(-((x/10-.9)/.7)**2)*math.copysign(1, yk+.2), .05) for x in range(-30, 40)],
               color=(.85, .98, .95))
for i, (x, y, r, c) in enumerate([(-16, 34, 11., 'stone_d'), (-2, 40, 14., 'stone_d'), (14, 32, 10., 'green'), (26, 42, 13., 'stone_d')]):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=(x, y, -r*.35), segments=48, ring_count=24); h = bpy.context.object
    h.scale[2] = .55; bpy.ops.object.shade_smooth(); assign(h, T.toon(f'hill{i}', PAL[c], levels=(.55, .80, .95)))   # 远山：冷中间调压住画面
T.fog_card('far', (3, 26, 2.0), (90, 7), alpha_max=.5)              # 远山前一片雾：拉开空间层次
cam = camera(sc, lens=30.); cam.location = (5.4, -6.2, 3.6); look_at(cam, (-.2, .6, 1.3), up=(0, 0, 1))   # up=Z：地平线水平
T.comp_outline(sc, nthr=(.8, 1.4), zthr=(.06, .14))               # ④ 墨线；zthr 抬高防掠射地面远处糊灰
T.render_still(sc, os.path.join(HERE, 'out', 'example.png'), pct=opt('--pct', 50))   # ⑤ 渲染 → 纸纹 → 测量
