"""从一张已有封面图反推相机 lat / lon / dist（网格搜索）。
注意：只对按当前（v2）外观渲染的封面有效；2026-10 之前的旧封面用的是另一套着色器，反推会有偏差。

用法（在仓库根目录）：
  python cover/tools/fit_view_from_image.py <封面.png> l "[[35,40,45],[45,50,55],[2.8,3.0,3.2]]"
  python cover/tools/fit_view_from_image.py <封面.png> p "[[30,35,40],[45,50,55],[5.0,5.3,5.6]]"
第二个参数 l=横版 1920x1080，p=竖版 1080x1920；第三个参数是 lat、lon、dist 三个候选列表。
先粗搜再细搜。打分方法：两边都缩到 1/8，去掉标题带（横版 y 330–560，竖版 y 700–940），
做亮度归一化后算均方差，越小越像。环境变量 SS 控制渲染超采样（默认 0.5，越大越慢越准）。
只读输入图片，不写任何文件。
"""
import sys, os, json, itertools, time
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ROOT = os.path.dirname(HERE)
ref_path, orient, spec = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
W, H = (1920, 1080) if orient == 'l' else (1080, 1920)
os.environ['EARTH_W'], os.environ['EARTH_H'] = str(W), str(H)
sys.path[:0] = [ROOT, HERE]
import numpy as np
from PIL import Image
from globe import Globe
from make_cover import sun_latlon, GLOBE
from cam import Cam, sph
SS = float(os.environ.get('SS', '0.5'))
g = Globe(SS)
ref = np.asarray(Image.open(ref_path).convert('RGB').resize((W//8, H//8), Image.BOX)).astype(float)
m = np.ones(ref.shape[:2], bool)
if orient == 'l': m[330//8:560//8] = False
else: m[700//8:940//8] = False
def score(la, lo, d):
    c = Cam(tuple(sph(la, lo, d)), (0, 0, 0), 35)
    A = g.render(c, sun=tuple(sph(*sun_latlon(la, lo))), **GLOBE)   # 与 make_cover.py 同一套外观和太阳规则
    im = np.asarray(Image.fromarray(A[:, :, :3]).resize((W//8, H//8), Image.BOX)).astype(float)
    a, b = im[m], ref[m]; a = (a-a.mean())/a.std(); b = (b-b.mean())/b.std()
    return float(((a-b)**2).mean())
t0 = time.time()
res = sorted((score(la, lo, d), la, lo, d) for la, lo, d in itertools.product(*spec))
print(f'{len(res)} 个候选，用时 {time.time()-t0:.1f}s。最好的 6 个 (score, lat, lon, dist)：')
for r in res[:6]: print('  %.4f  %s  %s  %s' % r)
