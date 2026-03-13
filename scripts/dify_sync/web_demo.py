#!/usr/bin/env python3
"""Q&A API server. Runs locally or on Cloud Run."""

import base64
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date
from http.server import HTTPServer, SimpleHTTPRequestHandler, ThreadingHTTPServer

import requests as http_requests

from openai import OpenAI

from config import (VECTOR_STORE_ID, DAILY_FREE_LIMIT, PERMISSION_CACHE_TTL,
                     CMONEY_LICENSE_URL, CMONEY_AUTH_TYPE, CMONEY_SUBJECT_ID)

client = OpenAI()

# --- Rate Limiter (per-IP, sliding window) ---
RATE_LIMIT = 20          # max requests per window
RATE_WINDOW = 60         # window in seconds
_request_log = defaultdict(list)   # ip -> [timestamp, ...]

# --- Permission Control ---
_permission_cache = {}   # uid -> {"is_premium": bool, "cached_at": float}
_daily_usage = {}        # "uid:<id>" or "ip:<addr>" -> {"count": int, "date": "YYYY-MM-DD"}


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


def _decode_token(token):
    """Decode JWT payload to extract uid (sub) and exp. No signature verification."""
    try:
        payload_b64 = token.split(".")[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        uid = payload.get("sub")
        exp = payload.get("exp")
        return uid, exp
    except Exception:
        return None, None


def _check_permission(uid, token):
    """Check if user is premium via cache or CMoney license API."""
    now = time.time()
    cached = _permission_cache.get(uid)
    if cached and (now - cached["cached_at"]) < PERMISSION_CACHE_TTL:
        return cached["is_premium"]

    try:
        url = f"{CMONEY_LICENSE_URL}/{CMONEY_AUTH_TYPE}/{CMONEY_SUBJECT_ID}"
        resp = http_requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=5)
        is_premium = resp.status_code == 200
    except Exception:
        is_premium = False

    _permission_cache[uid] = {"is_premium": is_premium, "cached_at": now}
    return is_premium


def _check_daily_quota(key):
    """Check and increment daily usage. Returns (allowed: bool, remaining: int)."""
    today = date.today().isoformat()
    usage = _daily_usage.get(key)

    if not usage or usage["date"] != today:
        _daily_usage[key] = {"count": 1, "date": today}
        return True, DAILY_FREE_LIMIT - 1

    if usage["count"] >= DAILY_FREE_LIMIT:
        return False, 0

    usage["count"] += 1
    return True, DAILY_FREE_LIMIT - usage["count"]


# Allowed origins for CORS (GitHub Pages + local dev)
ALLOWED_ORIGINS = {
    "https://cyt9999.github.io",
    "https://talk-library.up.railway.app",
    "http://localhost:5500",
    "http://localhost:5501",
    "http://127.0.0.1:5500",
}

