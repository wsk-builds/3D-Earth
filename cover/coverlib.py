"""封面用的 skia 小工具：画笔 P() 和字体缓存（与原系列 lib.py 中的实现逐行一致，保证复现）。"""
import skia

def hexc(h):
    h = h.lstrip('#')
    if len(h) == 3: h = ''.join(ch*2 for ch in h)
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def col(h, a=1.0):
    r, g, b = hexc(h) if isinstance(h, str) else h
    return skia.ColorSetARGB(int(max(0, min(1, a))*255), r, g, b)

def P(color='#f4f1ea', a=1.0, style='fill', w=1, cap='round', blend=None, blur=0, shader=None, dash=None, aa=True):
    """画笔：color 十六进制，a 不透明度，style 'fill'/'stroke'，w 线宽，blend 'add'（加色）/'screen'，blur 模糊半径。"""
    p = skia.Paint(AntiAlias=aa)
    p.setColor(col(color, a))
    if style == 'stroke':
        p.setStyle(skia.Paint.kStroke_Style); p.setStrokeWidth(w)
        p.setStrokeCap({'round': skia.Paint.kRound_Cap, 'butt': skia.Paint.kButt_Cap, 'square': skia.Paint.kSquare_Cap}[cap])
        p.setStrokeJoin(skia.Paint.kRound_Join)
    if blend == 'add': p.setBlendMode(skia.BlendMode.kPlus)
    elif blend == 'screen': p.setBlendMode(skia.BlendMode.kScreen)
    if blur: p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, blur))
    if shader is not None: p.setShader(shader)
    if dash: p.setPathEffect(skia.DashPathEffect.Make(list(dash[:2]), dash[2] if len(dash) > 2 else 0))
    return p

def make_font(files):
    """files: {'sb': (path, ttc_index), 'sr': (path, ttc_index)} -> font(kind, size)"""
    tfs, cache = {}, {}
    def font(kind, size):
        if kind not in tfs:
            tf = skia.Typeface.MakeFromFile(*files[kind])
            if tf is None: raise SystemExit(f'无法加载字体 {files[kind]}')
            tfs[kind] = tf
        k = (kind, round(size, 1))
        if k not in cache:
            f = skia.Font(tfs[kind], size); f.setSubpixel(True)
            f.setEdging(skia.Font.Edging.kSubpixelAntiAlias); cache[k] = f
        return cache[k]
    return font
