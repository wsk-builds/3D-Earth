import numpy as np, math, os
# 画幅：默认 1920x1080，可在 import 之前用环境变量 EARTH_W / EARTH_H 修改（例如竖版 1080x1920）
W, H = int(os.environ.get('EARTH_W', 1920)), int(os.environ.get('EARTH_H', 1080))
def norm(v): v = np.asarray(v, float); return v/np.linalg.norm(v)
def look_at(eye, tgt, up=(0, 1, 0)):
    eye = np.asarray(eye, float); f = norm(np.asarray(tgt, float)-eye); r = norm(np.cross(f, up)); u = np.cross(r, f)
    return eye, f, r, u
class Cam:
    def __init__(self, eye, tgt, fov=35.0, up=(0, 1, 0)):
        self.eye, self.f, self.r, self.u = look_at(eye, tgt, up); self.fov = fov
        self.th = math.tan(math.radians(fov)/2)
    def project(self, p):
        """world point(s) -> screen x,y, depth (z along view). p shape (...,3)"""
        p = np.asarray(p, float); d = p-self.eye
        z = d@self.f; x = d@self.r; y = d@self.u
        sx = W/2 + (x/(z*self.th))*(H/2); sy = H/2 - (y/(z*self.th))*(H/2)
        return sx, sy, z
    def uniforms(self):
        return dict(cam_eye=tuple(self.eye), cam_f=tuple(self.f), cam_r=tuple(self.r), cam_u=tuple(self.u), cam_th=self.th)
def sph(lat, lon, r=1.0):
    la, lo = math.radians(lat), math.radians(lon)
    return np.array([r*math.cos(la)*math.sin(lo), r*math.sin(la), r*math.cos(la)*math.cos(lo)])
