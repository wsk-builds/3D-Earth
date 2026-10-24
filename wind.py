"""wind.py —— 在 3D 地球上画"风"：彗星状气流粒子（流线、风场、垂直环流、台风螺旋）。

来自科普视频《北纬30度》里的哈德来环流和季风水汽镜头。所有图层都：
  * 是 3D 的：粒子位于地表上方一定高度（单位：地球半径），经相机透视投影；
  * 会被地球正确遮挡（逐点做光线-球体求交，转到背面的部分自动隐去）；
  * 由时间 t 完全确定（同一个 t 永远画出同一帧，不闪烁，可分块/断点续渲）；
  * 用 skia 在屏幕空间画：尾巴由细到粗、由透明到不透明，头部一个小亮点。

快速上手：
    from globe import Globe
    from cam import Cam, sph
    import wind
    g = Globe(); cam = Cam(tuple(sph(15, 101, 2.35)), (0, 0, 0))
    flow = wind.PathFlow([[(-12, 52), (8, 56), (15, 80), (25, 106), (31, 119)]])
    img = wind.composite(g.render(cam, sun=tuple(sph(21, 107))), cam, [flow], t=1.0)

坐标约定与 cam.py 一致：地球半径 1，y 轴指向北极，经度 0° 朝 +z，东经朝 +x。
"""
import math
import numpy as np
import skia
from cam import W, H

__all__ = ['llr', 'visible', 'draw_streaks', 'composite', 'Flow', 'PathFlow', 'FieldFlow', 'VerticalLoops',
           'Typhoon', 'hexrgb', 'smooth_path']


# ------------------------------------------------------------------ 基础工具
def hexrgb(c):
    """'#9fd0ff' 或 (r,g,b) 0..1 → np.array([r,g,b])"""
    if isinstance(c, str):
        c = c.lstrip('#'); return np.array([int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)])
    return np.asarray(c, float)


def llr(lat, lon, alt=0.0):
    """纬度、经度（度）+ 离地高度（地球半径为单位，0.01 ≈ 64 km）→ 世界坐标 (...,3)"""
    la = np.radians(np.asarray(lat, float)); lo = np.radians(np.asarray(lon, float)); r = 1.0 + np.asarray(alt, float)
    return np.stack([r * np.cos(la) * np.sin(lo), r * np.sin(la), r * np.cos(la) * np.cos(lo)], -1)


def visible(cam, p):
    """世界坐标点 p (N,3) 是否没被地球（单位球）挡住：从相机到点的线段与球求交。"""
    e = np.asarray(cam.eye, float); d = p - e; L = np.linalg.norm(d, axis=-1); u = d / L[:, None]
    b = u @ e; c = e @ e - 1.0; disc = b * b - c
    t0 = -b - np.sqrt(np.maximum(disc, 0.0))
    return ~((disc > 0) & (t0 > 0) & (t0 < L - 1e-4))


