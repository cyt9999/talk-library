# Permission Control Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add free/paid user permission gating to the 投資Talk君 AI chat, with free users limited to 3 questions/day.

**Architecture:** Backend validates CMoney JWT token from cookie, calls license API to check paid status (cached 10min by uid), and enforces daily quota for free users. Frontend reads token from cookie and sends via Authorization header.

**Tech Stack:** Python 3.12 (stdlib + requests), Vanilla JS, CMoney License API

**Design Doc:** `docs/plans/2026-03-12-permission-control-design.md`

---

### Task 1: Add `requests` dependency

**Files:**
- Modify: `scripts/dify_sync/requirements-api.txt`

**Step 1: Add requests to requirements**

Add `requests` to `scripts/dify_sync/requirements-api.txt`:

```
openai>=1.0.0
python-dotenv>=1.0.0
requests>=2.31.0
```

**Step 2: Install locally to verify**

Run: `pip install requests`

**Step 3: Commit**

```bash
git add scripts/dify_sync/requirements-api.txt
git commit -m "chore: add requests dependency for CMoney license API"
```

---

### Task 2: Add permission config to `config.py`

**Files:**
- Modify: `scripts/dify_sync/config.py`

**Step 1: Add permission constants**

Add these lines at the end of `scripts/dify_sync/config.py`:

```python
# Permission control
DAILY_FREE_LIMIT = int(os.getenv("DAILY_FREE_LIMIT", "3"))
PERMISSION_CACHE_TTL = int(os.getenv("PERMISSION_CACHE_TTL", "600"))  # seconds
CMONEY_LICENSE_URL = "https://license.cmoney.tw/AuthorizationServer/Authorization"
CMONEY_AUTH_TYPE = "MobilePaid"
CMONEY_SUBJECT_ID = "245"
```

**Step 2: Verify config loads without error**

Run: `cd scripts/dify_sync && python -c "from config import DAILY_FREE_LIMIT, PERMISSION_CACHE_TTL, CMONEY_LICENSE_URL; print(f'Limit={DAILY_FREE_LIMIT}, TTL={PERMISSION_CACHE_TTL}, URL={CMONEY_LICENSE_URL}')"`

Expected: `Limit=3, TTL=600, URL=https://license.cmoney.tw/AuthorizationServer/Authorization`

**Step 3: Commit**

```bash
git add scripts/dify_sync/config.py
git commit -m "feat: add permission control config constants"
```

---

### Task 3: Add token decode + permission check + quota logic to `web_demo.py`

**Files:**
- Modify: `scripts/dify_sync/web_demo.py`

**Step 1: Add imports and new config imports**

At the top of `web_demo.py`, after the existing imports, add:

```python
import base64
from datetime import date

import requests as http_requests

from config import (VECTOR_STORE_ID, DAILY_FREE_LIMIT, PERMISSION_CACHE_TTL,
                     CMONEY_LICENSE_URL, CMONEY_AUTH_TYPE, CMONEY_SUBJECT_ID)
```

Replace the existing `from config import VECTOR_STORE_ID` line.

**Step 2: Add permission data structures**

After the existing `_request_log` dict, add:

```python
# --- Permission Control ---
_permission_cache = {}   # uid -> {"is_premium": bool, "cached_at": float}
_daily_usage = {}        # "uid:<id>" or "ip:<addr>" -> {"count": int, "date": "YYYY-MM-DD"}
```

**Step 3: Add `_decode_token` function**

After the `_is_rate_limited` function, add:

```python
def _decode_token(token):
    """Decode JWT payload to extract uid (sub) and exp. No signature verification."""
    try:
        payload_b64 = token.split(".")[1]
        # Add padding
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        uid = payload.get("sub")
        exp = payload.get("exp")
        return uid, exp
    except Exception:
        return None, None
```

**Step 4: Add `_check_permission` function**

```python
def _check_permission(uid, token):
    """Check if user is premium via cache or CMoney license API."""
    now = time.time()

    # Check cache
    cached = _permission_cache.get(uid)
    if cached and (now - cached["cached_at"]) < PERMISSION_CACHE_TTL:
        return cached["is_premium"]

    # Call CMoney license API
    try:
        url = f"{CMONEY_LICENSE_URL}/{CMONEY_AUTH_TYPE}/{CMONEY_SUBJECT_ID}"
        resp = http_requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=5)
        is_premium = resp.status_code == 200
    except Exception:
        # On API failure, default to free
        is_premium = False

    _permission_cache[uid] = {"is_premium": is_premium, "cached_at": now}
    return is_premium
```

> **Note:** The exact response format of the license API may need adjustment. If the API returns 200 with a JSON body containing an authorization flag, update the `is_premium` check accordingly. The current implementation treats HTTP 200 as "has permission".

**Step 5: Add `_check_daily_quota` function**

```python
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
```

**Step 6: Verify syntax**

Run: `cd scripts/dify_sync && python -c "import web_demo; print('OK')"`

Expected: `OK` (or server starts — Ctrl+C to stop)

**Step 7: Commit**

```bash
git add scripts/dify_sync/web_demo.py
git commit -m "feat: add token decode, permission check, and daily quota functions"
```

---

### Task 4: Integrate permission checks into `do_POST`

**Files:**
- Modify: `scripts/dify_sync/web_demo.py`

**Step 1: Replace the `do_POST` method**

Replace the entire `do_POST` method in the `Handler` class with:

```python
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
```