SYSTEM_PROMPT = """\
你是「投資Talk君 AI」，專門根據 Talk君（小逃）的 YouTube 影片摘要、X 平台短評、App 社團聊天室文章和 App 資料回答投資相關問題。

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

## 回答深度要求（非常重要）

你的回答必須有深度，像在寫一篇分析文章，而非只給一句話的結論。具體要求：

1. **展開分析邏輯**：不要只說「Talk君 看好 X」，要說明他看好的原因、背後的邏輯鏈、他引用了什麼數據或現象。
2. **引用具體細節**：提到具體的數字（如債券利差、持倉比重、CPI 數據）、具體事件、具體日期。
3. **說明大背景**：把 Talk君 的觀點放在更大的市場背景中解釋，例如板塊趨勢、宏觀環境、市場情緒。
4. **引用原話**：涉及 Talk君 對某標的的態度時，盡可能引用他的原話，而非用自己的詞彙總結。
5. **多段落結構**：回答至少 3-5 段，有層次地展開。先講結論，再講邏輯，再講背景。
6. **結尾總結**：最後用一句話收尾總結。

**錯誤示範**（太短、沒深度）：
> Talk君 對甲骨文的觀點為中性。他提到債券價格上漲。

**正確示範**（有深度）：
> 關於甲骨文（Oracle），Talk君 在第 1387 期節目裡重點分析了它的邏輯。他觀察到一個很有意思的現象：債券價格和股價出現了背離。
>
> 雖然股價在跌，但債券市場的投資者其實在買入。當時由於甲骨文宣布了新的融資計劃，債券利差從 165 個基點大幅下降到了 138 左右，這說明債權人認為公司的風險在降低...

## 參考來源格式

1. **附上影片連結**：提到影片內容時，在回答末尾附上影片標題和 YouTube 連結。格式範例：
   ✨【投资TALK君1387期】"赶紧让我跑！"软件板块的末日！AMD指引炸裂，但没用✨
   https://www.youtube.com/watch?v=C0VjlrqzaAU
2. 影片連結格式為 https://www.youtube.com/watch?v={影片ID}，影片ID可從資料中的 metadata 取得。
3. 如果引用了多個來源，全部列出。

## 回答規則

1. **僅根據提供的資料回答**：絕對不要編造或猜測。
2. **不提供投資建議**：結尾加上「以上是 Talk君 的個人觀點，不構成投資建議。」
3. **保持客觀**：如實呈現 Talk君 的觀點，不加入個人判斷。
4. **沒說就是沒說**：如果 Talk君 沒有明確表達對某標的的多空看法，直接說明並呈現相關事實。

## 問題分類與回應策略

1. **財經問題（資料中有提到）**：詳細回答，遵守上方的深度要求和回答規則。
2. **財經問題（資料中沒有提到）**：告知使用者「Talk君 目前沒有提到這方面的分析」，不要編造。
3. **關於 App 的問題**：根據 App 說明文件回答。
4. **關於本 AI 的問題**：你是投資Talk君 AI，根據 Talk君 的影片、X 貼文、社團聊天室文章和 App 資料回答問題，資料每日自動更新。不要透露技術架構、API、模型名稱等技術細節。
5. **非財經問題**：友善地引導回投資相關話題。

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
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

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
        """Serve a video summary from static JSON files in data/summaries/."""
        from urllib.parse import urlparse, parse_qs
        params = parse_qs(urlparse(self.path).query)
        video_id = params.get("id", [None])[0]
        date = params.get("date", [None])[0]

        if not video_id:
            self._send_json(400, {"error": "missing id param"})
            return

        summaries_dir = os.path.join(os.path.dirname(__file__), "data", "summaries")

        # Try exact match: {date}-{id}.json
        if date:
            exact_path = os.path.join(summaries_dir, f"{date}-{video_id}.json")
            if os.path.isfile(exact_path):
                self._serve_file_json(exact_path)
                return

        # Fallback: search for any file ending with -{id}.json
        try:
            for fname in os.listdir(summaries_dir):
                if fname.endswith(f"-{video_id}.json"):
                    self._serve_file_json(os.path.join(summaries_dir, fname))
                    return
        except FileNotFoundError:
            pass

        self._send_json(404, {"error": "summary not found", "id": video_id})

    def _serve_file_json(self, path):
        """Read and serve a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(data.encode("utf-8"))

    def do_POST(self):
        if self.path == "/api/ask":
            # Rate limit check (existing — per-IP, anti-abuse)
            client_ip = self.client_address[0]
            if _is_rate_limited(client_ip):
                self._send_json(429, {"error": "請求過於頻繁，請稍後再試"})
                return

            # --- Permission check ---
            auth_header = self.headers.get("Authorization", "")
            token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""

            remaining_quota = None

            if token:
                uid, exp = _decode_token(token)
                if not uid:
                    self._send_json(401, {"error": "無效的登入憑證，請重新登入"})
                    return
                if exp and time.time() > exp:
                    self._send_json(401, {"error": "登入已過期，請重新登入"})
                    return

                is_premium = _check_permission(uid, token)
                if not is_premium:
                    allowed, remaining_quota = _check_daily_quota(f"uid:{uid}")
                    if not allowed:
                        self._send_json(403, {
                            "error": "今日免費額度已用完，升級付費版即可無限提問！",
                            "quota_exceeded": True,
                            "remaining_quota": 0
                        })
                        return
            else:
                # No token — anonymous, IP-based limit
                allowed, remaining_quota = _check_daily_quota(f"ip:{client_ip}")
                if not allowed:
                    self._send_json(403, {
                        "error": "今日免費額度已用完，登入並升級付費版即可無限提問！",
                        "quota_exceeded": True,
                        "remaining_quota": 0
                    })
                    return

            # --- Process question ---
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            question = body.get("question", "")

            try:
                answer, sources = ask(question)
                response_data = {
                    "answer": answer,
                    "sources": sources
                }
                if remaining_quota is not None:
                    response_data["remaining_quota"] = remaining_quota
                self._send_json(200, response_data)
            except Exception as e:
                self._send_json(500, {"error": str(e)})
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

    def _send_json(self, status_code, data):
        """Send a JSON response with CORS headers."""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

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
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"投資Talk君 AI — API Server")
    print(f"Listening on {host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
