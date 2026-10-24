#!/usr/bin/env python3
"""地理科普系列 · 封面一键生成（横版 1920x1080 + 竖版 1080x1920）

规范见同目录 SPEC.md。版式、字体、暗角参数逐项取自《波斯湾石油》那期封面脚本；地球外观（v2）用仓库根目录的 globe.py，与 docs/wind_hadley.jpg 同款。

用法（在仓库根目录或 cover/ 下都可以）：
  python cover/make_cover.py cover/examples/persian_gulf.json
config 里的相对路径（out_dir、自定义特效 .py）都相对于 cover/ 目录解析；默认输出到 cover/out/。
字体：Noto Serif CJK SC（Bold + Regular），见 SPEC.md §2.4 安装方法；也可在 config 里用
  "font_bold": "/path/NotoSerifCJKsc-Bold.otf", "font_regular": "...", "font_index": 0 指定，
或用环境变量 COVER_FONT_BOLD / COVER_FONT_REGULAR。
config.json 示例（视角 lat/lon/dist 必填，没有默认值——见 SPEC.md §3「视角怎么选」，每期单独判断）：
  {
    "title": "波斯湾石油", "question": "为什么波斯湾沿岸盛产石油？",
    "out_dir": "out/my_topic",
    "landscape": {"lat": 0, "lon": 0, "dist": 0, "ty": 0},
    "portrait":  {"lat": 0, "lon": 0, "dist": 0, "ty": 0},
    "effect": "none" | "pg" | "monsoon" | "rof" | "examples/my_effect.py"
  }
  ty = 标题基线 y（像素）。系列标准：横版 500、竖版 880（见 SPEC.md §5）。
自定义特效文件需定义 draw(ctx)，ctx 提供 cv, cam, proj(lat,lon,r), visible(lat,lon), sc, P, W, H, orient, TY。
注意：cam.py 在 import 时读取 EARTH_W/EARTH_H 固定画布尺寸，所以横竖版各开一个子进程渲染。
"""
import sys, os, json, math, subprocess

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
PY = sys.executable

# ---------------- 字体 ----------------
FONT_CANDIDATES = {   # (路径, ttc 索引)。ttc 合集里索引 2 = SC（简体）
    'bold': [('/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc', 2), ('/usr/share/fonts/noto-cjk/NotoSerifCJK-Bold.ttc', 2),
             ('/usr/share/fonts/google-noto-cjk/NotoSerifCJK-Bold.ttc', 2), ('/Library/Fonts/NotoSerifCJKsc-Bold.otf', 0),
             (os.path.expanduser('~/Library/Fonts/NotoSerifCJKsc-Bold.otf'), 0), ('C:/Windows/Fonts/NotoSerifCJKsc-Bold.otf', 0),
             (os.path.join(HERE, 'fonts', 'NotoSerifCJKsc-Bold.otf'), 0)],
    'regular': [('/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc', 2), ('/usr/share/fonts/noto-cjk/NotoSerifCJK-Regular.ttc', 2),
                ('/usr/share/fonts/google-noto-cjk/NotoSerifCJK-Regular.ttc', 2), ('/Library/Fonts/NotoSerifCJKsc-Regular.otf', 0),
                (os.path.expanduser('~/Library/Fonts/NotoSerifCJKsc-Regular.otf'), 0), ('C:/Windows/Fonts/NotoSerifCJKsc-Regular.otf', 0),
                (os.path.join(HERE, 'fonts', 'NotoSerifCJKsc-Regular.otf'), 0)],
}
def find_font(kind, cfg):
    p = cfg.get(f'font_{kind}') or os.environ.get(f'COVER_FONT_{kind.upper()}')
    if p:
        if not os.path.exists(p): sys.exit(f'字体文件不存在：{p}')
        return p, int(cfg.get('font_index', 2 if p.lower().endswith('.ttc') else 0))
    for p, i in FONT_CANDIDATES[kind]:
        if os.path.exists(p): return p, i
    sys.exit(f'找不到 Noto Serif CJK SC {kind} 字体。请按 SPEC.md §2.4 安装（如 apt install fonts-noto-cjk-extra），'
             f'或在 config 里设 "font_{kind}": "/path/to/NotoSerifCJKsc-{kind.capitalize()}.otf"')

