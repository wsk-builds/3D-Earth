"""通用插画风：风格预设 + 色板（纯 Python，不依赖 bpy；toon.py / paper.py / check_frame.py 共用）。

两个预设：
  vivid（默认）：明艳版。strength=1.0 = 用户选定的「B8-C 档」，1.25 = 「溪流 D 档」；0 = fresh；上限 1.4。
  fresh       ：旧的偏青清新版（旧项目成片原样）。
用法：
  import style; P = style.preset('vivid', 1.0); PAL = style.palette(P); paper_kw = P['paper']
颜色约定：代码里全部是 Blender 线性值；hex 一律指 sRGB 显示色（亮档、未加纸纹时的屏幕颜色）。"""
import colorsys

# ---------------------------------------------------------------- 预设
FRESH = dict(
    tint=(.62, .80, .84),          # 暗部色调：浅青 #CEE7EC
    mid_k=.45,                      # 中档带多少暗部色调（0..1）
    shadow_sat=0.,                  # 暗档按固有色加饱和：暗档 ×(1+x)、中档 ×(1+x/2)
    lit=(1., 1., 1.),               # 亮档倍率（= 主光颜色在平涂里的体现）
    sat_k=1., warm_k=1., teal_hue=186., teal_move=0., teal_v=0.,
    green_hue=102., green_move=0., green_s=0., warm_neutral=0.,
    sun_k=1., sun_warm=0.,          # 主光能量倍率 / 向 (1,.80,.55) 偏暖的比例
    fog_col=(.72, .86, .82), fog_a=1.,
    sky_h=(.68, .82, .78), sky_t=(.50, .69, .67), ambient=.46, amb_col=(.85, .95, 1.),
    paper=dict(k=.16, warm=.035, vig=.10, sat=1.12),
)
VIVID_1 = dict(                     # = C 档（B8-C 选定）
    tint=(.768, .672, .807),        # 暖紫 #E3D6E8
    mid_k=.30, shadow_sat=.30, lit=(1.02, .995, .945),
    sat_k=1.30, warm_k=1.30, teal_hue=186., teal_move=.75, teal_v=.04,
    green_hue=102., green_move=.70, green_s=.26, warm_neutral=.14,
    sun_k=1.30, sun_warm=.60,
    fog_col=(.84, .84, .77), fog_a=.70,
    sky_h=(.77, .84, .79), sky_t=(.67, .77, .73), ambient=.46, amb_col=(.96, .94, .96),
    paper=dict(k=.16, warm=.065, vig=.06, sat=1.25),
)
VIVID_125 = dict(                   # = D 档（溪流选定）
    tint=(.80, .66, .80),
    mid_k=.30, shadow_sat=.40, lit=(1.03, .99, .925),
    sat_k=1.45, warm_k=1.40, teal_hue=190., teal_move=.75, teal_v=.06,
    green_hue=100., green_move=.70, green_s=.30, warm_neutral=.18,
    sun_k=1.45, sun_warm=.80,
    fog_col=(.88, .85, .76), fog_a=.60,
    sky_h=(.81, .86, .79), sky_t=(.73, .80, .74), ambient=.46, amb_col=(.98, .94, .95),
    paper=dict(k=.16, warm=.08, vig=.05, sat=1.30),
)
VIVID_MAX = 1.4

def _lerp(a, b, t):
    if isinstance(a, dict): return {k: _lerp(a[k], b[k], t) for k in a}
    if isinstance(a, (tuple, list)): return tuple(x + (y-x)*t for x, y in zip(a, b))
    return a + (b-a)*t

def preset(name='vivid', strength=1.0):
    """返回参数字典。vivid 的 strength 分段线性：0→fresh，1→C，1.25→D，>1.25 沿 C→D 方向外推到 1.4。"""
    if name == 'fresh': P = dict(FRESH); P['name'] = 'fresh'; P['strength'] = 0.; return P
    s = max(0., min(float(strength), VIVID_MAX))
    P = _lerp(FRESH, VIVID_1, s) if s <= 1 else _lerp(VIVID_1, VIVID_125, (s-1)/.25)
    P['paper'] = {k: round(v, 4) for k, v in P['paper'].items()}
    P['name'] = 'vivid'; P['strength'] = s; return P

# ---------------------------------------------------------------- 颜色转换
def to_srgb(x): x = max(0., min(1., x)); return x*12.92 if x <= .0031308 else 1.055*x**(1/2.4) - .055
def to_lin(x): return x/12.92 if x <= .04045 else ((x+.055)/1.055)**2.4
def hex2lin(h): h = h.lstrip('#'); return tuple(to_lin(int(h[i:i+2], 16)/255) for i in (0, 2, 4))
def lin2hex(c): return '#' + ''.join(f'{round(to_srgb(x)*255):02X}' for x in c[:3])
def _hmove(h, tgt, t): d = ((tgt - h + 180) % 360) - 180; return (h + d*t) % 360

