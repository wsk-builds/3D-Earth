"""交付前自动测量：亮度 / 饱和度 / 暖色占比 / 过曝 / 最暗像素，判断是否在「明艳而不艳俗」界线内（SPEC §2.3）。
用法：
    python3 check_frame.py frame.png [frame2.png ...]          # 测已加纸纹的成品帧
    python3 check_frame.py --raw raw.png [--vivid 1.0]          # 测 Blender 原图：先按该强度的纸纹后期再测。原图一般是 render_still 写出的 out/<名>_raw.png，运行时才生成，仓库不附带
    python3 check_frame.py --cool frame.png                      # 冷主调题材（水、冰雪、海洋）：暖色占比改用宽松下限
    python3 check_frame.py --json ...                            # 机器可读输出
返回码：全部通过 0，否则 1。"""
import sys, os, json
import numpy as np
from PIL import Image

# 界线：以用户选定的 B8-C（街巷，vivid 1.0）和 B6-D（溪流，vivid 1.25）实测值为中心，两边留余量；
# 下限挡住「偏青、发灰」的旧版（B8-A S=.131），上限挡住「艳俗」（荧光、整屏橙、过曝）。
BOUNDS = {
    'L':      (.58, .80,  '平均亮度'),
    'L10':    (.30, None, '亮度 10% 分位（暗部不压黑）'),
    'S':      (.17, .32,  '平均饱和度'),
    'Smed':   (None, .40, '饱和度中位数（大面积不出纯色）'),
    'neon':   (None, 8.,  '高饱和像素 %（S>.70 且 V>.60，只许是焦点/点缀）'),
    'warm':   (12., 45.,  '暖色占比 %（色相 <65° 或 >320°，S>.15）'),
    'clip':   (None, 4.,  '过曝像素 %（任一通道 >.995）'),
    'dark':   (None, .5,  '最暗像素 %（亮度 <.15）'),
}
COOL_WARM_MIN = .3   # --cool：水/冰雪主导的画面，暖色只当点缀，>=0.3% 即可（B6-D 实测 0.35%）
COOL_S_MIN = .25     # --cool：暖色少了就得靠冷色本身够鲜（B6-D .297；旧版 B6-A .221 不过）

def rgb_to_hsv(x):
    mx = x.max(-1); mn = x.min(-1); d = mx - mn
    s = np.where(mx > 1e-6, d/np.maximum(mx, 1e-6), 0.)
    r, g, b = x[..., 0], x[..., 1], x[..., 2]; dd = np.maximum(d, 1e-6)
    h = np.where(mx == r, ((g-b)/dd) % 6, np.where(mx == g, (b-r)/dd + 2, (r-g)/dd + 4))*60.
    h = np.where(d > 1e-6, h, 0.)
    return h, s, mx

def measure(img):
    x = (np.asarray(img.convert('RGB'), np.float32)/255.).reshape(-1, 3)
    L = x @ np.array([.2126, .7152, .0722], np.float32)
    H, S, V = rgb_to_hsv(x)
    warm = ((H < 65) | (H > 320)) & (S > .15)
    return dict(L=float(L.mean()), L10=float(np.percentile(L, 10)), S=float(S.mean()), Smed=float(np.median(S)),
                neon=float(100*((S > .70) & (V > .60)).mean()), warm=float(100*warm.mean()),
                clip=float(100*(x.max(1) > .995).mean()), dark=float(100*(L < .15).mean()))

def judge(m, cool=False):
    bad = []
    for k, (lo, hi, _) in BOUNDS.items():
        if k == 'warm' and cool: lo = COOL_WARM_MIN
        if k == 'S' and cool: lo = COOL_S_MIN
        if lo is not None and m[k] < lo: bad.append(f'{k}={m[k]:.3g}<{lo}')
        if hi is not None and m[k] > hi: bad.append(f'{k}={m[k]:.3g}>{hi}')
    return bad

def main(argv):
    if not argv or "-h" in argv or "--help" in argv: print(__doc__); return 0
    raw = "--raw" in argv; cool = '--cool' in argv; js = '--json' in argv
    vivid = float(argv[argv.index('--vivid')+1]) if '--vivid' in argv else 1.0
    files = [a for i, a in enumerate(argv) if not a.startswith('--') and (i == 0 or argv[i-1] != '--vivid')]
    ok = True; res = {}
    for f in files:
        im = Image.open(f)
        if raw:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from paper import paper; import style
            im = Image.fromarray(paper(np.asarray(im.convert('RGB')), **style.preset('vivid', vivid)['paper']))
        m = measure(im); bad = judge(m, cool); ok &= not bad; res[f] = dict(m, pass_=not bad, fail=bad)
        if not js:
            print(f"{'PASS' if not bad else 'FAIL'}  {os.path.basename(f)}  " +
                  '  '.join(f"{k}={m[k]:.3f}" if k in ('L', 'L10', 'S', 'Smed') else f"{k}={m[k]:.2f}%" for k in BOUNDS) +
                  (f"   ← {'; '.join(bad)}" if bad else ''))
    if js: print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
