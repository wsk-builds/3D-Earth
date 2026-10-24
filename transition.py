"""matched-view cross-dissolve（匹配视角交叉溶解）转场模板，与渲染器无关，只依赖 numpy。

A -> B（正向，"拉出"）或 B -> A（反向，"潜入"）。所有时间单位为秒（绝对时间轴）。
"""
from __future__ import annotations
from dataclasses import dataclass, replace
import numpy as np

# ---------------------------------------------------------------- easing
def clamp01(x): return float(min(1.0, max(0.0, x)))
def prog(t, t0, dur):                       # 0..1 线性进度
    return 1.0 if dur <= 0 else clamp01((t - t0) / dur)
def smoothstep(x): x = clamp01(x); return x * x * (3 - 2 * x)
def smootherstep(x): x = clamp01(x); return x * x * x * (x * (6 * x - 15) + 10)
def ease_in_out(x): x = clamp01(x); return 4 * x**3 if x < .5 else 1 - (-2 * x + 2)**3 / 2
def ease_in(x): return clamp01(x)**3
def ease_out(x): return 1 - (1 - clamp01(x))**3
EASINGS = dict(linear=clamp01, smoothstep=smoothstep, smootherstep=smootherstep,
               ease_in_out=ease_in_out, ease_in=ease_in, ease_out=ease_out)

# ---------------------------------------------------------------- camera
def _n(v):
    v = np.asarray(v, float); l = np.linalg.norm(v); return v / l if l > 1e-12 else v

@dataclass(frozen=True)
class Camera:
    eye: tuple = (0.0, 0.0, 5.0)
    target: tuple = (0.0, 0.0, 0.0)
    up: tuple = (0.0, 1.0, 0.0)
    fov: float = 40.0                         # 垂直视场角（度）；2D 渲染器可当作缩放
    def forward(self): return _n(np.subtract(self.target, self.eye))

def _slerp(a, b, t):
    a, b = _n(a), _n(b); d = float(np.clip(np.dot(a, b), -1, 1))
    if d > 0.9995: return _n(a + (b - a) * t)
    om = np.arccos(d); return _n((np.sin((1 - t) * om) * a + np.sin(t * om) * b) / np.sin(om))

def lerp_camera(a: Camera, b: Camera, t: float, slerp: bool = False) -> Camera:
    """插值相机。up 向量总是重新归一化（并与视线正交化），避免画面倾斜/翻转。
    slerp=True 时，视线方向按球面插值（大角度转向更自然），距离线性插值。"""
    t = clamp01(t)
    eye = np.add(np.multiply(a.eye, 1 - t), np.multiply(b.eye, t))
    if slerp:
        dist = (1 - t) * np.linalg.norm(np.subtract(a.target, a.eye)) + t * np.linalg.norm(np.subtract(b.target, b.eye))
        tgt = eye + _slerp(a.forward(), b.forward(), t) * dist
        up = _slerp(a.up, b.up, t)
    else:
        tgt = np.add(np.multiply(a.target, 1 - t), np.multiply(b.target, t))
        up = np.add(np.multiply(a.up, 1 - t), np.multiply(b.up, t))
    f = _n(tgt - eye); up = _n(np.asarray(up) - f * np.dot(up, f))   # 正交化
    return Camera(tuple(eye), tuple(tgt), tuple(up), (1 - t) * a.fov + t * b.fov)

def offset_camera(base: Camera, ref_from: Camera, ref_to: Camera, scale: float = 1.0) -> Camera:
    """把 ref_from->ref_to 的运动增量（平移、视场）按 scale 套到 base 上——
    让溶解期间 A 跟着 B 一起动（运动连续）。"""
    d_eye = np.subtract(ref_to.eye, ref_from.eye) * scale
    d_tgt = np.subtract(ref_to.target, ref_from.target) * scale
    return Camera(tuple(np.add(base.eye, d_eye)), tuple(np.add(base.target, d_tgt)), base.up,
                  base.fov + (ref_to.fov - ref_from.fov))

