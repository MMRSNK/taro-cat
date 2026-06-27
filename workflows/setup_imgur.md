# Workflow: Set up Imgur image hosting

Goal: get an `IMGUR_CLIENT_ID` so the bot can upload composed forecast images and
get a public URL (required by the Threads API).

## Steps
1. Sign in at https://imgur.com (free account).
2. Go to https://api.imgur.com/oauth2/addclient and register an application:
   - **Authorization type:** *"OAuth 2 authorization without a callback URL"*
     (we only do anonymous image uploads — no user login needed).
   - Fill name / email.
3. Copy the **Client ID** it gives you.
4. Put it in `.env`:
   ```
   IMGUR_CLIENT_ID=your_client_id
   ```

## Verify
```bash
python tools/upload_imgur.py .tmp/<some_forecast>.png
# prints a public https://i.imgur.com/....png URL
```

## Notes
- Anonymous uploads use only the Client ID (no secret/token).
- Free tier has rate limits (plenty for a few posts/day). If you ever hit limits or
  want permanent hosting, switch to Cloudinary/S3 by replacing `tools/upload_imgur.py`.
