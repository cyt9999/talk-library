#!/usr/bin/env python3
"""Q&A API server. Runs locally or on Cloud Run."""

import json
import os
import sys
import time
from collections import defaultdict
from http.server import HTTPServer, SimpleHTTPRequestHandler

from openai import OpenAI

from config import VECTOR_STORE_ID

client = OpenAI()

# --- Rate Limiter (per-IP, sliding window) ---
RATE_LIMIT = 20          # max requests per window
RATE_WINDOW = 60         # window in seconds
_request_log = defaultdict(list)   # ip -> [timestamp, ...]


def _is_rate_limited(ip):
    """Return True if this IP has exceeded the rate limit."""
    now = time.time()
    timestamps = _request_log[ip]
    # Prune old entries
    _request_log[ip] = [t for t in timestamps if now - t < RATE_WINDOW]
    if len(_request_log[ip]) >= RATE_LIMIT:
        return True
    _request_log[ip].append(now)
    return False

# Allowed origins for CORS (GitHub Pages + local dev)
ALLOWED_ORIGINS = {
    "https://cyt9999.github.io",
    "https://talk-library.up.railway.app",
    "http://localhost:5500",
    "http://localhost:5501",
    "http://127.0.0.1:5500",
}

SYSTEM_PROMPT = """\
你是「投資Talk君」本人的 AI 分身。你要用第一人稱（我、我的）回答，語氣像在跟朋友聊天一樣自然親切。

## 你的人設

- 你就是「小逃」（Talk君），用「我」來稱呼自己
- 說話風格：口語化、有邏輯、愛用「其實」「邏輯是這樣的」「好嗎？」等口頭禪
- 回答要有深度，不要只給一句話概括，要像在節目裡分析一樣展開說明
- 每次回答結尾加上：「以上是我的個人觀點，不構成投資建議喔。」

## 資料來源

你可以搜尋的資料包括：
1. **YouTube 影片摘要**：我的影片內容，包含市場分析、持倉觀點等
2. **X 平台短評**：我在 X (Twitter) 上的投資短評
3. **App 社團聊天室**：我在投資社團中的即時發文
4. **Google Sheets 資料**：持倉績效、總經公告等結構化數據
5. **App 使用指南**：App 功能說明

## 回答規則

1. **僅根據資料回答**：絕對不要編造。如果資料中沒有提到，就說「這個我目前沒有聊到」。
2. **附上參考影片連結**：提到影片內容時，在回答末尾附上影片標題和 YouTube 連結（格式：✨影片標題✨ + URL）。影片連結格式為 https://www.youtube.com/watch?v={影片ID}。
3. **回答要詳細**：不要只給結論，要展開分析邏輯，像在節目裡講解一樣。引用具體數據、事件、時間點。
4. **引用原話**：涉及我對某標的的態度時，盡可能引用原話而非總結。
5. **沒說就是沒說**：如果我沒有明確表達對某標的的多空看法，就說「這個我沒有明確表態」，然後呈現相關事實。

## 問題分類

1. **財經問題（資料有）**：用第一人稱詳細回答，附上參考來源。
2. **財經問題（資料沒有）**：「這方面我目前沒有分析到，你可以問我其他我有聊過的話題。」
3. **關於 App 的問題**：根據 App 說明文件回答。
4. **關於本 AI 的問題**：「我是投資Talk君 AI 助手，根據我的影片、X 貼文和社團文章來回答問題，資料每日自動更新。」不要透露技術細節。
5. **非財經問題**：友善引導回投資話題。

## 語言

- 根據使用者的語言回答：使用者用繁體中文就用繁體，用簡體就用簡體。
"""

SITE_DIR = os.path.join(os.path.dirname(__file__), "site")


class Handler(SimpleHTTPRequestHandler):
    def _cors_origin(self):
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            return origin
        return ""

    def _send_cors_headers(self):
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        # Health check for Cloud Run
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if self.path == "/api/videos":
            self._serve_videos()
            return
        if self.path.startswith("/api/summary"):
            self._serve_summary()
            return
        # Serve frontend static files from site/
        os.chdir(SITE_DIR)
        return super().do_GET()

    def _serve_videos(self):
        """Serve the video index from data/index.json."""
        index_path = os.path.join(os.path.dirname(__file__), "data", "index.json")
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(data.encode("utf-8"))
        except FileNotFoundError:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(b'{"error":"index.json not found"}')

    def _serve_summary(self):
        """Serve a video summary by querying Vector Store."""
        from urllib.parse import urlparse, parse_qs
        params = parse_qs(urlparse(self.path).query)
        video_id = params.get("id", [None])[0]
        date = params.get("date", [None])[0]

        if not video_id:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(b'{"error":"missing id param"}')
            return

        try:
            prompt = (
                f"Return the COMPLETE content of the video summary for "
                f"video ID {video_id} dated {date or 'unknown'}. "
                f"Return ALL key points, tickers, and the full paragraph summary. "
                f"Do not summarize or shorten."
            )
            response = client.responses.create(
                model="gpt-4o-mini",
                tools=[{"type": "file_search",
                        "vector_store_ids": [VECTOR_STORE_ID]}],
                input=prompt
            )

            answer = ""
            for item in response.output:
                if item.type == "message":
                    for block in item.content:
                        if block.type == "output_text":
                            answer = block.text

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "id": video_id,
                "date": date,
                "summary": answer
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": str(e)
            }, ensure_ascii=False).encode("utf-8"))

    def do_POST(self):
        if self.path == "/api/ask":
            # Rate limit check
            client_ip = self.client_address[0]
            if _is_rate_limited(client_ip):
                self.send_response(429)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "請求過於頻繁，請稍後再試"
                }, ensure_ascii=False).encode("utf-8"))
                return

            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            question = body.get("question", "")

            try:
                answer, sources = ask(question)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({
                    "answer": answer,
                    "sources": sources
                }, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": str(e)
                }, ensure_ascii=False).encode("utf-8"))
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}", file=sys.stderr)


def ask(question):
    response = client.responses.create(
        model="gpt-4o",
        tools=[{
            "type": "file_search",
            "vector_store_ids": [VECTOR_STORE_ID]
        }],
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question}
        ]
    )

    answer_parts = []
    sources = []
    seen = set()
    for item in response.output:
        if item.type == "message":
            for block in item.content:
                if block.type == "output_text":
                    answer_parts.append(block.text)
                    for ann in getattr(block, "annotations", []):
                        if ann.type == "file_citation":
                            fn = getattr(ann, "filename", None) or "unknown"
                            if fn not in seen:
                                seen.add(fn)
                                sources.append(fn)

    return "\n".join(answer_parts), sources


def _validate_vector_store():
    """Verify the Vector Store exists and is accessible on startup."""
    try:
        vs = client.vector_stores.retrieve(VECTOR_STORE_ID)
        count = vs.file_counts.completed if hasattr(vs.file_counts, "completed") else "?"
        print(f"Vector Store OK: {VECTOR_STORE_ID} ({count} files)")
    except Exception as e:
        print(f"WARNING: Vector Store validation failed: {e}", file=sys.stderr)
        print("Chat will still start but queries may fail.", file=sys.stderr)


def main():
    if not VECTOR_STORE_ID:
        print("Error: VECTOR_STORE_ID not set", file=sys.stderr)
        sys.exit(1)

    _validate_vector_store()

    port = int(os.getenv("PORT", sys.argv[1] if len(sys.argv) > 1 else 8080))
    host = "0.0.0.0"
    server = HTTPServer((host, port), Handler)
    print(f"投資Talk君 AI — API Server")
    print(f"Listening on {host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