# ---------------- 全系列固定参数（v2：地球外观 = 仓库根目录 globe.py，与 docs/wind_hadley.jpg 同款） ----------------
SS = 2.0                       # 2x 超采样渲染后 LANCZOS 缩回
FOV = 35                       # 竖直视场角（度）
# 太阳：近正面光，取自 example_wind.py 的哈德来场景（视点 5°N 18°E，太阳 sph(3, 46)）：
# 太阳方向与视线的大圆夹角 28.0°，方位角约 94°（正东略偏南）。按同样的夹角和方位从视点推出太阳，任何纬度下光照都一致。
SUN_REF = (5.0, 18.0, 3.0, 46.0)
def sun_latlon(lat, lon):
    f1, l1, f2, l2 = map(math.radians, SUN_REF)
    d = math.acos(math.sin(f1)*math.sin(f2)+math.cos(f1)*math.cos(f2)*math.cos(l2-l1))                       # 夹角 28.0°
    b = math.atan2(math.sin(l2-l1)*math.cos(f2), math.cos(f1)*math.sin(f2)-math.sin(f1)*math.cos(f2)*math.cos(l2-l1))  # 方位 ≈94°
    f1, l1 = math.radians(lat), math.radians(lon)
    f2 = math.asin(math.sin(f1)*math.cos(d)+math.cos(f1)*math.sin(d)*math.cos(b))
    l2 = l1+math.atan2(math.sin(b)*math.sin(d)*math.cos(f1), math.cos(d)-math.sin(f1)*math.sin(f2))
    return math.degrees(f2), math.degrees(l2)
GLOBE = dict(t=4.0, cloud_a=.16, star_a=1.0)   # 其余（atmo/exposure/night/land_dim…）全用 globe.py 默认值：无 DEM 浮雕、无 ocean_k
LAYOUT = {   # 字号/字距/最大宽度/副标题间距/暗角（中心y偏移, 半径, 不透明度）
    'l': dict(W=1920, H=1080, sc=1.0, title=150, tsp=40, maxw=1500, qsize=46, qsp=18, qgap=110,
              scrims=[(-50, 700, .42), (100, 420, .35)]),
    'p': dict(W=1080, H=1920, sc=1.15, title=175, tsp=45, maxw=980, qsize=54, qsp=18, qgap=130,
              scrims=[(-40, 640, .42), (130, 460, .55), (130, 300, .35)]),
}
QCOLOR, QALPHA = (.93, .96, 1), .92

# ---------------- 预置特效（克制：细线+小光点，加色混合，低不透明度） ----------------
def fx_pg(x):
    coast = [(30.0,48.0),(29.3,48.1),(28.0,48.7),(27.0,49.6),(26.2,50.2),(25.6,50.6),(24.6,51.4),(24.2,52.5),(24.2,54.0),
             (25.2,55.3),(26.0,56.2),(26.6,56.4),(27.1,56.0),(26.8,54.5),(27.5,52.6),(28.7,51.0),(29.8,50.2),(30.4,49.0),(30.0,48.0)]
    sk, P, sc, cv = x['skia'], x['P'], x['sc'], x['cv']
    pts = [x['proj'](la, lo)[:2] for la, lo in coast]
    pa = sk.Path(); pa.moveTo(*pts[0]); [pa.lineTo(*q) for q in pts[1:]]
    cv.drawPath(pa, P('#ffb040', .28, 'stroke', 14*sc, blur=9, blend='add'))   # 海湾轮廓柔光
    cv.drawPath(pa, P('#ffd27a', .35, 'stroke', 1.6*sc))                         # 1.6px 细金线
    for la, lo in [(25.4,49.6),(29.0,48.0),(30.4,47.4),(28.1,48.8),(26.6,52.0),(31.3,48.7),(35.5,44.4),(24.8,53.6)]:  # 主要油气田
        px, py, _ = x['proj'](la, lo)
        cv.drawCircle(px, py, 7*sc, P('#ff9a20', .4, blur=6, blend='add')); cv.drawCircle(px, py, 2.4*sc, P('#ffc860', .95))

