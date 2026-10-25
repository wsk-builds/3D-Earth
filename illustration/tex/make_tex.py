"""N30 插画风贴图（numpy/PIL 生成）：伞面、墙面水渍、远山水墨层、纸纹。"""
import numpy as np, math
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import gaussian_filter
rng = np.random.default_rng(30)
def hexc(h): h = h.lstrip('#'); return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def fbm(shape, scales=(64, 32, 16, 8, 4), amps=(1, .6, .4, .25, .15), seed=0):
    r = np.random.default_rng(seed); out = np.zeros(shape, np.float32)
    for s, a in zip(scales, amps):
        out += a*gaussian_filter(r.standard_normal(shape).astype(np.float32), s, mode='wrap')*s**.5
    out -= out.min(); out /= out.max(); return out

# ---------------- 纸纹（后期叠加用，灰度 0.5 为中性）
def paper(w=1920, h=1080):
    n = fbm((h, w), (40, 12, 3, 1), (1, .5, .35, .3), seed=1)
    fib = gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), (0.6, 7), mode='wrap')   # 横向纤维
    fib2 = gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), (6, 0.6), mode='wrap')
    p = .5 + (n-.5)*.35 + fib*1.2 + fib2*.6
    Image.fromarray(np.clip(p*255, 0, 255).astype(np.uint8)).save('paper.png')

# ---------------- 油纸伞伞面（正俯视，中心=伞轴，半径=画布半宽*0.985）
def umbrella(S=2048, NR=28):
    c = S/2; R = S/2*.985
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32); dx, dy = xx-c, yy-c
    r = np.hypot(dx, dy)/R; th = np.arctan2(dy, dx)
    a0 = np.array(hexc('#EFAE52'), np.float32); a1 = np.array(hexc('#D9822E'), np.float32)
    k = np.clip((r-.15)/.8, 0, 1)[..., None]
    img = a0*(1-k) + a1*k
    # 宣纸/桐油纸纤维 + 油渍斑驳
    fib = fbm((S, S), (24, 6, 2, .8), (1, .6, .5, .4), seed=5)
    img *= (.93 + .1*fib)[..., None]
    blot = fbm((S, S), (90, 40), (1, .6), seed=6); img *= (1 - .07*np.clip((blot-.55)*4, 0, 1))[..., None]
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert('RGBA'); d = ImageDraw.Draw(im, 'RGBA')
    # 水墨梅枝：分叉的锥形笔画
    ink = hexc('#2A2C27')
    def branch(p, ang, L, w, depth):
        pts = [p]; a = ang
        for i in range(14):
            a += rng.normal(0, .16); q = (pts[-1][0]+math.cos(a)*L/14, pts[-1][1]+math.sin(a)*L/14); pts.append(q)
        for i in range(len(pts)-1):
            ww = w*(1-i/len(pts))+1.5
            d.line([pts[i], pts[i+1]], fill=(*ink, 235), width=int(ww)); d.ellipse([pts[i+1][0]-ww/2, pts[i+1][1]-ww/2, pts[i+1][0]+ww/2, pts[i+1][1]+ww/2], fill=(*ink, 235))
        tips.append(pts[-1])
        for j in range(3, 13, 3):
            if depth > 0 and rng.random() < .8:
                branch(pts[j], a + rng.choice([-1, 1])*rng.uniform(.5, 1.0), L*rng.uniform(.35, .55), w*.5, depth-1)
            if rng.random() < .9: blossoms.append(pts[j+1])
    tips = []; blossoms = []
    for ang0, start in ((-0.6, (c-R*.97, c+R*.25)), (2.6, (c+R*.95, c-R*.3))):
        branch(start, ang0, R*.95, 26, 2)
    def flower(p, s, col, ctr):
        for i in range(5):
            a = i*2*math.pi/5 + rng.uniform(0, 1)
            q = (p[0]+math.cos(a)*s*.55, p[1]+math.sin(a)*s*.55)
            d.ellipse([q[0]-s*.42, q[1]-s*.42, q[0]+s*.42, q[1]+s*.42], fill=col)
        d.ellipse([p[0]-s*.22, p[1]-s*.22, p[0]+s*.22, p[1]+s*.22], fill=ctr)
        for i in range(6):
            a = rng.uniform(0, 2*math.pi); q = (p[0]+math.cos(a)*s*.32, p[1]+math.sin(a)*s*.32); d.ellipse([q[0]-2.5, q[1]-2.5, q[0]+2.5, q[1]+2.5], fill=(*hexc('#B8641E'), 255))
    for p in blossoms + tips:
        rr = math.hypot(p[0]-c, p[1]-c)/R
        if .2 < rr < .9:
            col = (*hexc('#FBF1DE'), 245) if rng.random() < .7 else (*hexc('#E7684A'), 240)
            flower((p[0]+rng.normal(0, 8), p[1]+rng.normal(0, 8)), rng.uniform(26, 40), col, (*hexc('#F2C14E'), 255))
    im = np.asarray(im.convert('RGB')).astype(np.float32)
    # 伞骨压痕：每根骨处暗线，骨间中缝略亮（伞面褶）
    ph = (th/(2*np.pi)*NR) % 1.0; dd = np.minimum(ph, 1-ph)
    rib = np.exp(-(dd*R*2*np.pi*np.maximum(r, .05)/NR/2.2)**2)
    im *= (1 - .32*rib*(r > .16))[..., None]
    mid = np.exp(-((ph-.5)*R*2*np.pi*np.maximum(r, .05)/NR/1.6)**2); im *= (1 - .10*mid*(r > .2))[..., None]
    def ring(r0, r1, col, a=1.):
        m = ((r >= r0) & (r < r1))[..., None]; im[:] = np.where(m, im*(1-a) + np.array(col, np.float32)*a, im)
    # 中心伞顶 + 彩线缠绕环 + 边缘青色包边
    ring(0, .075, hexc('#1E4A47')); ring(.075, .085, hexc('#F1D9A8'))
    for i, (r0, col) in enumerate([(.085, '#2E7A70'), (.098, '#F3C25A'), (.108, '#B5482A'), (.116, '#F3C25A'), (.124, '#2E7A70'), (.14, '#F1D9A8')]):
        ring(r0, r0+.013, hexc(col))
    hatch = (np.sin(th*NR*6) > 0) & (r > .085) & (r < .153); im[hatch] *= .82
    ring(.915, .925, hexc('#F7E6C4')); ring(.925, .985, hexc('#245E58')); ring(.985, 1.01, hexc('#163A37'))
    alpha = np.clip((1.012-r)*400, 0, 1)
    out = np.dstack([np.clip(im, 0, 255), alpha*255]).astype(np.uint8)
    Image.fromarray(out, 'RGBA').save('umbrella.png')

