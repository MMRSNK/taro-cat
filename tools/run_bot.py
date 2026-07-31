"""Orchestrator: schedules the daily forecast post and polls for new replies.

Reply source is set by REPLY_SOURCES (default `post_replies` = comments under the
bot's own posts, which works for any user with no Meta verification; `mentions` =
/me/mentions, testers only until advanced access).

Flows
  daily  : draw 3 -> forecast -> compose image -> host -> publish to Threads
  reply  : for each new reply -> draw 3 -> forecast(question) -> image ->
           host -> reply -> mark processed

Run modes
  python tools/run_bot.py                # long-running scheduler (default; Docker CMD)
  python tools/run_bot.py --post-now     # run the daily flow once, then exit
  python tools/run_bot.py --reply-once   # process pending replies once, then exit
  python tools/run_bot.py --seed-seen    # mark existing replies seen, DON'T answer (run once)
  python tools/run_bot.py --answer-url URL  # build+print a reading for a post link (no posting)
  python tools/run_bot.py --telegram-once   # process pending Telegram messages/buttons once
  python tools/run_bot.py --dry-run      # build everything but DON'T post to Threads
  python tools/run_bot.py --offline      # also skip OpenAI + host (local smoke test)
"""
import argparse
import logging
from uuid import uuid4

import config
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
# Appended to the DAILY post only — invites people to comment, which feeds the
# post-replies source. Fixed wording (not model-generated) so it's exact + stable.
DAILY_CTA = "Задай своє питання в коментарях — зроблю розклад тобі. 🐾"


def with_cta(text):
    """Append the daily call-to-action, clamping the body first so the CTA always
    survives the 500-char Threads limit."""
    from threads_post import clamp_text, THREADS_TEXT_LIMIT
    body = clamp_text(text, THREADS_TEXT_LIMIT - len(DAILY_CTA) - 2).rstrip()
    # clamp_text adds a trailing «…»; drop it when the body already ends on a full
    # sentence so we don't get an ugly «...праці.…».
    if body[-1:] == "…" and body[-2:-1] in ".!?":
        body = body[:-1]
    return f"{body}\n\n{DAILY_CTA}"


def build_forecast(question="", theme=None, offline=False, subtitle=None):
    """Return (cards, text, image_path). `subtitle` overrides the image caption
    (defaults to the question, or the theme when there's no question)."""
    theme = theme or settings.DAILY_THEME
    cards = draw(3)

    if offline:
        text = OFFLINE_STUB
    else:
        from generate_forecast import generate
        text = generate(cards, question=question, theme=theme)

    if subtitle is None:
        subtitle = question.strip() if question else theme
    image_path = compose(cards, title=TITLE, subtitle=subtitle)
    return cards, text, image_path


def publish(text, image_path, reply_to_id=None, offline=False, dry_run=False):
    """Upload image + post to Threads. Returns media id, or None if skipped."""
    if offline or dry_run:
        log.info("[skip-post] image=%s reply_to=%s\n--- text ---\n%s",
                 image_path, reply_to_id, text)
        return None

    from threads_post import post

    if not image_path:
        media_id = post(text, image_url=None, reply_to_id=reply_to_id)
        log.info("published to Threads -> media id %s", media_id)
        return media_id

    # Self-host the image and post. No fallback: on failure the caller alerts
    # the operator over Telegram (see do_daily / handle_post_callback).
    from upload_image import upload

    image_url = upload(image_path)
    log.info("image at %s", image_url)
    media_id = post(text, image_url=image_url, reply_to_id=reply_to_id)
    log.info("published to Threads -> media id %s", media_id)
    return media_id


def notify_operator(text):
    """DM the operator over Telegram (best-effort; no-op if the bridge is off)."""
    if not (settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_ALLOWED_USER_ID):
        return
    try:
        from telegram_listener import send_message
        send_message(settings.TELEGRAM_ALLOWED_USER_ID, text)
    except Exception:
        log.exception("operator notify failed")


