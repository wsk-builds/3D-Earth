"""8 采样 vs 4 采样对比（SPEC §11.4）：细线、雨、浪花、粒子、快速运动的镜头，改用 4 采样前先跑一次。
先用 render_anim.py 把同一段帧分别渲成 8 采样和 4 采样，再比：
  python3 render_anim.py scenes/anim_xxx.py --frames 1-60 --samples 8 --out out/anim/xxx_s8
  python3 render_anim.py scenes/anim_xxx.py --frames 1-60 --samples 4 --out out/anim/xxx_s4
  python3 compare_samples.py out/anim/xxx_s8 out/anim/xxx_s4 [--mp4] [--crop x,y,w,h]
指标：
  diff16   每帧 |4-8| > 16 级的像素占比（均值 / 最大）
  flicker  4 采样相对 8 采样「多出来的闪」：r_t = 亮度(4) - 亮度(8)，在描边像素上取 |r_t - r_{t-1}| 的均值（单位：0–255 级）
  motion   参考量：8 采样本身描边像素的帧间变化（镜头运动造成），flicker 要远小于它
判定（沙盘基准：diff16 0.07%，flicker 0.33，motion 11.5）：diff16 最大 < 0.2% 且 flicker < 1.0 → 可用 4 采样；否则保持 8。【推断】阈值 ≈ 沙盘实测值 × 3
--mp4 输出左右对比 compare_8v4.mp4（左 8 右 4）；--crop 再出一段 3 倍放大的局部对比 compare_8v4_zoom.mp4。返回码：0 可用 4 采样，1 不建议。"""
import os, sys, re, json, shutil, subprocess
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

def lum(p): return np.asarray(Image.open(p).convert('RGB'), np.float32) @ np.array([.2126, .7152, .0722], np.float32)

def main(a):
    if len(a) < 2 or '-h' in a: print(__doc__); return 2
    d8, d4 = a[0], a[1]
    frames = lambda d: {f for f in os.listdir(d) if re.fullmatch(r'\d+\.png', f)}
    names = sorted(frames(d8) & frames(d4))
    if len(names) < 3: print('两个目录里共同的成品帧少于 3 张'); return 2
    diff16, flick, motion, prev_r, prev8 = [], [], [], None, None
    for n in names:
        l8, l4 = lum(f'{d8}/{n}'), lum(f'{d4}/{n}'); r = l4 - l8
        g = np.hypot(ndi.sobel(l8, 0), ndi.sobel(l8, 1)); m = ndi.binary_dilation(g > 120)   # 描边 / 强边缘像素
        rgb = np.abs(np.asarray(Image.open(f'{d8}/{n}').convert('RGB'), np.int16) - np.asarray(Image.open(f'{d4}/{n}').convert('RGB'), np.int16)).max(-1)
        diff16.append(100*(rgb > 16).mean())
        if prev_r is not None: flick.append(float(np.abs(r - prev_r)[m].mean())); motion.append(float(np.abs(l8 - prev8)[m].mean()))
        prev_r, prev8 = r, l8
    res = dict(frames=len(names), diff16_mean=float(np.mean(diff16)), diff16_max=float(np.max(diff16)),
               flicker_mean=float(np.mean(flick)), flicker_max=float(np.max(flick)), motion_mean=float(np.mean(motion)))
    ok = res['diff16_max'] < .2 and res['flicker_mean'] < 1.0; res['verdict'] = '可用 4 采样' if ok else '保持 8 采样'
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if '--mp4' in a:
        ff = shutil.which('ffmpeg'); first = int(names[0][:-4]); dg = len(names[0]) - 4; out = os.path.dirname(os.path.abspath(d4))
        src = ['-start_number', str(first), '-i', f'{d8}/%0{dg}d.png', '-start_number', str(first), '-i', f'{d4}/%0{dg}d.png']
        enc = ['-frames:v', str(len(names)), '-c:v', 'libx264', '-crf', '17', '-preset', 'slow', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an']
        lab = lambda t: f"drawtext=text='{t}':x=24:y=24:fontsize=48:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=10"
        subprocess.run([ff, '-y', '-loglevel', 'error', '-framerate', '30'] + src[:4] + ['-framerate', '30'] + src[4:] +
                       ['-filter_complex', f"[0]{lab('8 samples')}[l];[1]{lab('4 samples')}[r];[l][r]hstack,scale=trunc(iw/4)*2:-2"] + enc + [f'{out}/compare_8v4.mp4'], check=True)
        print('MP4：', f'{out}/compare_8v4.mp4')
        if '--crop' in a:
            x, y, w, h = map(int, a[a.index('--crop')+1].split(','))
            c = f'crop={w}:{h}:{x}:{y},scale={3*w}:{3*h}:flags=neighbor'
            subprocess.run([ff, '-y', '-loglevel', 'error', '-framerate', '30'] + src[:4] + ['-framerate', '30'] + src[4:] +
                           ['-filter_complex', f"[0]{c},{lab('8 samples x3')}[l];[1]{c},{lab('4 samples x3')}[r];[l][r]hstack,scale=trunc(iw/2)*2:trunc(ih/2)*2"] + enc + [f'{out}/compare_8v4_zoom.mp4'], check=True)
            print('MP4：', f'{out}/compare_8v4_zoom.mp4')
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
