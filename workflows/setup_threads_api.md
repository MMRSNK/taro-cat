# Workflow: Set up the Threads (Meta) Graph API

Goal: obtain `THREADS_USER_ID` and a long-lived `THREADS_ACCESS_TOKEN` so the bot
can publish posts, reply, and read mentions.

## Prerequisites
- A Threads account (public) linked to the person who will run the bot.
- A Meta/Facebook account to create a developer app.

## Steps

1. **Create a Meta app**
   - Go to https://developers.facebook.com/apps → *Create app*.
   - Choose use case **"Access the Threads API"** (or add the **Threads** product later).

2. **Add the Threads use case + permissions**
   In the app dashboard → *Use cases* → Threads → *Customize*, request these scopes:
   - `threads_basic` — required for everything
   - `threads_content_publish` — publish posts
   - `threads_manage_replies` — post replies
   - `threads_read_replies` — read replies (optional but useful)
   - `threads_manage_mentions` — read @mentions (needed for the reply feature)

3. **Add yourself as a Threads tester**
   - App roles → add your Threads account as a tester.
   - Accept the invite inside the Threads app (Settings → Website permissions / Invites).

4. **Generate a user access token**
   - Use the Threads API token generator in the dashboard (or the Graph API Explorer)
     for your tester account with the scopes above.
   - This gives a **short-lived** token first.

5. **Exchange for a long-lived token (~60 days)**
   ```bash
   curl -s "https://graph.threads.net/access_token\
   ?grant_type=th_exchange_token\
   &client_secret=APP_SECRET\
   &access_token=SHORT_LIVED_TOKEN"
   ```
   Save the returned `access_token` as `THREADS_ACCESS_TOKEN`.
   > Refresh it before expiry with `grant_type=th_refresh_token`.

6. **Get your Threads user id**
   ```bash
   curl -s "https://graph.threads.net/v1.0/me?fields=id,username\
   &access_token=YOUR_TOKEN"
   ```
   Save `id` as `THREADS_USER_ID`.

7. **Fill `.env`**
   ```
   THREADS_USER_ID=...
   THREADS_ACCESS_TOKEN=...
   ```

## Verify
```bash
# whoami
curl -s "https://graph.threads.net/v1.0/me?fields=id,username&access_token=$THREADS_ACCESS_TOKEN"
# mentions endpoint reachable (needs threads_manage_mentions)
curl -s "https://graph.threads.net/v1.0/me/mentions?fields=id,text,username&access_token=$THREADS_ACCESS_TOKEN"
```

## Notes / gotchas
- **Images must be at a public URL** to publish — the bot uploads to a host (default
  catbox.moe, no account; see `setup_image_host.md`).
- Image containers may need a few seconds of processing before publish; `threads_post.py`
  polls container `status` until `FINISHED`.
- Post text limit is **500 characters**; the bot clamps the forecast to fit.
- Long-lived tokens expire (~60 days). Set a reminder to refresh, or automate it later.
