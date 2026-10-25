"""纸纹批处理：一个 Python 进程 + 多进程池，每个子进程只读一次纸纹贴图、只算一次暗角，再逐帧处理。
算式与 paper.paper 完全相同（同样的 dtype 和运算顺序），输出逐像素一致。
用法：python3 paper_batch.py RAW_DIR OUT_DIR [--jobs 8] [--style vivid] [--vivid 1.0]
      或  from paper_batch import paper_files; paper_files([(raw, out), ...], kw, jobs)"""
import os, sys
from multiprocessing import Pool
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import paper as _paper

_KW = None; _CACHE = {}

def _tex_vig(h, w, vig):
    key = (h, w, vig)
    if key not in _CACHE:
        p = np.asarray(Image.open(os.path.join(HERE, 'tex', 'paper.png')).convert('L'), np.float32)/255.
        if p.shape != (h, w): p = np.asarray(Image.fromarray((p*255).astype(np.uint8)).resize((w, h), Image.BILINEAR), np.float32)/255.
        yy, xx = np.mgrid[0:h, 0:w]; r = np.hypot((xx-w/2)/(w/2), (yy-h/2)/(h/2))
        _CACHE.clear(); _CACHE[key] = (p, (1 - vig*np.clip(r-.55, 0, 1)**1.5)[..., None])
    return _CACHE[key]

def paper_cached(img, k=.16, warm=.065, vig=.06, sat=1.25):
    """= paper.paper(img, ...)，但贴图缩放和暗角按分辨率缓存。改 paper.py 的算式时这里要同步（verify() 会报差异）。"""
    a = img.astype(np.float32)/255. if img.dtype == np.uint8 else img
    h, w = a.shape[:2]; p, v = _tex_vig(h, w, vig)
    a = a*(1 + (p-.5)[..., None]*k)
    m_ = a.mean(-1, keepdims=True); a = m_ + (a-m_)*sat
    a = a*(1-warm) + warm*np.array([.97, .92, .80])*a.mean(-1, keepdims=True)*1.08
    a = a*v
    return (np.clip(a, 0, 1)*255+.5).astype(np.uint8)

def _init(kw):
    global _KW; _KW = kw

def _one(job):
    src, dst = job
    out = paper_cached(np.asarray(Image.open(src).convert('RGB')), **_KW)
    tmp = os.path.join(os.path.dirname(dst), f'.tmp_{os.getpid()}_{os.path.basename(dst)}')
    Image.fromarray(out).save(tmp, format='PNG'); os.replace(tmp, dst)          # 原子写入
    return dst

def verify(raw_png, kw):
    """和 paper.paper 逐像素比，返回最大差（应为 0）。"""
    im = np.asarray(Image.open(raw_png).convert('RGB'))
    return int(np.abs(paper_cached(im, **kw).astype(int) - _paper.paper(im, **kw).astype(int)).max())

def paper_files(pairs, kw, jobs=None, on_done=None):
    if not pairs: return []
    jobs = max(1, min(jobs or os.cpu_count() or 1, len(pairs))); done = []
    with Pool(jobs, initializer=_init, initargs=(kw,)) as pool:
        for d in pool.imap_unordered(_one, pairs, chunksize=1):
            done.append(d)
            if on_done: on_done(d, len(done), len(pairs))
    return done

if __name__ == '__main__':
    a = sys.argv[1:]; src, dst = a[0], a[1]; os.makedirs(dst, exist_ok=True)
    jobs = int(a[a.index('--jobs')+1]) if '--jobs' in a else None
    pairs = [(os.path.join(src, f), os.path.join(dst, f)) for f in sorted(os.listdir(src)) if f.endswith('.png') and not f.startswith('.')]
    paper_files(pairs, _paper.kw_for(a), jobs); print('PAPER_OK', len(pairs))
