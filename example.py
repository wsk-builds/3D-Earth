"""示例：渲染一张静帧 + 一段短环绕镜头。

    python example.py                 # 输出 out/still.png 和 out/orbit.mp4（无 ffmpeg 时输出 out/orbit.gif）
    python example.py --frames 48     # 环绕帧数
    python example.py --ss 0.5        # 渲染缩放（0.5 = 960x540，快速预览）
"""
import argparse, math, os, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
from globe import Globe
from cam import Cam, sph


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='out')
    ap.add_argument('--ss', type=float, default=1.0, help='渲染分辨率缩放（相对 cam.W x cam.H）')
    ap.add_argument('--frames', type=int, default=72, help='环绕镜头帧数（30fps）')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    g = Globe(a.ss)
    sun = sph(25, 40)                       # 太阳方向：纬度 25°、经度 40° 的上空

    # 1) 静帧：从北纬 20°、东经 15° 上空 2.6 个地球半径处看向地心（非洲—欧洲）
    cam = Cam(tuple(sph(20, 15, 2.6)), (0, 0, 0), fov=35)
    img = g.render(cam, t=0.0, sun=tuple(sun), cloud_a=0.8)
    Image.fromarray(img[:, :, :3]).save(os.path.join(a.out, 'still.png'))
    print('写出', os.path.join(a.out, 'still.png'))

    # 2) 短环绕：相机经度从 -10° 平滑转到 40°，同时略微推近
    fdir = os.path.join(a.out, 'orbit_frames'); os.makedirs(fdir, exist_ok=True)
    for i in range(a.frames):
        k = i / max(a.frames - 1, 1)
        e = 0.5 - 0.5 * math.cos(math.pi * k)          # 缓入缓出
        lon, dist = -10 + 50 * e, 2.9 - 0.3 * e
        cam = Cam(tuple(sph(18, lon, dist)), (0, 0, 0), fov=35)
        img = g.render(cam, t=i / 30, sun=tuple(sun), cloud_a=0.8)
        Image.fromarray(img[:, :, :3]).save(os.path.join(fdir, f'{i:04d}.png'))
    if shutil.which('ffmpeg'):
        mp4 = os.path.join(a.out, 'orbit.mp4')
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '30', '-i', os.path.join(fdir, '%04d.png'),
                        '-c:v', 'libx264', '-profile:v', 'main', '-pix_fmt', 'yuv420p', '-crf', '18', '-movflags', '+faststart', mp4], check=True)
        print('写出', mp4)
    else:
        frames = [Image.open(os.path.join(fdir, f'{i:04d}.png')).resize((640, 360)) for i in range(a.frames)]
        gif = os.path.join(a.out, 'orbit.gif')
        frames[0].save(gif, save_all=True, append_images=frames[1:], duration=33, loop=0)
        print('未找到 ffmpeg，写出', gif)


if __name__ == '__main__':
    main()
