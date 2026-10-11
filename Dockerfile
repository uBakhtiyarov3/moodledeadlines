FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
# ffmpeg converts AI voice replies to Telegram voice notes (OGG/Opus)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY webapp ./webapp
RUN useradd -m -u 1000 bot && mkdir -p data && chown bot data
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
# The ./data volume is created by Docker as root on the host: fix its owner on every start,
# then drop privileges and run the app as the unprivileged "bot" user.
CMD ["sh", "-c", "chown -R bot:bot /srv/data && exec setpriv --reuid=bot --regid=bot --init-groups python -m app.main"]
