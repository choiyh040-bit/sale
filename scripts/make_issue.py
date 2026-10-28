"""
툰 → 스레드 이슈 본문 만들기 (Phase 5)

합성이 끝난 툰 한 건을 GitHub 이슈 본문으로 엮는다.
그 이슈를 `scripts/post_threads.py` 가 집어가서 스레드에 올린다.

실행:
    python scripts/make_issue.py content/2026-09-03-겨울-온열매트
    python scripts/make_issue.py content/... --now      # 승인 없이 바로 예약
    python scripts/make_issue.py content/... --force    # 자리표시 그림이어도 진행

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


def has_art(content_dir, n):
    """사람이 그린 원본이 있는지. 없으면 out/ 의 그림은 자리표시다."""
    return any((content_dir / "art" / f"cut{n}.{ext}").exists() for ext in ART_EXTS)


def build_body(toon, content_dir, slug, ref):
    """이슈 본문을 만든다. (본문, 경고목록) 을 돌려준다."""
    warns = []
    cuts = toon["cuts"]

    link = toon.get("product", {}).get("affiliate", {}).get("url", "").strip()
    disclosure = toon.get("disclosure", "").strip()

    # --- 본문 글 ---
    parts = []
    if disclosure:
        # 고지는 본문 맨 앞에. 댓글은 접힐 수 있어서 '숨겼다' 고 볼 여지가 생긴다.
        parts.append(disclosure)
    parts.append(toon["caption"].strip())
    tags = " ".join("#" + t.lstrip("#") for t in toon.get("hashtags", []))
    if tags:
        parts.append(tags)
    text = "\n\n".join(p for p in parts if p)

    if len(text) > MAX_CHARS:
        warns.append(f"본문이 {len(text)}자입니다. 스레드는 {MAX_CHARS}자까지라 잘립니다.")

    # --- 컷 이미지 ---
    lines = [text, ""]
    missing_art = []
    for cut in cuts[:MAX_CAROUSEL]:
        n = cut["n"]
        png = content_dir / "out" / f"cut{n}.png"
        if not png.exists():
            print(f"❌ {png} 가 없습니다. 먼저 합성하세요:")
            print(f"      python scripts/compose.py {content_dir}")
            sys.exit(1)
        if not committed(png):
            warns.append(f"{png} 가 아직 커밋되지 않았습니다. "
                         "커밋·푸시해야 스레드가 이미지를 가져갈 수 있습니다.")
        if not has_art(content_dir, n):
            missing_art.append(n)
        lines.append(f"![컷{n}](https://raw.githubusercontent.com/{slug}/{ref}/{png.as_posix()})")

    if len(cuts) > MAX_CAROUSEL:
        warns.append(f"컷이 {len(cuts)}개인데 스레드 캐러셀은 {MAX_CAROUSEL}장까지입니다.")

    # --- 첫 댓글 (제휴 링크) ---
    if link:
        lines += ["", REPLY_MARK, "", link]

    return "\n".join(lines), warns, missing_art


def main():
    ap = argparse.ArgumentParser(description="툰 한 건을 스레드 이슈 본문으로 엮는다")
    ap.add_argument("content_dir", help="콘티 폴더 (예: content/2026-09-03-겨울-온열매트)")
    ap.add_argument("--now", action="store_true",
                    help="'초안' 대신 '예약 지금' 으로 만든다 (검수 건너뜀)")
    ap.add_argument("--force", action="store_true",
                    help="자리표시 그림이어도 진행한다")
    ap.add_argument("--ref", default="main",
                    help="이미지를 가져올 git 참조 (기본 main)")
    ap.add_argument("-o", "--out", default="",
                    help="본문을 파일로 저장할 경로")
    args = ap.parse_args()

    content_dir = Path(args.content_dir)
    toon_path = content_dir / "toon.json"
    if not toon_path.exists():
        print(f"❌ {toon_path} 가 없습니다.")
        sys.exit(1)

    slug = repo_slug()
    if not slug:
        print("❌ git 저장소 주소를 읽지 못했습니다. 이미지 공개 주소를 만들 수 없습니다.")
        sys.exit(1)

    toon = json.loads(toon_path.read_text(encoding="utf-8"))
    body, warns, missing_art = build_body(toon, content_dir, slug, args.ref)

    # 자리표시 그림이 섞이면 빈 만화가 올라간다. 기본값은 막는다.
    if missing_art and not args.force:
        print(f"❌ 컷 {', '.join(map(str, missing_art))} 에 그림이 없습니다.")
        print(f"   지금 out/ 에 있는 건 자리표시 이미지라 그대로 올라가면 빈 만화가 됩니다.")
        print(f"   그림을 {content_dir}/art/cut{missing_art[0]}.png 처럼 넣고 다시 합성하세요:")
        print(f"      python scripts/compose.py {content_dir}")
        print("   그래도 진행하려면 --force")
        sys.exit(1)

    keyword = toon.get("product", {}).get("name") or content_dir.name
    title = f"예약 지금 {keyword}" if args.now else f"초안 {keyword}"

    for w in warns:
        print(f"⚠️  {w}")
    if warns:
        print()

    print(f"제목: {title}")
    print("─" * 60)
    print(body)
    print("─" * 60)

    if args.out:
        Path(args.out).write_text(body, encoding="utf-8")
        print(f"\n본문을 {args.out} 에 저장했습니다.")

    print()
    if args.now:
        print("다음: 이 제목·본문으로 이슈를 만들면 바로 올라갑니다.")
    else:
        print("다음: 이 제목·본문으로 이슈를 만드세요.")
        print(f"      검수한 뒤 제목을 '초안' → '예약 지금' 으로 바꾸면 발행됩니다.")


if __name__ == "__main__":
    main()