def fx_rof(x):
    import numpy as np
    pts = json.load(open(os.path.join(HERE, 'data', 'volcanoes_lonlat.json'))); P, sc, cv = x['P'], x['sc'], x['cv']
    cvec = np.array(x['sph'](x['LAT'], x['LON'], 1.0))
    for lo, la in pts:
        p = np.array(x['sph'](la, lo, 1.004))
        if np.dot(p, cvec) < 0.25 or not (lo > 100 or lo < -60): continue
        px, py, _ = x['cam'].project(tuple(p))
        cv.drawCircle(px, py, 7*sc, P('#ff5a00', .45, blur=6, blend='add')); cv.drawCircle(px, py, 2.2*sc, P('#ffd060', .95))

def fx_monsoon(x):
    import numpy as np
    sk, P, sc, cv = x['skia'], x['P'], x['sc'], x['cv']
    paths = [[(-5,50),(2,58),(10,65),(16,72),(20,77)], [(-8,60),(0,70),(7,80),(14,87),(21,90)],
             [(-6,95),(2,103),(10,110),(18,114),(26,118)], [(-10,75),(-2,85),(6,93),(14,98),(22,101)]]
    for pl in paths:
        pts = []
        for i in range(len(pl)-1):
            for s in np.linspace(0, 1, 10, endpoint=False):
                la = pl[i][0]+(pl[i+1][0]-pl[i][0])*s; lo = pl[i][1]+(pl[i+1][1]-pl[i][1])*s
                pts.append(x['proj'](la, lo, 1.01)[:2])
        pts.append(x['proj'](*pl[-1], 1.01)[:2])
        pa = sk.Path(); pa.moveTo(*pts[0]); [pa.lineTo(*q) for q in pts[1:]]
        cv.drawPath(pa, P('#7fd4ff', .35, 'stroke', 22*sc, blur=10, blend='add')); cv.drawPath(pa, P('#e8f6ff', .55, 'stroke', 3*sc))
        (x1, y1), (x0, y0) = pts[-1], pts[-4]; a = math.atan2(y1-y0, x1-x0); L = 22*sc
        ah = sk.Path(); ah.moveTo(x1+math.cos(a)*8, y1+math.sin(a)*8)
        ah.lineTo(x1+math.cos(a+2.5)*L, y1+math.sin(a+2.5)*L); ah.lineTo(x1+math.cos(a-2.5)*L, y1+math.sin(a-2.5)*L); ah.close()
        cv.drawPath(ah, P('#e8f6ff', .7))

PRESETS = {'none': None, 'pg': fx_pg, 'rof': fx_rof, 'monsoon': fx_monsoon}

