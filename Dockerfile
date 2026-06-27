FROM python:3.12-slim

# Fonts for Pillow text rendering (Cyrillic) + tzdata for cron timezones
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Long-running orchestrator (scheduled posts + mention polling)
CMD ["python", "tools/run_bot.py"]
