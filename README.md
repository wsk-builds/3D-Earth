# 3D-Earth · 代码生成的 3D 地球

用 Python + moderngl（GLSL 片元着色器）**逐像素光线求交**渲染的 3D 地球，来自科普视频《为什么撒哈拉曾经是绿色的》。不需要 3D 建模软件，一个 Python 进程离屏（无窗口）就能出 1920×1080 的画面，适合批量渲染视频帧和封面。

## 特性

- **光线追踪球体**：每个像素从相机发出一条光线，与单位球解析求交，没有多边形网格，边缘永远是圆的。
- **真实卫星贴图**：NASA Blue Marble 卫星影像（等经纬度投影），伽马校正后做光照。
- **陆地掩膜**：贴图的 Alpha 通道区分陆地和海洋，用于海面高光、陆地凹凸等。
- **云层**：NASA 云图，可调透明度，随时间 `t` 缓慢漂移，并在地面投下云影。
- **大气光晕**：球面边缘的蓝色菲涅尔边缘光，加上球外的大气辉光（朝阳一侧更亮，晨昏线带一点暖色）。
- **凹凸（bump）**：用贴图亮度的梯度扰动陆地法线，山脉有立体感。
- **海面高光**：太阳在海面上的镜面反射。
- **星空背景**：程序生成的稀疏星点。
- **太阳方向**：任意方向的平行光，自动形成昼夜交界和夜面微光。
- **相机**：`look_at` 相机，可设位置、目标、视场角；`project()` 把 3D 点投影成屏幕坐标，便于在画面上叠加标注。
- **ACES 色调映射 + 抖动**，减少色带。
- 视频专用的示意效果（默认关闭）：绿色撒哈拉、古湖泊、季风雨带、经纬网格。
- `transition.py`：与渲染器无关的"匹配视角交叉溶解"转场模板（只依赖 numpy），可用来做两个镜头之间的匹配剪辑。

## 安装

需要 Python 3.9+ 和支持 OpenGL 3.3 的环境（有显卡驱动的桌面，或 Linux 上的 Mesa/EGL 软件渲染均可）。

```bash
git clone https://github.com/wsk-builds/3D-Earth.git
cd 3D-Earth
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python textures.py        # 把 tex_b64/ 里的贴图解码到 tex/（首次渲染时也会自动执行）
```

> 为什么贴图是 base64 文本？这个仓库是通过只支持文本文件的接口上传的，所以二进制图片被编码成 `tex_b64/*.b64.partNN`。`textures.py` 会把它们还原成 `tex/earth_rgb.jpg`、`tex/land_mask.png`、`tex/cloud_combined_2048.jpg`。

导出视频需要系统里装有 `ffmpeg`（可选，没有的话示例会导出 GIF）。

## 使用

```bash
python example.py                  # out/still.png（静帧）+ out/orbit.mp4（短环绕镜头）
python example.py --ss 0.5         # 半分辨率快速预览
python example.py --frames 120     # 更长的环绕
EARTH_W=1080 EARTH_H=1920 python example.py   # 竖版画幅
```

在自己的代码里：

```python
from PIL import Image
from globe import Globe
from cam import Cam, sph

g = Globe(ss=1.0)                                   # 创建渲染器并加载贴图（只需一次）
cam = Cam(eye=tuple(sph(20, 15, 2.6)),              # 相机在北纬 20°、东经 15°，距地心 2.6 个地球半径
          tgt=(0, 0, 0), fov=35)
img = g.render(cam, t=0.0, sun=tuple(sph(25, 40)), cloud_a=0.8)   # 返回 HxWx4 uint8
Image.fromarray(img[:, :, :3]).save('earth.png')

x, y, depth = cam.project(sph(30, 31))              # 开罗在屏幕上的位置（depth>0 表示在相机前方）
```

坐标约定：地球半径为 1，地心在原点，`y` 轴指向北极；`sph(lat, lon, r)` 把纬度、经度（度）和半径转成三维坐标，经度 0° 朝 `+z`，东经朝 `+x`。

## 参数