def do_daily(offline=False, dry_run=False):
    log.info("=== daily forecast ===")
    try:
        cards, text, img = build_forecast(theme=settings.DAILY_THEME, offline=offline)
        text = with_cta(text)
        publish(text, img, offline=offline, dry_run=dry_run)
    except Exception as e:
        log.exception("daily forecast failed")
        notify_operator(f"⚠️ Збій завантаження посту (денний):\n{e}")


def _new_mentions():
    from threads_mentions import new_mentions
    return new_mentions()


def _new_post_replies():
    from threads_replies import new_replies
    return new_replies()


_SOURCE_FUNCS = {"mentions": _new_mentions, "post_replies": _new_post_replies}


def collect_pending():
    """Pending reply items from every configured source, deduped by id.
    A failing source is logged and skipped; the others still run."""
    items, seen = [], set()
    names = [s.strip() for s in settings.REPLY_SOURCES.split(",") if s.strip()]
    for name in names:
        fetch = _SOURCE_FUNCS.get(name)
        if not fetch:
            log.warning("unknown REPLY_SOURCES entry %r — skipping", name)
            continue
        try:
            for it in fetch():
                iid = it.get("id")
                if iid and iid not in seen:
                    seen.add(iid)
                    items.append(it)
        except Exception:
            log.exception("could not fetch reply source %r", name)
    return items


def seed_seen():
    """Mark all currently-visible replies as seen WITHOUT answering — run once on
    first deploy so the existing backlog doesn't get a flood of answers."""
    from state import mark_seen
    items = collect_pending()
    for it in items:
        mark_seen(it["id"])
    log.info("seeded %d existing reply id(s) as seen (no answers sent)", len(items))


def do_replies(offline=False, dry_run=False):
    from state import mark_seen

    mentions = collect_pending()

    if not mentions:
        log.info("no new replies")
        return

    from moderation import screen, pick_canned
    from logsink import log_block

    log.info("processing %d new reply/replies", len(mentions))
    for m in mentions:
        mid = m["id"]
        raw_q = m.get("question") or ""
        log.info("mention %s from @%s: %s", mid, m.get("username"), raw_q)

        # Suspicious / off-topic / injection -> canned reply, no tarot reading.
        reason = screen(raw_q)
        if reason:
            ctext, cimg = pick_canned()
            log.info("rejected mention %s (%s) -> canned reply", mid, reason)
            log_block("REJECTED_REPLY", mention=mid, user=m.get("username"),
                      reason=reason, question=raw_q, reply=ctext, image=str(cimg))
            try:
                publish(ctext, cimg, reply_to_id=mid, offline=offline, dry_run=dry_run)
                if not (offline or dry_run):
                    mark_seen(mid)
            except Exception:
                log.exception("failed canned reply for %s", mid)
            continue

        question = raw_q or "Загальний розклад на сьогодні"
        asker = m.get("username")
        try:
            cards, text, img = build_forecast(
                question=question, theme="питання користувача", offline=offline,
                subtitle=f"@{asker}" if asker else None)
            publish(text, img, reply_to_id=mid, offline=offline, dry_run=dry_run)
            if not (offline or dry_run):
                mark_seen(mid)
        except Exception:
            log.exception("failed to handle mention %s", mid)


def build_for_link(url, offline=False):
    """Resolve a Threads post link and build a reading for it.
    Returns (info, text, image_path). The post's own text is the reading's
    context (generic reading if it couldn't be read). The post is operator-
    chosen, so off-topic/injection screening is skipped."""
    from answer_url import resolve

    info = resolve(url)
    log.info("=== link reading ===")
    log.info("post by @%s | id=%s | text=%r",
             info["username"], info["post_id"], info["text"] or "(unavailable)")
    question = info["text"] or "Загальний розклад для цього допису"
    _, text, img = build_forecast(
        question=question, theme="відповідь на допис користувача",
        offline=offline, subtitle=f"@{info['username']}")
    return info, text, img


