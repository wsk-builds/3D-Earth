"""动画示例：桌面地形沙盘，3 秒缓慢环绕 + 推近（SPEC §11 的基准镜头）。
python3 render_anim.py scenes/anim_sandbox.py --mp4            → out/anim/anim_sandbox/0001.png… + anim_sandbox.mp4
blender -b --python scenes/anim_sandbox.py -- --pct 50          → 只渲中间一帧预览 out/anim_sandbox.png"""
import sys, os, math
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, HERE)
from mathutils import Vector
import toon as T
from bl_common import look_at

a = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
opt = lambda k, d: type(d)(a[a.index(k)+1]) if k in a else d

# ① 搭场景：直接复用单帧脚本（--vivid 等参数照样生效）
G = T.build_scene('scenes/scene_sandbox.py'); sc, cam = G['sc'], G['cam']

# ② 镜头：绕目标点环绕 9°、推近 8%、俯角加 1.5°，smoothstep 缓入缓出。逐帧打关键帧（线性插值），帧号从 1 开始
FPS, SEC = 30, 3.0; N = int(FPS*SEC)
tgt = Vector((.15, .3, .5)); c0 = cam.location - tgt
r0, az0, el0 = c0.length, math.atan2(c0.y, c0.x), math.asin(c0.z/c0.length)
for f in range(1, N+1):
    s = (f-1)/(N-1); s = s*s*(3-2*s)
    az, r, el = az0 + math.radians(-4.5 + 9*s), r0*(1 - .08*s), el0 + math.radians(-1.5*s)
    cam.location = tgt + Vector((r*math.cos(el)*math.cos(az), r*math.cos(el)*math.sin(az), r*math.sin(el)))
    look_at(cam, tgt, up=(0, 0, 1)); cam.keyframe_insert('location', frame=f); cam.keyframe_insert('rotation_euler', frame=f)
for fc in cam.animation_data.action.fcurves:
    for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'

# ③ 契约：帧范围 + fps 写进场景，最后一行交给 render_anim
sc.render.fps = FPS; sc.frame_start, sc.frame_end = 1, N
T.render_anim(sc, os.path.join(HERE, 'out', 'anim_sandbox.png'), pct=opt('--pct', 50))
