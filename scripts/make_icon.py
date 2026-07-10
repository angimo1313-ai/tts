"""Voice Studio 앱 아이콘(.ico) 생성 — 애플 감성 블루 라운드 스퀘어 + ◐ 로고."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "static" / "icon.ico"

SIZE = 256
ACCENT = (0, 113, 227, 255)   # #0071e3
ACCENT2 = (10, 132, 255, 255)


def rounded(size, radius, fill):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=fill)
    return img


def main():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    # 배경 그라디언트(수직) + 라운드 마스크
    grad = Image.new("RGBA", (SIZE, SIZE))
    for y in range(SIZE):
        t = y / SIZE
        r = int(ACCENT[0] * (1 - t) + ACCENT2[0] * t)
        g = int(ACCENT[1] * (1 - t) + ACCENT2[1] * t)
        b = int(ACCENT[2] * (1 - t) + ACCENT2[2] * t)
        for x in range(SIZE):
            grad.putpixel((x, y), (r, g, b, 255))
    mask = rounded(SIZE, 56, (255, 255, 255, 255)).split()[3]
    img.paste(grad, (0, 0), mask)

    # ◐ 반원 로고 (흰색)
    d = ImageDraw.Draw(img)
    cx, cy, rad = SIZE // 2, SIZE // 2, 66
    d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(255, 255, 255, 255), width=14)
    d.pieslice([cx - rad, cy - rad, cx + rad, cy + rad], 90, 270, fill=(255, 255, 255, 255))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon ->", OUT)


if __name__ == "__main__":
    main()