def build_for_question(username, question, offline=False):
    """Build a reading for a `@nickname - question` Telegram command.
    Image caption shows only @nickname (like the link flow); the question text
    drives the forecast. Operator-trusted, so screening is skipped.
    Returns (text, image_path)."""
    handle = (username or "").lstrip("@")
    log.info("=== question reading === @%s | q=%r", handle, question)
    _, text, img = build_forecast(
        question=question, theme="питання користувача",
        offline=offline, subtitle=f"@{handle}")
    return text, img


# In-memory store of /post drafts awaiting a button press, keyed by a short id.
# Lives only in the running scheduler process — a restart drops pending drafts,
# and the callback handler tells the user to re-run /post (the image also lives in
# .tmp, so persisting across restarts would be brittle). YAGNI: no disk store.
_DRAFTS = {}


def _draft_keyboard(did):
    """Inline keyboard offered under a /post draft."""
    return {"inline_keyboard": [[
        {"text": "✅ Запостити", "callback_data": f"post:{did}"},
        {"text": "♻️ Перепрогноз", "callback_data": f"redo:{did}"},
        {"text": "❌ Відмінити", "callback_data": f"cancel:{did}"},
    ]]}


def build_post_draft(question, offline=False):
    """Build a general Threads post (post body + daily CTA) for a /post question.
    Image caption is the bot's own @handle. Returns a draft dict."""
    handle = (settings.THREADS_USERNAME or "myaufar").lstrip("@")
    log.info("=== /post draft === q=%r", question)
    _, text, img = build_forecast(
        question=question, theme="питання користувача",
        offline=offline, subtitle=f"@{handle}")
    return {"question": question, "text": with_cta(text), "img": img}


def _send_draft(chat_id, draft):
    """Store a draft under a fresh id and send it with the action buttons."""
    from telegram_listener import send_photo
    did = uuid4().hex[:8]
    _DRAFTS[did] = draft
    send_photo(chat_id, draft["img"], caption=draft["text"],
               reply_markup=_draft_keyboard(did))


def handle_post_callback(cmd, chat_id, offline=False):
    """React to a /post inline button (Publish / Re-forecast / Cancel)."""
    from telegram_listener import (answer_callback, edit_caption,
                                   edit_reply_markup, send_message)
    cbq = cmd["callback_query_id"]
    mid = cmd["message_id"]
    action, _, did = (cmd.get("data") or "").partition(":")
    draft = _DRAFTS.get(did)

    if not draft:
        answer_callback(cbq, "Чернетка застаріла — зроби /post ще раз")
        edit_reply_markup(chat_id, mid)  # strip stale buttons
        return

    if action == "cancel":
        _DRAFTS.pop(did, None)
        answer_callback(cbq, "Відмінено")
        edit_caption(chat_id, mid, "❌ Відмінено", reply_markup={"inline_keyboard": []})

    elif action == "post":
        answer_callback(cbq, "Публікую в Threads…")
        try:
            media_id = publish(draft["text"], draft["img"],
                               reply_to_id=None, offline=offline)
            _DRAFTS.pop(did, None)
            edit_caption(chat_id, mid,
                         f"✅ Опубліковано в Threads (media id {media_id})",
                         reply_markup={"inline_keyboard": []})
        except Exception as e:
            log.exception("telegram /post publish failed")
            # Keep the draft + buttons so the user can retry.
            send_message(chat_id, f"⚠️ Збій завантаження посту:\n{e}")

    elif action == "redo":
        answer_callback(cbq, "Роблю новий прогноз…")
        edit_reply_markup(chat_id, mid)  # strip old buttons; a new message follows
        _DRAFTS.pop(did, None)
        try:
            _send_draft(chat_id, build_post_draft(draft["question"], offline=offline))
        except Exception as e:
            log.exception("telegram /post re-forecast failed")
            send_message(chat_id, f"Не вдалося перепрогнозувати: {e}")

    else:
        answer_callback(cbq, "")  # unknown action — just dismiss the spinner


