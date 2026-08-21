"""6-hour AI & Crypto newsletter bot: RSS -> Gemini -> Slack.

Two run modes, both calling the same main():
- `python news_bot.py`        -> single run, exits. For crontab (`0 */6 * * *`).
- `python news_bot.py --loop` -> runs forever, calling main() every 6 hours
  via `schedule`. For hosting platforms without OS-level cron (e.g. cloudtype),
  where the process must stay alive.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fcntl

import feedparser
import requests
import schedule
from dotenv import load_dotenv
from google import genai

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

GEMINI_MODEL = "gemini-3.5-flash"
ARTICLE_LIMIT = 5

RSS_FEEDS = {
    "crypto": [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://www.theblock.co/rss.xml",
    ],
    "ai": [
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.technologyreview.com/feed/",
    ],
}

PROMPT_TEMPLATE = """당신은 전문 테크/금융 뉴스레터 에디터입니다.
아래 영문 원문 기사를 바탕으로 한국어 데일리 뉴스레터를 작성하세요.
단순 직역이 아니라 매끄러운 뉴스레터 문체로 재가공하세요.

[출력 형식 - Slack mrkdwn 문법만 사용]
- 굵게는 *별표 하나*로 표시 (마크다운 ** 금지)
- # 헤더 문법 금지
- 아래 구조를 정확히 따를 것

🗞️ *[6시간 AI & Crypto 브리핑]*

🚀 *AI 기술 & 산업 동향*
(아래 AI 원문 기사 중 핵심 2~3개를 선별하여 기사마다 아래 형식 반복)
*[기사 제목 한글 번역]*
[핵심 내용 2줄 요약]
🔗 원본 기사: <링크>

🪙 *크립토 & 블록체인 동향*
(아래 크립토 원문 기사 중 핵심 2~3개를 선별하여 동일 형식 반복)

[톤앤매너]
전문적이면서 읽기 쉬운 구어체를 사용하세요. (예: ~했습니다, ~전망입니다)

[AI 원문 기사 목록]
{ai_block}

