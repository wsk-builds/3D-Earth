# 自定义特效示例：亚马孙河干流一条细淡蓝线 + 河口一个小光点（克制：细线、低不透明度、加色）
def draw(x):
    sk, P, sc, cv = x['skia'], x['P'], x['sc'], x['cv']
    river = [(-4.4,-73.5),(-3.7,-70.0),(-3.3,-65.0),(-3.1,-60.0),(-2.5,-56.0),(-1.9,-54.0),(-1.0,-51.5),(-0.3,-50.0)]
    pts = [x['proj'](la, lo)[:2] for la, lo in river if x['visible'](la, lo) > 0.05]   # 背面的点不画
    if len(pts) < 2: return
    pa = sk.Path(); pa.moveTo(*pts[0]); [pa.lineTo(*q) for q in pts[1:]]
    cv.drawPath(pa, P('#9fd8ff', .22, 'stroke', 10*sc, blur=7, blend='add'))   # 柔光 ≤ .3
    cv.drawPath(pa, P('#e6f6ff', .45, 'stroke', 1.6*sc))                         # 1.6px 细线
    px, py, _ = x['proj'](-0.3, -50.0)
    cv.drawCircle(px, py, 6*sc, P('#9fd8ff', .35, blur=5, blend='add')); cv.drawCircle(px, py, 2.2*sc, P('#f0faff', .9))
