"""
말풍선 합성기 (Phase 2)

toon.json 을 읽어서 각 컷 이미지에 말풍선과 대사를 얹고,
인스타그램 규격(1080x1350, 4:5) PNG 로 저장한다.

실행:
    python scripts/compose.py content/2026-08-31-winter-heatmat

컷 그림이 아직 없으면(=Phase 3 전) 자리표시용 그림을 자동으로 그려서
합성 결과를 먼저 확인할 수 있게 한다. 나중에 진짜 그림을
<콘티폴더>/art/cut1.png ... 로 넣어두면 그걸 자동으로 집어 쓴다.
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# --- 설정 -----------------------------------------------------------------
FONT_DIALOGUE = "assets/fonts/GothicA1-Bold.ttf"      # 말풍선 대사
FONT_NOTE = "assets/fonts/NanumGothic-Regular.ttf"    # 고지 문구 등 작은 글씨

FONT_SIZE = 46          # 대사 글자 크기
LINE_GAP = 14           # 줄 간격
PAD_X, PAD_Y = 34, 26   # 말풍선 안쪽 여백
MARGIN = 56             # 캔버스 가장자리 여백
BALLOON_MAX_RATIO = 0.62  # 말풍선 최대 폭 (캔버스 대비)

INK = (28, 28, 34)          # 글자/테두리 색
BALLOON_BG = (255, 255, 255)
STROKE = 4                  # 말풍선 테두리 두께


# --- 한글 줄바꿈 -----------------------------------------------------------
def wrap_korean(text, font, max_width):
    """한글 대사를 max_width 안에 들어가도록 줄을 나눈다.

    한국어는 어절(띄어쓰기) 단위로 끊어야 읽기 자연스럽다.
    단, 어절 하나가 통째로 너무 길면 그때만 글자 단위로 쪼갠다.
    """
    def width(s):
        box = font.getbbox(s)
        return box[2] - box[0]

    lines = []
    for para in text.split("\n"):
        if not para.strip():
            lines.append("")
            continue

        line = ""
        for word in para.split(" "):
            trial = word if not line else line + " " + word

            if width(trial) <= max_width:
                line = trial
                continue

            # 지금 줄을 확정하고 새 줄 시작
            if line:
                lines.append(line)
                line = ""

            # 어절 하나가 한 줄보다 길면 글자 단위로 강제 분리
            if width(word) > max_width:
                chunk = ""
                for ch in word:
                    if width(chunk + ch) <= max_width:
                        chunk += ch
                    else:
                        lines.append(chunk)
                        chunk = ch
                line = chunk
            else:
                line = word

        if line:
            lines.append(line)

    return lines


def text_block_size(lines, font):
    """줄 목록이 차지하는 전체 크기(폭, 높이)를 잰다."""
    w = 0
    for ln in lines:
        box = font.getbbox(ln if ln else " ")
        w = max(w, box[2] - box[0])
    line_h = font.getbbox("가힣")[3]
    h = len(lines) * line_h + (len(lines) - 1) * LINE_GAP
    return w, h, line_h


# --- 말풍선 ---------------------------------------------------------------
def balloon_box(canvas_size, box_w, box_h, pos, bottom_reserve=0):
    """말풍선을 캔버스 어느 구석에 놓을지 계산한다.

    bottom_reserve: 하단에 이미 뭔가(고지 문구 띠)가 있으면 그만큼 위로 올린다.
    이게 없으면 하단 말풍선이 고지 문구를 덮어버린다.
    """
    W, H = canvas_size
    x = MARGIN if "left" in pos else W - MARGIN - box_w
    y = MARGIN if "top" in pos else H - MARGIN - bottom_reserve - box_h
    return int(x), int(y), int(x + box_w), int(y + box_h)


def draw_tail(draw, box, tail):
    """말풍선 꼬리(말하는 사람 쪽을 가리키는 삼각형)를 그린다."""
    x0, y0, x1, y1 = box
    size = 46

    if tail.startswith("down"):
        base_y, tip_y = y1, y1 + size
    else:
        base_y, tip_y = y0, y0 - size

    if tail.endswith("right"):
        bx = x0 + (x1 - x0) * 0.68
        tip_x = bx + size * 0.7
    else:
        bx = x0 + (x1 - x0) * 0.32
        tip_x = bx - size * 0.7

    pts = [(bx - size * 0.35, base_y), (bx + size * 0.35, base_y), (tip_x, tip_y)]
    draw.polygon(pts, fill=BALLOON_BG)
    # 밑변은 말풍선 몸통과 이어지므로 두 변만 테두리를 그린다
    draw.line([pts[0], pts[2]], fill=INK, width=STROKE)
    draw.line([pts[1], pts[2]], fill=INK, width=STROKE)


def draw_balloon(img, text, pos, tail, bottom_reserve=0):
    """이미지 위에 말풍선 + 대사를 얹는다."""
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_DIALOGUE, FONT_SIZE)

    max_text_w = int(img.width * BALLOON_MAX_RATIO) - PAD_X * 2
    lines = wrap_korean(text, font, max_text_w)
    tw, th, line_h = text_block_size(lines, font)

    box = balloon_box(img.size, tw + PAD_X * 2, th + PAD_Y * 2, pos, bottom_reserve)

    draw_tail(draw, box, tail)
    draw.rounded_rectangle(box, radius=28, fill=BALLOON_BG, outline=INK, width=STROKE)

    # 대사는 가운데 정렬
    ty = box[1] + PAD_Y
    for ln in lines:
        lw = font.getbbox(ln if ln else " ")[2] - font.getbbox(ln if ln else " ")[0]
        tx = box[0] + (box[2] - box[0] - lw) / 2
        draw.text((tx, ty), ln, font=font, fill=INK)
        ty += line_h + LINE_GAP

    return img


def draw_disclosure(img, text):
    """제휴 고지 문구를 이미지 하단에 띠로 얹는다.

    캡션에도 넣지만, 캡션은 '더보기'로 접히거나 잘릴 수 있어서
    이미지에도 남긴다. 고지는 법적 의무라 빠지면 안 된다.
    """
    draw = ImageDraw.Draw(img, "RGBA")
    font = ImageFont.truetype(FONT_NOTE, 24)

    lines = wrap_korean(text, font, img.width - MARGIN * 2)
    tw, th, line_h = text_block_size(lines, font)
    bar_h = th + 32

    draw.rectangle([0, img.height - bar_h, img.width, img.height], fill=(0, 0, 0, 165))
    ty = img.height - bar_h + 16
    for ln in lines:
        lw = font.getbbox(ln)[2] - font.getbbox(ln)[0]
        draw.text(((img.width - lw) / 2, ty), ln, font=font, fill=(255, 255, 255))
        ty += line_h + LINE_GAP

    return bar_h


# --- 컷 그림 --------------------------------------------------------------
MOOD = {
    "hook": (86, 108, 148), "problem": (104, 118, 140),
    "escalation": (48, 58, 92), "turn": (128, 118, 140),
    "solution": (206, 132, 74), "cta": (190, 138, 96),
}


def placeholder(size, cut):
    """진짜 그림이 없을 때 쓰는 자리표시 이미지.

    컷 역할에 따라 색을 달리해서 흐름(차가움 → 따뜻함)이 눈에 보이게 한다.
    """
    img = Image.new("RGB", size, MOOD.get(cut["role"], (110, 110, 120)))
    draw = ImageDraw.Draw(img)
    big = ImageFont.truetype(FONT_DIALOGUE, 150)
    small = ImageFont.truetype(FONT_NOTE, 30)

    label = f"{cut['n']}"
    lw = big.getbbox(label)[2] - big.getbbox(label)[0]
    draw.text(((size[0] - lw) / 2, size[1] * 0.30), label, font=big, fill=(255, 255, 255, 90))

    for i, ln in enumerate(wrap_korean(cut["scene"], small, size[0] - 200)):
        lw = small.getbbox(ln)[2] - small.getbbox(ln)[0]
        draw.text(((size[0] - lw) / 2, size[1] * 0.52 + i * 42), ln,
                  font=small, fill=(255, 255, 255, 160))

    # 안내문은 화면 한가운데 근처에 둔다. 아래쪽에 두면 하단 말풍선과 겹친다.
    note = "[ 자리표시 이미지 — Phase 3에서 실제 그림으로 교체 ]"
    nw = small.getbbox(note)[2] - small.getbbox(note)[0]
    draw.text(((size[0] - nw) / 2, size[1] * 0.66), note, font=small, fill=(255, 255, 255, 120))
    return img


def load_art(content_dir, n, size):
    """<콘티폴더>/art/cutN.png 를 찾아 캔버스에 맞게 잘라 넣는다."""
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = content_dir / "art" / f"cut{n}.{ext}"
        if p.exists():
            img = Image.open(p).convert("RGB")
            # 비율 유지하며 캔버스를 덮도록 확대 후 가운데 크롭
            scale = max(size[0] / img.width, size[1] / img.height)
            img = img.resize((round(img.width * scale), round(img.height * scale)))
            left = (img.width - size[0]) // 2
            top = (img.height - size[1]) // 2
            return img.crop((left, top, left + size[0], top + size[1]))
    return None


# --- 메인 -----------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print("사용법: python scripts/compose.py <콘티폴더>")
        print("예시:   python scripts/compose.py content/2026-08-31-winter-heatmat")
        sys.exit(1)

    content_dir = Path(sys.argv[1])
    toon_path = content_dir / "toon.json"

    if not toon_path.exists():
        print(f"❌ {toon_path} 가 없습니다. 경로를 확인하세요.")
        sys.exit(1)

    toon = json.loads(toon_path.read_text(encoding="utf-8"))

    disclosure = toon.get("disclosure", "").strip()
    if not disclosure:
        print("❌ toon.json 에 disclosure(제휴 고지 문구)가 비어 있습니다.")
        print("   제휴 게시물의 고지는 법적 의무라 없으면 만들지 않습니다.")
        sys.exit(1)

    size = tuple(toon["format"]["canvas"])
    out_dir = content_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    used_placeholder = 0
    for cut in toon["cuts"]:
        img = load_art(content_dir, cut["n"], size)
        if img is None:
            img = placeholder(size, cut)
            used_placeholder += 1

        # 고지 문구를 먼저 그리고, 그 높이만큼 말풍선을 피하게 한다.
        # 순서를 바꾸면 하단 말풍선이 고지 문구를 덮는다.
        reserve = 0
        if cut is toon["cuts"][-1]:
            reserve = draw_disclosure(img, disclosure) + 16

        if cut["dialogue"].strip():
            img = draw_balloon(img, cut["dialogue"], cut["balloon"]["pos"],
                               cut["balloon"]["tail"], bottom_reserve=reserve)

        out = out_dir / f"cut{cut['n']}.png"
        img.save(out)
        print(f"  ✅ {out}")

    print()
    print(f"완성: {len(toon['cuts'])}컷 → {out_dir}/")
    if used_placeholder:
        print(f"⚠️  {used_placeholder}컷이 자리표시 이미지입니다.")
        print(f"   진짜 그림은 {content_dir}/art/cut1.png ... 로 넣으면 자동으로 바뀝니다.")


if __name__ == "__main__":
    main()