# ---------------------------------------------------------------- spec
@dataclass(frozen=True)
class TransitionSpec:
    """时间轴（cut = 交接中心时刻）：
        declutter: [cut - align - declutter_lead, ... + declutter]  A 的叠加层淡出
        align:     [cut - align, cut]                               A 相机缓动到 handoff_a
        overlap:   [cut - overlap/2, cut + overlap/2]               交叉溶解
        reveal:    [cut, cut + reveal]                              B 相机从 handoff_b 继续运动到 b_end
        b_overlay: 从 cut + b_overlay_delay 起 B 的叠加层淡入
    """
    cut: float
    cam_a_start: Camera            # A 在对齐开始时的相机
    handoff_a: Camera              # A 的交接视角
    handoff_b: Camera              # B 中与之匹配的视角
    cam_b_end: Camera              # B 揭示阶段结束的相机
    align: float = 2.6
    declutter: float = 0.8
    declutter_lead: float = 0.2    # 叠加层比相机对齐提前多少开始淡出
    overlap: float = 0.8
    reveal: float = 2.8
    b_overlay_delay: float = 0.6
    b_overlay_fade: float = 0.6
    align_ease: str = "ease_in_out"
    reveal_ease: str = "ease_out"  # 揭示阶段起步就有速度：避免"停在切点"
    dissolve_ease: str = "smoothstep"
    motion_scale: float = 1.0      # A/B 世界单位比例，用于溶解期间 A 跟随 B 的运动
    slerp: bool = False
    reverse: bool = False          # True: 叙事方向 B->A（潜入）；见 reversed_spec

    @property
    def t_align0(self): return self.cut - self.align
    @property
    def t_dec0(self): return self.t_align0 - self.declutter_lead
    @property
    def t_mix0(self): return self.cut - self.overlap / 2
    @property
    def t_mix1(self): return self.cut + self.overlap / 2
    @property
    def t_end(self): return self.cut + self.reveal

def reversed_spec(spec: TransitionSpec) -> TransitionSpec:
    """生成反向（潜入）转场：原来的 B 变为“出发场景”，原 A 变为“到达场景”。
    返回的 spec 中，'A' 指出发场景，因此调用 compose 时要把回调对调（compose 的 reverse 参数会自动处理）。"""
    return replace(spec, cam_a_start=spec.cam_b_end, handoff_a=spec.handoff_b,
                   handoff_b=spec.handoff_a, cam_b_end=spec.cam_a_start,
                   motion_scale=1.0 / spec.motion_scale, reverse=not spec.reverse)

# ---------------------------------------------------------------- per-time queries
def dissolve_weight(spec, t):
    """B 层权重（0=只有 A，1=只有 B）。"""
    return EASINGS[spec.dissolve_ease](prog(t, spec.t_mix0, spec.overlap))

def overlay_alpha_a(spec, t):
    return 1.0 - smoothstep(prog(t, spec.t_dec0, spec.declutter))

def overlay_alpha_b(spec, t):
    return smoothstep(prog(t, spec.cut + spec.b_overlay_delay, spec.b_overlay_fade))

def camera_b(spec, t):
    k = EASINGS[spec.reveal_ease](prog(t, spec.cut, spec.reveal))
    return lerp_camera(spec.handoff_b, spec.cam_b_end, k, spec.slerp)

def camera_a(spec, t):
    if t <= spec.cut:
        k = EASINGS[spec.align_ease](prog(t, spec.t_align0, spec.align))
        return lerp_camera(spec.cam_a_start, spec.handoff_a, k, spec.slerp)
    # 切点之后（溶解尾段）A 跟随 B 的运动，避免 A 层“定格”
    return offset_camera(spec.handoff_a, spec.handoff_b, camera_b(spec, t), spec.motion_scale)

def active(spec, t):
    """哪一层需要渲染：('a',) / ('b',) / ('a','b')"""
    if t < spec.t_mix0: return ("a",)
    if t > spec.t_mix1: return ("b",)
    return ("a", "b")

# ---------------------------------------------------------------- compose
def compose(spec, t, render_a, render_b, post=None):
    """render_x(t, cam: Camera, overlay_alpha: float) -> HxWx(3|4) float32 [0,1] 或 uint8。
    reverse=True 的 spec（来自 reversed_spec）表示：出发层用 render_b，到达层用 render_a。
    post(img, t) -> img：在合成之后统一施加（bloom/暗角/调色/颗粒），保证两层“同一套底片”。"""
    src, dst = (render_b, render_a) if spec.reverse else (render_a, render_b)
    def f(img):
        img = np.asarray(img)
        return img.astype(np.float32) / 255.0 if img.dtype == np.uint8 else img.astype(np.float32)
    w = dissolve_weight(spec, t); layers = active(spec, t)
    A = f(src(t, camera_a(spec, t), overlay_alpha_a(spec, t))) if "a" in layers else None
    B = f(dst(t, camera_b(spec, t), overlay_alpha_b(spec, t))) if "b" in layers else None
    out = A if B is None else B if A is None else A * (1 - w) + B * w
    return post(out, t) if post else out