def vivid_rgb(lin, P):
    """把一个「清新版」固有色（线性）按预设推成明艳版：青绿→湖蓝、灰绿→嫩芽绿、暖色提一档、中灰转暖灰；暖白不动。"""
    c = [to_srgb(x) for x in lin[:3]]
    h, s, v = colorsys.rgb_to_hsv(*c); hd = h*360
    if s < .10:
        if v > .80: pass                                              # 墙、纸、蒸汽：保持干净暖白
        elif v > .45 and P['warm_neutral']: hd = 34.; s = max(s, P['warm_neutral'])
    elif 140 <= hd <= 205:
        hd = _hmove(hd, P['teal_hue'], P['teal_move']); s *= P['sat_k']; v += P['teal_v']
    elif 65 <= hd < 140:
        hd = _hmove(hd, P['green_hue'], P['green_move']); s = max(s*P['sat_k'], P['green_s'])
    elif hd < 65 or hd > 320:
        s *= P['warm_k']; v += .02*min(P['strength'] if 'strength' in P else 1, 1)
    else:
        s *= P['sat_k']
    s = min(s, .88); v = min(v, 1.)
    return tuple(to_lin(x) for x in colorsys.hsv_to_rgb(hd/360, s, v))

# ---------------------------------------------------------------- 基础色板（清新版原值，线性）
PAL_BASE = dict(
    paper=(.93, .90, .82), wall=(.92, .89, .81), tile=(.11, .14, .15), stone=(.36, .43, .42), stone_d=(.22, .28, .28),
    water=(.13, .34, .34), teal=(.16, .52, .50), teal_l=(.45, .74, .68), gold=(.95, .68, .28), gold_d=(.66, .40, .14),
    wood=(.42, .25, .11), red=(.78, .26, .10), green=(.30, .52, .30), green_l=(.55, .70, .38), sand=(.93, .72, .40),
    mist=(.80, .86, .83), sky=(.74, .82, .80), black=(.02, .03, .03), skin=(.93, .76, .60))
PAL_USE = dict(
    paper='纸面、浅底、桌面亮部', wall='白墙、白色建筑立面', tile='瓦、深色屋顶、铁件', stone='石、岩、水泥',
    stone_d='深石、岩缝、树干', water='深水、阴影里的水', teal='主水色 / 湖蓝主色', teal_l='浅水、高光水、玻璃',
    gold='暖金点缀（灯、金属、流线）', gold_d='深金、铜', wood='木门、木构、桌面', red='朱红点缀（灯笼、旗、屋顶）',
    green='植被主色', green_l='嫩芽绿（草、苔、新叶）', sand='沙、暖台面、土路', mist='雾片', sky='平涂天',
    black='最深色（头发等极少量）', skin='肤色')
INK = (.045, .07, .07)               # 墨青描边 #3C4B4B，两个预设共用

def palette(P):
    """预设下的色板（线性）。fresh = 原值；vivid = 原值经 vivid_rgb 推一遍。"""
    if P['name'] == 'fresh' or P['strength'] == 0: return dict(PAL_BASE)
    out = {k: vivid_rgb(v, P) for k, v in PAL_BASE.items()}
    out['mist'] = tuple(P['fog_col']); out['sky'] = tuple(P['sky_h'])
    return out

# ---------------------------------------------------------------- 题材主色（vivid 1.0 下的显示色 hex，直接拿来用，不再 vivid_rgb）
# 每组：main = 大面积主色（2–3 个），accent = 点缀（≤2 个，合计 ≤ 画面 10%），note = 用法。
THEMES = {
    'landscape': dict(main=['#7FCFD3', '#B9DE8E', '#F4EEDF'], accent=['#F2B54B', '#E9784A'],
                      note='自然山水：湖蓝水 + 嫩芽绿植被 + 暖白云/雾；暖色给花、叶、亭子、人物'),
    'city':      dict(main=['#F3EDE2', '#C9B9A8', '#7EC3CC'], accent=['#F4B13E', '#E3604A'],
                      note='城市：暖白立面 + 暖灰石材 + 湖蓝玻璃；橙灯、红招牌做焦点'),
    'desert':    dict(main=['#F7D7A0', '#EDB777', '#86D0CF'], accent=['#62B86D', '#E9784A'],
                      note='沙漠/绿洲：沙金 + 赭橙大面积；湖蓝水和嫩绿棕榈是唯一冷色，面积 15–25%'),
    'ocean':     dict(main=['#5FC0CF', '#A9E1E2', '#F6F0E2'], accent=['#E9604A', '#F2B54B'],
                      note='海洋：湖蓝海 + 浅青浪 + 暖白浪花/沙；红白灯塔、橙救生圈做焦点（冷主调，按 --cool 测）'),
    'snow':      dict(main=['#F7F4EE', '#CFE3EC', '#B8C9E6'], accent=['#F2A64A', '#E3604A'],
                      note='冰雪【推断】：暖白雪面 + 浅蓝冰 + 淡蓝紫阴影；暖窗、红围巾做焦点（冷主调，按 --cool 测）'),
    'interior':  dict(main=['#F6EFE3', '#E3BE8E', '#9FD3C8'], accent=['#F4B13E', '#E9784A'],
                      note='室内：暖白墙 + 木色家具 + 薄荷/湖蓝小件；台灯、果盘做焦点'),
    'science':   dict(main=['#F5EFE4', '#7FCFD3', '#B9DE8E', '#F2C77A'], accent=['#E9604A', '#5A9BE0'],
                      note='科学示意：暖白底 + 湖蓝/嫩绿/金三色编码数据；红、钴蓝只给箭头和标注'),
}
def theme(name): t = THEMES[name]; return dict(main=[hex2lin(h) for h in t['main']], accent=[hex2lin(h) for h in t['accent']])

if __name__ == '__main__':
    for nm, s in [('fresh', 0), ('vivid', 1.0), ('vivid', 1.25)]:
        P = preset(nm, s); pal = palette(P)
        print(nm, s, {k: lin2hex(v) for k, v in pal.items()}, 'tint', lin2hex(P['tint']))
