#!/usr/bin/env python3
"""GitHub 이슈로 예약한 글을 스레드에 올린다.

── 출처 ──────────────────────────────────────────────────────────────
이 파일은 핫딜 계정 저장소에서 복사해 왔다.

    choiyh040-bit/link : scripts/post_threads.py
    가져온 커밋 5a0b1f6  (2026-10-28)

런타임으로 묶지 않고 복사한 이유는 두 계정을 따로 운영하기 때문이다.
한쪽을 고칠 때 다른 쪽이 깨지면 "따로 운영한다"는 결정이 무의미해진다.
`link` 쪽이 고쳐졌는지 확인하려면 위 커밋과 비교하고, 가져올 값이 있을 때만
의도적으로 다시 맞춘다. (MASTER_PLAN 4-7절)

툰 계정용으로 바꾼 곳은 아래 'TOON' 주석으로 표시해 두었다.
──────────────────────────────────────────────────────────────────────

이슈 제목 규칙 (한국 시간 기준)
  예약 10/23 09:00 계란   → 그 시각이 지나면 게시
  예약 지금 계란          → 다음 실행 때 바로 게시
  초안 ...                → 게시하지 않음 (제목을 '예약'으로 바꾸면 승인)
  점검                    → 토큰만 확인하고 결과를 댓글로 남김

이슈 본문
  게시할 글. 붙여 넣은 이미지(첫 번째 1장)는 이미지로 올라가고 본문 글에서는 빠진다.
  '=== 첫 댓글 ===' 줄 아래 내용은 게시 직후 내 글에 댓글로 단다.
  <!-- --> 주석은 지워진다.

필요한 환경 변수: GITHUB_TOKEN, GITHUB_REPOSITORY, THREADS_ACCESS_TOKEN
"""
import base64
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

THREADS = "https://graph.threads.net/v1.0"
GITHUB = "https://api.github.com"
KST = dt.timezone(dt.timedelta(hours=9))
MAX_PER_RUN = 3          # 한 번에 너무 많이 올라가 스팸으로 보이지 않게
MAX_CHARS = 500          # 스레드 글자 수 제한
REPLY_MARK = "=== 첫 댓글 ==="

REPO = os.environ.get("GITHUB_REPOSITORY", "")
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
TH_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "")


class PostError(Exception):
    pass


