"""
검수용 대지(contact sheet) 만들기

완성된 컷들을 한 장에 모아서 폰에서 한눈에 확인할 수 있게 한다.
계획서의 '사람 검수' 단계에서 쓰는 도구다.

실행:
    python scripts/contact_sheet.py content/2026-08-31-winter-heatmat
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = "assets/fonts/NanumGothic-Bold.ttf"
COLS = 3
THUMB_W = 460
GAP = 18
HEADER = 86
BG = (245, 245, 247)


def main():
    if len(sys.argv) < 2:
        print("사용법: python scripts/contact_sheet.py <콘티폴더>")
        sys.exit(1)

    content_dir = Path(sys.argv[1])
    toon = json.loads((content_dir / "toon.json").read_text(encoding="utf-8"))
    cuts = toon["cuts"]

    images = []
    for cut in cuts:
        p = content_dir / "out" / f"cut{cut['n']}.png"
        if not p.exists():
            print(f"❌ {p} 가 없습니다. 먼저 compose.py 를 실행하세요.")
            sys.exit(1)
        img = Image.open(p)
        h = round(THUMB_W * img.height / img.width)
        images.append(img.resize((THUMB_W, h)))

    thumb_h = images[0].height
    rows = (len(images) + COLS - 1) // COLS
    W = COLS * THUMB_W + (COLS + 1) * GAP
    H = HEADER + rows * (thumb_h + 34) + (rows + 1) * GAP

    sheet = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(sheet)

    title = ImageFont.truetype(FONT, 34)
    label = ImageFont.truetype(FONT, 24)

    head = f"{toon['meta']['keyword']}  ·  {len(cuts)}컷  ·  {toon['meta']['status']}"
    draw.text((GAP, 26), head, font=title, fill=(30, 30, 36))

    for i, (img, cut) in enumerate(zip(images, cuts)):
        r, c = divmod(i, COLS)
        x = GAP + c * (THUMB_W + GAP)
        y = HEADER + GAP + r * (thumb_h + 34 + GAP)
        sheet.paste(img, (x, y))
        draw.rectangle([x, y, x + THUMB_W, y + thumb_h], outline=(200, 200, 206), width=2)
        draw.text((x + 4, y + thumb_h + 6), f"컷 {cut['n']} · {cut['role']}",
                  font=label, fill=(90, 90, 100))

    out = content_dir / "out" / "_contact_sheet.png"
    sheet.save(out)
    print(f"✅ {out}  ({W}x{H})")


if __name__ == "__main__":
    main()