`Globe(ss=1.0)`：`ss` 是渲染缩放，输出尺寸为 `cam.W*ss × cam.H*ss`（`ss=2` 可做超采样后再缩小）。

`Globe.render(cam, ...)`：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `t` | 0.0 | 时间（秒），驱动云层漂移和噪声 |
| `sun` | (0.6, 0.3, 0.75) | 太阳方向（会自动归一化），可用 `sph(lat, lon)` |
| `cloud_a` | 1.0 | 云层不透明度，0 = 无云 |
| `night` | 1.0 | 夜面微光强度 |
| `atmo` | 1.0 | 大气边缘光 / 光晕强度 |
| `exposure` | 1.0 | 曝光 |
| `star_a` | 1.0 | 星空亮度 |
| `land_dim` | 1.0 | 陆地亮度系数（压暗陆地突出叠加层时用） |
| `spin` | 0.0 | 地球绕地轴自转角（度） |
| `grid_a` | 0.0 | 经纬网格（10° 间隔）透明度 |
| `green` | 0.0 | 示意：撒哈拉变绿程度 0–1 |
| `lake_a` | 0.0 | 示意：古乍得湖等古湖泊 |
| `rain_a`, `rain_lat` | 0.0, 10.0 | 示意：北非季风雨带强度和所在纬度 |
| `desert_a` | 0.0 | 示意：沙漠暖色加强 |

`Cam(eye, tgt, fov=35.0, up=(0,1,0))`：相机位置、注视点、垂直视场角（度）。

环境变量：`EARTH_W` / `EARTH_H`（画幅，默认 1920×1080，需在 import 之前设置）、`EARTH_TEX_DIR`（贴图目录，默认是代码旁的 `tex/`）。

## 文件

| 文件 | 作用 |
| --- | --- |
| `globe.py` | 地球着色器和 `Globe` 渲染器 |
| `cam.py` | 相机、投影、经纬度转坐标 |
| `glcore.py` | moderngl 离屏上下文、全屏 Pass、贴图加载、公共 GLSL（噪声、ACES） |
| `textures.py` | 贴图解码和合成（卫星影像 + 陆地掩膜 → RGBA） |
| `transition.py` | 匹配视角交叉溶解转场模板 |
| `example.py` | 示例：静帧 + 环绕镜头 |
| `tex_b64/` | base64 编码的贴图 |

## 贴图来源与版权

- **地球影像**：NASA Visible Earth，*Blue Marble: Next Generation*，2004 年 12 月，5400×2700（8 km/像素）。
  来源页：<https://visibleearth.nasa.gov/images/74218/december-blue-marble-next-generation/74219l>。
  原视频项目的记录是"NASA Visible Earth Blue Marble（2004 年 12 月）"；具体是带地形/海底地形晕渲的版本还是基础版本，原项目没有记录。
  仓库中的 `earth_rgb.jpg` 是原项目贴图的 JPEG（质量 97，4:4:4）重新编码版本，与原 PNG 渲染结果的逐像素差异平均约 0.1/255（PSNR ≈ 55 dB），肉眼看不出区别。
- **陆地掩膜** `land_mask.png`：原项目贴图的 Alpha 通道（0 海洋 … 255 陆地，边缘有过渡）。它最初是怎么生成的，原项目没有留下记录。
- **云图** `cloud_combined_2048.jpg`：NASA Visible Earth，*Blue Marble: Clouds*（image 57747，2002 年），2048×1024，未做修改（SHA-256 与 NASA 原文件一致）。
  来源页：<https://visibleearth.nasa.gov/images/57747/blue-marble-clouds/77558l>。
  原始文件：<https://eoimages.gsfc.nasa.gov/images/imagerecords/57000/57747/cloud_combined_2048.jpg>

影像来自 NASA Goddard Space Flight Center / NASA Earth Observatory（Reto Stöckli 等）。NASA 影像在美国一般不受版权保护，使用时请注明来源，且不得暗示 NASA 背书，详见 NASA 媒体使用政策：<https://www.nasa.gov/nasa-brand-center/images-and-media/>。

绿色撒哈拉、古湖泊、雨带等效果为**示意**，不是真实数据。
