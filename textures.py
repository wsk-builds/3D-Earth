"""贴图加载：把卫星影像 (earth_rgb.jpg) 和陆地掩膜 (land_mask.png) 合成为着色器使用的 RGBA 贴图。

GitHub 仓库里的二进制贴图以 base64 文本分片保存在 tex_b64/ 下（上传工具只支持文本）。
首次使用时会自动解码到 tex/；也可以手动运行：  python textures.py
如果 tex/ 下已经有 earth_rgba.png（RGBA，A = 陆地掩膜），则优先直接使用它。
"""
import base64, glob, os
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TEX_DIR = os.environ.get('EARTH_TEX_DIR', os.path.join(HERE, 'tex'))
B64_DIR = os.path.join(HERE, 'tex_b64')
FILES = ['earth_rgb.jpg', 'land_mask.png', 'cloud_combined_2048.jpg']


def unpack(force=False):
    """把 tex_b64/<name>.b64.partNN 解码成 tex/<name>。已存在的文件默认跳过。"""
    os.makedirs(TEX_DIR, exist_ok=True)
    for name in FILES:
        dst = os.path.join(TEX_DIR, name)
        if os.path.exists(dst) and not force:
            continue
        parts = sorted(glob.glob(os.path.join(B64_DIR, name + '.b64.part*')))
        if not parts:
            continue
        data = base64.b64decode(''.join(open(p).read() for p in parts).replace('\n', ''))
        with open(dst, 'wb') as f:
            f.write(data)
        print(f'[textures] 解码 {name}  ({len(data)/1e6:.1f} MB)')


def _need(name):
    p = os.path.join(TEX_DIR, name)
    if not os.path.exists(p):
        unpack()
    if not os.path.exists(p):
        raise FileNotFoundError(f'找不到贴图 {p}，请先运行 python textures.py（见 README）')
    return p


def earth_rgba():
    """返回 HxWx4 uint8：RGB = 卫星影像，A = 陆地掩膜（0 海洋 … 255 陆地）。"""
    legacy = os.path.join(TEX_DIR, 'earth_rgba.png')
    if os.path.exists(legacy):
        return np.asarray(Image.open(legacy).convert('RGBA'))
    rgb = np.asarray(Image.open(_need('earth_rgb.jpg')).convert('RGB'))
    mask = np.asarray(Image.open(_need('land_mask.png')).convert('L'))
    return np.dstack([rgb, mask])


def cloud_path():
    return _need('cloud_combined_2048.jpg')


if __name__ == '__main__':
    unpack(force=True)
