FROM python:3.12-slim

WORKDIR /app

COPY scripts/dify_sync/requirements-api.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/dify_sync/config.py .
COPY scripts/dify_sync/web_demo.py .
COPY data/index.json ./data/index.json
COPY site/ ./site/

ENV PORT=8080
EXPOSE 8080

CMD ["python3", "web_demo.py"]