# ---------------- 墙面水渍（灰度遮罩：1 = 污渍最重；上缘向下垂流 + 墙脚返潮）
def stains(W=1024, H=1024):
    m = np.zeros((H, W), np.float32)
    for i in range(160):
        x = rng.uniform(0, W); L = rng.uniform(.08, .55)*H; w = rng.uniform(2, 16); s = rng.uniform(.25, 1)
        ys = np.arange(int(L)); xs = x + np.cumsum(rng.normal(0, .25, len(ys)))
        for y, xx in zip(ys[::2], xs[::2]):
            x0, x1 = int(xx-w/2), int(xx+w/2)+1; m[H-1-y if False else y, max(x0, 0):min(x1, W)] += s*(1-y/L)**.6
    m = gaussian_filter(m, (6, 2.5), mode='wrap')
    top = gaussian_filter(rng.random((H, W)).astype(np.float32), 18, mode='wrap'); yy = np.linspace(0, 1, H)[:, None]
    m += np.clip(1-yy/.12, 0, 1)*(.4+top*1.5)
    base = fbm((H, W), (40, 14, 5), (1, .5, .3), seed=9)
    m += np.clip((yy-.78)/.22, 0, 1)**1.2*(.6+base*1.2)*np.clip(1.1-(1-yy)*4*(1.3-base), 0, 1)
    m = np.clip(m/np.percentile(m, 99.5), 0, 1)
    Image.fromarray((m*255).astype(np.uint8)).save('stains.png')   # 注意：图像 y=0 为墙顶

# ---------------- 远山水墨层（RGBA，横向可平铺）
def mountains(W=4096, H=1024):
    cols = ['#5F7E79', '#86A29C', '#AFC4BE']
    for li, col in enumerate(cols):
        r = np.random.default_rng(40+li); x = np.arange(W)
        h = np.zeros(W)
        for k, a in ((2, .35), (5, .2), (11, .1), (23, .05), (60, .02)):
            h += a*np.sin(2*np.pi*k*x/W + r.uniform(0, 6.28))*r.uniform(.6, 1.2)
        h = (h-h.min())/(h.max()-h.min()); top = (1-(.25+.6*h))*H*.75 + H*.08
        yy = np.arange(H)[:, None]; below = (yy - top[None, :])
        a = np.clip(below/2.0, 0, 1)*np.clip(1 - below/(H*.55), 0, 1)**1.6      # 山脊清晰，向下淡入雾中
        tex = fbm((H, W), (30, 8, 2), (1, .5, .3), seed=50+li)
        a *= .78 + .3*tex
        rgb = np.array(hexc(col), np.float32)[None, None]*(.9+.15*tex[..., None])
        Image.fromarray(np.dstack([np.clip(rgb, 0, 255), np.clip(a*255, 0, 255)]).astype(np.uint8), 'RGBA').save(f'mtn{li}.png')

if __name__ == '__main__':
    import sys
    for f in (sys.argv[1:] or ['paper', 'umbrella', 'stains', 'mountains']): globals()[f]()
    print('done')
