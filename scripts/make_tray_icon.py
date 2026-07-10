#!/usr/bin/env python3
"""从 icon.png 生成 macOS 菜单栏 tray 图标

1. 裁掉透明边距
2. 补成正方形（居中）
3. 转为黑色剪影
4. 缩放为 18x18 / 36x36
"""

from PIL import Image


def main() -> None:
    src = Image.open("resources/icon.png").convert("RGBA")

    # 裁掉透明边距
    bbox = src.getbbox()
    if bbox:
        src = src.crop(bbox)

    # 补成正方形，居中放置
    w, h = src.size
    side = max(w, h)
    padded = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    padded.paste(src, ((side - w) // 2, (side - h) // 2))
    src = padded

    # 将所有不透明像素变为黑色
    pixels = src.load()
    for y in range(src.height):
        for x in range(src.width):
            r, g, b, a = pixels[x, y]
            if a > 0:
                pixels[x, y] = (0, 0, 0, a)

    # 覆盖原 icon.png
    src.save("resources/icon.png")
    print(f"Updated icon.png  ({src.size[0]}x{src.size[1]})")

    # 生成 tray 图标
    for suffix, size in [("", 18), ("@2x", 36)]:
        resized = src.resize((size, size), Image.Resampling.LANCZOS)
        out = f"resources/tray_icon{suffix}.png"
        resized.save(out)
        print(f"Saved {out}  ({size}x{size})")


if __name__ == "__main__":
    main()
