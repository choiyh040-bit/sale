"""
Claude API 연결 확인용 스크립트. (Phase 0 - P0-5)

이 스크립트가 성공하면 Phase 0 이 끝납니다.
여기서 확인하는 것은 딱 세 가지입니다.
  1. .env 파일을 제대로 읽는가
  2. API 키가 유효한가
  3. Claude 에게 요청을 보내고 답을 받아오는가

실행:
    python scripts/hello.py
"""

import os
import sys

from dotenv import load_dotenv

# 프로젝트 루트의 .env 를 읽어 환경변수로 올립니다.
load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")

# --- 1단계: 키가 있는지 --------------------------------------------------
if not api_key:
    print("❌ ANTHROPIC_API_KEY 를 찾을 수 없습니다.")
    print()
    print("   해결 순서:")
    print("   1) cp .env.example .env        (Windows: copy .env.example .env)")
    print("   2) https://console.anthropic.com 에서 API 키를 발급받습니다.")
    print("   3) .env 를 열어 ANTHROPIC_API_KEY= 뒤에 그 키를 붙여넣습니다.")
    sys.exit(1)

# 예시값을 그대로 둔 경우를 잡아냅니다. (초보자가 가장 자주 하는 실수)
if "여기에" in api_key or not api_key.startswith("sk-ant-"):
    print("❌ .env 의 키가 아직 예시값이거나 형식이 이상합니다.")
    print(f"   현재 값: {api_key[:12]}...")
    print("   실제 키는 'sk-ant-' 로 시작합니다. console.anthropic.com 에서 확인하세요.")
    sys.exit(1)

# --- 2단계: Claude 에게 인사 ---------------------------------------------
import anthropic

client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 를 자동으로 읽습니다

print("Claude 에게 인사를 보내는 중...")

try:
    response = client.messages.create(
        model="claude-opus-5",
        max_tokens=200,
        messages=[{"role": "user", "content": "안녕! 한 문장으로 짧게 인사해줘."}],
    )
except anthropic.AuthenticationError:
    print("❌ 키가 거부되었습니다 (401).")
    print("   .env 의 ANTHROPIC_API_KEY 값을 다시 확인하세요. 앞뒤 공백이나 따옴표가 붙어있지 않은지도요.")
    sys.exit(1)
except anthropic.RateLimitError:
    print("❌ 요청이 너무 잦습니다 (429). 잠시 후 다시 실행하세요.")
    sys.exit(1)
except anthropic.APIConnectionError as e:
    print(f"❌ 네트워크 연결에 실패했습니다: {e}")
    print("   인터넷 연결과 방화벽/VPN 설정을 확인하세요.")
    sys.exit(1)
except anthropic.APIStatusError as e:
    print(f"❌ API 오류 (HTTP {e.status_code}): {e.message}")
    sys.exit(1)

# --- 3단계: 결과 출력 -----------------------------------------------------
text = "".join(block.text for block in response.content if block.type == "text")

print()
print("✅ 성공! Claude 응답:")
print(f"   {text}")
print()
print(f"   모델   : {response.model}")
print(f"   토큰   : 입력 {response.usage.input_tokens} / 출력 {response.usage.output_tokens}")
print()
print("Phase 0 의 마지막 확인이 끝났습니다. TODAY.md 의 P0-5 를 체크하세요.")
