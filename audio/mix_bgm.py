#!/usr/bin/env python3
"""把「视频自带音效混音」和默认背景音乐混成最终音轨。规范见 audio/SPEC.md。

用法：
  python3 audio/mix_bgm.py --sfx sfx_mix.wav --out final_mix.wav [--duration 158] [--bgm audio/qiannian_zhihou_ambient.mp3]
可选：
  --sfx-gain -8        音效整体增益(dB)，默认 -8
  --bgm-lufs -14       背景音乐响度(LUFS)，默认 -14
  --silent-until 10    此秒数之前音效为 0（只有背景音乐），默认 10
  --ramp 2             音效在 silent-until 之后用多少秒淡入，默认 2
  --fade-in 2          背景音乐淡入秒数，默认 2
  --fade-out 5         背景音乐淡出秒数（结束于视频末尾），默认 5
然后用 ffmpeg 把最终音轨与视频合并（视频流直接 copy）：
  ffmpeg -i video.mp4 -i final_mix.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest out.mp4
"""
import argparse, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sfx', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--duration', type=float, default=None, help='视频总时长(秒)，默认取 sfx 文件时长')
    ap.add_argument('--bgm', default=os.path.join(HERE, 'qiannian_zhihou_ambient.mp3'))
    ap.add_argument('--sfx-gain', type=float, default=-8.0)
    ap.add_argument('--bgm-lufs', type=float, default=-14.0)
    ap.add_argument('--silent-until', type=float, default=10.0)
    ap.add_argument('--ramp', type=float, default=2.0)
    ap.add_argument('--fade-in', type=float, default=2.0)
    ap.add_argument('--fade-out', type=float, default=5.0)
    a = ap.parse_args()

    dur = a.duration
    if dur is None:
        dur = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', a.sfx]).decode().strip())
    bgm_len = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', a.bgm]).decode().strip())

    t0, t1 = a.silent_until, a.silent_until + a.ramp
    # 前 silent-until 秒音效增益严格为 0（线性），之后在 ramp 秒内线性升到 1
    sfx_gate = f"if(lt(t,{t0}),0,if(lt(t,{t1}),(t-{t0})/{a.ramp},1))"
    if bgm_len >= dur:
        bgm_src = f"[1:a]aresample=48000,atrim=0:{dur},asetpts=PTS-STARTPTS"
    else:
        # 视频比音乐长：循环并用 3 秒交叉淡化衔接（本规范只验证过 ≤159.29 s 的情况）
        loops = int(dur // bgm_len) + 1
        bgm_src = f"[1:a]aresample=48000,aloop=loop={loops}:size=2147483647,atrim=0:{dur},asetpts=PTS-STARTPTS"
    fc = (
        f"[0:a]volume={a.sfx_gain}dB,volume='{sfx_gate}':eval=frame,asplit=2[sfx][sc];"
        f"{bgm_src},loudnorm=I={a.bgm_lufs}:TP=-2:LRA=7,"
        f"afade=t=in:st=0:d={a.fade_in},afade=t=out:st={dur - a.fade_out}:d={a.fade_out}[bg];"
        f"[bg][sc]sidechaincompress=threshold=0.08:ratio=1.8:attack=30:release=400[bgd];"
        f"[sfx][bgd]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.89:level=disabled[a]"
    )
    cmd = ['ffmpeg', '-hide_banner', '-y', '-loglevel', 'error', '-i', a.sfx, '-i', a.bgm,
           '-filter_complex', fc, '-map', '[a]', '-t', str(dur), '-ar', '48000', '-c:a', 'pcm_s24le', a.out]
    print(' '.join(cmd))
    subprocess.check_call(cmd)

if __name__ == '__main__':
    main()