[크립토 원문 기사 목록]
{crypto_block}
"""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("news_bot")

RUN_DEDUPE_WINDOW = timedelta(minutes=15)
LAST_RUN_PATH = Path(__file__).resolve().parent / ".news_bot_last_run.json"


def acquire_singleton_lock():
    """Prevent multiple app instances from running at the same time."""
    lock_path = Path(__file__).resolve().parent / ".news_bot.lock"
    lock_file = open(lock_path, "w")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.critical("이미 실행 중인 news_bot 프로세스가 있어 종료함: %s", lock_path)
        lock_file.close()
        raise SystemExit(0)

    logger.info("프로세스 락 획득: %s", lock_path)
    return lock_file


def should_skip_run():
    """Skip runs that start within a short dedupe window of the previous one."""
    now = datetime.now(timezone.utc)
    try:
        if LAST_RUN_PATH.exists():
            raw = LAST_RUN_PATH.read_text(encoding="utf-8").strip()
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict) and "last_run" in data:
                    last_run = datetime.fromisoformat(data["last_run"])
                    if last_run.tzinfo is None:
                        last_run = last_run.replace(tzinfo=timezone.utc)

                    if last_run > now:
                        logger.warning(
                            "마지막 실행 시각이 현재보다 미래라서 시간대 차이를 보정함: %s > %s",
                            last_run.isoformat(),
                            now.isoformat(),
                        )
                    elif now - last_run < RUN_DEDUPE_WINDOW:
                        logger.info(
                            "중복 실행 방지: 마지막 실행 시각 %s 이후 %s분이 지나지 않아 건너뜀",
                            last_run.isoformat(timespec="seconds"),
                            int((now - last_run).total_seconds() // 60),
                        )
                        return True
    except Exception:
        logger.exception("마지막 실행 시각 읽기 실패")

    LAST_RUN_PATH.write_text(json.dumps({"last_run": now.isoformat()}), encoding="utf-8")
    return False


def fetch_rss(url, limit=ARTICLE_LIMIT):
    """Fetch top `limit` entries from an RSS feed as title/link/summary dicts."""
    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"RSS 파싱 실패: {url} ({parsed.bozo_exception})")

    articles = []
    for entry in parsed.entries[:limit]:
        articles.append(
            {
                "title": entry.get("title", "(제목 없음)"),
                "link": entry.get("link", ""),
                "summary": entry.get("summary", entry.get("description", "")),
            }
        )
    return articles


def fetch_category(urls, limit=ARTICLE_LIMIT):
    """Fetch top `limit` articles from each RSS url and combine them.

    A single feed failing (site down, feed moved, etc.) is logged and
    skipped rather than dropping the whole category.
    """
    articles = []
    for url in urls:
        try:
            articles.extend(fetch_rss(url, limit))
        except Exception:
            logger.exception(f"RSS 피드 수집 실패, 건너뜀: {url}")
    return articles


def _format_articles(articles):
    lines = []
    for a in articles:
        lines.append(f"- 제목: {a['title']}\n  링크: {a['link']}\n  요약: {a['summary']}")
    return "\n".join(lines) if lines else "(수집된 기사 없음)"


def generate_newsletter(ai_articles, crypto_articles):
    """Call Gemini to turn raw articles into a Korean Slack-formatted newsletter."""
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = PROMPT_TEMPLATE.format(
        ai_block=_format_articles(ai_articles),
        crypto_block=_format_articles(crypto_articles),
    )
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    if not response.text:
        raise RuntimeError("Gemini 응답이 비어 있음")
    return response.text


def send_slack(message):
    """POST the newsletter text to the Slack incoming webhook."""
    response = requests.post(
        SLACK_WEBHOOK_URL,
        json={
            "text": message,
            "unfurl_links": False,
            "unfurl_media": False,
        },
        timeout=10,
    )
    response.raise_for_status()
    return True


def main():
    if should_skip_run():
        return

    if not GEMINI_API_KEY or not SLACK_WEBHOOK_URL:
        logger.critical("GEMINI_API_KEY / SLACK_WEBHOOK_URL 환경변수가 설정되지 않았음")
        sys.exit(1)

    try:
        ai_articles = fetch_category(RSS_FEEDS["ai"])
        crypto_articles = fetch_category(RSS_FEEDS["crypto"])
        logger.info(f"RSS 수집 완료: AI {len(ai_articles)}건, Crypto {len(crypto_articles)}건")
    except Exception:
        logger.exception("RSS 수집 중 오류 발생")
        return

    try:
        newsletter = generate_newsletter(ai_articles, crypto_articles)
        logger.info("뉴스레터 생성 완료")
    except Exception:
        logger.exception("Gemini 뉴스레터 생성 중 오류 발생")
        return

    try:
        send_slack(newsletter)
        logger.info("Slack 전송 완료")
    except Exception:
        logger.exception("Slack 전송 중 오류 발생")
        return


DAILY_RUN_TIMES = ["00:00", "06:00", "12:00", "18:00"]
SCHEDULE_TIMEZONE = "Asia/Seoul"
STARTUP_OVERLAP_WINDOW = timedelta(minutes=10)


def run_forever():
    """Run main() once immediately (build/redeploy smoke test), then daily
    at fixed KST times. For always-on hosting without OS-level cron.

    If the process starts within STARTUP_OVERLAP_WINDOW of a scheduled slot,
    that slot's next run is pushed a day ahead so the immediate run above
    doesn't get followed by a near-duplicate a few minutes later.
    """
    logger.info(f"스케줄러 시작: 배포 직후 1회 실행 + 매일 {DAILY_RUN_TIMES} ({SCHEDULE_TIMEZONE}) 실행")
    main()
    now = datetime.now()
    for run_time in DAILY_RUN_TIMES:
        job = schedule.every().day.at(run_time, SCHEDULE_TIMEZONE).do(main)
        if job.next_run - now < STARTUP_OVERLAP_WINDOW:
            job.next_run += timedelta(days=1)
            logger.info(f"{run_time} 슬롯은 방금 실행한 것과 겹쳐서 다음날로 미룸 (다음 실행: {job.next_run})")
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    lock_file = acquire_singleton_lock()
    try:
        if "--loop" in sys.argv:
            run_forever()
        else:
            main()
    finally:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            lock_file.close()
