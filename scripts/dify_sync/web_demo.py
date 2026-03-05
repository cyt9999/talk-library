#!/usr/bin/env python3
"""Q&A API server. Runs locally or on Cloud Run."""

import json
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

from openai import OpenAI

from config import VECTOR_STORE_ID

client = OpenAI()

# Allowed origins for CORS (GitHub Pages + local dev)
ALLOWED_ORIGINS = {
    "https://cyt9999.github.io",
    "https://talk-library.onrender.com",
    "http://localhost:5500",
    "http://localhost:5501",
    "http://127.0.0.1:5500",
}

SYSTEM_PROMPT = """\
你是「投資Talk君 AI」，專門根據Talk君的YouTube影片摘要和X平台短評回答投資相關問題。

## 規則

1. **僅根據提供的資料回答**：如果資料中沒有相關內容，請誠實說明「目前資料中沒有這方面的分析」。絕對不要編造或猜測。
2. **附上參考來源**：每個回答必須附上參考來源，包括影片標題、日期或X貼文日期。
3. **使用繁體中文**：所有回答必須使用繁體中文。
4. **不提供投資建議**：絕對不要使用「建議買入」「應該賣出」等投資建議用語。你只是整理和呈現Talk君的分析內容。
5. **保持客觀**：如實呈現Talk君的觀點，不加入個人判斷。
"""

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


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
        if self.path == "/" or self.path == "/index.html":
            self.path = "/index.html"
            os.chdir(STATIC_DIR)
            return super().do_GET()
        os.chdir(STATIC_DIR)
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/ask":
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


def main():
    if not VECTOR_STORE_ID:
        print("Error: VECTOR_STORE_ID not set", file=sys.stderr)
        sys.exit(1)

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
