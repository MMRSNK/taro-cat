"""Orchestrator: schedules the daily forecast post and polls for @mentions.

Flows
  daily  : draw 3 -> forecast -> compose image -> Imgur -> publish to Threads
  reply  : for each new mention -> draw 3 -> forecast(question) -> image ->
           Imgur -> reply -> mark processed

Run modes
  python tools/run_bot.py                # long-running scheduler (default; Docker CMD)
  python tools/run_bot.py --post-now     # run the daily flow once, then exit
  python tools/run_bot.py --reply-once   # process pending mentions once, then exit
  python tools/run_bot.py --dry-run      # build everything but DON'T post to Threads
  python tools/run_bot.py --offline      # also skip OpenAI + Imgur (local smoke test)
"""
import argparse
import logging

from config import settings
from compose_image import compose
from draw_cards import draw

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("taro-bot")

TITLE = "Таро прогноз"
OFFLINE_STUB = ("Тестовий прогноз (offline-режим). Карти склали візерунок дня — "
                "це лише перевірка конвеєра, без звернення до OpenAI.")


def build_forecast(question="", theme=None, offline=False):
    """Return (cards, text, image_path)."""
    theme = theme or settings.DAILY_THEME
    cards = draw(3)

    if offline:
        text = OFFLINE_STUB
    else:
        from generate_forecast import generate
        text = generate(cards, question=question, theme=theme)

    subtitle = question.strip() if question else theme
    image_path = compose(cards, title=TITLE, subtitle=subtitle)
    return cards, text, image_path


def publish(text, image_path, reply_to_id=None, offline=False, dry_run=False):
    """Upload image + post to Threads. Returns media id, or None if skipped."""
    if offline or dry_run:
        log.info("[skip-post] image=%s reply_to=%s\n--- text ---\n%s",
                 image_path, reply_to_id, text)
        return None

    from upload_imgur import upload
    from threads_post import post

    image_url = upload(image_path)
    log.info("uploaded image -> %s", image_url)
    media_id = post(text, image_url=image_url, reply_to_id=reply_to_id)
    log.info("published to Threads -> media id %s", media_id)
    return media_id


def do_daily(offline=False, dry_run=False):
    log.info("=== daily forecast ===")
    try:
        cards, text, img = build_forecast(theme=settings.DAILY_THEME, offline=offline)
        publish(text, img, offline=offline, dry_run=dry_run)
    except Exception:
        log.exception("daily forecast failed")


def do_replies(offline=False, dry_run=False):
    from threads_mentions import new_mentions
    from state import mark_seen

    try:
        mentions = new_mentions()
    except Exception:
        log.exception("could not fetch mentions")
        return

    if not mentions:
        log.info("no new mentions")
        return

    log.info("processing %d new mention(s)", len(mentions))
    for m in mentions:
        mid = m["id"]
        question = m.get("question") or "Загальний розклад на сьогодні"
        log.info("mention %s from @%s: %s", mid, m.get("username"), question)
        try:
            cards, text, img = build_forecast(
                question=question, theme="питання користувача", offline=offline)
            publish(text, img, reply_to_id=mid, offline=offline, dry_run=dry_run)
            if not (offline or dry_run):
                mark_seen(mid)
        except Exception:
            log.exception("failed to handle mention %s", mid)


def run_scheduler():
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    sched = BlockingScheduler(timezone=settings.TZ)
    sched.add_job(do_daily, CronTrigger.from_crontab(settings.POST_CRON,
                                                     timezone=settings.TZ),
                  id="daily_post")
    sched.add_job(do_replies, "interval",
                  minutes=settings.MENTION_POLL_MINUTES, id="poll_mentions")
    log.info("scheduler up | daily cron=%r tz=%s | mention poll every %d min",
             settings.POST_CRON, settings.TZ, settings.MENTION_POLL_MINUTES)
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("shutting down")


def main():
    ap = argparse.ArgumentParser(description="Threads tarot bot")
    ap.add_argument("--post-now", action="store_true", help="run daily flow once")
    ap.add_argument("--reply-once", action="store_true", help="process mentions once")
    ap.add_argument("--dry-run", action="store_true", help="build but don't post")
    ap.add_argument("--offline", action="store_true",
                    help="skip OpenAI + Imgur + Threads (local smoke test)")
    a = ap.parse_args()

    if a.post_now:
        do_daily(offline=a.offline, dry_run=a.dry_run)
    elif a.reply_once:
        do_replies(offline=a.offline, dry_run=a.dry_run)
    else:
        run_scheduler()


if __name__ == "__main__":
    main()
