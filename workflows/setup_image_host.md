# Workflow: Image hosting (public URL for Threads)

The Threads API can't take a raw image upload — it needs the image at a **public URL**.
The bot uploads the composed forecast image to a host and passes that URL to Threads.

## Default: catbox.moe (no account, no key) ✅
Nothing to set up. `IMAGE_HOST=catbox` (default) just works.
- Permanent direct links (`https://files.catbox.moe/xxxx.png`).
- No registration, no API key.

## Options (set `IMAGE_HOST` in `.env`)

| Host | Account/key? | Notes |
|------|--------------|-------|
| `catbox` (default) | none | permanent links, simplest |
| `tmpfiles` | none | link valid ~1h — fine, Threads fetches the image within seconds at publish |
| `imgur` | needs `IMGUR_CLIENT_ID` | only if you already have one |

> Why ephemeral hosts are OK: Threads downloads the image into its own storage during
> the publish step (seconds after upload). The public URL only needs to live that long.

## Verify
```bash
# compose a test image first
python tools/compose_image.py
# upload it (uses IMAGE_HOST from .env, default catbox)
python tools/upload_image.py .tmp/<forecast_file>.png
# -> prints a public https URL; open it in a browser to confirm it loads
```

## Switch hosts
Just change `.env`:
```
IMAGE_HOST=tmpfiles
```
No code change. To add another host (Cloudinary/S3/etc.), add a function in
`tools/upload_image.py` and register it in `_PROVIDERS`.
