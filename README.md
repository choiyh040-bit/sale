# sale — 인스타툰 제휴수익 자동화

쿠팡파트너스 / 토스 쉐어링크 제휴 링크로 수익을 내는 인스타툰 계정의 제작 파이프라인.

## 문서

| 파일 | 용도 |
|---|---|
| [`docs/MASTER_PLAN.md`](docs/MASTER_PLAN.md) | **전체 계획서.** 목표·구조·제약·Phase 로드맵 |
| [`docs/TODAY.md`](docs/TODAY.md) | **오늘의 할일.** PDCA 한 사이클 = 하루 |
| [`logs/worklog/`](logs/worklog/) | 작업일지. 커밋할 때마다 자동 생성 |
| [`CLAUDE.md`](CLAUDE.md) | Claude Code 상시 규칙 |

## 이 저장소가 스스로 하는 일

1. **세션 자동 로드** — Claude Code 대화창을 열면 `SessionStart` 훅이
   전체 계획서 요약 + 오늘의 할일 전문 + 최근 일지를 자동으로 읽어 옵니다.
   덕분에 매번 "우리 뭐 하고 있었지"를 설명할 필요가 없습니다.

2. **자동 작업일지** — `git commit` 이 성공할 때마다 `PostToolUse` 훅이
   `logs/worklog/YYYY-MM-DD-NN.md` 를 만들고 커밋 해시·변경 파일·현재 Phase를 채워 둡니다.
   시간 기준이 아니라 **분기점(=커밋) 기준**입니다.

## 명령어

```
/log      지금까지 한 작업을 마일스톤 작업일지로 기록
/today    docs/TODAY.md 를 다음 사이클로 갱신
```

## 처음 시작하기

```bash
cp .env.example .env      # 그리고 .env 안에 실제 API 키를 넣습니다
python3 -m venv .venv
source .venv/bin/activate # Windows: .venv\Scripts\activate
```

그다음 `docs/TODAY.md` 의 P(Plan) 항목부터 하나씩 진행하세요.

## 훅 동작 확인

```bash
# 세션 시작 훅이 뭘 불러오는지 미리 보기
./.claude/hooks/session-start.sh
```
