import moderngl, numpy as np, os
from PIL import Image
from cam import W, H
_ctx = None
def ctx():
    global _ctx
    if _ctx is None: _ctx = moderngl.create_standalone_context(require=330)
    return _ctx
VS = """#version 330
in vec2 in_pos; out vec2 uv;
void main(){ uv = in_pos*0.5+0.5; gl_Position = vec4(in_pos,0,1); }"""
CAMGLSL = """
uniform vec3 cam_eye, cam_f, cam_r, cam_u; uniform float cam_th; uniform vec2 res;
vec3 ray_dir(vec2 fc){ vec2 p = (fc - 0.5*res)/(0.5*res.y); return normalize(cam_f + cam_th*(p.x*cam_r + p.y*cam_u)); }
float hash12(vec2 p){ vec3 p3 = fract(vec3(p.xyx)*.1031); p3 += dot(p3, p3.yzx+33.33); return fract((p3.x+p3.y)*p3.z); }
float hash13(vec3 p3){ p3 = fract(p3*.1031); p3 += dot(p3, p3.zyx+31.32); return fract((p3.x+p3.y)*p3.z); }
float vnoise3(vec3 p){ vec3 i=floor(p), f=fract(p); f=f*f*(3.-2.*f);
  return mix(mix(mix(hash13(i),hash13(i+vec3(1,0,0)),f.x),mix(hash13(i+vec3(0,1,0)),hash13(i+vec3(1,1,0)),f.x),f.y),
             mix(mix(hash13(i+vec3(0,0,1)),hash13(i+vec3(1,0,1)),f.x),mix(hash13(i+vec3(0,1,1)),hash13(i+vec3(1,1,1)),f.x),f.y),f.z); }
float fbm3(vec3 p){ float a=.5, s=0.; for(int i=0;i<5;i++){ s+=a*vnoise3(p); p=p*2.03+vec3(1.7,9.2,3.1); a*=.5;} return s; }
vec3 sst_pal(float t){ // t in 0..1 : deep blue -> cyan -> yellow -> orange -> red
  vec3 c0=vec3(.05,.12,.45), c1=vec3(.10,.55,.85), c2=vec3(.55,.85,.75), c3=vec3(.98,.85,.35), c4=vec3(.97,.45,.12), c5=vec3(.80,.08,.10);
  t=clamp(t,0.,1.)*5.;
  if(t<1.) return mix(c0,c1,t); if(t<2.) return mix(c1,c2,t-1.); if(t<3.) return mix(c2,c3,t-2.); if(t<4.) return mix(c3,c4,t-3.); return mix(c4,c5,t-4.); }
vec3 aces(vec3 x){ return clamp((x*(2.51*x+.03))/(x*(2.43*x+.59)+.14),0.,1.); }
"""
class Pass:
    def __init__(self, fs, ss=1.0):
        c = ctx(); self.prog = c.program(vertex_shader=VS, fragment_shader=fs)
        q = np.array([-1, -1, 1, -1, -1, 1, 1, 1], 'f4'); self.vbo = c.buffer(q.tobytes())
        self.vao = c.vertex_array(self.prog, [(self.vbo, '2f', 'in_pos')])
        self.w, self.h = int(W*ss), int(H*ss)
        self.fbo = c.framebuffer(color_attachments=[c.texture((self.w, self.h), 4, dtype='f1')])
        self.tex = {}
    def set(self, **u):
        for k, v in u.items():
            if k in self.prog:
                try: self.prog[k].value = v
                except Exception: self.prog[k].write(np.asarray(v, 'f4').tobytes())
    def bind_tex(self, name, tex, unit):
        if name in self.prog: self.prog[name].value = unit; tex.use(unit)
    def render(self, **u):
        self.fbo.use(); self.set(res=(float(self.w), float(self.h)), **u)
        for i, (n, t) in enumerate(self.tex.items()): self.bind_tex(n, t, i)
        self.vao.render(moderngl.TRIANGLE_STRIP)
        a = np.frombuffer(self.fbo.read(components=4), np.uint8).reshape(self.h, self.w, 4)[::-1]
        return a
def load_tex(path, mip=True, repeat_x=True):
    im = Image.open(path); im = im.convert('RGBA'); a = np.asarray(im)
    t = ctx().texture(im.size, 4, a.tobytes())
    if mip: t.build_mipmaps(); t.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR); t.anisotropy = 8.0
    t.repeat_x = repeat_x; t.repeat_y = False
    return t
def load_tex_array(a, mip=True, repeat_x=True):
    """从 HxWx4 uint8 数组创建贴图（与 load_tex 相同的采样设置）。"""
    a = np.ascontiguousarray(a, dtype=np.uint8); h, w = a.shape[:2]
    t = ctx().texture((w, h), 4, a.tobytes())
    if mip: t.build_mipmaps(); t.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR); t.anisotropy = 8.0
    t.repeat_x = repeat_x; t.repeat_y = False
    return t
def data_tex(arr, comps=4):
    arr = np.ascontiguousarray(arr.astype('f4')); h, w = arr.shape[:2]
    t = ctx().texture((w, h), comps, arr.tobytes(), dtype='f4'); t.filter = (moderngl.LINEAR, moderngl.LINEAR); t.repeat_x = False; t.repeat_y = False
    return t