def _sm(a, b, x):
    t = np.clip((np.asarray(x, float) - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)


def _hash(i, n, k=0):
    """确定性伪随机 0..1（粒子编号 i、第 n 次重生、通道 k），代替随机数生成器，保证逐帧可复现。"""
    x = np.sin(i * 12.9898 + n * 78.233 + k * 37.719 + 0.5) * 43758.5453
    return x - np.floor(x)


def smooth_path(pts, iters=3):
    """Chaikin 圆角：把折线 [(lat,lon),...] 变成平滑曲线（端点保持不动）。"""
    p = np.asarray(pts, float)
    for _ in range(iters):
        q = np.empty((2 * (len(p) - 1), 2)); q[0::2] = .75 * p[:-1] + .25 * p[1:]; q[1::2] = .25 * p[:-1] + .75 * p[1:]
        p = np.vstack([p[:1], q, p[-1:]])
    return p


def _resample(pl, n=400):
    """按球面上的弧长（经度乘 cos 纬度）等距重采样"""
    d = np.hypot(np.diff(pl[:, 0]), np.diff(pl[:, 1]) * np.cos(np.radians(.5 * (pl[1:, 0] + pl[:-1, 0]))))
    s = np.r_[0, np.cumsum(d)]; u = np.linspace(0, s[-1], n)
    return np.c_[np.interp(u, s, pl[:, 0]), np.interp(u, s, pl[:, 1])]


# ------------------------------------------------------------------ 核心：画彗星尾
def draw_streaks(canvas, cam, pos, rgb, alpha, width=3.6, blur=0.5, head=True, head_color='#ffffff', head_alpha=0.55,
                 taper=1.3, glow=0.0, additive=False, occlude=True):
    """把 N 条 3D 折线画成彗星尾。

    pos   (N,K,3) 世界坐标，每条从尾到头 K 个点
    rgb   (N,3) 颜色 0..1；alpha (N,) 或 (N,K)
    width 线宽（像素），指"相机到地表距离"处的宽度，更近更粗、更远更细（透视）
    blur  尾巴的高斯模糊半径（像素），0.3–1 让线条柔一点
    head  头部画一个小亮点（加色混合）；head_alpha 控制亮度
    taper 尾巴透明度沿长度的幂次：越大尾巴消失得越快
    glow  外发光强度，默认 0（不发光）；0.15–0.3 是很淡的光晕
    additive 尾巴是否用加色混合（重叠处变亮）；默认普通 alpha 叠加，更克制
    """
    pos = np.asarray(pos, float)
    if pos.size == 0: return
    N, K, _ = pos.shape
    flat = pos.reshape(-1, 3); x, y, z = cam.project(flat)
    vis = visible(cam, flat) if occlude else np.ones(len(flat), bool)
    x, y, z, vis = (v.reshape(N, K) for v in (x, y, z, vis.astype(float)))
    al = np.broadcast_to(np.asarray(alpha, float).reshape(N, -1), (N, K))
    zr = np.linalg.norm(cam.eye) - 1.0
    rgb = np.broadcast_to(np.asarray(rgb, float).reshape(-1, 3), (N, 3))
    hc = hexrgb(head_color)
    mf = skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, blur) if blur > 0 else None
    for i in range(N):
        c = rgb[i]
        for k in range(K - 1):
            f = (k + 1) / (K - 1)
            a = al[i, k + 1] * vis[i, k] * vis[i, k + 1] * f ** taper
            if a < .01 or z[i, k] <= 0 or z[i, k + 1] <= 0: continue
            wd = width * zr / max(z[i, k], 1e-3) * (.35 + .65 * f)
            if glow > 0:
                pg = skia.Paint(AntiAlias=True, Color4f=skia.Color4f(c[0], c[1], c[2], min(1, a * glow)), StrokeWidth=wd * 3.5,
                                Style=skia.Paint.kStroke_Style, StrokeCap=skia.Paint.kRound_Cap)
                pg.setBlendMode(skia.BlendMode.kPlus); pg.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, wd * 2))
                canvas.drawLine(x[i, k], y[i, k], x[i, k + 1], y[i, k + 1], pg)
            pt = skia.Paint(AntiAlias=True, Color4f=skia.Color4f(c[0], c[1], c[2], min(1, a)), StrokeWidth=max(.6, wd),
                            Style=skia.Paint.kStroke_Style, StrokeCap=skia.Paint.kRound_Cap)
            if additive: pt.setBlendMode(skia.BlendMode.kPlus)
            if mf is not None: pt.setMaskFilter(mf)
            canvas.drawLine(x[i, k], y[i, k], x[i, k + 1], y[i, k + 1], pt)
        if head:
            a = al[i, -1] * vis[i, -1] * head_alpha
            if a > .01 and z[i, -1] > 0:
                wd = width * zr / z[i, -1]
                ph = skia.Paint(AntiAlias=True, Color4f=skia.Color4f(hc[0], hc[1], hc[2], min(1, a)))
                ph.setBlendMode(skia.BlendMode.kPlus)
                canvas.drawCircle(x[i, -1], y[i, -1], max(.8, wd * .75), ph)


