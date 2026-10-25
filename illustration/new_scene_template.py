"""新题材脚本骨架：复制成 scenes/scene_xxx.py 再改。
blender -b --python new_scene_template.py -- --pct 50 [--vivid 1.0|1.25] [--cool]   → out/template.png"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(HERE) == 'scenes': HERE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bpy
from bl_common import reset, setup_render, camera, look_at, assign
import toon as T, style

a = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
opt = lambda k, d: type(d)(a[a.index(k)+1]) if k in a else d
COOL = '--cool' in a                                                  # 水/冰雪/海洋主调的题材打开

# ① 选档（必须在建材质之前）+ 题材色
T.use_style('vivid', opt('--vivid', 1.0)); PAL = T.PAL
th = style.theme('landscape'); MAIN1, MAIN2, MAIN3 = th['main']; ACC1, ACC2 = th['accent']

# ② 场景、平涂天、光（主光定明暗交界，颜色不进画面）
sc = reset(); setup_render(sc); T.toon_setup(sc)
T.sky_world(sc)                                                       # 冷主调可给 top=style.hex2lin('#A9D5DA')
T.key_light('Sun', (55, 0, 30), energy=3.0)                          # 从侧后上方来，主体留一面中档
T.fill_light('Fill', (-8, -6, 7), energy=200)

# ③ 大面：亮档 ≤ .84–.92；颜色浅、中饱和（纸色和主色混）；纹理用世界坐标噪声切硬边色块
EARTH = tuple(.6*p + .4*q for p, q in zip(PAL['paper'], PAL['sand']))
ground = lambda m: T.posterize(m, T.noise(m, .09, 1., .4, vec=T.wpos(m)).outputs['Fac'], [(0., PAL['green']), (.40, PAL['green_l']), (.53, EARTH)])
bpy.ops.mesh.primitive_plane_add(size=200); assign(bpy.context.object, T.toon('ground', ground, levels=(.55, .76, .84)))
bpy.ops.mesh.primitive_plane_add(size=1, location=(.5, -1.6, .02)); o = bpy.context.object; o.scale = (60, 1.6, 1)
assign(o, T.toon('water', MAIN1, levels=(.62, .86, 1.0)))         # 一条湖蓝水带，冷暖互衬

# ④ 主体：简单几何体 + 3 档平涂，一个暖色焦点
bpy.ops.mesh.primitive_cube_add(size=1.4, location=(0, 0, .7)); assign(bpy.context.object, T.toon('body', PAL['wall'], levels=(.62, .86, 1.0)))
bpy.ops.mesh.primitive_cube_add(size=1, location=(.35, -.71, .4)); o = bpy.context.object; o.scale = (.36, .02, .8); assign(o, T.toon('door', PAL['wood']))
bpy.ops.mesh.primitive_cone_add(radius1=1.1, depth=.8, location=(0, 0, 1.8), vertices=4)
o = bpy.context.object; o.rotation_euler[2] = .785; assign(o, T.toon('roof', ACC2, levels=(.55, .80, .95)))
bpy.ops.mesh.primitive_uv_sphere_add(radius=.9, location=(2.2, .8, 1.3)); bpy.ops.object.shade_smooth()
assign(bpy.context.object, T.toon('tree', lambda m: T.band_by_z(m, [(-1, PAL['green']), (.1, PAL['green_l'])])))   # base 可传 callable(m)->socket

# ⑤ 难元素用现成函数：云 / 雾片 / 流线 / 箭头 / 光束 / 浪花
T.puffs('cloud', [(-1, 12, 4.6, 1.0), (.2, 12, 5.0, 1.3), (1.6, 12, 4.6, .9)])
T.fog_card('fog', (0, 14, .8), (500, 3.), alpha_max=.5)
T.flowline('wind', [(-3, -1, 1.2), (-1.5, -1.2, 1.5), (0, -1.0, 1.4)], color=PAL['teal_l'])

# ⑥ 相机：24–35 mm，up=Z 保持地平线水平
cam = camera(sc, lens=30.); cam.location = (-6, -7, 3.2); look_at(cam, (.6, 1.0, 1.4), up=(0, 0, 1))

# ⑦ 描边 → 单帧 → 纸纹 → 自检
T.comp_outline(sc, nthr=(.8, 1.4), zthr=(.06, .14))
T.render_still(sc, os.path.join(HERE, 'out', 'template.png'), pct=opt('--pct', 50), cool=COOL)
