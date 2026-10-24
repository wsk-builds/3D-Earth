import numpy as np, math
from glcore import Pass, load_tex, load_tex_array, CAMGLSL
from textures import earth_rgba, cloud_path
FS = """#version 330
in vec2 uv; out vec4 fragColor;
""" + CAMGLSL + """
uniform sampler2D earth; uniform sampler2D clouds;
uniform vec3 sun_dir; uniform float t, cloud_a, night, atmo, exposure, star_a, land_dim, grid_a, green, lake_a, rain_a, rain_lat, spin, desert_a;
const float PI=3.14159265;
float dlon(float a, float b){ float d=a-b; return mod(d+540.,360.)-180.; }
vec3 stars(vec3 rd){
  vec3 c=vec3(0.); vec3 p = rd*300.; vec3 i=floor(p); float h=hash13(i);
  if(h>.996){ vec3 f=fract(p)-.5; float d=length(f); c += vec3(.8,.85,1.)*smoothstep(.25,.0,d)*(h-.996)*250.; }
  return c*star_a;
}
void main(){
  vec2 fc = gl_FragCoord.xy; vec3 ro = cam_eye, rd = ray_dir(fc);
  vec3 col = vec3(0.004,0.006,0.014) + stars(rd);
  float b = dot(ro, rd); float c = dot(ro,ro)-1.; float disc = b*b-c;
  float tca = -b; vec3 pc = ro+rd*max(tca,0.); float dmin = length(pc);
  // atmosphere halo
  float halo = 0.;
  if(disc>0. && -b-sqrt(disc)>0.){
    float tt = -b-sqrt(disc); vec3 p = ro+rd*tt; vec3 n = normalize(p);
    float lat = degrees(asin(clamp(p.y,-1.,1.))), lon = dlon(degrees(atan(p.x,p.z)) - spin, 0.);
    vec2 tuv = vec2((lon+180.)/360., (90.-lat)/180.);
    vec4 e = texture(earth, tuv);
    float land = e.a;
    vec3 alb = pow(e.rgb, vec3(2.2));
    // bump from luminance
    vec2 dt = vec2(1./5400., 1./2700.);
    float l0 = dot(texture(earth,tuv).rgb, vec3(.33)), lx = dot(texture(earth,tuv+vec2(dt.x,0)).rgb,vec3(.33)), ly=dot(texture(earth,tuv+vec2(0,dt.y)).rgb,vec3(.33));
    vec3 east = normalize(cross(vec3(0,1,0), n)+1e-5), north = cross(n, east);
    vec3 nb = normalize(n - land*1.6*((lx-l0)*east - (ly-l0)*north));
    float ndl = dot(nb, sun_dir);
    float diff = smoothstep(-.12, .35, ndl)*clamp(ndl*.7+.45,0.,1.);
    // ocean
    vec3 ocean = alb*vec3(.85,.95,1.1);
    // ---- green Sahara (schematic)
    float nz = fbm3(vec3(lon*.18, lat*.18, 3.1)); float nz2 = fbm3(vec3(lon*.9, lat*.9, 7.7));
    float ej = (nz-.5)*10.;
    float lonw = smoothstep(-19.,-14.,lon)*(1.-smoothstep(25.,37.,lon+ej));
    float latw = smoothstep(6.,12.,lat+ej*.4)*(1.-smoothstep(22.,31.5,lat+ej*.5));
    float reg = lonw*latw*land;
    float gw = clamp(green*(1.25 - .45*smoothstep(18.,31.,lat) + (nz-.5)*.9), 0., 1.)*reg;
    vec3 grass = mix(vec3(.36,.36,.16), vec3(.14,.25,.08), smoothstep(.3,.75,nz2));
    grass = mix(grass, vec3(.45,.40,.20), smoothstep(21.,29.,lat)*.6);
    grass = mix(grass, vec3(.07,.17,.05), smoothstep(16.,9.,lat)*.7);
    float rough = clamp((l0-.55)*3.,0.,1.);            // keep bright rocky massifs partly visible
    vec3 albg = mix(pow(grass,vec3(2.2)), alb, rough*.35);
    alb = mix(alb, albg, gw);
    alb = mix(alb, alb*vec3(1.08,1.0,.9), desert_a*reg);
    // lakes
    float lk = 0.;
    { vec2 q = vec2((lon-16.5)/4.3, (lat-15.0)/3.1); float d = length(q) + (nz-.5)*.45; lk = max(lk, 1.-smoothstep(.92,1.0,d)); }
    { vec2 q = vec2((lon-13.0)/1.4, (lat-26.3)/1.0); float d = length(q) + (nz2-.5)*.5; lk = max(lk, (1.-smoothstep(.9,1.0,d))*.95); }
    { vec2 q = vec2((lon-27.5)/1.2, (lat-19.0)/1.0); float d = length(q) + (nz2-.5)*.5; lk = max(lk, (1.-smoothstep(.9,1.0,d))*.95); }
    { vec2 q = vec2((lon+4.5)/1.3, (lat-21.5)/0.9); float d = length(q) + (nz2-.5)*.5; lk = max(lk, (1.-smoothstep(.9,1.0,d))*.95); }
    lk *= lake_a*land;
    alb = mix(alb, vec3(.010,.035,.06), lk);
    land *= 1.-lk;
    vec3 surf = mix(ocean, alb*land_dim, land) ;
    surf = mix(surf, vec3(.010,.035,.06), lk);
    // grid lines (lat/lon)
    float grd = 0.;
    { float g1 = abs(fract(lat/10.+.5)-.5)*10., g2 = abs(fract(lon/10.+.5)-.5)*10.; float w = .07;
      grd = max(1.-smoothstep(0.,w,g1), 1.-smoothstep(0.,w,g2)); if(abs(lat)<0.12) grd=1.; }
    vec3 lit = surf*(diff*vec3(1.0,.97,.92)*1.25 + vec3(.010,.014,.03)*night);
    // specular on ocean
    vec3 h = normalize(sun_dir - rd); float nh = max(dot(n,h),0.); float sp = (pow(nh, 600.)*1.2 + pow(nh,40.)*.05)*(1.-land)*smoothstep(0.,.2,ndl);
    lit += vec3(1.,.9,.75)*sp;
    // clouds
    float ca = 0.;
    if(cloud_a>0.){
      vec2 cuv = tuv + vec2(t*.0015,0.);
      float cv = texture(clouds, cuv).r; ca = pow(smoothstep(.04,.95,cv),.9)*cloud_a*.92;
      vec2 shuv = cuv - vec2(sun_dir.x, sun_dir.y)*.0015; float sh = smoothstep(.12,.85,texture(clouds, shuv).r)*cloud_a;
      lit *= 1.-.45*sh*diff;
      vec3 cc = vec3(1.)*(smoothstep(-.1,.4,ndl)*1.1+.02);
      // monsoon rain band (schematic)
      float rb = exp(-pow((lat-rain_lat)/4.5,2.))*smoothstep(-30.,-18.,lon)*(1.-smoothstep(38.,46.,lon));
      float rn = fbm3(vec3(lon*.25 - t*.25, lat*.35, t*.05));
      float rca = rb*smoothstep(.42,.72,rn)*rain_a;
      ca = max(ca, rca*.95);
      lit = mix(lit, cc, ca);
    }
    lit += vec3(.9,.95,1.)*grd*grid_a*(.25+.6*diff);
        // atmosphere rim on disc
    float mu = max(dot(n,-rd),0.);
    float rim = pow(1.-mu, 2.6);
    float sunf = smoothstep(-.25, .5, dot(n,sun_dir));
    lit = mix(lit, vec3(.30,.55,1.0)*sunf*1.1, rim*.55*atmo);
    col = lit;
  } else {
    float hgt = dmin-1.;
    if(tca>0.){ halo = exp(-max(hgt,0.)/0.022)*atmo; vec3 n = normalize(pc);
      float sunf = smoothstep(-.35, .4, dot(n,sun_dir));
      col += vec3(.25,.5,1.0)*halo*sunf*1.25 + vec3(.6,.35,.2)*halo*pow(1.-abs(dot(n,sun_dir)),8.)*.3*sunf; }
  }
  col *= exposure;
  col = aces(col);
  col = pow(col, vec3(1./2.2));
  col += (hash12(fc+fract(t)*91.)-.5)/255.;
  fragColor = vec4(col,1.);
}
"""
class Globe:
    def __init__(self, ss=1.0):
        self.p = Pass(FS, ss)
        # 贴图默认放在本模块旁边的 tex/ 目录；可用环境变量 EARTH_TEX_DIR 覆盖
        self.p.tex['earth'] = load_tex_array(earth_rgba())      # RGB = 卫星影像，A = 陆地掩膜
        self.p.tex['clouds'] = load_tex(cloud_path())
    def render(self, cam, t=0.0, sun=(0.6, 0.3, 0.75), cloud_a=1.0, night=1.0, atmo=1.0, exposure=1.0, star_a=1.0, land_dim=1.0, grid_a=0.0,
               green=0.0, lake_a=0.0, rain_a=0.0, rain_lat=10.0, spin=0.0, desert_a=0.0):
        s = np.array(sun, float); s /= np.linalg.norm(s)
        return self.p.render(sun_dir=tuple(s), t=t, cloud_a=cloud_a, night=night, atmo=atmo, exposure=exposure, star_a=star_a, land_dim=land_dim,
                             grid_a=grid_a, green=green, lake_a=lake_a, rain_a=rain_a, rain_lat=rain_lat, spin=spin, desert_a=desert_a, **cam.uniforms())
