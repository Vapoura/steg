# -*- coding: utf-8 -*-
"""生成应用图标 app.ico：相框里一张图，右下角探出一个文件 —— 藏东西的意思"""
from PIL import Image, ImageDraw

K = 4                    # 超采样倍数
S = 512 * K
M = 96 * K               # 外边距

# ---- 圆角底：蓝紫渐变 ----
grad = Image.linear_gradient("L").resize((S, S), Image.BICUBIC)
top_c = Image.new("RGB", (S, S), (92, 156, 255))
bot_c = Image.new("RGB", (S, S), (72, 58, 194))
bg = Image.composite(bot_c, top_c, grad)

mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=112 * K, fill=255)

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
img.paste(bg, (0, 0), mask)
d = ImageDraw.Draw(img)

# ---- 藏着的“文件”：先画，让相框压在上面 ----
fx0, fy0, fx1, fy1 = 300 * K, 300 * K, 392 * K, 392 * K
d.rounded_rectangle([fx0, fy0, fx1, fy1], radius=14 * K, fill=(174, 206, 255, 255))

# ---- 相框 ----
bx0, by0, bx1, by1 = 116 * K, 132 * K, 372 * K, 372 * K
d.rounded_rectangle(
    [bx0, by0, bx1, by1], radius=26 * K,
    outline=(255, 255, 255, 255), width=17 * K,
)

# ---- 框内：山 + 太阳（裁剪在框内）----
inner = Image.new("RGBA", (S, S), (0, 0, 0, 0))
di = ImageDraw.Draw(inner)
di.polygon(
    [(140 * K, 356 * K), (232 * K, 236 * K), (306 * K, 330 * K), (340 * K, 296 * K), (352 * K, 356 * K)],
    fill=(255, 255, 255, 255),
)
di.ellipse([268 * K, 176 * K, 316 * K, 224 * K], fill=(255, 255, 255, 255))

clip = Image.new("L", (S, S), 0)
ImageDraw.Draw(clip).rounded_rectangle(
    [bx0 + 9 * K, by0 + 9 * K, bx1 - 9 * K, by1 - 9 * K], radius=18 * K, fill=255)
img.paste(inner, (0, 0), Image.composite(clip, Image.new("L", (S, S), 0), inner.split()[3]))

# 山压住了相框内的描边，重新描一遍框线保证轮廓清晰
d = ImageDraw.Draw(img)
d.rounded_rectangle(
    [bx0, by0, bx1, by1], radius=26 * K,
    outline=(255, 255, 255, 255), width=17 * K,
)

out = img.resize((512, 512), Image.LANCZOS)
out.save("app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
out.save("app_256.png")
print("icon ok")
