"""
소재 큐 (Phase 9)

"무슨 상품으로 콘티를 만들지" 를 쌓아두는 곳. content/queue.json 을 다룬다.

지금은 사람이 그록 앱 결과를 보고 채우고, 나중에 grok_trends.py 가 같은 파일을
자동으로 채운다. 채우는 주체가 바뀌어도 뒷단(make_toon.py)은 안 바뀐다.

실행:
    python scripts/queue.py add "겨울 온열매트" --why "한파로 난방비 얘기 많음" --heat 상
    python scripts/queue.py list
    python scripts/queue.py next
    python scripts/queue.py done "겨울 온열매트"
    python scripts/queue.py drop "겨울 온열매트" --note "쿠팡에 없음"

자세한 사용법은 docs/SOURCING.md.
"""

import argparse
import json
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

QUEUE = Path("content/queue.json")
SCHEMA_VERSION = 1

HEATS = ["상", "중", "하"]
SOURCES = ["grok", "coupang", "naver", "manual"]
STATUSES = ["todo", "doing", "done", "drop"]

# 트렌드는 식는다. 이 날수를 넘긴 todo 는 재검토 대상으로 표시한다.
STALE_DAYS = 14

# 큐가 길어지면 오래된 소재가 썩는다. 계획서 성공 기준이 주 3~5건이므로
# todo 가 이 개수를 넘으면 경고한다. (막지는 않는다 — 판단은 사람이 한다)
TODO_SOFT_LIMIT = 5


