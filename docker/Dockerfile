FROM python:3.12.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/android/platform-tools:${PATH}"
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip ffmpeg bash \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/android \
    && curl -fsSL https://dl.google.com/android/repository/platform-tools_r37.0.1-linux.zip -o /tmp/adb.zip \
    && echo '477254aa5f903c15cf51001717bdf347fb6b53e0  /tmp/adb.zip' | sha1sum -c - \
    && unzip -q /tmp/adb.zip -d /opt/android && rm /tmp/adb.zip
WORKDIR /gateway
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -c constraints.txt -r requirements.txt
COPY app app
COPY migrations migrations
COPY alembic.ini pyproject.toml ./
COPY scripts scripts
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"]
