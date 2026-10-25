"""后期：纸纹颗粒 → 饱和度 → 暖纸调 → 暗角（插画统一质感）。参数随风格预设走（style.preset(...)['paper']）。
用法：python3 paper.py in.png out.png [--style vivid|fresh] [--vivid 1.0]     或  from paper import paper"""
import os, sys
import numpy as np
from PIL import Image
_P = None
HERE = os.path.dirname(os.path.abspath(__file__))

def paper(img, k=.16, warm=.065, vig=.06, sat=1.25):
    """默认值 = vivid 1.0。fresh 用 k=.16, warm=.035, vig=.10, sat=1.12。"""
    global _P
    if _P is None: _P = np.asarray(Image.open(os.path.join(HERE, 'tex', 'paper.png')).convert('L'), np.float32)/255.
    a = img.astype(np.float32)/255. if img.dtype == np.uint8 else img
    h, w = a.shape[:2]; p = _P
    if p.shape != (h, w): p = np.asarray(Image.fromarray((p*255).astype(np.uint8)).resize((w, h), Image.BILINEAR), np.float32)/255.
    a = a*(1 + (p-.5)[..., None]*k)                                              # 1 纸纹颗粒
    m_ = a.mean(-1, keepdims=True); a = m_ + (a-m_)*sat                           # 2 饱和度（围绕像素灰度均值放大）
    a = a*(1-warm) + warm*np.array([.97, .92, .80])*a.mean(-1, keepdims=True)*1.08  # 3 暖纸调
    yy, xx = np.mgrid[0:h, 0:w]; r = np.hypot((xx-w/2)/(w/2), (yy-h/2)/(h/2))
    a = a*(1 - vig*np.clip(r-.55, 0, 1)**1.5)[..., None]                         # 4 暗角（中心 55% 半径不压）
    return (np.clip(a, 0, 1)*255+.5).astype(np.uint8)

def kw_for(argv):
    sys.path.insert(0, HERE); import style
    name = argv[argv.index('--style')+1] if '--style' in argv else 'vivid'
    s = float(argv[argv.index('--vivid')+1]) if '--vivid' in argv else 1.0
    return style.preset(name, s)['paper']

if __name__ == '__main__':
    a = sys.argv[1:]
    Image.fromarray(paper(np.asarray(Image.open(a[0]).convert('RGB')), **kw_for(a))).save(a[1])
