"""
콘티 생성기 (Phase 1)

키워드를 받아 Gemini 로 인스타툰 콘티를 만들고 toon.json 으로 저장한다.

실행:
    python scripts/make_toon.py "겨울 온열매트"
    python scripts/make_toon.py "겨울 온열매트" --cuts 4
    python scripts/make_toon.py --list-models        # 쓸 수 있는 모델 이름 확인

API 키는 환경변수 GEMINI_API_KEY 로 넣는다. (.env 도 읽지만 컨테이너에서는 사라진다)
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

# --- 코드가 책임지는 값 -----------------------------------------------------
# 제휴 고지 문구는 법으로 정해진 문장이라 LLM 에게 맡기지 않는다.
# 한 글자라도 바뀌면 안 되므로 여기 고정한다.
DISCLOSURE = (
    "이 게시물은 쿠팡 파트너스 활동의 일환으로, "
    "이에 따라 일정액의 수수료를 제공받습니다."
)

CANVAS = [1080, 1350]
SCHEMA_VERSION = 1

ROLES = ["hook", "problem", "escalation", "turn", "solution", "cta"]
POSITIONS = ["top-left", "top-right", "bottom-left", "bottom-right"]
TAILS = ["down-left", "down-right", "up-left", "up-right"]

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

# 무료 등급에서는 최신 모델일수록 자주 붐빈다(503). 앞에서부터 순서대로 시도한다.
# 맨 앞이 실패하면 다음 모델로 넘어가므로, 한 모델이 붐벼도 작업이 멈추지 않는다.
FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.6-flash"]


# --- Gemini 응답 형식 강제 --------------------------------------------------
# 이걸 넘기면 모델이 반드시 이 구조의 JSON 을 뱉는다.
# "JSON 으로 답해줘" 라고 부탁하는 것과 달리 형식이 깨질 수 없다.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "plan": {
            "type": "object",
            "properties": {
                "persona": {"type": "string"},
                "pain": {"type": "string"},
                "hook": {"type": "string"},
                "angle": {"type": "string"},
                "cta": {"type": "string"},
            },
            "required": ["persona", "pain", "hook", "angle", "cta"],
        },
        "character": {
            "type": "object",
            "properties": {"prompt_prefix": {"type": "string"}},
            "required": ["prompt_prefix"],
        },
        "cuts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "role": {"type": "string", "enum": ROLES},
                    "scene": {"type": "string"},
                    "dialogue": {"type": "string"},
                    "balloon": {
                        "type": "object",
                        "properties": {
                            "pos": {"type": "string", "enum": POSITIONS},
                            "tail": {"type": "string", "enum": TAILS},
                        },
                        "required": ["pos", "tail"],
                    },
                    "image_prompt": {"type": "string"},
                },
                "required": ["n", "role", "scene", "dialogue", "balloon", "image_prompt"],
            },
        },
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["plan", "character", "cuts", "caption", "hashtags"],
}


def load_system_prompt():
    """prompts/toon_prompt.md 에서 시스템 지시문만 뽑아온다."""
    p = Path("prompts/toon_prompt.md")
    if not p.exists():
        print(f"❌ {p} 가 없습니다.")
        sys.exit(1)
    text = p.read_text(encoding="utf-8")
    m = re.search(r"<!-- SYSTEM:START -->(.*?)<!-- SYSTEM:END -->", text, re.S)
    if not m:
        print(f"❌ {p} 에 SYSTEM:START / SYSTEM:END 표시가 없습니다.")
        sys.exit(1)
    return m.group(1).strip()


def slugify(keyword):
    """폴더 이름으로 쓸 영문 슬러그. 한글은 자리표시로 바뀌므로 날짜와 함께 쓴다."""
    s = re.sub(r"[^\w가-힣]+", "-", keyword.strip()).strip("-")
    return s[:40] or "toon"


# --- 검증 -----------------------------------------------------------------
# 숫자를 지어내면 허위·과장 광고가 되므로 사람이 보기 전에 걸러낸다.
SUSPICIOUS_NUMBER = re.compile(
    # 아라비아 숫자 + 단위:  "3만원", "80%", "2배"
    r"\d+\s*(%|퍼센트|배|원|만원|천원|배로|배나)"
    # 한글 수사 + 금액:  "천원", "만원", "삼만원"
    # 숫자 없이 한글로만 쓰면 위 규칙을 빠져나가므로 따로 잡는다.
    # 십/백/천/만/억/조 만 넣는다. 일·이·삼·사·오·구 는 '구원' '사원' 처럼
    # 평범한 단어에서도 나와 오탐이 난다.
    r"|(십|백|천|만|억|조)\s*원"
    # 한글 수사 + 배수:  "두 배", "몇 배"
    r"|(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|몇)\s*배"
    # 비율을 뜻하는 관용 표현
    r"|절반|반값|반토막"
)


def validate(toon):
    """콘티가 규칙을 지켰는지 확인한다. (문제 목록, 경고 목록) 을 돌려준다."""
    errors, warns = [], []
    cuts = toon.get("cuts", [])

    if not 4 <= len(cuts) <= 8:
        errors.append(f"컷 수가 {len(cuts)}개입니다. 4~8개여야 합니다.")

    if not toon.get("disclosure", "").strip():
        errors.append("제휴 고지 문구(disclosure)가 비어 있습니다.")

    for c in cuts:
        n = c.get("n", "?")
        pos, tail = c["balloon"]["pos"], c["balloon"]["tail"]

        # 말풍선이 위에 있는데 꼬리도 위로 향하면 화면 밖으로 나간다
        if pos.startswith("top") and not tail.startswith("down"):
            errors.append(f"컷{n}: 말풍선이 위({pos})인데 꼬리가 {tail} 입니다. down-* 여야 합니다.")
        if pos.startswith("bottom") and not tail.startswith("up"):
            errors.append(f"컷{n}: 말풍선이 아래({pos})인데 꼬리가 {tail} 입니다. up-* 여야 합니다.")

        if len(c["dialogue"]) > 25:
            warns.append(f"컷{n}: 대사가 {len(c['dialogue'])}자입니다. 25자 이내를 권장합니다.")

        hit = SUSPICIOUS_NUMBER.search(c["dialogue"])
        if hit:
            errors.append(
                f"컷{n}: 대사에 수치 표현 '{hit.group()}' 이 있습니다. "
                "근거 없는 수치는 허위·과장 광고가 됩니다. 체감 표현으로 바꾸세요."
            )

    hit = SUSPICIOUS_NUMBER.search(toon.get("caption", ""))
    if hit:
        errors.append(f"캡션에 수치 표현 '{hit.group()}' 이 있습니다. 근거가 없으면 빼세요.")

    if "http" in toon.get("caption", ""):
        warns.append("캡션에 URL 이 있습니다. 인스타는 캡션 링크가 클릭되지 않습니다.")

    # 연속된 컷에서 말풍선 위치가 같으면 단조로워 보인다
    for a, b in zip(cuts, cuts[1:]):
        if a["balloon"]["pos"] == b["balloon"]["pos"]:
            warns.append(f"컷{a['n']}-{b['n']}: 말풍선 위치가 같습니다({a['balloon']['pos']}).")

    return errors, warns


def build_toon(keyword, data, cut_count):
    """LLM 이 만든 부분과 코드가 정하는 부분을 합쳐 완성된 toon 을 만든다."""
    slug = slugify(keyword)
    toon_id = f"{date.today().isoformat()}-{slug}"

    cuts = data["cuts"][:cut_count]
    for i, c in enumerate(cuts, 1):
        c["n"] = i  # 번호는 코드가 다시 매긴다 (모델이 건너뛸 수 있음)

    return {
        "meta": {
            "id": toon_id,
            "keyword": keyword,
            "created_at": date.today().isoformat(),
            "made_by": "gemini",
            "schema_version": SCHEMA_VERSION,
            "status": "draft",
        },
        "product": {
            "name": keyword,
            "category": "",
            "affiliate": {
                "platform": "coupang",
                "url": "",
                "landing": "linkinbio",
                "note": "인스타 캡션·댓글의 URL은 클릭이 안 된다. 반드시 프로필 링크로 유도할 것.",
            },
        },
        "plan": data["plan"],
        "character": {
            "ref": "assets/character/main_front.png",
            "prompt_prefix": data["character"]["prompt_prefix"],
        },
        "format": {"canvas": CANVAS, "cut_count": len(cuts)},
        "cuts": cuts,
        "caption": data["caption"],
        "hashtags": data["hashtags"],
        "disclosure": DISCLOSURE,   # ← 코드가 넣는다. LLM 이 쓰게 두지 않는다.
    }


def get_client():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        print("❌ GEMINI_API_KEY 를 찾을 수 없습니다.")
        print()
        print("   1) 폰 브라우저로 aistudio.google.com 에서 키를 발급받으세요.")
        print("   2) 그 키를 환경 설정의 '환경변수' 에 GEMINI_API_KEY 로 넣으세요.")
        print("      (.env 파일은 이 컨테이너가 사라질 때 같이 없어집니다)")
        sys.exit(1)

    try:
        from google import genai
    except ImportError:
        print("❌ google-genai 가 설치되어 있지 않습니다.")
        print("   pip install -r requirements.txt")
        sys.exit(1)

    return genai.Client(api_key=key)


def generate_with_fallback(client, model, contents, config):
    """붐비는(503) / 너무 자주 부른(429) 경우를 넘기며 콘티를 받아온다.

    같은 모델로 잠깐 기다렸다 다시 부르고, 그래도 안 되면 다음 모델로 넘어간다.
    돌려주는 것은 (응답, 실제로 성공한 모델 이름).
    """
    tried = [model] + [m for m in FALLBACK_MODELS if m != model]
    last = None

    for name in tried:
        for attempt in range(3):
            try:
                return client.models.generate_content(
                    model=name, contents=contents, config=config
                ), name
            except Exception as e:
                msg = str(e)
                last = e
                busy = "503" in msg or "UNAVAILABLE" in msg
                too_fast = "429" in msg or "RESOURCE_EXHAUSTED" in msg
                if not (busy or too_fast):
                    raise            # 모델명 오류·키 오류는 재시도해도 소용없다
                wait = 5 * (attempt + 1)
                why = "붐빔" if busy else "호출이 너무 잦음"
                print(f"   ({name} {why} — {wait}초 뒤 재시도)")
                time.sleep(wait)
        print(f"   → {name} 은 계속 실패. 다음 모델로 넘어갑니다.")

    raise last


def list_models():
    """쓸 수 있는 모델 이름을 출력한다. 모델명이 안 맞을 때 여기서 확인한다."""
    client = get_client()
    print("사용 가능한 모델:")
    for m in client.models.list():
        actions = getattr(m, "supported_actions", None) or []
        if not actions or "generateContent" in actions:
            print(f"  {m.name}")


def main():
    ap = argparse.ArgumentParser(description="키워드로 인스타툰 콘티를 만든다")
    ap.add_argument("keyword", nargs="?", help="상품 키워드 (예: '겨울 온열매트')")
    ap.add_argument("--cuts", type=int, default=6, help="컷 수 (4~8, 기본 6)")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"모델 이름 (기본 {DEFAULT_MODEL})")
    ap.add_argument("--list-models", action="store_true", help="쓸 수 있는 모델 이름 출력")
    args = ap.parse_args()

    if args.list_models:
        list_models()
        return

    if not args.keyword:
        ap.print_help()
        sys.exit(1)

    if not 4 <= args.cuts <= 8:
        print("❌ --cuts 는 4~8 사이여야 합니다.")
        sys.exit(1)

    client = get_client()
    system = load_system_prompt()

    print(f"'{args.keyword}' 콘티를 {args.cuts}컷으로 만드는 중... (모델: {args.model})")

    try:
        resp, used_model = generate_with_fallback(
            client,
            args.model,
            f"상품 키워드: {args.keyword}\n컷 수: {args.cuts}컷",
            {
                "system_instruction": system,
                "response_mime_type": "application/json",
                "response_schema": RESPONSE_SCHEMA,
            },
        )
        if used_model != args.model:
            print(f"   ({args.model} 대신 {used_model} 로 만들었습니다)")
    except Exception as e:
        msg = str(e)
        print(f"❌ 생성 실패: {msg}")
        if "404" in msg or "not found" in msg.lower():
            print()
            print("   모델 이름이 맞지 않는 것 같습니다. 아래로 쓸 수 있는 이름을 확인하세요:")
            print("      python scripts/make_toon.py --list-models")
            print("   그다음 --model 로 넘기거나 환경변수 GEMINI_MODEL 로 지정하세요.")
        sys.exit(1)

    data = json.loads(resp.text)
    toon = build_toon(args.keyword, data, args.cuts)

    errors, warns = validate(toon)
    for w in warns:
        print(f"  ⚠️  {w}")
    if errors:
        print()
        for e in errors:
            print(f"  ❌ {e}")
        print()
        print("규칙을 어긴 콘티라 저장하지 않았습니다. 다시 실행해 보세요.")
        sys.exit(1)

    out_dir = Path("content") / toon["meta"]["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "toon.json"
    out_path.write_text(json.dumps(toon, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    for c in toon["cuts"]:
        print(f"  컷{c['n']} [{c['role']:10}] {c['dialogue']}")
    print()
    print(f"✅ {out_path}")
    print(f"   다음: python scripts/compose.py {out_dir}")


if __name__ == "__main__":
    main()