def do_telegram_poll(offline=False):
    """Poll the Telegram bridge once; for each linked post, build a reading and
    send the image + text back to the sender in Telegram (no Threads publish —
    the API can't reply under a 3rd-party post). A failure on one link is
    reported to the user and logged, never crashes the poll."""
    from telegram_listener import poll_once, send_message, send_photo

    def handle(cmd, chat_id):
        log.info("telegram command from chat %s: %s", chat_id, cmd)
        kind = cmd["kind"]

        if kind == "callback":
            handle_post_callback(cmd, chat_id, offline=offline)
            return

        if kind == "post":
            send_message(chat_id, "Готую пост, дай хвилинку… 🔮")
            try:
                _send_draft(chat_id, build_post_draft(cmd["question"], offline=offline))
            except Exception as e:
                log.exception("telegram /post build failed for %s", cmd)
                send_message(chat_id, f"Не вдалося зробити прогноз: {e}")
            return

        send_message(chat_id, "Прийняв, роблю розклад… 🔮")
        try:
            if kind == "link":
                _, text, img = build_for_link(cmd["url"], offline=offline)
            else:  # "question": @nickname - question
                text, img = build_for_question(
                    cmd["username"], cmd["question"], offline=offline)
            send_photo(chat_id, img, caption=text)
        except Exception as e:
            log.exception("telegram reading failed for %s", cmd)
            send_message(chat_id, f"Не вдалося зробити розклад: {e}")

    try:
        poll_once(handle)
    except Exception:
        log.exception("telegram poll failed")


def run_scheduler():
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    sched = BlockingScheduler(timezone=settings.TZ)
    sched.add_job(do_daily, CronTrigger.from_crontab(settings.POST_CRON,
                                                     timezone=settings.TZ),
                  id="daily_post")
    sched.add_job(do_replies, "interval",
                  minutes=settings.MENTION_POLL_MINUTES, id="poll_mentions")
    if settings.TELEGRAM_BOT_TOKEN:
        sched.add_job(do_telegram_poll, "interval",
                      seconds=settings.TELEGRAM_POLL_SECONDS, id="poll_telegram")
        log.info("telegram bridge ON | poll every %ds | allowed user=%s",
                 settings.TELEGRAM_POLL_SECONDS, settings.TELEGRAM_ALLOWED_USER_ID)
    log.info("scheduler up | daily cron=%r tz=%s | mention poll every %d min",
             settings.POST_CRON, settings.TZ, settings.MENTION_POLL_MINUTES)
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("shutting down")


def main():
    ap = argparse.ArgumentParser(description="Threads tarot bot")
    ap.add_argument("--post-now", action="store_true", help="run daily flow once")
    ap.add_argument("--reply-once", action="store_true", help="process replies once")
    ap.add_argument("--seed-seen", action="store_true",
                    help="mark existing replies seen WITHOUT answering (run once)")
    ap.add_argument("--answer-url", metavar="URL",
                    help="build and print a reading for this Threads post link (no posting)")
    ap.add_argument("--telegram-once", action="store_true",
                    help="process pending Telegram command messages once, then exit")
    ap.add_argument("--dry-run", action="store_true", help="build but don't post")
    ap.add_argument("--offline", action="store_true",
                    help="skip OpenAI + Imgur + Threads (local smoke test)")
    a = ap.parse_args()

    if settings.PUBLIC_IMAGE_BASE and not a.offline:
        import image_server
        image_server.start_background()
        log.info("image server on :%d serving %s",
                 settings.IMAGE_SERVER_PORT, config.PUBLIC_DIR)

    if a.answer_url:
        # Build a reading for the link and print it (no Threads publish — the API
        # can't reply under a 3rd-party post; delivery is via Telegram).
        _, text, img = build_for_link(a.answer_url, offline=a.offline)
        log.info("reading built -> %s\n--- text ---\n%s", img, text)
    elif a.telegram_once:
        do_telegram_poll(offline=a.offline)
    elif a.post_now:
        do_daily(offline=a.offline, dry_run=a.dry_run)
    elif a.seed_seen:
        seed_seen()
    elif a.reply_once:
        do_replies(offline=a.offline, dry_run=a.dry_run)
    else:
        run_scheduler()


if __name__ == "__main__":
    main()
