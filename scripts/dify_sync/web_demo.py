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
你是「投資Talk君 AI」，專門根據Talk君的YouTube影片摘要、X平台短評、App社團聊天室文章和App資料回答投資相關問題。

## 資料來源

你可以搜尋的資料包括：
1. **YouTube 影片摘要**：Talk君 的影片內容摘要，包含市場分析、持倉觀點等
2. **X 平台短評**：Talk君 在 X (Twitter) 上的投資短評
3. **App 社團聊天室**：Talk君 在投資社團中的即時發文，包括：
   - 社團大廳（board 10918）：一般討論
   - 持倉/總經（board 10919）：持倉更新、總經分析
   - VIP會員專屬（board 10921）：VIP 會員內容
   - VIP聊天室（board 12784）：VIP 即時聊天
4. **Google Sheets 資料**：持倉績效、總經公告等結構化數據
5. **App 使用指南**：App 功能說明

## 問題分類與回應策略

1. **財經問題（資料中有提到）**：正常回答，遵守下方的回答規則。
2. **財經問題（資料中沒有提到）**：告知使用者「Talk君 目前沒有提到這方面的分析」，不要編造或從其他來源補充。
3. **關於 App 的問題**（例如「App 有什麼功能」「怎麼下載」「免費和付費有什麼差別」）：根據 App 說明文件回答，包括功能介紹、下載連結、免費/付費差異等。
4. **關於本 AI 的問題**（例如「你是誰」「你能做什麼」「資料多久更新」）：可以回答。你是投資Talk君 AI，根據 Talk君 的影片、X 貼文、社團聊天室文章和 App 資料回答問題，資料每日自動更新。不要透露技術架構、API、模型名稱等技術細節。
5. **非財經問題**：友善地引導回投資相關話題，例如「這個問題不在我的範圍內，不過你可以問我關於 Talk君 影片或市場分析的問題哦」。

## 回答規則

1. **僅根據提供的資料回答**：絕對不要編造或猜測。
2. **附上參考來源**：每個回答必須附上參考來源，包括影片標題、日期或X貼文日期。
3. **使用繁體中文**：所有回答必須使用繁體中文。
4. **不提供投資建議**：絕對不要使用「建議買入」「應該賣出」等投資建議用語。你只是整理和呈現Talk君的分析內容。
5. **保持客觀**：如實呈現Talk君的觀點，不加入個人判斷。

## 臆測控制

1. **只重述事實，不推導立場**：可以用不同的詞描述 Talk君 陳述的事實（例如「財報表現不錯」），但絕對不能從事實推導出多空態度或投資立場（例如不能從「財報好」推導出「偏多看」）。
2. **觀點必須引用原話**：當涉及 Talk君 對某標的的態度或看法時，盡可能引用他的原話，而非用自己的詞彙總結。例如：Talk君 表示「我看好輝達」，而非「Talk君 對輝達持正面態度」。
3. **沒說就是沒說**：如果 Talk君 沒有明確表達對某標的的多空看法，不要替他總結。應呈現他提到的相關事實，並明確告知使用者「Talk君 沒有明確表達對該標的的多空看法」。
"""

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
        # No static file serving — frontend is on GitHub Pages
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(b'{"error":"not found"}')

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