**Step 2: Add `_send_json` helper method**

Add this method to the `Handler` class (before `log_message`):

```python
    def _send_json(self, status_code, data):
        """Send a JSON response with CORS headers."""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
```

**Step 3: Verify syntax**

Run: `cd scripts/dify_sync && python -c "import web_demo; print('OK')"`

**Step 4: Commit**

```bash
git add scripts/dify_sync/web_demo.py
git commit -m "feat: integrate permission checks into /api/ask endpoint"
```

---

### Task 5: Update frontend `chat.js` — token + auth headers

**Files:**
- Modify: `site/js/chat.js`

**Step 1: Add `_getTokenFromCookie` function**

Inside the ChatModule IIFE, after the variable declarations (`var _videoIndex = {};`), add:

```javascript
  function _getTokenFromCookie() {
    var match = document.cookie.match(/(?:^|;\s*)cm_at=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : '';
  }
```

**Step 2: Update fetch call in `_onSend` to include Authorization header**

Replace the existing `fetch(API_URL, {...})` call in `_onSend` with:

```javascript
    var headers = { 'Content-Type': 'application/json' };
    var token = _getTokenFromCookie();
    if (token) {
      headers['Authorization'] = 'Bearer ' + token;
    }

    fetch(API_URL, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({ question: text })
    })
```

**Step 3: Update response handling to show remaining quota and handle 401/403**

Replace the `.then` and `.catch` chain with:

```javascript
      .then(function (res) {
        if (res.status === 429) throw new Error('RATE_LIMIT');
        if (res.status === 401) throw new Error('AUTH_EXPIRED');
        if (res.status === 403) {
          return res.json().then(function (data) {
            var err = new Error('QUOTA_EXCEEDED');
            err.message_text = data.error;
            throw err;
          });
        }
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        thinkingEl.remove();
        _addAiBubble(data.answer || '', data.sources || []);
        if (data.remaining_quota !== undefined && data.remaining_quota !== null) {
          _showQuotaHint(data.remaining_quota);
        }
      })
      .catch(function (err) {
        thinkingEl.remove();
        if (err.message === 'RATE_LIMIT') {
          _addErrorBubble(TalkApp.label('chatRateLimit'));
        } else if (err.message === 'AUTH_EXPIRED') {
          _addErrorBubble('登入已過期，請重新開啟頁面');
        } else if (err.message === 'QUOTA_EXCEEDED') {
          _addErrorBubble(err.message_text || '今日免費額度已用完，升級付費版即可無限提問！');
        } else {
          _addErrorBubble(TalkApp.label('chatError'));
        }
      })
```

**Step 4: Add `_showQuotaHint` function**

Add after the `_addThinking` function:

```javascript
  function _showQuotaHint(remaining) {
    // Remove previous hint if exists
    var prev = _messagesEl.querySelector('.chat-quota-hint');
    if (prev) prev.remove();

    var hint = document.createElement('div');
    hint.className = 'chat-quota-hint';
    hint.textContent = '今日免費剩餘 ' + remaining + '/' + 3 + ' 次';
    _messagesEl.appendChild(hint);
    _scrollToBottom();
  }
```

**Step 5: Commit**

```bash
git add site/js/chat.js
git commit -m "feat: add token auth and quota display to chat frontend"
```

---

### Task 6: Add CSS for quota hint

**Files:**
- Modify: `site/css/style.css`

**Step 1: Find the chat section in style.css and add quota hint styles**

Search for `.chat-bubble-error` or similar chat styles in `site/css/style.css`, then add after them:

```css
.chat-quota-hint {
  text-align: center;
  font-size: 0.75rem;
  color: var(--text-muted, #888);
  padding: 0.25rem 0;
  opacity: 0.8;
}
```

**Step 2: Commit**

```bash
git add site/css/style.css
git commit -m "feat: add quota hint styling"
```

---

### Task 7: Add CORS support for Authorization header

**Files:**
- Modify: `scripts/dify_sync/web_demo.py`

**Step 1: Update CORS headers to allow Authorization**

In the `_send_cors_headers` method, change the `Access-Control-Allow-Headers` line:

From:
```python
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
```

To:
```python
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
```

**Step 2: Commit**

```bash
git add scripts/dify_sync/web_demo.py
git commit -m "fix: allow Authorization header in CORS"
```

---

### Task 8: Manual integration test

**Step 1: Start local server**

Run: `cd scripts/dify_sync && python web_demo.py`

**Step 2: Test anonymous request (no token)**

```bash
curl -s -X POST http://localhost:8080/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "test"}' | python -m json.tool
```

Expected: 200 with `remaining_quota` field (should be 2 after first request).

**Step 3: Test anonymous quota exhaustion**

Run the same curl 3 more times. 4th request should return 403 with `quota_exceeded: true`.

**Step 4: Test with invalid token**

```bash
curl -s -X POST http://localhost:8080/api/ask \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer invalid.token.here" \
  -d '{"question": "test"}'
```

Expected: 401 with error message.

**Step 5: Test preflight CORS**

```bash
curl -s -X OPTIONS http://localhost:8080/api/ask \
  -H "Origin: https://cyt9999.github.io" \
  -H "Access-Control-Request-Headers: Authorization" \
  -D - -o /dev/null
```

Expected: 204 with `Access-Control-Allow-Headers: Content-Type, Authorization`.

**Step 6: Commit all work if any fixes were needed**

```bash
git add -A
git commit -m "test: verify permission control integration"
```