def composite(globe_rgba, cam, layers, t, alpha=1.0, ss=None):
    """把若干风图层画到 Globe.render() 的输出上，返回 HxWx4 uint8。

    globe_rgba 可以是 Globe(ss) 的任意分辨率输出；图层坐标按 cam.W x cam.H 计算后自动缩放。
    layers 里可以放 Flow 对象，也可以放 callable(canvas, cam, t)。
    """
    a = np.ascontiguousarray(globe_rgba).copy(); a[..., 3] = 255
    h, w = a.shape[:2]; ss = ss or w / W
    surf = skia.Surface(w, h); c = surf.getCanvas()
    c.drawImage(skia.Image.fromarray(a, colorType=skia.kRGBA_8888_ColorType), 0, 0)
    c.save(); c.scale(ss, ss)
    for L in layers:
        if isinstance(L, Flow): L.draw(c, cam, t, alpha)
        else: L(c, cam, t)
    c.restore()
    return surf.makeImageSnapshot().toarray(colorType=skia.kRGBA_8888_ColorType)


# ------------------------------------------------------------------ 图层基类
class Flow:
    """所有风图层的基类：streaks(t) 返回 (pos, rgb, alpha)，draw() 负责画。"""
    width, blur, head, head_alpha, taper, glow, additive = 3.6, 0.5, True, 0.55, 1.3, 0.0, False

    def streaks(self, t):
        raise NotImplementedError

    def draw(self, canvas, cam, t, alpha=1.0):
        if alpha <= .01: return
        pos, rgb, al = self.streaks(t)
        if len(pos) == 0: return
        draw_streaks(canvas, cam, pos, rgb, np.asarray(al) * alpha, width=self.width, blur=self.blur, head=self.head,
                     head_alpha=self.head_alpha, taper=self.taper, glow=self.glow, additive=self.additive)


def _style(obj, width, blur, head, head_alpha, taper, glow, additive):
    obj.width, obj.blur, obj.head, obj.head_alpha, obj.taper, obj.glow, obj.additive = width, blur, head, head_alpha, taper, glow, additive


# ------------------------------------------------------------------ 1) 沿给定路径的流线（季风、洋流、急流……）
class PathFlow(Flow):
    """粒子沿一条或多条经纬度路径流动，路径两侧随机散开、向终点收拢。

    paths   [[(lat,lon),...], ...]，每条按从起点到终点的顺序给出
    weights 各路径分到的粒子比例（默认平均）
    colors  每条路径的颜色（默认淡蓝白）
    n       粒子数；speed (lo,hi) 每秒走完路径的比例；tail 尾长（占路径比例）；K 尾巴采样点数
    spread  路径两侧散开的标准差（度）；converge 0..1，越大越向终点收拢
    alt     离地高度（地球半径；0.012 ≈ 76 km，示意高度）
    smooth  Chaikin 圆角迭代次数，0 = 按原折线
    """

    def __init__(self, paths, weights=None, colors=('#9fd0ff', '#b9e6ff'), n=340, speed=(.07, .10), tail=.08, K=10,
                 spread=2.6, converge=.6, alt=.012, opacity=.85, fade=(.06, .15), smooth=3, seed=7,
                 width=3.6, blur=.6, head=True, head_alpha=.55, taper=1.3, glow=0.0, additive=False):
        self.paths = [_resample(smooth_path(p, smooth) if smooth else np.asarray(p, float)) for p in paths]
        m = len(self.paths); w = np.ones(m) if weights is None else np.asarray(weights, float)
        r = np.random.default_rng(seed)
        self.pid = r.choice(m, size=n, p=w / w.sum())
        self.off = r.normal(0, 1, n); self.ph = r.uniform(0, 1, n); self.v = r.uniform(*speed, n)
        cols = [colors] if isinstance(colors, str) else list(colors)
        self.rgb = np.array([hexrgb(cols[k % len(cols)]) for k in self.pid])
        self.tail, self.K, self.spread, self.converge, self.alt, self.opacity, self.fade = tail, K, spread, converge, alt, opacity, fade
        # 每条路径的单位法向（在当地东-北平面内，指向路径左侧）
        self.nrm = []
        for pl in self.paths:
            d = np.gradient(pl, axis=0); e = d[:, 1] * np.cos(np.radians(pl[:, 0])); nn = d[:, 0]
            L = np.hypot(e, nn) + 1e-9; self.nrm.append(np.c_[e / L, -nn / L])      # (dlat, dlon_east) 法向
        _style(self, width, blur, head, head_alpha, taper, glow, additive)

    def streaks(self, t):
        pos = []; al = []
        for i in range(len(self.ph)):
            pl, nm = self.paths[self.pid[i]], self.nrm[self.pid[i]]
            u = (self.ph[i] + t * self.v[i]) % 1.0
            us = np.clip(u - np.linspace(self.tail, 0, self.K), 0, .999)
            idx = us * (len(pl) - 1); i0 = idx.astype(int); fr = (idx - i0)[:, None]; i1 = np.minimum(i0 + 1, len(pl) - 1)
            p = pl[i0] * (1 - fr) + pl[i1] * fr; n_ = nm[i0] * (1 - fr) + nm[i1] * fr
            o = self.spread * self.off[i] * (1 - self.converge * us)
            la = p[:, 0] + o * n_[:, 0]; lo = p[:, 1] + o * n_[:, 1] / np.cos(np.radians(p[:, 0]))
            pos.append(llr(la, lo, self.alt))
            al.append(self.opacity * _sm(0, self.fade[0], u) * (1 - _sm(1 - self.fade[1], 1, u)))
        return np.array(pos), self.rgb, np.array(al)


