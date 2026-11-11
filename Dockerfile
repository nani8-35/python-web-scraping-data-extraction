FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    SCRAPING_BROWSER_BINARY=/usr/bin/chromium
RUN apt-get update && apt-get install -y --no-install-recommends chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 scraper
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . && mkdir -p /app/artifacts && chown -R scraper:scraper /app
USER scraper
ENTRYPOINT ["python", "-m", "scraping_system.cli"]
CMD ["books", "--max-pages", "1", "--format", "json"]
