"""插画动画渲染器（SPEC §11）：一个镜头一次命令，四条提速全开。
  1 每个 Blender 进程只搭一次场景、连续渲一段帧；2 默认 4 采样；3 纸纹多进程批处理，check_frame 只测首/中/尾三帧；
  4 N 个 Blender 进程并行，各渲一段帧。可断点续渲：已完成的帧跳过，所有文件原子写入。

用法（纯 Python 3，需要 numpy + Pillow；Blender 用环境变量 BLENDER，没设就用 PATH 里的 blender）：
  python3 render_anim.py scenes/anim_sandbox.py [--frames 1-90] [--workers N] [--samples 4] [--pct 100]
                         [--vivid 1.0] [--cool] [--out DIR] [--mp4] [--no-check] [--clean-raw] [--restart]
  --samples 8      回到 8 采样（细线/雨/浪花/粒子还没做 8-vs-4 对比时用，见 SPEC §11.4）
  --workers N      并行 Blender 进程数；缺省 = min(CPU 核数/2, (可用内存-0.5GB)/1.2GB)，至少 1
  --out DIR        缺省 out/anim/<场景名>/ ；成品帧 DIR/0001.png，原图 DIR/raw/，日志 DIR/logs/
  --restart        清空 DIR 后从头渲；参数（采样、分辨率、档位）和上次不同时必须加
返回码：0 成功；1 check_frame 不过；2 渲染/纸纹失败（失败 worker 的日志尾部会打印出来）。"""
import os, sys, json, time, shutil, signal, subprocess, threading, argparse
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
GB_PER_WORKER = 1.2

def blender_bin():
    b = os.environ.get('BLENDER') or shutil.which('blender')
    if not b or not (os.path.isfile(b) or shutil.which(b)): sys.exit('找不到 Blender：设置环境变量 BLENDER=/path/to/blender-3.6/blender，或把 blender 放进 PATH')
    return b

def mem_available_gb():
    """Linux 读 /proc/meminfo 的 MemAvailable；其他系统拿不到就按 8GB 估。"""
    try:
        for ln in open('/proc/meminfo'):
            if ln.startswith('MemAvailable:'): return int(ln.split()[1])/1024/1024
    except OSError: pass
    return 8.

