#!/usr/bin/env bash
# ---------------------------------------------------------------
# SessionStart 훅 — 대화창을 열 때마다 작업 기준을 자동으로 불러옵니다.
#
# 여기서 echo 한 내용은 그대로 Claude의 대화 맥락에 주입됩니다.
# 즉, 매 세션이 "같은 계획서를 읽고 시작"하게 됩니다.
#
# 전체 계획서를 통째로 넣고 싶으면 아래 FULL_PLAN 을 1 로 바꾸세요.
# ---------------------------------------------------------------
set -uo pipefail

FULL_PLAN=0

DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$DIR" 2>/dev/null || exit 0

PLAN="docs/MASTER_PLAN.md"
TODAY="docs/TODAY.md"

echo "=============================================="
echo " 프로젝트 작업 기준 자동 로드 (SessionStart)"
echo "=============================================="
echo

# --- 1. 전체 계획서 -------------------------------------------
if [ -f "$PLAN" ]; then
  echo "## [전체 계획서] docs/MASTER_PLAN.md"
  echo
  if [ "$FULL_PLAN" = "1" ]; then
    cat "$PLAN"
  else
    sed -n '/<!-- SUMMARY:START -->/,/<!-- SUMMARY:END -->/p' "$PLAN" \
      | grep -v 'SUMMARY:START\|SUMMARY:END'
    echo
    echo "(전체 로드맵·제약사항은 docs/MASTER_PLAN.md 를 직접 읽을 것)"
  fi
  echo
else
  echo "⚠️  docs/MASTER_PLAN.md 가 없습니다. 계획서부터 복구하세요."
  echo
fi

# --- 2. 오늘의 할일 -------------------------------------------
if [ -f "$TODAY" ]; then
  echo "## [오늘의 할일] docs/TODAY.md (전문)"
  echo
  cat "$TODAY"
  echo
else
  echo "⚠️  docs/TODAY.md 가 없습니다. /today 로 새로 만드세요."
  echo
fi

# --- 3. 최근 작업일지 -----------------------------------------
echo "## [최근 작업일지]"
echo
RECENT="$(ls -1 logs/worklog/*.md 2>/dev/null | sort | tail -3)"
if [ -n "$RECENT" ]; then
  for f in $RECENT; do
    echo "- $f"
    sed -n 's/^## 무엇을 했나//p;' "$f" >/dev/null 2>&1
    awk '/^## 무엇을 했나/{flag=1;next} /^## /{flag=0} flag && NF && $0 !~ /^<!--/ {print "    " $0; exit}' "$f"
  done
else
  echo "- (아직 없음)"
fi
echo

# --- 4. 이번 세션 행동 규칙 -----------------------------------
cat <<'RULES'
## [이번 세션 규칙]

1. 위 "오늘의 할일"의 P(Plan) 항목을 벗어나는 작업은 먼저 물어볼 것.
2. 작업이 진행되면 docs/TODAY.md 의 체크박스와 D(Do) 칸을 실제로 갱신할 것.
3. 커밋하면 logs/worklog/ 에 일지 뼈대가 자동 생성됨 → 내용을 채울 것.
4. API 키·토큰은 .env 에만. 코드나 문서에 값을 절대 쓰지 말 것.
5. 게시물 관련 코드를 만들 땐 쿠팡파트너스 고지 문구 필드를 반드시 포함할 것.
RULES
echo
echo "=============================================="
exit 0
