"""示例：用 wind.py 在 3D 地球上画季风、哈德来环流和台风。

    python example_wind.py                    # out/wind_monsoon.png, wind_hadley.png, wind_typhoon.png, wind_field.png
    python example_wind.py --video            # 另外输出 4 秒的 out/wind_<场景>.mp4（需要 ffmpeg）
    python example_wind.py --ss 0.5 --only typhoon   # 半分辨率、只渲染一个场景
"""
import argparse, os, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
from globe import Globe
from cam import Cam, sph
import wind


def look(lat, lon, dist, tlat=None, tlon=None, tk=0.0, fov=35):
    """环绕相机：在 (lat, lon) 上空 dist 个地球半径处，看向地心（tk>0 时注视点向地表某点偏移）"""
    tgt = np.zeros(3) if tlat is None else sph(tlat, tlon) * tk
    return Cam(tuple(sph(lat, lon, dist)), tuple(tgt), fov)


def scene_monsoon():
    """夏季风：印度洋西南季风 + 太平洋东南季风，把暖湿水汽送进东亚（视频 1:30 左右的镜头）"""
    indian = [(-12, 52), (-2, 49), (8, 56), (13, 68), (15, 80), (17, 89), (21, 97), (25, 106), (29, 113), (31, 119), (32, 126)]
    pacific = [(14, 152), (16, 140), (18, 128), (20, 119), (24, 114), (28, 115), (31, 119), (32.5, 126)]
    flow = wind.PathFlow([indian, pacific], weights=[.58, .42], colors=['#9fd0ff', '#b9e6ff'])
    cam = look(14.3, 100.5, 2.32, 31.5, 89, .48)
    return cam, dict(sun=tuple(sph(21, 107)), cloud_a=.16), [flow]


def scene_hadley():
    """哈德来环流：赤道上升、高空流向两极、在南北纬 30° 附近下沉、贴地流回（视频 0:25 左右的镜头）"""
    clon = 18.0
    loops = wind.VerticalLoops(lat_rise=0, lat_sink=30, lon_clusters=((clon - 106, 16), (clon + 74, 16)),
                               guide_alpha=.22, guide_lons=(clon - 96, clon - 80, clon + 80, clon + 96))
    cam = look(5.0, clon, 3.45)
    return cam, dict(sun=tuple(sph(3, clon + 28)), cloud_a=.16), [loops]


def scene_typhoon():
    """台湾以东洋面上的一个台风：北半球逆时针螺旋流入，中心留出风眼"""
    ty = wind.Typhoon(center=(22.5, 128.0), radius=8.0, rmax=1.3, eye=.55)
    cam = look(17.0, 123.0, 2.05, 22.5, 128.0, .5)
    return cam, dict(sun=tuple(sph(46, 104)), cloud_a=.12), [ty]


def scene_field():
    """风场模式：一个示意的行星风带 —— 0–30° 信风（东风、偏向赤道），30–60° 西风（偏向极地）"""
    def planetary(lat, lon):
        a = np.radians(np.abs(lat))
        u = -5.0 * np.sin(6 * a) - 1.5 * np.exp(-(lat / 12.0) ** 2)   # 0–30° 东风（信风），30–60° 西风，60° 以上东风
        v = -1.6 * np.sign(lat) * np.sin(6 * a)                       # 信风吹向赤道，西风带偏向极地
        return u, v
    ff = wind.FieldFlow(planetary, region=(-62, 62, -90, 40), n=700, life=5.0, tail=1.0,
                        color=lambda s: (.62 + .2 * min(s / 5, 1), .8 + .12 * min(s / 5, 1), 1.0))
    cam = look(12.0, -30.0, 2.9)
    return cam, dict(sun=tuple(sph(30, 40)), cloud_a=.16), [ff]


SCENES = dict(monsoon=scene_monsoon, hadley=scene_hadley, typhoon=scene_typhoon, field=scene_field)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='out')
    ap.add_argument('--ss', type=float, default=1.0)
    ap.add_argument('--t', type=float, default=6.0, help='静帧对应的时间（秒）')
    ap.add_argument('--only', choices=list(SCENES), default=None)
    ap.add_argument('--video', action='store_true')
    ap.add_argument('--seconds', type=float, default=4.0)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    g = Globe(a.ss)
    for name, fn in SCENES.items():
        if a.only and name != a.only: continue
        cam, gkw, layers = fn()
        base = g.render(cam, t=a.t, **gkw)
        img = wind.composite(base, cam, layers, t=a.t)
        p = os.path.join(a.out, f'wind_{name}.png'); Image.fromarray(img[:, :, :3]).save(p); print('写出', p)
        if a.video and shutil.which('ffmpeg'):
            fdir = os.path.join(a.out, f'wind_{name}_frames'); os.makedirs(fdir, exist_ok=True)
            nf = int(a.seconds * 30)
            for i in range(nf):
                t = a.t + i / 30                       # 地球和相机不动时可只渲染一次底图；这里每帧重渲让云层也动
                img = wind.composite(g.render(cam, t=t, **gkw), cam, layers, t=t)
                Image.fromarray(img[:, :, :3]).save(os.path.join(fdir, f'{i:04d}.png'))
            mp4 = os.path.join(a.out, f'wind_{name}.mp4')
            subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '30', '-i', os.path.join(fdir, '%04d.png'), '-c:v', 'libx264',
                            '-profile:v', 'main', '-pix_fmt', 'yuv420p', '-crf', '18', '-movflags', '+faststart', mp4], check=True)
            print('写出', mp4)


if __name__ == '__main__':
    main()
