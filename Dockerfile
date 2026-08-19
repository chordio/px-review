FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PX_REVIEW_DATABASE=/data/px-review.db

WORKDIR /app

COPY pyproject.toml README.md ./
COPY pxreview ./pxreview
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 pxreview \
    && mkdir /data \
    && chown pxreview:pxreview /data
USER pxreview

EXPOSE 8000
CMD ["px-review", "serve", "--host", "0.0.0.0", "--port", "8000"]

