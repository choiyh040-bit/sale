"""
자체 점검 (API 키 없이 도는 검사)

콘티 생성기의 규칙이 제대로 작동하는지 확인한다.
API 를 호출하지 않으므로 돈이 들지 않고, 아무 때나 돌려도 된다.

실행:
    python scripts/selftest.py
"""

import copy
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import make_toon as M  # noqa: E402

SAMPLE = Path("content/2026-08-31-winter-heatmat/toon.json")

_ok = _fail = 0


def check(label, cond):
    global _ok, _fail
    if cond:
        print(f"  ✅ {label}")
        _ok += 1
    else:
        print(f"  ❌ {label}")
        _fail += 1


def main():
    if not SAMPLE.exists():
        print(f"❌ 기준 콘티 {SAMPLE} 가 없습니다.")
        sys.exit(1)
    real = json.loads(SAMPLE.read_text(encoding="utf-8"))

    print("=== 프롬프트 파일 ===")
    sysprompt = M.load_system_prompt()
    check("SYSTEM 블록 추출됨", len(sysprompt) > 500)
    check("마커가 섞여 들어가지 않음", "SYSTEM:START" not in sysprompt)

    print("\n=== 기준 콘티(손으로 만든 1호)가 규칙을 통과하는가 ===")
    errors, _ = M.validate(real)
    check("에러 없음", not errors)
    for e in errors:
        print(f"      → {e}")

    print("\n=== 허위·과장 광고 차단 ===")
    # 차단해야 하는 것 / 통과해야 하는 것
    cases = [
        ("난방비 3만원으로 줄었어", True), ("전기료 80% 절약!", True),
        ("2배나 따뜻해", True), ("천원도 안 나와", True),
        ("만원이면 충분해", True), ("두 배는 따뜻한 듯", True),
        ("전기세가 반값 됐어", True),
        ("집은 추워도 이불 속은 여름이야", False),
        ("발이… 왜 이렇게 시리지…", False), ("…이게 난방비라고?", False),
        # 아래 셋은 오탐 확인용. 수사가 들어간 평범한 단어다.
        ("사원증을 놓고 왔네", False), ("구원받은 기분이야", False),
        ("정말 만족스러워", False),
    ]
    for text, should_block in cases:
        t = copy.deepcopy(real)
        t["cuts"][0]["dialogue"] = text
        errs, _ = M.validate(t)
        blocked = any("수치" in e for e in errs)
        check(f"{'차단' if should_block else '통과'}: {text!r}", blocked == should_block)

    print("\n=== 말풍선 꼬리 방향 모순 ===")
    for pos, tail in [("top-left", "up-right"), ("bottom-left", "down-right")]:
        t = copy.deepcopy(real)
        t["cuts"][0]["balloon"] = {"pos": pos, "tail": tail}
        errs, _ = M.validate(t)
        check(f"{pos} + {tail} → 에러", any("꼬리" in e for e in errs))

    print("\n=== 제휴 고지 문구는 코드가 넣는가 ===")
    fake = {
        "plan": {k: "x" for k in ["persona", "pain", "hook", "angle", "cta"]},
        "character": {"prompt_prefix": "webtoon style"},
        "cuts": [{"n": 99, "role": "hook", "scene": "s", "dialogue": "d",
                  "balloon": {"pos": "top-left", "tail": "down-right"},
                  "image_prompt": "p"} for _ in range(6)],
        "caption": "c", "hashtags": ["#a"],
        "disclosure": "LLM 이 지어낸 가짜 고지 문구",
    }
    # 제휴 링크가 있을 때 — 고지가 법정 문구로 들어가야 한다
    paid = M.build_toon("겨울 온열매트", fake, 6, link="https://link.coupang.com/x")
    check("링크 있으면 법정 문구로 고정됨", paid["disclosure"] == M.DISCLOSURE["coupang"])
    check("LLM 이 넣은 문구가 무시됨", "지어낸" not in paid["disclosure"])
    check("토스 문구도 선택됨",
          M.build_toon("k", fake, 6, link="https://toss.shopping/x",
                       platform="toss")["disclosure"] == M.DISCLOSURE["toss"])

    # 제휴 링크가 없을 때 — 고지가 비어 있어야 한다 (없는 제휴를 있다고 하지 않는다)
    free = M.build_toon("겨울 온열매트", fake, 6)
    check("링크 없으면 고지가 비어 있음", free["disclosure"] == "")
    check("링크 없으면 affiliate.url 도 빔",
          free["product"]["affiliate"]["url"] == "")

    check("컷 번호 재부여 (1..6)", [c["n"] for c in paid["cuts"]] == [1, 2, 3, 4, 5, 6])
    check("컷 수 제한 적용", len(M.build_toon("k", fake, 4)["cuts"]) == 4)

    print("\n=== 고지 문구와 제휴 링크는 짝이다 ===")
    t = copy.deepcopy(real)
    t["product"]["affiliate"]["url"] = "https://link.coupang.com/x"
    t["disclosure"] = ""
    errs, _ = M.validate(t)
    check("링크 있는데 고지 없음 → 에러", any("표시광고법" in e for e in errs))

    t2 = copy.deepcopy(real)
    t2["product"]["affiliate"]["url"] = ""
    t2["disclosure"] = M.DISCLOSURE["coupang"]
    errs2, _ = M.validate(t2)
    check("링크 없는데 고지 있음 → 에러", any("거짓" in e for e in errs2))

    t3 = copy.deepcopy(real)
    t3["product"]["affiliate"]["url"] = ""
    t3["disclosure"] = ""
    errs3, _ = M.validate(t3)
    check("둘 다 없음 → 통과 (순수 툰)",
          not any("고지" in e or "거짓" in e for e in errs3))

    print("\n=== 캡션 URL 경고 ===")
    t = copy.deepcopy(real)
    t["caption"] = "구매는 https://link.coupang.com/xxx 에서"
    _, warns = M.validate(t)
    check("인스타 캡션 링크 경고", any("URL" in w for w in warns))

    print("\n=== 발행처는 스레드다 (인스타 흔적 경고) ===")
    t4 = copy.deepcopy(real)
    t4["caption"] = "자세한 건 프로필 링크에서 확인하세요!"
    _, w4 = M.validate(t4)
    check("'프로필 링크' 유도 → 경고", any("프로필 링크" in w for w in w4))

    t5 = copy.deepcopy(real)
    t5["hashtags"] = ["인스타툰", "겨울"]
    _, w5 = M.validate(t5)
    check("'인스타' 태그 → 경고", any("스레드" in w for w in w5))

    t6 = copy.deepcopy(real)
    t6["caption"] = "오늘 밤부터 따뜻하게 자요."
    t6["hashtags"] = ["겨울필수템", "자취방"]
    _, w6 = M.validate(t6)
    check("깨끗한 캡션 → 경고 없음",
          not any("프로필" in w or "스레드" in w for w in w6))

    print("\n=== 이슈 본문 만들기 (Phase 5) ===")
    import make_issue as I

    check("저장소 주소를 읽음", I.repo_slug() == "choiyh040-bit/sale")
    cdir = Path("content/2026-09-03-겨울-온열매트")
    tj = json.loads((cdir / "toon.json").read_text(encoding="utf-8"))

    body, warns, missing = I.build_body(tj, cdir, "choiyh040-bit/sale", "main")
    check("그림 없는 컷을 전부 찾아냄", missing == [1, 2, 3, 4, 5, 6])
    check("컷 이미지가 전부 들어감", body.count("raw.githubusercontent.com") == 6)
    check("캐러셀 순서가 1..6", [int(n) for n in re.findall(r"!\[컷(\d)\]", body)] == [1,2,3,4,5,6])
    check("링크 없으면 첫 댓글 칸이 없음", I.REPLY_MARK not in body)

    paid_t = copy.deepcopy(tj)
    paid_t["product"]["affiliate"]["url"] = "https://toss.shopping/_m/XXXX"
    paid_t["disclosure"] = M.DISCLOSURE["toss"]
    pbody, _, _ = I.build_body(paid_t, cdir, "choiyh040-bit/sale", "main")
    check("링크 있으면 첫 댓글 칸이 생김", I.REPLY_MARK in pbody)
    check("고지는 본문 맨 앞", pbody.startswith(M.DISCLOSURE["toss"]))
    check("링크는 첫 댓글 아래",
          pbody.index("toss.shopping") > pbody.index(I.REPLY_MARK))

    print("\n=== 소재 큐 (Phase 9) ===")
    import queue as Q

    check("한글 폭 계산 (한글 2칸)", Q.w("겨울") == 4 and Q.w("ab") == 2)
    check("한글 표 정렬", len(Q.pad("겨울", 10)) == 10 - 4 + len("겨울"))

    qf = Path("content/queue.json")
    if qf.exists():
        qd = json.loads(qf.read_text(encoding="utf-8"))
        items = qd.get("items", [])
        check("queue.json 파싱됨", isinstance(items, list))
        check("스키마 버전 일치", qd.get("schema_version") == Q.SCHEMA_VERSION)
        need = {"keyword", "status", "coupang", "added", "source", "heat"}
        check("모든 항목이 필수 필드를 가짐",
              all(need <= set(i) for i in items))
        check("status 값이 정의된 것뿐",
              all(i["status"] in Q.STATUSES for i in items))
        check("source 값이 정의된 것뿐",
              all(i["source"] in Q.SOURCES for i in items))
        check("heat 값이 정의된 것뿐",
              all(i["heat"] in Q.HEATS for i in items))
        check("키워드 중복 없음",
              len({i["keyword"] for i in items}) == len(items))
    else:
        check("queue.json 존재", False)

    print(f"\n{'=' * 46}")
    print(f"통과 {_ok} / 실패 {_fail}")
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
