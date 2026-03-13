# 投資Talk君 權限控管設計

## 概述

為投資Talk君 AI 問答功能加入免費/付費用戶權限控管。免費用戶每日限 3 題，付費用戶不限次數。

## 方案選擇

**採用方案 C：後端驗證 Token + 快取**

- 後端拿 CMoney JWT token → 呼叫 license API 驗證付費狀態 → 快取結果
- 不使用不同 URL/blueprint 區分，單一入口靠 token 判斷

淘汰方案：
- 方案 A（後端驗證無快取）：可行但每次都打 API，不必要
- 方案 B（前端驗證）：不安全，用戶可偽造參數

## 認證與權限流程

```
App 透過 silent_renew 代登 → webview 寫入 cookie (cm_at)
        ↓
前端從 cookie 讀取 cm_at token
        ↓
用戶發送問題 → POST /api/ask
    headers: { Authorization: Bearer <token> }
    body: { question: "..." }
        ↓
後端收到請求：
  1. 從 Authorization header 取 token
     - 無 token → 走 IP-based 限制（每日 3 題）
     - 有 token → 繼續
  2. Decode JWT → 取 uid + 檢查 exp
     - exp 過期 → 401
  3. 用 uid 查記憶體快取：uid → { is_premium, cached_at }
     - 命中且未過期(10min) → 用快取
     - 未命中/過期 → 呼叫 license API → 快取結果
  4. 判斷權限：
     - 付費用戶 → 直接放行
     - 免費用戶 → 查每日用量（uid 為 key）
       - < 3 題 → 放行，計數 +1
       - >= 3 題 → 403 + 升級引導
        ↓
回傳：{ answer, sources, remaining_quota }
```

## 權限 API

```
GET https://license.cmoney.tw/AuthorizationServer/Authorization/MobilePaid/245
Authorization: Bearer <cm_at>
```

- authType: MobilePaid
- subjectId: 245（投資Talk君）
- 不使用 MobileService（即將關閉）
- 不使用 CMoney member GraphQL（只有基本資料，無權限）

## 儲存與資料結構

全部使用記憶體 dict，不引入外部 DB。容器重啟會清空，影響極小。

```python
# 權限快取：uid → 付費狀態
_permission_cache = {}
# { uid: { "is_premium": True/False, "cached_at": timestamp } }
# TTL: 10 分鐘

# 每日用量計數：uid 或 IP → 當日已問題數
_daily_usage = {}
# { "uid:12345": { "count": 2, "date": "2026-03-12" } }
# { "ip:1.2.3.4": { "count": 1, "date": "2026-03-12" } }
# 日期不同時自動重置

# 常數
DAILY_FREE_LIMIT = 3
PERMISSION_CACHE_TTL = 600  # 10 分鐘（秒）
```

設計決策：
- uid 和 IP 用同一個 dict，靠前綴 `uid:` / `ip:` 區分
- 日期切換自動歸零，不需要排程清理
- 不做持久化，未來有需要再加 Redis

## 改動範圍

### 後端 `web_demo.py`

| 改動 | 說明 |
|------|------|
| 新增 `_decode_token(token)` | base64 decode JWT，取 uid + exp，不做簽章驗證 |
| 新增 `_check_permission(uid, token)` | 查快取或呼叫 license API，回傳 is_premium |
| 新增 `_check_daily_quota(key)` | 檢查 uid/IP 的每日用量，回傳 (allowed, remaining) |
| 修改 `do_POST /api/ask` | 在呼叫 `ask()` 前插入權限檢查邏輯 |
| 回傳格式新增 `remaining_quota` | 讓前端顯示剩餘次數 |

### 後端 `config.py`

| 改動 | 說明 |
|------|------|
| 新增 `DAILY_FREE_LIMIT` | 預設 3 |
| 新增 `CMONEY_LICENSE_API_URL` | `https://license.cmoney.tw/AuthorizationServer/Authorization` |
| 新增 `CMONEY_AUTH_TYPE` | `MobilePaid` |
| 新增 `CMONEY_SUBJECT_ID` | `245` |
| 新增 `PERMISSION_CACHE_TTL` | 預設 600 秒 |

### 前端 `chat.js`

| 改動 | 說明 |
|------|------|
| 新增 `_getTokenFromCookie()` | 從 cookie 讀取 `cm_at` |
| 修改 `fetch` 請求 | 加上 `Authorization: Bearer <token>` header |
| 新增處理 401/403 回應 | 401 顯示「請重新登入」；403 顯示升級引導 |
| 新增剩餘次數顯示 | 免費用戶顯示「今日剩餘 X/3 次」 |

### 不改動

- `ask()` 函式 — 不動，純粹負責問 OpenAI
- CORS 設定 — 不動
- 現有 IP rate limit (20 req/min) — 保留，和每日額度是不同層級的防護
- 部署設定 — 不需改動

## 部署備註

- 目前部署在 Render（計劃遷移至 Railway）
- 記憶體 dict 策略在兩個平台都適用
- 無需新增環境變數（license API URL 和 subjectId 寫死即可）