def w(text):
    """화면에서 차지하는 칸 수. 한글·이모지는 2칸이다."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in str(text))


def pad(text, width):
    """칸 수 기준으로 오른쪽을 채운다. f-string 의 :<N 은 글자 수로 세서 한글 표가 어긋난다."""
    text = str(text)
    return text + " " * max(0, width - w(text))


def load():
    if not QUEUE.exists():
        return {"schema_version": SCHEMA_VERSION, "updated": str(date.today()), "items": []}
    try:
        data = json.loads(QUEUE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"❌ {QUEUE} 를 읽을 수 없습니다: {e}")
        print("   파일이 손상됐습니다. git 으로 되돌리세요:")
        print(f"      git checkout {QUEUE}")
        sys.exit(1)
    data.setdefault("items", [])
    return data


def save(data):
    data["updated"] = str(date.today())
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def find(items, keyword):
    """키워드로 항목을 찾는다. 정확히 일치하는 게 없으면 부분 일치도 본다."""
    for it in items:
        if it["keyword"] == keyword:
            return it
    hits = [it for it in items if keyword in it["keyword"]]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        print(f"❌ '{keyword}' 로 여러 개가 걸립니다. 정확히 적어주세요:")
        for it in hits:
            print(f"   - {it['keyword']}")
        sys.exit(1)
    return None


def days_old(item):
    try:
        added = datetime.strptime(item.get("added", ""), "%Y-%m-%d").date()
    except ValueError:
        return 0
    return (date.today() - added).days


# --- 명령들 ---------------------------------------------------------------


def cmd_add(args):
    data = load()
    items = data["items"]

    if find(items, args.keyword) and any(i["keyword"] == args.keyword for i in items):
        print(f"❌ '{args.keyword}' 는 이미 큐에 있습니다.")
        print("   상태를 바꾸려면:  python scripts/queue.py done/drop \"키워드\"")
        sys.exit(1)

    item = {
        "keyword": args.keyword,
        "why": args.why,
        "heat": args.heat,
        "source": args.source,
        "coupang": not args.no_coupang,
        "status": "todo",
        "added": str(date.today()),
        "note": args.note,
    }
    items.append(item)
    save(data)

    print(f"✅ 큐에 넣었습니다: {args.keyword}")
    if args.no_coupang:
        print("   ⚠️  쿠팡에서 못 사는 물건으로 표시했습니다. 링크를 못 걸면 수익이 0입니다.")

    todos = [i for i in items if i["status"] == "todo"]
    if len(todos) > TODO_SOFT_LIMIT:
        print()
        print(f"   ⚠️  대기 중인 소재가 {len(todos)}개입니다 (권장 {TODO_SOFT_LIMIT}개 이하).")
        print("       트렌드는 식습니다. 쌓기보다 만드는 게 낫습니다.")


def cmd_list(args):
    data = load()
    items = data["items"]
    if not items:
        print("큐가 비어 있습니다.")
        print()
        print("   폰에서 그록에게 물어보고 채우세요 — 질문 템플릿은 docs/SOURCING.md 에 있습니다.")
        return

    shown = [i for i in items if args.all or i["status"] in ("todo", "doing")]
    if not shown:
        print("대기 중인 소재가 없습니다. (--all 로 끝난 것까지 봅니다)")
        return

    mark = {"todo": "⬜", "doing": "🔨", "done": "✅", "drop": "✖️"}
    kw_width = max([w(i["keyword"]) for i in shown] + [w("키워드")]) + 2
    print(f"{pad('상태', 5)}{pad('화제', 5)}{pad('키워드', kw_width)}{pad('경과', 8)}이유")
    print("─" * (18 + kw_width + 30))
    for it in shown:
        old = days_old(it)
        stale = it["status"] == "todo" and old >= STALE_DAYS
        age = f"{old}일{'⚠️' if stale else ''}"
        cp = "" if it.get("coupang", True) else " ❌쿠팡X"
        print(
            pad(mark.get(it["status"], "?"), 5)
            + pad(it.get("heat", "-"), 5)
            + pad(it["keyword"], kw_width)
            + pad(age, 8)
            + f"{it.get('why', '')}{cp}"
        )

    stales = [i for i in shown if i["status"] == "todo" and days_old(i) >= STALE_DAYS]
    if stales:
        print()
        print(f"⚠️  {STALE_DAYS}일 넘게 대기 중인 소재 {len(stales)}건. 아직 유효한지 다시 보세요.")


def cmd_next(args):
    """다음에 만들 것 하나를 고른다. 화제도 높고 오래된 것부터."""
    data = load()
    todos = [
        i for i in data["items"] if i["status"] == "todo" and i.get("coupang", True)
    ]
    if not todos:
        print("만들 수 있는 소재가 없습니다.")
        skipped = [
            i
            for i in data["items"]
            if i["status"] == "todo" and not i.get("coupang", True)
        ]
        if skipped:
            print(f"   (쿠팡에서 못 사는 것 {len(skipped)}건은 제외했습니다)")
        return

    order = {"상": 0, "중": 1, "하": 2}
    todos.sort(key=lambda i: (order.get(i.get("heat"), 3), -days_old(i)))
    pick = todos[0]

    pick["status"] = "doing"
    save(data)

    print(f"▶ 다음 소재: {pick['keyword']}")
    if pick.get("why"):
        print(f"   왜: {pick['why']}")
    print(f"   화제도 {pick.get('heat', '-')} / 큐에 들어온 지 {days_old(pick)}일")
    print()
    print("   콘티 만들기:")
    print(f'      python scripts/make_toon.py "{pick["keyword"]}"')


def _set_status(keyword, status, note):
    data = load()
    it = find(data["items"], keyword)
    if not it:
        print(f"❌ 큐에 '{keyword}' 가 없습니다.")
        print("   목록 보기:  python scripts/queue.py list --all")
        sys.exit(1)
    it["status"] = status
    if note:
        it["note"] = note
    save(data)
    return it


def cmd_done(args):
    it = _set_status(args.keyword, "done", args.note)
    print(f"✅ 완료 처리: {it['keyword']}")


def cmd_drop(args):
    it = _set_status(args.keyword, "drop", args.note)
    print(f"✖️  버림 처리: {it['keyword']}")
    if args.note:
        print(f"   이유: {args.note}")
    else:
        print("   ⚠️  이유를 안 남기면 나중에 왜 버렸는지 모릅니다. --note 를 쓰세요.")


def main():
    ap = argparse.ArgumentParser(description="소재 큐를 다룬다 (docs/SOURCING.md 참조)")
    sub = ap.add_subparsers(dest="cmd")

    a = sub.add_parser("add", help="소재 추가")
    a.add_argument("keyword", help="상품 키워드 (브랜드명 말고 일반명사)")
    a.add_argument("--why", default="", help="왜 지금 화제인지")
    a.add_argument("--heat", default="중", choices=HEATS, help="화제도 (기본 중)")
    a.add_argument("--source", default="manual", choices=SOURCES, help="어디서 나왔나")
    a.add_argument("--no-coupang", action="store_true", help="쿠팡에서 못 사는 물건")
    a.add_argument("--note", default="", help="메모")
    a.set_defaults(func=cmd_add)

    l = sub.add_parser("list", help="큐 보기")
    l.add_argument("--all", action="store_true", help="끝난 것까지 전부")
    l.set_defaults(func=cmd_list)

    n = sub.add_parser("next", help="다음에 만들 것 꺼내기")
    n.set_defaults(func=cmd_next)

    d = sub.add_parser("done", help="완료 처리")
    d.add_argument("keyword")
    d.add_argument("--note", default="")
    d.set_defaults(func=cmd_done)

    r = sub.add_parser("drop", help="버림 처리")
    r.add_argument("keyword")
    r.add_argument("--note", default="", help="왜 버리는지 (남기는 게 좋습니다)")
    r.set_defaults(func=cmd_drop)

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