# ------------------------------------------------------------------ 通用积分器（风场、台风共用）
def _trail(deriv, s0, age, steps, tail, K):
    """从出生状态 s0 (N,D) 用 RK2 积分到各自的年龄 age (N,)，每个粒子步长 = age/steps，
    因此头部位置随 t 连续变化（不会逐帧跳动）。返回尾→头 K 个时刻的状态 (N,K,D)。"""
    N = len(s0); dt = (age / steps)[:, None]; hist = [s0]; s = s0
    for _ in range(steps):
        k1 = deriv(s); k2 = deriv(s + .5 * dt * k1); s = s + dt * k2; hist.append(s)
    hist = np.stack(hist, 1)                                       # (N, steps+1, D)
    tq = np.clip(age[:, None] - np.linspace(tail, 0, K)[None, :], 0, None)   # 尾→头的时刻
    f = np.where(age[:, None] > 0, tq / np.maximum(age[:, None], 1e-9) * steps, 0)
    i0 = np.clip(f.astype(int), 0, steps - 1); fr = (f - i0)[..., None]
    a = np.take_along_axis(hist, i0[..., None], 1); b = np.take_along_axis(hist, i0[..., None] + 1, 1)
    return a * (1 - fr) + b * fr


class _Lifecycle(Flow):
    """粒子循环出生-消亡：第 i 个粒子以周期 life 重生，每次重生的位置由 (i, 重生次数) 哈希决定。"""

    def _ages(self, t):
        x = t / self.life + self.ph; n = np.floor(x); age = (x - n) * self.life
        return n, age, _sm(0, self.fade_in, age / self.life) * (1 - _sm(1 - self.fade_out, 1, age / self.life))


