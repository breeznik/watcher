FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for Playwright/Chromium
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libcups2 libdrm2 libxkbcommon0 libasound2 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
    libpangocairo-1.0-0 libatspi2.0-0 libx11-xcb1 libxshmfence1 \
    libgtk-3-0 libxss1 libxtst6 libglib2.0-0 fonts-liberation \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir playwright==1.49.0 \
    && python -m playwright install chromium

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts/entrypoint.sh ./

# Ensure runtime directories exist without copying local data
RUN mkdir -p /app/data/artifacts

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
CMD ["/app/entrypoint.sh"]