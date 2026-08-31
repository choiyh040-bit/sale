"""
Gemini API 연결 확인용 스크립트. (Phase 0)

이 스크립트가 성공하면 Phase 0 이 끝난다.
확인하는 것은 세 가지다.
  1. API 키를 제대로 읽는가
  2. 키가 유효한가
  3. Gemini 에게 요청을 보내고 답을 받아오는가

실행:
    python scripts/hello.py
"""

import os
import sys

# .env 도 읽지만, 이 컨테이너는 세션이 끝나면 사라지므로
# 키는 '환경 설정의 환경변수' 로 넣는 것이 맞다.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

# --- 1단계: 키가 있는지 ----------------------------------------------------
if not api_key:
    print("❌ GEMINI_API_KEY 를 찾을 수 없습니다.")
    print()
    print("   해결 순서:")
    print("   1) 폰 브라우저로 https://aistudio.google.com 접속 → API 키 발급")
    print("   2) 그 키를 '환경 설정 → 환경변수' 에 GEMINI_API_KEY 로 등록")
    print("   ⚠️  키를 채팅창에 붙여넣지 마세요. 대화 기록에 영구히 남습니다.")
    sys.exit(1)

if "여기에" in api_key or len(api_key) < 20:
    print("❌ 키가 예시값이거나 너무 짧습니다.")
    print(f"   현재 값의 앞부분: {api_key[:10]}...")
    sys.exit(1)

# --- 2단계: Gemini 에게 인사 -----------------------------------------------
try:
    from google import genai
except ImportError:
    print("❌ google-genai 가 설치되어 있지 않습니다.")
    print("   pip install -r requirements.txt")
    sys.exit(1)

client = genai.Client(api_key=api_key)
print(f"Gemini 에게 인사를 보내는 중... (모델: {MODEL})")

try:
    response = client.models.generate_content(
        model=MODEL,
        contents="안녕! 한 문장으로 짧게 인사해줘.",
    )
except Exception as e:
    msg = str(e)
    print(f"❌ 실패: {msg}")
    print()
    if "API_KEY_INVALID" in msg or "401" in msg or "403" in msg:
        print("   키가 거부되었습니다. 앞뒤 공백이나 따옴표가 붙어있지 않은지 확인하세요.")
    elif "404" in msg or "not found" in msg.lower():
        print("   모델 이름이 맞지 않습니다. 쓸 수 있는 이름을 확인하세요:")
        print("      python scripts/make_toon.py --list-models")
        print("   그다음 환경변수 GEMINI_MODEL 로 지정하세요.")
    elif "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        print("   호출 한도를 넘었습니다. 잠시 후 다시 실행하세요.")
    else:
        print("   네트워크 연결을 확인하세요.")
    sys.exit(1)

# --- 3단계: 결과 출력 ------------------------------------------------------
print()
print("✅ 성공! Gemini 응답:")
print(f"   {response.text.strip()}")
print()
print("Phase 0 완료입니다. 다음:")
print('   python scripts/make_toon.py "겨울 온열매트"')