# ------------------------------------------------------------------ 2) 风场模式
class FieldFlow(_Lifecycle):
    """在区域内撒种子，粒子顺着风场 field(lat, lon) -> (u, v) 漂流。

    field   接受 numpy 数组的函数，返回东向 u、北向 v，单位：度（大圆弧）/秒
    region  (lat_min, lat_max, lon_min, lon_max) 撒种子的范围（按面积均匀）
    life    每个粒子的寿命（秒），到期在新位置重生；tail 尾巴对应的时长（秒）
    steps   每帧积分步数（越大越精确，越慢）
    color   颜色，或 callable(speed) -> rgb 按风速上色
    """

    def __init__(self, field, region, n=600, life=4.0, tail=.6, K=10, steps=24, alt=.012, color='#cfe6ff', opacity=.85,
                 fade=(.12, .2), seed=11, width=3.0, blur=.5, head=True, head_alpha=.55, taper=1.3, glow=0.0, additive=False):
        self.field, self.region, self.life, self.tail, self.K, self.steps, self.alt = field, region, life, tail, K, steps, alt
        self.color, self.opacity, (self.fade_in, self.fade_out) = color, opacity, fade
        self.idx = np.arange(n); self.ph = _hash(self.idx, seed, 9)
        _style(self, width, blur, head, head_alpha, taper, glow, additive)

    def _deriv(self, s):
        u, v = self.field(s[:, 0], s[:, 1]); u = np.asarray(u, float) * np.ones(len(s)); v = np.asarray(v, float) * np.ones(len(s))
        return np.c_[v, u / np.maximum(np.cos(np.radians(s[:, 0])), 1e-3)]

    def streaks(self, t):
        n, age, fa = self._ages(t)
        la0, la1, lo0, lo1 = self.region
        s1, s2 = math.sin(math.radians(la0)), math.sin(math.radians(la1))
        lat = np.degrees(np.arcsin(s1 + (s2 - s1) * _hash(self.idx, n, 1))); lon = lo0 + (lo1 - lo0) * _hash(self.idx, n, 2)
        tr = _trail(self._deriv, np.c_[lat, lon], age, self.steps, self.tail, self.K)
        pos = llr(tr[..., 0], tr[..., 1], self.alt)
        if callable(self.color):
            u, v = self.field(tr[:, -1, 0], tr[:, -1, 1]); rgb = np.array([hexrgb(self.color(s)) for s in np.hypot(u, v) * np.ones(len(tr))])
        else:
            rgb = np.tile(hexrgb(self.color), (len(tr), 1))
        return pos, rgb, self.opacity * fa


# ------------------------------------------------------------------ 3) 台风 / 气旋螺旋
class Typhoon(_Lifecycle):
    """热带气旋：外围空气螺旋流入，在眼墙附近高速旋转，中心留出风眼。

    center  (lat, lon) 气旋中心；北半球逆时针、南半球顺时针（俯视），按纬度自动判断，也可用 spin=+1/-1 指定
    radius  外围半径（度）；rmax 最大风速半径（眼墙，度）；eye 风眼半径（度）
    inflow  外围流入角（度），20–30° 接近真实台风的螺旋臂
    vmax    眼墙处旋转速度（度/秒，示意）
    core_opacity 眼墙附近的亮度系数（粒子在那里最密，默认压到 0.5 免得糊成一个白圈）
    bands   螺旋雨带条数（粒子亮度沿对数螺旋调制），0 = 均匀；band_depth 调制深度 0..1
    """

    def __init__(self, center, radius=8.0, rmax=1.4, eye=.6, inflow=24.0, vmax=2.6, spin=None, n=560, life=4.5, tail=.8,
                 K=12, steps=28, alt=.014, color='#dfeaff', core_color='#f4f8ff', opacity=.72, bands=3, band_depth=.8, core_opacity=.4, fade=(.15, .25), seed=5,
                 width=3.0, blur=.5, head=True, head_alpha=.5, taper=1.3, glow=0.0, additive=False):
        self.lat0, self.lon0 = center
        self.spin = spin if spin is not None else (1.0 if self.lat0 >= 0 else -1.0)
        self.R, self.rm, self.eye, self.ta, self.vmax = radius, rmax, eye, math.tan(math.radians(inflow)), vmax
        self.life, self.tail, self.K, self.steps, self.alt = life, tail, K, steps, alt
        self.c_out, self.c_in, self.opacity, (self.fade_in, self.fade_out) = hexrgb(color), hexrgb(core_color), opacity, fade
        self.bands, self.band_depth, self.core_opacity = bands, band_depth, core_opacity
        self.idx = np.arange(n); self.ph = _hash(self.idx, seed, 9)
        _style(self, width, blur, head, head_alpha, taper, glow, additive)

    def _vt(self, r):
        """修正兰金涡：眼墙内线性增大，眼墙外按 r^-0.5 衰减"""
        return self.vmax * np.where(r < self.rm, r / self.rm, (self.rm / np.maximum(r, 1e-6)) ** .5)

    def _deriv(self, s):
        r = np.maximum(s[:, 0], 1e-4); vt = self._vt(r)
        inflow = self.ta * _sm(self.rm * .9, self.rm * 1.6, r)      # 眼墙外向内流入，到眼墙附近停下来绕圈
        return np.c_[-vt * inflow, self.spin * vt / r]

    def streaks(self, t):
        n, age, fa = self._ages(t)
        r0 = self.rm + (self.R - self.rm) * np.sqrt(_hash(self.idx, n, 1)); th0 = 2 * np.pi * _hash(self.idx, n, 2)
        tr = _trail(self._deriv, np.c_[r0, th0], age, self.steps, self.tail, self.K)
        r = np.maximum(tr[..., 0], self.eye); th = tr[..., 1]
        x, y = r * np.cos(th), r * np.sin(th)                       # 当地东、北（度）
        la = self.lat0 + y; lo = self.lon0 + x / np.cos(np.radians(la))
        pos = llr(la, lo, self.alt)
        k = _sm(self.rm * 3, self.rm, tr[:, -1, 0])[:, None]
        rgb = self.c_out * (1 - k) + self.c_in * k
        rh = tr[:, -1, 0]
        edge = 1 - _sm(.6 * self.R, self.R, rh)                     # 外缘淡出，不留硬边
        band = 1.0
        if self.bands:                                              # 螺旋雨带：沿 θ = ±ln(r)/tan(流入角) 的对数螺旋
            arm = th[:, -1] + self.spin * np.log(np.maximum(rh, 1e-3)) / max(self.ta, 1e-3)
            band = 1 - self.band_depth * (1 - np.cos(self.bands * arm) ** 2) * _sm(self.rm * 1.5, self.rm * 3, rh)
        core = 1 - (1 - self.core_opacity) * _sm(self.rm * 2.2, self.rm * 1.1, rh)   # 眼墙处粒子最密，压一点亮度
        return pos, rgb, self.opacity * fa * edge * band * core


