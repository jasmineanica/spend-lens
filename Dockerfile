FROM python:3.12-slim

# Native libraries WeasyPrint needs for PDF rendering (Pango/Cairo/HarfBuzz) + fonts.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libcairo2 \
    libffi8 \
    libjpeg62-turbo \
    libfontconfig1 \
    fonts-dejavu-core \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV ENABLE_LLM=false \
    PORT=8000

# Render (and most PaaS) inject $PORT; shell form expands it.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