def http(method, url, data=None, headers=None, raw=False):
    body = None
    headers = dict(headers or {})
    if data is not None:
        if isinstance(data, (bytes, bytearray)):
            body = data
        elif headers.get("Content-Type") == "application/json":
            body = json.dumps(data).encode()
        else:
            body = urllib.parse.urlencode(data).encode()
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            content = r.read()
            return content if raw else json.loads(content or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        # 토큰이 오류 메시지에 섞여 나가지 않게
        if TH_TOKEN:
            detail = detail.replace(TH_TOKEN, "***")
        raise PostError(f"{method} {url.split('?')[0]} → HTTP {e.code}: {detail}")


# ---------- GitHub ----------
def gh(method, path, data=None):
    return http(method, GITHUB + path, data, {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "scribble-toon-bot",   # TOON: 계정이 다르다
    })


def comment(number, text):
    gh("POST", f"/repos/{REPO}/issues/{number}/comments", {"body": text})


def download(url):
    """이슈에 붙인 이미지를 받는다. 서명된 저장소 주소로 넘어가면 인증 헤더 없이 받는다."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {GH_TOKEN}", "User-Agent": "scribble-toon-bot"})
    try:
        with opener.open(req, timeout=60) as r:
            return r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
            with urllib.request.urlopen(urllib.request.Request(e.headers["Location"], headers={"User-Agent": "scribble-toon-bot"}), timeout=60) as r:
                return r.read(), r.headers.get("Content-Type", "")
        raise PostError(f"이미지를 받지 못했어요 (HTTP {e.code}).")


def store_image(number, data, ctype):
    """이미지를 저장소 images/ 에 올리고 누구나 열 수 있는 주소를 돌려준다."""
    ext = "png" if "png" in ctype else "jpg" if ("jpeg" in ctype or "jpg" in ctype) else None
    if not ext:
        raise PostError(f"PNG나 JPG 이미지만 올릴 수 있어요 (받은 형식: {ctype or '알 수 없음'}).")
    path = f"images/{dt.datetime.now(KST):%Y%m%d}-issue{number}.{ext}"
    res = gh("PUT", f"/repos/{REPO}/contents/{path}", {
        "message": f"Add image for post #{number}",
        "content": base64.b64encode(data).decode(),
    })
    sha = res["commit"]["sha"]
    return f"https://raw.githubusercontent.com/{REPO}/{sha}/{path}"


# ---------- Threads ----------
def th(method, path, data=None):
    data = dict(data or {})
    data["access_token"] = TH_TOKEN
    if method == "GET":
        return http("GET", f"{THREADS}{path}?{urllib.parse.urlencode(data)}")
    return http("POST", f"{THREADS}{path}", data)


def wait_ready(container_id):
    for _ in range(20):
        st = th("GET", f"/{container_id}", {"fields": "status,error_message"})
        if st.get("status") == "FINISHED":
            return
        if st.get("status") in ("ERROR", "EXPIRED"):
            raise PostError(f"스레드가 게시물을 준비하지 못했어요: {st.get('error_message') or st.get('status')}")
        time.sleep(5)
    raise PostError("스레드 게시 준비가 100초 안에 끝나지 않았어요.")


def publish(user_id, fields):
    cid = th("POST", f"/{user_id}/threads", fields)["id"]
    wait_ready(cid)
    return th("POST", f"/{user_id}/threads_publish", {"creation_id": cid})["id"]


# ---------- 이슈 해석 ----------
def due_time(title, now):
    """제목에서 게시 시각을 읽는다. 게시 대상이 아니면 None."""
    t = title.strip()
    if not t.startswith("예약"):
        return None
    if re.match(r"^예약\s+(지금|바로)", t):
        return now
    m = re.match(r"^예약\s+(\d{1,2})[/.\-](\d{1,2})\s+(\d{1,2}):(\d{2})", t)
    if not m:
        raise PostError("제목 형식을 읽지 못했어요. 예: `예약 10/23 09:00 계란` 또는 `예약 지금 계란`")
    mo, d, h, mi = map(int, m.groups())
    when = dt.datetime(now.year, mo, d, h, mi, tzinfo=KST)
    if when - now > dt.timedelta(days=200):   # 12/31에 1/2 예약 같은 경우
        when = when.replace(year=now.year - 1)
    elif now - when > dt.timedelta(days=200):
        when = when.replace(year=now.year + 1)
    return when


IMG_MD = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
IMG_TAG = re.compile(r"<img[^>]*?src=\"(https?://[^\"]+)\"[^>]*>", re.I)


def parse_body(body):
    body = (body or "").replace("\r\n", "\n")
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    main, _, reply = body.partition(REPLY_MARK)
    images = [m.group(1) for m in IMG_MD.finditer(main)] + [m.group(1) for m in IMG_TAG.finditer(main)]
    text = IMG_TAG.sub("", IMG_MD.sub("", main))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, images, reply.strip()


MAX_CAROUSEL = 20


def public_url(number, url, idx):
    """Meta가 읽을 수 있는 이미지 주소. 저장소 밖 이미지는 받아서 images/ 에 올린다."""
    if url.startswith(f"https://raw.githubusercontent.com/{REPO}/"):
        return url
    data, ctype = download(url)
    stored = store_image(f"{number}-{idx}", data, ctype)
    time.sleep(3)
    return stored


def split_reply(reply):
    """빈 줄 단위 문단을 500자 안쪽 덩어리로 묶는다."""
    chunks, cur = [], ""
    for para in [p.strip() for p in reply.split("\n\n") if p.strip()]:
        if len(para) > MAX_CHARS:
            raise PostError(f"댓글 문단 하나가 {len(para)}자예요. {MAX_CHARS}자 안으로 줄여 주세요.")
        cand = f"{cur}\n\n{para}" if cur else para
        if len(cand) > MAX_CHARS:
            chunks.append(cur)
            cand = para
        cur = cand
    if cur:
        chunks.append(cur)
    return chunks


def handle(issue, user_id):
    number = issue["number"]
    text, images, reply = parse_body(issue.get("body"))
    if not text:
        raise PostError("본문에 게시할 글이 없어요.")
    if len(text) > MAX_CHARS:
        raise PostError(f"글이 {len(text)}자예요. 스레드는 {MAX_CHARS}자까지라 줄여 주세요.")
    urls = [public_url(number, u, i) for i, u in enumerate(images[:MAX_CAROUSEL], 1)]
    if len(urls) >= 2:   # 여러 장이면 넘겨 보기(캐러셀)
        children = []
        for u in urls:
            cid = th("POST", f"/{user_id}/threads", {"media_type": "IMAGE", "image_url": u, "is_carousel_item": "true"})["id"]
            wait_ready(cid)
            children.append(cid)
        media_id = publish(user_id, {"media_type": "CAROUSEL", "children": ",".join(children), "text": text})
    elif urls:
        media_id = publish(user_id, {"media_type": "IMAGE", "image_url": urls[0], "text": text})
    else:
        media_id = publish(user_id, {"media_type": "TEXT", "text": text})
    link = th("GET", f"/{media_id}", {"fields": "permalink"}).get("permalink", "")
    note = ""
    if reply:
        try:
            parent = media_id
            chunks = split_reply(reply)
            for chunk in chunks:   # 500자가 넘으면 댓글에 댓글로 이어 단다
                parent = publish(user_id, {"media_type": "TEXT", "text": chunk, "reply_to_id": parent})
            note = f"\n- 링크 댓글도 달았어요 ({len(chunks)}개)."
        except PostError as e:
            note = f"\n- ⚠️ 본문은 올라갔지만 링크 댓글은 실패했어요. 링크가 없는 글이 되니 직접 댓글을 달아 주세요: {e}"
    comment(number, f"✅ 스레드에 올렸어요: {link or media_id}{note}\n\n---\n_툰 자동 게시_")
    gh("PATCH", f"/repos/{REPO}/issues/{number}", {"state": "closed", "state_reason": "completed"})


def main():
    if not (REPO and GH_TOKEN):
        sys.exit("GITHUB_TOKEN / GITHUB_REPOSITORY가 없어요.")
    now = dt.datetime.now(KST)
    issues = [i for i in gh("GET", f"/repos/{REPO}/issues?state=open&per_page=100&direction=asc")
              if "pull_request" not in i]

    checks = [i for i in issues if i["title"].strip().startswith("점검")]
    queue = []
    for i in issues:
        try:
            when = due_time(i["title"], now)
        except PostError as e:
            gh("PATCH", f"/repos/{REPO}/issues/{i['number']}", {"title": "실패 " + i["title"]})
            comment(i["number"], f"❌ {e}\n\n제목을 고친 뒤 맨 앞을 `예약`으로 바꾸면 다시 시도해요.")
            continue
        if when and when <= now:
            queue.append(i)

    if not (checks or queue):
        print("올릴 예약 글이 없어요.")
        return
    if not TH_TOKEN:
        for i in checks + queue[:1]:
            comment(i["number"], "❌ 저장소에 `THREADS_ACCESS_TOKEN` 비밀값이 없어요. docs/threads-setup.md 5단계를 해 주세요.")
        sys.exit("THREADS_ACCESS_TOKEN이 없어요.")

    try:
        me = th("GET", "/me", {"fields": "id,username"})
    except PostError as e:
        for i in checks + queue[:1]:
            comment(i["number"], f"❌ 스레드 토큰이 올바르지 않거나 만료됐어요. docs/threads-setup.md에서 토큰을 다시 받아 주세요.\n\n```\n{e}\n```")
        sys.exit(str(e))

    for i in checks:
        comment(i["number"], f"✅ 토큰 정상: @{me.get('username')} 계정에 올릴 수 있어요.")
        gh("PATCH", f"/repos/{REPO}/issues/{i['number']}", {"state": "closed", "state_reason": "completed"})

    for i in queue[:MAX_PER_RUN]:
        print(f"#{i['number']} 게시: {i['title']}")
        try:
            handle(i, me["id"])
        except PostError as e:
            gh("PATCH", f"/repos/{REPO}/issues/{i['number']}", {"title": "실패 " + i["title"]})
            comment(i["number"], f"❌ 올리지 못했어요.\n\n```\n{e}\n```\n고친 뒤 제목 맨 앞의 `실패`를 지우면 다시 시도해요.")
    if len(queue) > MAX_PER_RUN:
        print(f"나머지 {len(queue) - MAX_PER_RUN}개는 다음 실행 때 올려요.")


if __name__ == "__main__":
    main()
