"""
툰 → 스레드 이슈 본문 만들기 (Phase 5)

완성된 툰 이미지를 GitHub 이슈 본문으로 엮는다.
그 이슈를 `scripts/post_threads.py` 가 집어가서 스레드에 올린다.

**말풍선까지 들어간 완성 이미지를 사람이 직접 만든다** (2026-10-29 사용자 결정).
그래서 `compose.py` 합성 단계는 거치지 않는다. 이미지는 `art/` 에서 바로 가져온다.
`compose.py` 는 남겨두지만 쓰지 않는다 — 나중에 말풍선을 코드로 얹고 싶어지면 그때 쓴다.

실행:
    python scripts/make_issue.py content/2026-10-29-첫툰
    python scripts/make_issue.py content/... --now                  # 승인 없이 바로 예약
    python scripts/make_issue.py content/... --caption "본문 글"     # toon.json 없이

이미지는 `<콘티폴더>/art/cut1.png`, `cut2.png` … 순서대로 넣는다.
번호가 곧 캐러셀 순서이고, **1번이 썸네일**이다.

만들어지는 이슈
    제목:  초안 겨울 온열매트          ← 사람이 '예약' 으로 바꾸면 발행된다
    본문:  캡션 + 해시태그 + 컷 이미지 6장
           (제휴 링크가 있을 때만) 고지 문구는 본문에, 링크는 '=== 첫 댓글 ===' 아래

왜 '초안' 으로 만드는가
    계획서 원칙 2 — 완전자동 금지. 발행 직전 사람 검수를 남긴다.
    제목 앞 두 글자를 '예약' 으로 바꾸는 것이 승인이다.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# 스레드 글자 수 제한. link 저장소의 검증된 코드와 같은 값을 쓴다.
MAX_CHARS = 500
MAX_CAROUSEL = 20
REPLY_MARK = "=== 첫 댓글 ==="

ART_EXTS = ("png", "jpg", "jpeg", "webp")


def repo_slug():
    """origin 주소에서 owner/repo 를 뽑는다. 이미지 공개 주소를 만들 때 쓴다."""
    try:
        url = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", url)
    return m.group(1) if m else None


def committed(path):
    """이 파일이 git 에 올라가 있는지. 안 올라가면 공개 주소가 생기지 않는다."""
    r = subprocess.run(["git", "ls-files", "--error-unmatch", str(path)],
                       capture_output=True, text=True)
    return r.returncode == 0


# 스레드가 받아주는 이미지 형식. webp 는 거부될 수 있어 경고한다.
SAFE_EXTS = ("png", "jpg", "jpeg")


def find_art(content_dir):
    """art/cut1.*, cut2.* ... 를 번호 순서대로 찾는다. 번호가 캐러셀 순서다."""
    art_dir = content_dir / "art"
    found = []
    n = 1
    while True:
        hit = None
        for ext in ART_EXTS:
            p = art_dir / f"cut{n}.{ext}"
            if p.exists():
                hit = p
                break
        if hit is None:
            break
        found.append(hit)
        n += 1
    return found


def build_body(toon, content_dir, slug, ref, caption=None, tags=None):
    """이슈 본문을 만든다. (본문, 경고목록) 을 돌려준다."""
    warns = []

    link = toon.get("product", {}).get("affiliate", {}).get("url", "").strip()
    disclosure = toon.get("disclosure", "").strip()

    # --- 본문 글 ---
    parts = []
    if disclosure:
        # 고지는 본문 맨 앞에. 댓글은 접힐 수 있어서 '숨겼다' 고 볼 여지가 생긴다.
        parts.append(disclosure)
    body_caption = caption if caption is not None else toon.get("caption", "")
    parts.append(body_caption.strip())
    tag_list = tags if tags is not None else toon.get("hashtags", [])
    tag_line = " ".join("#" + t.lstrip("#") for t in tag_list)
    if tag_line:
        parts.append(tag_line)
    text = "\n\n".join(p for p in parts if p)

    if not text.strip():
        warns.append("본문 글이 비어 있습니다. --caption 으로 넣거나 toon.json 에 caption 을 쓰세요.")
    if len(text) > MAX_CHARS:
        warns.append(f"본문이 {len(text)}자입니다. 스레드는 {MAX_CHARS}자까지라 잘립니다.")

    # --- 완성 이미지 (art/) ---
    arts = find_art(content_dir)
    if not arts:
        print(f"❌ {content_dir}/art/ 에 이미지가 없습니다.")
        print("   완성한 툰을 art/cut1.png, cut2.png ... 순서대로 넣어 주세요.")
        sys.exit(1)

    if len(arts) > MAX_CAROUSEL:
        warns.append(f"이미지가 {len(arts)}장인데 스레드 캐러셀은 {MAX_CAROUSEL}장까지입니다. "
                     f"뒤 {len(arts) - MAX_CAROUSEL}장은 빠집니다.")

    lines = [text, ""]
    for i, art in enumerate(arts[:MAX_CAROUSEL], 1):
        if art.suffix.lstrip(".").lower() not in SAFE_EXTS:
            warns.append(f"{art.name} 은 {art.suffix} 형식입니다. "
                         "스레드가 거부할 수 있으니 png 나 jpg 로 바꾸는 편이 안전합니다.")
        if not committed(art):
            warns.append(f"{art} 가 아직 커밋되지 않았습니다. "
                         "커밋·푸시해야 스레드가 이미지를 가져갈 수 있습니다.")
        lines.append(f"![컷{i}](https://raw.githubusercontent.com/{slug}/{ref}/{art.as_posix()})")

    # --- 첫 댓글 (제휴 링크) ---
    if link:
        lines += ["", REPLY_MARK, "", link]

    return "\n".join(lines), warns, arts


def main():
    ap = argparse.ArgumentParser(description="완성한 툰을 스레드 이슈 본문으로 엮는다")
    ap.add_argument("content_dir", help="콘티 폴더 (예: content/2026-10-29-첫툰)")
    ap.add_argument("--now", action="store_true",
                    help="'초안' 대신 '예약 지금' 으로 만든다 (검수 건너뜀)")
    ap.add_argument("--caption", default=None,
                    help="본문 글. 안 주면 toon.json 의 caption 을 쓴다")
    ap.add_argument("--tags", default=None,
                    help="해시태그. 쉼표나 공백으로 구분. 안 주면 toon.json 의 hashtags")
    ap.add_argument("--title", default="",
                    help="이슈 제목에 쓸 이름. 안 주면 toon.json 이나 폴더명에서 가져온다")
    ap.add_argument("--ref", default="main",
                    help="이미지를 가져올 git 참조 (기본 main)")
    ap.add_argument("-o", "--out", default="", help="본문을 파일로 저장할 경로")
    args = ap.parse_args()

    content_dir = Path(args.content_dir)
    if not content_dir.is_dir():
        print(f"❌ {content_dir} 폴더가 없습니다.")
        sys.exit(1)

    slug = repo_slug()
    if not slug:
        print("❌ git 저장소 주소를 읽지 못했습니다. 이미지 공개 주소를 만들 수 없습니다.")
        sys.exit(1)

    # toon.json 은 있으면 쓰고 없으면 넘어간다.
    # 완성 이미지를 직접 올리는 경우 콘티 파일이 없을 수 있다.
    toon_path = content_dir / "toon.json"
    toon = json.loads(toon_path.read_text(encoding="utf-8")) if toon_path.exists() else {}

    tags = None
    if args.tags is not None:
        tags = [t for t in re.split(r"[,\s]+", args.tags) if t]

    body, warns, arts = build_body(toon, content_dir, slug, args.ref, args.caption, tags)

    name = (args.title or toon.get("product", {}).get("name") or content_dir.name)
    title = f"예약 지금 {name}" if args.now else f"초안 {name}"

    for w in warns:
        print(f"⚠️  {w}")
    if warns:
        print()

    print(f"이미지 {len(arts)}장: {', '.join(a.name for a in arts)}")
    print(f"제목: {title}")
    print("─" * 60)
    print(body)
    print("─" * 60)

    if args.out:
        Path(args.out).write_text(body, encoding="utf-8")
        print(f"\n본문을 {args.out} 에 저장했습니다.")

    print()
    print("다음:")
    print("  1) 이미지를 커밋·푸시한다 (안 하면 스레드가 그림을 못 가져간다)")
    if args.now:
        print("  2) 이 제목·본문으로 이슈를 만들면 바로 올라간다")
    else:
        print("  2) 이 제목·본문으로 이슈를 만든다")
        print("  3) 눈으로 확인한 뒤 제목을 '초안' → '예약 지금' 으로 바꾸면 발행된다")


if __name__ == "__main__":
    main()