def default_workers():
    cpu = os.cpu_count() or 2
    return max(1, min(cpu//2, int((mem_available_gb() - .5)//GB_PER_WORKER)))

def parse_range(s):
    a, b = s.split('-'); return int(a), int(b)

def chunks(frames, n):
    """连续切成 n 段（帧顺序不变，每段大小差不超过 1）。"""
    n = max(1, min(n, len(frames))); k, r = divmod(len(frames), n); out, i = [], 0
    for j in range(n):
        m = k + (1 if j < r else 0); out.append(frames[i:i+m]); i += m
    return [c for c in out if c]

def png_ok(p):
    if not os.path.isfile(p) or os.path.getsize(p) < 64: return False
    try:
        from PIL import Image
        with Image.open(p) as im: im.verify()
        return True
    except Exception: return False

def run_blender(bl, scene, extra):
    cmd = [bl, '-b', '--python-exit-code', '1', '--python', scene, '--'] + extra
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, cwd=HERE, start_new_session=True)

def probe(bl, scene, opts, d):
    meta = os.path.join(d, 'logs', 'probe.json'); log = os.path.join(d, 'logs', 'probe.log')
    p = run_blender(bl, scene, ['--anim-probe', meta] + opts); out = p.communicate()[0]; open(log, 'w').write(out)
    if p.returncode != 0 or not os.path.isfile(meta):
        print(out[-3000:]); sys.exit(f'探测帧范围失败（{scene}）。场景脚本最后要调用 T.render_anim(sc)，见 SPEC §11.1')
    return json.load(open(meta))

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('scene'); ap.add_argument('--frames'); ap.add_argument('--workers', type=int)
    ap.add_argument('--samples', type=int, default=4); ap.add_argument('--pct', type=int, default=100)
    ap.add_argument('--vivid', type=float); ap.add_argument('--cool', action='store_true')
    ap.add_argument('--out'); ap.add_argument('--mp4', action='store_true'); ap.add_argument('--no-check', action='store_true')
    ap.add_argument('--clean-raw', action='store_true'); ap.add_argument('--restart', action='store_true')
    ap.add_argument('--paper-jobs', type=int, default=os.cpu_count())
    A = ap.parse_args(argv)
    def _term(*_): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, _term)                               # kill / 关终端也走「中断」分支：停掉 worker，保留已完成帧
    T0 = time.time(); scene = os.path.abspath(A.scene); name = os.path.splitext(os.path.basename(scene))[0]
    d = os.path.abspath(A.out or os.path.join(HERE, 'out', 'anim', name)); raw = os.path.join(d, 'raw'); logs = os.path.join(d, 'logs')
    if A.restart and os.path.isdir(d): shutil.rmtree(d)
    for x in (d, raw, logs): os.makedirs(x, exist_ok=True)
    for dd in (d, raw):                                                # 上次中断留下的半成品
        for f in os.listdir(dd):
            if f.startswith('.tmp_'): os.remove(os.path.join(dd, f))
    bl = blender_bin(); sopts = (['--vivid', str(A.vivid)] if A.vivid is not None else []) + (['--cool'] if A.cool else [])
    # 运行参数：续渲时必须一致，否则混帧
    run_p = os.path.join(d, '_run.json'); settings = dict(scene=scene, samples=A.samples, pct=A.pct, vivid=A.vivid, cool=A.cool)
    prev = json.load(open(run_p)) if os.path.isfile(run_p) else None
    if prev and prev.get('settings') != settings:
        sys.exit(f'{d} 里已有用不同参数渲的帧：\n  上次 {prev.get("settings")}\n  这次 {settings}\n换 --out，或加 --restart 从头渲')
    meta = (prev or {}).get('meta')
    if not meta and os.path.isfile(os.path.join(logs, 'meta0.json')): meta = json.load(open(os.path.join(logs, 'meta0.json')))
    t = time.time()
    if A.frames: f0, f1 = parse_range(A.frames)
    else:
        if not meta: meta = probe(bl, scene, sopts, d); print(f'探测：帧 {meta["frame_start"]}-{meta["frame_end"]} @ {meta["fps"]:g} fps（{time.time()-t:.1f}s）')
        f0, f1 = meta['frame_start'], meta['frame_end']
    t_probe = time.time() - t
    json.dump(dict(settings=settings, meta=meta), open(run_p, 'w'), indent=1)
    digits = max(4, len(str(f1))); fn = lambda f: f'{f:0{digits}d}.png'
    frames = list(range(f0, f1+1))
    done = [f for f in frames if png_ok(os.path.join(d, fn(f)))]
    need_paper = [f for f in frames if f not in set(done) and png_ok(os.path.join(raw, fn(f)))]
    need_render = [f for f in frames if f not in set(done) and f not in set(need_paper)]
    W = A.workers or default_workers(); W = max(1, min(W, len(need_render))) if need_render else 0
    print(f'镜头 {name}：帧 {f0}-{f1} 共 {len(frames)}；已完成 {len(done)}，只差纸纹 {len(need_paper)}，待渲染 {len(need_render)}；'
          f'{W} 个 Blender 进程，{A.samples} 采样，{A.pct}%；输出 {d}', flush=True)
    # ---- 4. N 个 Blender 并行，各渲一段（1. 每个进程只搭一次场景；2. 采样数进 job）
    t = time.time(); procs = []; fail = []; n_ok = [0]; t_warm = [0.]; lock = threading.Lock(); rtimes = []
    def pump(i, p, logf, total):
        with open(logf, 'a') as L:
            for ln in p.stdout:
                L.write(ln)
                if ln.startswith('ANIM_FRAME'):
                    _, f, s = ln.split()
                    with lock:
                        n_ok[0] += 1; rtimes.append(float(s)); el = time.time() - t; k = n_ok[0]
                        if k == W: t_warm[0] = el                         # 前 W 帧含搭场景时间，不拿来估速
                        eta = f'{(el - t_warm[0])/(k - W)*(total - k):4.0f}s' if k > W else '  —'
                        print(f'  [w{i}] 帧 {int(f):>4} {float(s):5.2f}s   {k}/{total}  已用 {el:5.0f}s  剩约 {eta}', flush=True)
    for i, ch in enumerate(chunks(need_render, W)):
        job = os.path.join(logs, f'job{i}.json')
        json.dump(dict(frames=ch, raw_dir=raw, samples=A.samples, pct=A.pct, digits=digits, meta_out=os.path.join(logs, f'meta{i}.json')), open(job, 'w'))
        logf = os.path.join(logs, f'worker{i}.log'); open(logf, 'w').close()
        p = run_blender(bl, scene, ['--anim-job', job] + sopts)
        th = threading.Thread(target=pump, args=(i, p, logf, len(need_render)), daemon=True); th.start(); procs.append((i, ch, p, th, logf))
        print(f'  w{i}: 帧 {ch[0]}-{ch[-1]}（{len(ch)} 帧）', flush=True)
    try:
        for i, ch, p, th, logf in procs: p.wait(); th.join()
    except KeyboardInterrupt:
        for _, _, p, _, _ in procs:
            try: os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError: pass
        print('\n已中断。已完成的帧都保留了，原样再跑一遍同一条命令即可续渲。'); return 130
    for i, ch, p, th, logf in procs:
        miss = [f for f in ch if not png_ok(os.path.join(raw, fn(f)))]
        if p.returncode != 0 or miss:
            fail.append(i); tail = open(logf).read().splitlines()[-25:]
            print(f'\n✗ worker w{i}（帧 {ch[0]}-{ch[-1]}）失败：返回码 {p.returncode}，缺 {len(miss)} 帧。日志 {logf} 末尾：\n  ' + '\n  '.join(tail), flush=True)
    t_render = time.time() - t
    if procs and not meta:
        m0 = os.path.join(logs, 'meta0.json')
        if os.path.isfile(m0): meta = json.load(open(m0)); json.dump(dict(settings=settings, meta=meta), open(run_p, 'w'), indent=1)
    # ---- 3. 纸纹批处理（对所有已有原图、还没成品的帧）
    t = time.time()
    import paper as PP, paper_batch as PB, style
    pstyle, pviv = (meta or {}).get('style', 'vivid'), (meta or {}).get('vivid', A.vivid if A.vivid is not None else 1.0)
    kw = style.preset(pstyle, pviv)['paper']
    todo = [(os.path.join(raw, fn(f)), os.path.join(d, fn(f))) for f in frames if not png_ok(os.path.join(d, fn(f))) and png_ok(os.path.join(raw, fn(f)))]
    if todo:
        print(f'纸纹：{len(todo)} 帧，{min(A.paper_jobs, len(todo))} 进程（{pstyle} {pviv:g}）', flush=True)
        PB.paper_files(todo, kw, A.paper_jobs)
    t_paper = time.time() - t
    if fail: print(f'\n有 {len(fail)} 个 worker 失败，修好后原样重跑同一条命令即可续渲。'); return 2
    missing = [f for f in frames if not png_ok(os.path.join(d, fn(f)))]
    if missing: print(f'仍缺 {len(missing)} 帧：{missing[:10]}…'); return 2
    # ---- 3. 只测首 / 中 / 尾三帧
    t = time.time(); rc = 0
    if not A.no_check:
        import check_frame as CF
        from PIL import Image
        for f in sorted({f0, (f0+f1)//2, f1}):
            m = CF.measure(Image.open(os.path.join(d, fn(f)))); bad = CF.judge(m, A.cool)
            print(f"{'PASS' if not bad else 'FAIL'}  {fn(f)}  " + '  '.join(f'{k}={v:.3f}' for k, v in m.items()) + (f'   ← {"; ".join(bad)}' if bad else ''))
            rc |= bool(bad)
    t_check = time.time() - t
    # ---- MP4
    t = time.time(); mp4 = None
    if A.mp4:
        fps = (meta or {}).get('fps', 30); mp4 = os.path.join(d, f'{name}.mp4')
        ff = shutil.which('ffmpeg') or sys.exit('找不到 ffmpeg')
        tmp = os.path.join(d, f'.tmp_{name}.mp4')
        subprocess.run([ff, '-y', '-loglevel', 'error', '-framerate', f'{fps:g}', '-start_number', str(f0), '-i', os.path.join(d, f'%0{digits}d.png'),
                        '-frames:v', str(len(frames)), '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2', '-c:v', 'libx264', '-profile:v', 'high', '-crf', '17',
                        '-preset', 'slow', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', '-f', 'mp4', tmp], check=True)
        os.replace(tmp, mp4)
    t_mp4 = time.time() - t
    if A.clean_raw: shutil.rmtree(raw, ignore_errors=True)
    tot = time.time() - T0; nr = len(need_render)
    parts = [f'总 {tot:.1f}s']
    if t_probe > .5: parts.append(f'探测 {t_probe:.1f}s')
    r = f'渲染 {t_render:.1f}s（{nr} 帧，{W} 进程'
    if nr and rtimes: r += f'，单帧渲染均值 {sum(rtimes)/len(rtimes):.2f}s，墙钟折合 {t_render/nr:.2f}s/帧'
    parts += [r + '）', f'纸纹 {t_paper:.1f}s', f'检查 {t_check:.1f}s'] + ([f'MP4 {t_mp4:.1f}s'] if A.mp4 else [])
    print('\n—— 用时 ——  ' + '  '.join(parts))
    if nr: print(f'本次渲了 {nr} 帧，整体 {tot/nr:.2f}s/帧')
    print('成品帧：' + d + (f'\nMP4：{mp4}' if mp4 else ''))
    return 1 if rc else 0

if __name__ == '__main__':
    sys.exit(main())
