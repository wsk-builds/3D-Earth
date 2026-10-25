"""风格总览图 style_sheet.png：上 = vivid 1.0 色板（名称 + hex + 用途）+ 暗部色调；下 = 2×2 参考帧，每帧标测量值。
用法：python3 make_sheet.py [--out style_sheet.png] [帧1 标题1 帧2 标题2 ...]"""
import sys, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import style
from check_frame import measure, judge

F = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'; FB = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
def font(sz, b=False): return ImageFont.truetype(FB if b else F, sz, index=2)   # index 2 = SC
REF = os.path.join(HERE, 'ref')   # B8-C / B6-D 参考帧副本
DEFAULT = [(f'{REF}/B8_C.png', 'B8-C  街巷 · vivid 1.0（用户选定）', False),
           (f'{REF}/B6_D.png', 'B6-D  溪流 · vivid 1.25（用户选定）', True),
           (f'{HERE}/out/lighthouse.png', '新题材 · 海边灯塔（ocean，vivid 1.0）', True),
           (f'{HERE}/out/sandbox.png', '新题材 · 桌面地形沙盘（science，vivid 1.0）', False)]
INKC = (60, 75, 75); BG = (247, 243, 234)

def main(argv):
    out = os.path.join(HERE, 'style_sheet.png')
    if '--out' in argv: i = argv.index('--out'); out = argv[i+1]; del argv[i:i+2]
    frames = [(argv[i], argv[i+1], 'cool' in argv[i+1].lower()) for i in range(0, len(argv) - 1, 2)] or DEFAULT
    TW, TH, G = 960, 540, 28; W = 2*TW + 3*G
    P = style.preset('vivid', 1.0); pal = style.palette(P)
    keys = [k for k in style.PAL_BASE if k not in ('mist', 'sky')]
    sw, cols = (W - 2*G)//10, 10; rows = (len(keys) + 2 + cols - 1)//cols
    top = 110 + rows*150; H = top + 2*(TH + 92) + G
    im = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(im)
    d.text((G, 22), '通用插画规范 · 明艳版色板（vivid 1.0，亮档显示色）', font=font(40, True), fill=INKC)
    d.text((G, 74), '3D 建模体积 + 平涂三档 toon + 墨青描边 + 纸纹 —— 明艳而不艳俗', font=font(24), fill=(110, 120, 118))
    items = [(k, style.lin2hex(pal[k]), style.PAL_USE[k]) for k in keys]
    items += [('tint 暗部色调', style.lin2hex(P['tint']), '暗档统一偏暖紫'), ('ink 描边', style.lin2hex(style.INK), '所有描边/字幕描边')]
    for i, (k, hx, use) in enumerate(items):
        x = G + (i % cols)*sw; y = 110 + (i//cols)*150
        rgb = tuple(int(hx[j:j+2], 16) for j in (1, 3, 5))
        d.rounded_rectangle([x, y, x + sw - 14, y + 78], 10, fill=rgb, outline=INKC, width=3)
        d.text((x, y + 84), k, font=font(20, True), fill=INKC)
        d.text((x, y + 108), hx, font=font(18), fill=(90, 100, 100))
        u = use if len(use) <= 9 else use[:9] + '…'
        d.text((x, y + 128), u, font=font(15), fill=(130, 138, 136))
    for n, (f, title, cool) in enumerate(frames[:4]):
        x = G + (n % 2)*(TW + G); y = top + (n//2)*(TH + 92)
        fr = Image.open(f).convert('RGB').resize((TW, TH), Image.LANCZOS)
        m = measure(fr if fr.size == Image.open(f).size else Image.open(f)); bad = judge(m, cool)
        d.text((x, y), title, font=font(26, True), fill=INKC)
        im.paste(fr, (x, y + 40)); d.rectangle([x - 1, y + 39, x + TW, y + 40 + TH], outline=INKC, width=2)
        s = (f"L {m['L']:.3f}  L10 {m['L10']:.3f}  S {m['S']:.3f}  Smed {m['Smed']:.3f}  neon {m['neon']:.1f}%  "
             f"warm {m['warm']:.1f}%  clip {m['clip']:.1f}%  {'--cool ' if cool else ''}{'PASS' if not bad else 'FAIL'}")
        d.text((x, y + 44 + TH), s, font=font(19), fill=(40, 130, 90) if not bad else (200, 70, 50))
    im.save(out); print(out, im.size)

if __name__ == '__main__':
    main(sys.argv[1:])
