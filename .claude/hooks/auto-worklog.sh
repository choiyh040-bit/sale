#!/usr/bin/env bash
# ---------------------------------------------------------------
# PostToolUse 훅 — "분기점"이 지나갈 때마다 작업일지를 자동 생성합니다.
#
# 분기점 = git commit 이 성공한 순간.
#   (시간 기준이 아니라 "의미 있는 작업 한 덩어리가 끝난 시점" 기준)
#
# 커밋 해시로 중복을 막으므로 같은 커밋에 일지가 두 번 생기지 않습니다.
# ---------------------------------------------------------------
set -uo pipefail

DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$DIR" 2>/dev/null || exit 0

INPUT="$(cat)"
CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null || echo "")"

# git commit 이 아니면 조용히 종료
case "$CMD" in
  *"git commit"*) ;;
  *) exit 0 ;;
esac

# 커밋이 실제로 만들어졌는지 확인
HASH="$(git rev-parse --short HEAD 2>/dev/null)" || exit 0
[ -n "$HASH" ] || exit 0

mkdir -p logs/worklog

# 이 커밋에 대한 일지가 이미 있으면 종료 (중복 방지)
if grep -rqs "meta: hash=$HASH" logs/worklog/ 2>/dev/null; then
  exit 0
fi

DATE="$(date +%Y-%m-%d)"
DATETIME="$(date '+%Y-%m-%d %H:%M')"
SUBJECT="$(git log -1 --pretty=%s 2>/dev/null)"
FILES="$(git show --stat --oneline --name-only --pretty=format: HEAD 2>/dev/null | sed '/^$/d' | head -20)"
[ -n "$FILES" ] || FILES="(변경 파일 없음)"

# 오늘 몇 번째 일지인지
SEQ="$(printf '%02d' "$(( $(ls -1 logs/worklog/"$DATE"-*.md 2>/dev/null | wc -l) + 1 ))")"

# 현재 Phase 를 TODAY.md 에서 읽어옴
PHASE="$(grep -m1 '현재 Phase' docs/TODAY.md 2>/dev/null | sed 's/.*현재 Phase\*\*: *//; s/^- *//')"
[ -n "$PHASE" ] || PHASE="(미지정)"

# 마일스톤 여부 판정
KIND="일반 커밋"
case "$SUBJECT" in
  *Phase*|*phase*|*마일스톤*|*완료*) KIND="★ 마일스톤" ;;
esac

OUT="logs/worklog/${DATE}-${SEQ}.md"
TPL="docs/templates/worklog-template.md"

if [ -f "$TPL" ]; then
  python3 - "$TPL" "$OUT" << PYEOF
import sys, io
tpl, out = sys.argv[1], sys.argv[2]
vals = {
    "{DATE}": """$DATE""",
    "{SEQ}": """$SEQ""",
    "{DATETIME}": """$DATETIME""",
    "{PHASE}": """$PHASE""",
    "{HASH}": """$HASH""",
    "{SUBJECT}": """$SUBJECT""",
    "{KIND}": """$KIND""",
    "{FILES}": """$FILES""",
}
s = io.open(tpl, encoding="utf-8").read()
for k, v in vals.items():
    s = s.replace(k, v)
io.open(out, "w", encoding="utf-8").write(s)
PYEOF
else
  {
    echo "# 작업일지 ${DATE} #${SEQ}"
    echo
    echo "- 시각: ${DATETIME}"
    echo "- Phase: ${PHASE}"
    echo "- 커밋: \`${HASH}\` — ${SUBJECT}"
    echo
    echo "<!-- meta: hash=${HASH} -->"
  } > "$OUT"
fi

# Claude 에게 "일지 채워라" 라고 알려줌
MSG="작업일지 뼈대가 자동 생성되었습니다: ${OUT}
방금 커밋(${HASH} — ${SUBJECT})을 기준으로 '무엇을 했나 / 왜 이렇게 했나 / 막힌 점·배운 점 / 다음 할 일' 네 칸을 이번 세션에서 실제로 한 작업 내용으로 채워 주세요. 추측으로 채우지 말고, 실제로 일어난 일만 적으세요.
그리고 docs/TODAY.md 의 해당 체크박스와 D(Do) 칸도 함께 갱신하세요."

jq -n --arg m "$MSG" \
  '{hookSpecificOutput:{hookEventName:"PostToolUse", additionalContext:$m}}' 2>/dev/null \
  || echo "$MSG"

exit 0