# ------------------------------------------------------------------ 4) 垂直环流圈（哈德来 / 费雷尔……）
class VerticalLoops(Flow):
    """粒子在"纬度-高度"平面里绕圈：在 lat_rise 上升、高空流向 lat_sink、下沉、贴地流回。

    lat_rise, lat_sink  上升支、下沉支所在纬度（北半球取正值；hemis 决定画哪个半球）
    height, base        环流顶、底的离地高度（地球半径；示意值，真实对流层只有 ~0.002）
    squareness          环形的"方"程度，1 = 椭圆，越小越像圆角矩形（视频用 0.44）
    lon_clusters        [(中心经度, 标准差), ...] 粒子集中的经度；uniform_frac 均匀分布在全球的比例
    lon_drift           粒子每绕一圈向东漂移的经度（度）
    speed (lo,hi)       每秒绕的圈数；tail 尾长（占一圈的比例）
    colors              (上升暖色, 高空冷色, 回流色)，沿环自动渐变
    start               给出时间则粒子从上升支依次"放出"（片头逐渐充满的效果）；None = 一开始就铺满
    guide_alpha         沿环画几条很淡的宽引导带（0 = 不画），guide_lons 为其经度
    """

    def __init__(self, lat_rise=0.0, lat_sink=30.0, height=.19, base=.012, squareness=2 / 4.5, hemis=(1, -1),
                 lon_clusters=((-88, 16), (92, 16)), uniform_frac=1 / 3, lon_drift=6.0, lon_jitter=1.5, n=520,
                 speed=(.072, .088), tail=.05, K=9, colors=('#ff9b6e', '#86b8ff', '#d7e6ff'), opacity=.85,
                 start=None, spread=(0.0, 3.6), guide_alpha=0.0, guide_lons=(), seed=8,
                 width=3.6, blur=.4, head=True, head_alpha=.55, taper=1.3, glow=0.0, additive=False):
        r = np.random.default_rng(seed)
        nu = int(round(n * uniform_frac)); nc = n - nu; m = max(len(lon_clusters), 1)
        lons = [r.uniform(-180, 180, nu)]
        for j, (c, sd) in enumerate(lon_clusters):
            lons.append(r.normal(c, sd, nc // m + (1 if j < nc % m else 0)))
        self.lon = np.concatenate(lons)[:n]; n = len(self.lon)
        self.hemi = r.choice(np.asarray(hemis, float), n); self.v = r.uniform(*speed, n); self.jit = r.normal(0, 1, n)
        self.ph = r.uniform(0, 1, n); self.delay = r.uniform(*spread, n)
        self.a, self.b, self.height, self.base, self.sq = lat_rise, lat_sink, height, base, squareness
        self.lon_drift, self.lon_jitter, self.tail, self.K, self.opacity, self.start = lon_drift, lon_jitter, tail, K, opacity, start
        self.cols = [hexrgb(c) for c in colors]; self.guide_alpha, self.guide_lons = guide_alpha, guide_lons
        _style(self, width, blur, head, head_alpha, taper, glow, additive)

    def loop(self, s, hemi=1.0):
        """环上参数 s∈[0,1) → (纬度, 高度)。s=0 在上升支半高处，0.25 顶部，0.5 下沉支，0.75 底部。"""
        th = np.pi - 2 * np.pi * np.asarray(s, float); cc, ss = np.cos(th), np.sin(th); q = self.sq
        mid, half = .5 * (self.a + self.b), .5 * (self.b - self.a)
        half = half + .5 * np.sign(half)
        lat = mid + half * np.sign(cc) * np.abs(cc) ** q
        alt = self.base + self.height * (.5 + .5 * np.sign(ss) * np.abs(ss) ** q)
        return hemi * lat, alt

    def color(self, s):
        s = np.asarray(s, float)[..., None]; w, c, p = self.cols
        w1 = np.clip((s - .18) / .40, 0, 1); col = w * (1 - w1) + c * w1
        w2 = np.clip((s - .78) / .22, 0, 1); return col * (1 - w2) + (p * .5 + w * .5) * w2

    def streaks(self, t):
        if self.start is None:
            head = self.ph + t * self.v; ok = np.ones(len(head), bool); born = np.ones(len(head))
        else:
            age = t - self.start - self.delay; ok = age > 0; head = np.maximum(age, 0) * self.v; born = _sm(0, .03, head)
        pos = []; rgb = []; al = []
        for i in np.nonzero(ok)[0]:
            sh = head[i]; ss = np.clip(sh - np.linspace(self.tail, 0, self.K), 0, None)
            la, alt = self.loop(ss % 1, self.hemi[i])
            lo = self.lon[i] + ss * self.lon_drift + self.jit[i] * self.lon_jitter
            pos.append(llr(la, lo, alt + self.jit[i] * .004)); rgb.append(self.color(sh % 1)); al.append(self.opacity * born[i])
        if not pos: return np.zeros((0, self.K, 3)), np.zeros((0, 3)), np.zeros(0)
        return np.array(pos), np.array(rgb), np.array(al)

    def draw(self, canvas, cam, t, alpha=1.0):
        if self.guide_alpha > 0 and alpha > .01:
            ss = np.linspace(0, 1, 160)
            for lo0 in self.guide_lons:
                for hemi in set(self.hemi.tolist()):
                    la, alt = self.loop(ss, hemi); P = llr(la, lo0 + ss * self.lon_drift, alt)
                    x, y, _ = cam.project(P); v = visible(cam, P); col = self.color(ss)
                    for k in range(len(ss) - 1):
                        if not (v[k] and v[k + 1]): continue
                        c = col[k]; p = skia.Paint(AntiAlias=True, Color4f=skia.Color4f(c[0], c[1], c[2], self.guide_alpha * alpha),
                                                   StrokeWidth=9, Style=skia.Paint.kStroke_Style, StrokeCap=skia.Paint.kRound_Cap)
                        p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 4)); canvas.drawLine(x[k], y[k], x[k + 1], y[k + 1], p)
        super().draw(canvas, cam, t, alpha)
