FROM python:3.12-slim

WORKDIR /app

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY config.py .
COPY web_demo.py .

ENV PORT=8080
EXPOSE 8080

CMD ["python3", "web_demo.py"]