# ---------------- 单个朝向渲染（子进程内） ----------------
def render_one(cfg, orient):
    L = dict(LAYOUT[orient]); L.update(cfg.get('layout_override', {}).get(orient, {}))   # 一般不要覆盖；仅用于复现旧封面
    os.environ['EARTH_W'], os.environ['EARTH_H'] = str(L['W']), str(L['H'])   # cam.py 在 import 时读取画幅
    for p in (ROOT, HERE):
        if p not in sys.path: sys.path.insert(0, p)
    import numpy as np, skia
    from PIL import Image
    from globe import Globe
    from cam import Cam, sph
    from coverlib import make_font, P
    fonts = {'sb': find_font('bold', cfg), 'sr': find_font('regular', cfg)}
    font = make_font(fonts)
    W, H = L['W'], L['H']; v = cfg['landscape' if orient == 'l' else 'portrait']
    for k in ('lat', 'lon', 'dist', 'ty'):
        if k not in v: sys.exit(f'缺少 {k}：视角/标题位置必须每期显式给出，见 SPEC.md §3')
    LAT, LON, DIST, TY = float(v['lat']), float(v['lon']), float(v['dist']), float(v['ty'])
    ss = float(cfg.get('ss', SS))
    # 1) 光线追踪地球
    g = Globe(ss)
    c = Cam(tuple(sph(LAT, LON, DIST)), (0, 0, 0), FOV)
    slat, slon = sun_latlon(LAT, LON)
    A = g.render(c, sun=tuple(sph(slat, slon)), **GLOBE)
    im = Image.fromarray(A[:, :, :3]).resize((W, H), Image.LANCZOS)
    surf = skia.Surface(W, H); cv = surf.getCanvas()
    cv.drawImage(skia.Image.fromarray(np.array(im.convert('RGBA')), colorType=skia.kRGBA_8888_ColorType), 0, 0)
    # 2) 主题特效
    eff = cfg.get('effect', 'none'); fn = PRESETS.get(eff) if eff in PRESETS else None
    if eff not in PRESETS:
        ep = eff if os.path.isabs(eff) else os.path.join(HERE, eff)
        ns = {}; exec(open(ep).read(), ns); fn = ns['draw']
    if fn:
        eye = np.array(c.eye)
        def visible(la, lo, r=1.004):
            p = np.array(sph(la, lo, r)); w = eye-p; return float(np.dot(p/np.linalg.norm(p), w/np.linalg.norm(w)))
        fn(dict(cv=cv, cam=c, proj=lambda la, lo, r=1.004: c.project(sph(la, lo, r)), visible=visible, sph=sph,
                sc=L['sc'], P=P, skia=skia, W=W, H=H, orient=orient, TY=TY, LAT=LAT, LON=LON, surf=surf))
    # 3) 文字背后的径向暗角（scrim）
    def rg(x, y, r, a):
        p = skia.Paint(); p.setShader(skia.GradientShader.MakeRadial((x, y), r, [skia.Color4f(0, 0, 0, a), skia.Color4f(0, 0, 0, 0)])); return p
    for dy, r, a in L['scrims']: cv.drawRect(skia.Rect.MakeWH(W, H), rg(W/2, TY+dy, r, a))
    # 4) 文字：逐字绘制（字距 sp），超宽则字号与字距等比缩小 → 永远单行
    def line(s, size, y, sp, kind, alpha=1.0, color=(1, 1, 1), maxw=None):
        f = font(kind, size); ws = [f.measureText(ch) for ch in s]; tot = sum(ws)+sp*(len(s)-1)
        if maxw and tot > maxw: return line(s, size*maxw/tot*0.99, y, sp*maxw/tot, kind, alpha, color, None)
        x = W/2-tot/2
        for ch, wch in zip(s, ws):
            sh = skia.Paint(AntiAlias=True, Color4f=skia.Color4f(0, 0, 0, .65*alpha)); sh.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, size*.08))
            cv.drawString(ch, x+size*.02, y+size*.05, f, sh)
            cv.drawString(ch, x, y, f, skia.Paint(AntiAlias=True, Color4f=skia.Color4f(*color, alpha))); x += wch+sp
        return size, tot
    ts = line(cfg['title'], L['title'], TY, L['tsp'], 'sb', maxw=L['maxw'])
    qs = line(cfg['question'], L['qsize'], TY+L['qgap'], L['qsp'], 'sr', QALPHA, QCOLOR, maxw=L['maxw'])
    print(f'[{orient}] sun {slat:.2f}/{slon:.2f}  title size/width {ts[0]:.1f}/{ts[1]:.0f}  question {qs[0]:.1f}/{qs[1]:.0f}')
    # 5) 导出
    out = surf.makeImageSnapshot().toarray(colorType=skia.kRGBA_8888_ColorType)[:, :, :3]
    name = 'landscape' if orient == 'l' else 'portrait'
    od = cfg.get('out_dir', 'out'); od = od if os.path.isabs(od) else os.path.join(HERE, od); os.makedirs(od, exist_ok=True)
    for ext in ('png', 'jpg'):
        p = f'{od}/cover_{name}.{ext}'
        if os.path.exists(p) and not cfg.get('overwrite', False): sys.exit(f'{p} 已存在，拒绝覆盖（config 里设 "overwrite": true 才覆盖）')
    Image.fromarray(out).save(f'{od}/cover_{name}.png'); Image.fromarray(out).save(f'{od}/cover_{name}.jpg', quality=92)
    print('saved', f'{od}/cover_{name}.png/.jpg')

if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == '--one':
        render_one(json.load(open(sys.argv[3])), sys.argv[2]); sys.exit()
    cfgp = os.path.abspath(sys.argv[1]); cfg = json.load(open(cfgp))
    for o in cfg.get('orients', ['l', 'p']):
        r = subprocess.run([PY, os.path.abspath(__file__), '--one', o, cfgp], capture_output=True, text=True)
        print(r.stdout.strip()); err = '\n'.join(l for l in r.stderr.splitlines() if 'Fontconfig' not in l)
        if r.returncode: print(err); sys.exit(r.returncode)
