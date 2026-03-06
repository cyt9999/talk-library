# 投資Talk君 — 技術架構文件

> **文件用途**：供開發團隊討論、改善與未來規劃使用  
> **最後更新**：2026-03-06  
> **專案倉庫**：https://github.com/cyt9999/talk-library  
> **此文件由 CI 自動產生**，手動維護段落以 `<!-- manual -->` 標記保護。

---

## 目錄

1. [專案概述](#1-專案概述)
2. [系統架構圖](#2-系統架構圖)
3. [資料來源與擷取](#3-資料來源與擷取)
4. [資料處理管線](#4-資料處理管線)
5. [RAG 知識庫架構](#5-rag-知識庫架構)
6. [前端架構](#6-前端架構)
7. [部署架構](#7-部署架構)
8. [自動化流程（GitHub Actions）](#8-自動化流程github-actions)
9. [成本估算](#9-成本估算)
10. [風險與限制](#10-風險與限制)
11. [正式環境準備度評估](#11-正式環境準備度評估)
12. [改善建議](#12-改善建議)

---

## 1. 專案概述

**投資Talk君**是一個 AI 驅動的投資內容摘要平台，自動彙整 YouTube 影片、X (Twitter) 貼文、Google Sheets 數據等多種資料來源，提供搜尋介面與 AI 問答功能。

**核心能力：**
- 每日自動抓取 YouTube 新影片 → 語音辨識 → AI 摘要（含標的、情緒分析）
- 每日同步 X 貼文與 Google Sheets 數據至知識庫
- 使用者可透過 AI 問答介面查詢 Talk君 的所有內容
- 所有回答附帶引用來源，絕不編造

**技術堆疊：**
| 層級 | 技術 |
|------|------|
| 前端 | Vanilla JS + CSS（無框架）|
| 後端 API | Python 3.12（SimpleHTTPRequestHandler）|
| AI 模型 | OpenAI GPT-4o / GPT-4o-mini / Whisper |
| 知識庫 | OpenAI Vector Store（file_search）|
| 前端部署 | GitHub Pages（免費）|
| API 部署 | Render Free Tier |
| CI/CD | GitHub Actions |
| 資料儲存 | Git（JSON 檔案）|

---

## 2. 系統架構圖

```
┌─────────────────────────────────────────────────────────┐
│                     資料來源層                            │
├─────────────┬──────────────┬──────────────┬─────────────┤
│  YouTube    │  X (Twitter) │ Google Sheets│  手動文件    │
│  影片頻道    │  @TJ_Research│  5 張試算表   │  app-guide  │
└──────┬──────┴──────┬───────┴──────┬───────┴──────┬──────┘
       │             │              │              │
       ▼             ▼              ▼              ▼
┌─────────────────────────────────────────────────────────┐
│                   資料擷取層（Python 腳本）                │
├─────────────┬──────────────┬──────────────┬─────────────┤
│ yt-dlp      │ X API v2     │ Sheets API   │  直接讀取    │
│ + Whisper   │ fetch_tweets │ fetch_sheets │  Markdown   │
└──────┬──────┴──────┬───────┴──────┬───────┴──────┬──────┘
       │             │              │              │
       ▼             ▼              ▼              ▼
┌─────────────────────────────────────────────────────────┐
│                   資料儲存層（JSON 檔案）                  │
│  data/summaries/*.json  data/tweets/  data/sheets/      │
│  data/docs/app-guide.md  data/index.json                │
└───────────────────────────┬─────────────────────────────┘
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
┌──────────────────────┐    ┌──────────────────────────┐
│   前端靜態網站         │    │   RAG 知識庫              │
│   GitHub Pages        │    │   OpenAI Vector Store     │
│                      │    │                          │
│  - 首頁（搜尋/篩選）   │    │  Markdown 檔案 → 向量化    │
│  - 摘要詳情頁          │    │  video-*.md              │
│  - 標的搜尋            │    │  tweets-*.md             │
│  - 收藏夾             │    │  sheet-*.md              │
│  - AI 問答            │    │  app-guide.md            │
└──────────┬───────────┘    └───────────┬──────────────┘
           │                            │
           │    POST /api/ask           │
           └──────────────┐             │
                          ▼             │
              ┌──────────────────────┐  │
              │   Chat API 伺服器     │  │
              │   Render (Docker)    │──┘
              │   GPT-4o + file_search
              └──────────────────────┘
```

---

## 3. 資料來源與擷取

### 3.1 YouTube 影片

| 項目 | 說明 |
|------|------|
| 頻道 | 投資TALK君 (`@yttalkjun`) |
| 擷取方式 | `yt-dlp` 工具取得影片列表 |
| 語音辨識 | 優先使用 YouTube 字幕（免費），無字幕時使用 OpenAI Whisper API |
| 摘要生成 | GPT-4o 擷取重點、標籤、提及標的（含情緒判斷） |
| 雙語支援 | 先產生簡體中文，再以 GPT-4o-mini 轉換為繁體中文 |
| 更新頻率 | 每日自動（GitHub Actions，UTC 00:00） |
| 目前資料量 | 16 部影片摘要 |

**處理流程：**
```
影片 URL → 下載字幕/音訊 → 語音辨識 → GPT-4o 摘要 → 儲存 JSON
```

### 3.2 X (Twitter) 貼文

| 項目 | 說明 |
|------|------|
| 帳號 | @TJ_Research |
| API | X API v2（Bearer Token 認證） |
| 擷取方式 | 增量抓取（`since_id` 避免重複） |
| 更新頻率 | 每日自動 |
| 目前資料量 | 1,275 則貼文 |

### 3.3 Google Sheets（5 張）

| 試算表名稱 | 更新頻率 | 說明 |
|-----------|---------|------|
| 投資talk君-總經公告 | 每日（混合） | 目前持倉清單（每日）+ 追蹤指標（固定） |
| 投資Talk君-持倉績效 ytd | 每日 | 歷史持倉變動 |
| 投資talk君-資料來源 | 每日 | 市場趨勢數據 |
| 投資talk君-持倉Beta | 每日 | 每日投組 Beta 值 |
| 爬蟲-投資talk君2025文章 | 一次性 | 社團歷史貼文（靜態） |

**認證方式：** Google Service Account（JSON 金鑰儲存於 GitHub Secrets）

### 3.4 手動文件

| 檔案 | 用途 |
|------|------|
| `data/docs/app-guide.md` | App 使用指南（人工撰寫，AI 可引用） |

### 3.5 未來資料來源（尚未實作）

- **社團 API**：CMoney 內部 API（開發中，在內網，需評估存取方式）
- **直播逐字稿**：即時直播的語音辨識
- **投資框架文件**：作者自定義的投資分析方法論

---

## 4. 資料處理管線

### 4.1 影片處理管線

```
fetch_new_videos.py              transcribe.py                    summarize.py
┌──────────────┐    ┌────────────────────────┐    ┌─────────────────────────┐
│ yt-dlp 取得   │    │ 方案 A: YouTube 字幕    │    │ GPT-4o 提取：            │
│ 頻道最新影片   │───▶│ 方案 B: Whisper API    │───▶│ - keyPoints（含時間戳）   │
│ (≤15 部/頻道) │    │ (自動壓縮至 <25MB)      │    │ - paragraph（100-200字） │
└──────────────┘    └────────────────────────┘    │ - tags                  │
                                                   │ - tickers（含情緒分析）   │
                                                   └──────────┬──────────────┘
                                                              │
                                                   ┌──────────▼──────────────┐
                                                   │ GPT-4o-mini             │
                                                   │ 簡體 → 繁體中文轉換       │
                                                   └──────────┬──────────────┘
                                                              │
                                                   ┌──────────▼──────────────┐
                                                   │ 儲存為 JSON              │
                                                   │ data/summaries/         │
                                                   │ {日期}-{影片ID}.json     │
                                                   └─────────────────────────┘
```

### 4.2 摘要 JSON 結構

```json
{
  "id": "影片ID",
  "title": "影片標題",
  "publishedAt": "2026-03-03",
  "duration": 1778,
  "summary": {
    "zh-Hant": {
      "keyPoints": [{"timestamp": 260, "text": "重點內容"}],
      "paragraph": "100-200字段落摘要",
      "tags": ["美股", "AI", "半導體"]
    }
  },
  "tickers": [
    {
      "symbol": "NVDA",
      "name": "英偉達",
      "sentiment": "bullish",
      "mentions": [{"start": 100, "end": 200, "context": "提及上下文"}]
    }
  ]
}
```

### 4.3 知識庫同步管線

```
每日排程（daily-sync-kb.yml）

  1. fetch_tweets.py     → data/tweets/tweets.json（增量）
  2. fetch_sheets.py     → data/sheets/*.json（全量覆寫）
  3. sync_vector_store.py：
     ├─ 所有 JSON → 轉換為 Markdown
     ├─ 比對 Vector Store 現有檔案
     ├─ 上傳新增/異動檔案
     └─ 刪除已移除檔案
  4. git commit + push   → 保留資料變更歷史
```

---

## 5. RAG 知識庫架構

### 5.1 核心設計

使用 **OpenAI Vector Store**（`file_search` 工具）作為集中式知識庫，取代原先規劃的 Dify 部署。

| 項目 | 說明 |
|------|------|
| Vector Store ID | `vs_69a812cf85008191aefce462491a94e3` |
| 儲存格式 | Markdown 檔案（向量化後用於語意搜尋） |
| 查詢方式 | OpenAI Responses API + `file_search` 工具 |
| 回應模型 | GPT-4o |

### 5.2 知識庫檔案命名規則

| 來源 | 檔案命名 | 更新策略 |
|------|---------|---------|
| YouTube 影片 | `video-{日期}-{影片ID}.md` | 新影片才上傳 |
| X 貼文 | `tweets-{年}-W{週數}.md` | 當週檔案每日覆蓋 |
| Google Sheets | `sheet-{代號}-latest.md` | 每日覆蓋 |
| 社團貼文 | `community-posts.md` | 一次性 |
| 使用指南 | `app-guide.md` | 有修改時上傳 |

### 5.3 智慧差異同步

同步邏輯避免重複上傳：

1. 列出 Vector Store 中的所有檔案
2. 比對本地 Markdown 檔案
3. **影片**：檔名含日期+ID，新增才上傳
4. **貼文/Sheets**：每日資料變動，一律重新上傳
5. **已刪除的本地檔案**：從 Vector Store 移除

### 5.4 Chat API 查詢流程

```
使用者提問
    │
    ▼
web_demo.py（Render）
    │
    ├─ System Prompt：
    │   - 僅根據資料回答
    │   - 附上參考來源
    │   - 使用繁體中文
    │   - 不提供投資建議
    │
    ├─ 呼叫 OpenAI Responses API
    │   model: gpt-4o
    │   tools: file_search（搜尋 Vector Store）
    │
    ▼
回傳答案 + 引用來源列表
```

### 5.5 引用來源顯示

前端會將檔案名稱轉換為可讀格式：

| 原始檔名 | 顯示 |
|---------|------|
| `video-2026-03-03-XKgWzUWnoa8_pw55djdi.md` | 📺 YouTube影片 [2026/03/03] |
| `tweets-2026-W09_iuo95ax7.md` | 📝 X平台短評 [2026年第09週] |
| `sheet-positions-ytd-latest_dozhb23t.md` | 📊 持倉績效 |
| `app-guide.md` | 📖 使用指南 |

---

## 6. 前端架構

### 6.1 頁面結構

| 頁面 | 檔案 | 功能 |
|------|------|------|
| 首頁 | `index.html` | 影片列表、搜尋、標籤/標的篩選 |
| 摘要詳情 | `summary.html` | 完整摘要、YouTube 嵌入、時間戳跳轉 |
| 標的搜尋 | `ticker.html` | 股票代號搜尋、情緒分析統計、相關影片 |
| 收藏夾 | `bookmarks.html` | localStorage 儲存的個人收藏 |
| AI 問答 | `chat.html` | 即時 AI 對話、引用來源顯示 |

### 6.2 JavaScript 模組

| 模組 | 行數 | 職責 |
|------|------|------|
| `app.js` | 340 | 核心工具：語言切換、資料載入、格式化、書籤更新 |
| `search.js` | 265 | 客戶端搜尋/篩選（Debounce 300ms） |
| `ticker.js` | 498 | 標的搜尋、自動補全、情緒圓餅圖 |
| `chat.js` | 260 | Chat UI、API 呼叫、來源格式化 |
| `bookmarks.js` | 105 | localStorage 書籤管理 |

### 6.3 設計特點

- **無框架**：純 Vanilla JavaScript，無 npm/webpack 依賴
- **雙語支援**：繁體/簡體中文即時切換（`lang-changed` 自訂事件）
- **深色主題**：以 CSS 自訂屬性實作（`--color-bg: #0a0a0f`）
- **行動裝置優先**：底部導航列、響應式佈局
- **客戶端搜尋**：載入 `index.json` 後全部在本地端篩選

---

## 7. 部署架構

### 7.1 前端（GitHub Pages）

| 項目 | 說明 |
|------|------|
| 平台 | GitHub Pages |
| 網址 | `https://cyt9999.github.io/talk-library/` |
| 觸發條件 | 推送至 `main` 分支且變更了 `site/` 或 `data/` |
| 費用 | 免費 |
| 限制 | 靜態檔案、無伺服器端邏輯 |

### 7.2 Chat API（Render）

| 項目 | 說明 |
|------|------|
| 平台 | Render Free Tier |
| 網址 | `https://talk-library.onrender.com` |
| 容器 | Docker（Python 3.12-slim） |
| 端口 | 8080 |
| 環境變數 | `OPENAI_API_KEY`、`VECTOR_STORE_ID` |
| 費用 | 免費（閒置 15 分鐘後休眠） |

### 7.3 CORS 設定

```python
ALLOWED_ORIGINS = {
    "https://cyt9999.github.io",
    "https://talk-library.onrender.com",
    "http://localhost:5500",
}
```

---

## 8. 自動化流程（GitHub Actions）

### 8.1 每日影片摘要 (`daily-summarize.yml`)

```
觸發：每日 UTC 00:00 + 手動
步驟：安裝 Python → 安裝 yt-dlp/ffmpeg → 執行管線 → 提交推送
環境變數：OPENAI_API_KEY, ANTHROPIC_API_KEY
```

### 8.2 每日知識庫同步 (`daily-sync-kb.yml`)

```
觸發：daily-summarize 完成後 + 手動
步驟：抓取推文 → 抓取 Sheets → 同步 Vector Store → 提交推送
環境變數：OPENAI_API_KEY, VECTOR_STORE_ID, X_BEARER_TOKEN,
         GOOGLE_SERVICE_ACCOUNT_KEY, SHEET_ID_* (5個)
```

### 8.3 網站部署 (`deploy-pages.yml`)

```
觸發：推送至 main（影響 site/ 或 data/）+ 手動
步驟：複製 data/ 至 site/data/ → 部署至 GitHub Pages
```

### 8.4 手動上傳處理 (`manual-upload.yml`)

```
觸發：推送至 data/uploads/** + 手動
步驟：安裝 ffmpeg → 處理上傳檔案 → 提交推送
```

### 8.5 執行順序

```
UTC 00:00
    │
    ▼
daily-summarize（抓取新影片、生成摘要）
    │ 完成後自動觸發
    ▼
daily-sync-kb（同步推文、Sheets、Vector Store）
    │ 推送 data/ 變更
    ▼
deploy-pages（重新部署靜態網站）
```

---

## 9. 成本估算

### 9.1 每部影片成本

| 項目 | 費用 | 備註 |
|------|------|------|
| 語音辨識 (Whisper) | ~$0.36/部 | 以 60 分鐘影片計算；有字幕時免費 |
| 摘要生成 (GPT-4o) | ~$0.005/部 | |
| 繁簡轉換 (GPT-4o-mini) | ~$0.0005/部 | |
| **合計** | **~$0.37/部** | 語音辨識佔成本 97% |

### 9.2 每月估算（假設每日 1-2 部新影片）

| 項目 | 月費 |
|------|------|
| OpenAI API（轉錄+摘要） | ~$11 |
| Chat API 查詢 | ~$1-5（視使用量） |
| GitHub Pages | 免費 |
| Render Free Tier | 免費 |
| GitHub Actions | 免費（公開倉庫） |
| **合計** | **~$12-16/月** |

### 9.3 降低成本機會

- ✅ 已實作：優先使用 YouTube 字幕（免費）
- ✅ 已實作：增量同步避免重複上傳
- ⬜ 可考慮：Whisper 本地部署（需 GPU）
- ⬜ 可考慮：使用較便宜模型（GPT-4o-mini）做摘要

---

<!-- manual-start:risks -->
## 10. 風險與限制

### 10.1 🔴 高風險

| 風險 | 說明 | 影響 | 建議 |
|------|------|------|------|
| **API 金鑰外洩** | OpenAI 金鑰若外洩可產生無上限費用 | 財務損失 | 設定 OpenAI 用量上限、定期輪換金鑰 |
| ~~**Render 冷啟動**~~ | ✅ 已透過 GitHub Actions keep-alive cron 每 14 分鐘 ping `/health` 解決 | — | — |
| ~~**無認證的 Chat API**~~ | ✅ 已加入 Per-IP 速率限制（20 req/min），超過回傳 429 | — | 可進一步加入 API Key 認證 |
| ~~**Vector Store 狀態不一致**~~ | ✅ 伺服器啟動時自動驗證 Vector Store ID 並記錄檔案數量 | — | — |

### 10.2 🟡 中風險

| 風險 | 說明 | 影響 | 建議 |
|------|------|------|------|
| **GPT-4o 幻覺** | 摘要可能包含影片未提及的內容 | 資訊不正確 | 人工審核前幾批摘要 |
| **X API 配額限制** | 免費方案有嚴格速率限制（402 錯誤） | 推文無法更新 | 升級 X API 方案或降低頻率 |
| **繁簡轉換品質** | 部分專有名詞轉換不準確 | 顯示錯誤 | 建立自訂詞彙對照表 |
| **情緒分析過度簡化** | 僅三分類（看多/看空/中性）無法表達複雜觀點 | 誤導使用者 | 加入信心分數或更細緻分類 |
| **大檔案處理失敗** | Whisper API 限制 25MB，超長影片（3小時+）壓縮後可能仍超過 | 影片無法處理 | 分段處理或本地 Whisper |

### 10.3 🟢 低風險

| 風險 | 說明 |
|------|------|
| GitHub Pages 容量限制 | 大量 JSON 檔案可能達到實際上限 |
| 客戶端搜尋效能 | 超過 1000+ 筆摘要時可能變慢 |
| YouTube 字幕品質 | 自動生成字幕可能有辨識錯誤 |
| 時區問題 | GitHub Actions 以 UTC 執行，可能影響日期判斷 |

<!-- manual-end:risks -->

---

<!-- manual-start:readiness -->
## 11. 正式環境準備度評估

### ✅ 已就緒

- [x] 每日自動抓取 YouTube 影片並生成摘要
- [x] Google Sheets 每日同步（4/5 張運作中）
- [x] Vector Store 自動同步管線
- [x] 前端網站已部署（GitHub Pages）
- [x] AI 問答功能已上線（Render）
- [x] 引用來源格式化顯示
- [x] 雙語支援（繁體/簡體）
- [x] 資料版本控制（Git 歷史）
- [x] Chat API 速率限制（Per-IP 20 req/min）
- [x] Vector Store 啟動驗證
- [x] Render keep-alive（GitHub Actions cron）
- [x] 架構文件自動更新（CI 自動產生）

### ⚠️ 部分就緒

- [ ] X 推文同步（受 API 配額限制，間歇性失敗）
- [ ] 社團貼文（僅一次性靜態資料，API 尚未開放）
- [ ] App 使用指南（佔位符，尚未填入實際內容）

### ❌ 尚未實作（正式環境必要）

- [x] **API 速率限制**：已加入 Per-IP 20 req/min 限制（可進一步加入 API Key 認證）
- [ ] **監控與告警**：無法得知工作流程失敗或 API 異常
- [ ] **錯誤重試機制**：失敗後不會自動重試
- [ ] **用量儀表板**：無法追蹤 API 使用量與成本
- [ ] **自動化測試**：無單元測試或整合測試
- [ ] **日誌紀錄**：僅依賴 GitHub Actions 日誌

### 結論

> **目前適合作為內部 Demo 或小規模測試使用，尚未具備面向公開用戶的正式環境條件。**
> 最大障礙是缺乏 API 認證機制與監控，可能導致費用失控或服務中斷而無人知曉。

<!-- manual-end:readiness -->

---

<!-- manual-start:improvements -->
## 12. 改善建議

### 短期（1-2 週）

1. ~~**加入 API 速率限制**~~：✅ 已完成 — Per-IP 20 req/min（可進一步加入 API Key 認證）
2. **設定 OpenAI 用量上限**：在 OpenAI 帳戶設定每月硬上限
3. **填寫 App 使用指南**：讓 AI 可以回答關於 App 功能的問題
4. ~~**加入 Render keep-alive**~~：✅ 已完成 — GitHub Actions cron 每 14 分鐘 ping

### 中期（1-2 月）

5. **遷移至付費主機**：Render 付費方案或 Cloud Run，消除冷啟動
6. **加入監控**：GitHub Actions 失敗通知（Slack/Email）
7. **加入自動化測試**：至少針對資料轉換與同步邏輯
8. **改善摘要品質**：建立人工回饋迴圈，微調 Prompt
9. **前端搜尋升級**：考慮 Algolia 或 MeiliSearch 提供全文搜尋

### 長期（3+ 月）

10. **社團 API 整合**：待 CMoney 內部 API 就緒後串接
11. **訂閱分級機制**：區分免費/付費用戶的內容存取權限
12. **主動推播通知**：重要訊號自動推送
13. **Whisper 本地部署**：降低語音辨識成本
14. **多頻道支援**：擴展至其他投資 YouTuber

<!-- manual-end:improvements -->

---

## 附錄：關鍵檔案索引

| 類別 | 檔案路徑 | 說明 |
|------|---------|------|
| 管線入口 | `scripts/run_pipeline.py` | 主流程控制 |
| 影片抓取 | `scripts/fetch_new_videos.py` | yt-dlp 取得新影片 |
| 語音辨識 | `scripts/transcribe.py` | Whisper API / YouTube 字幕 |
| AI 摘要 | `scripts/summarize.py` | GPT-4o 摘要產生 |
| 索引建立 | `scripts/build_index.py` | 前端搜尋用索引 |
| 推文抓取 | `scripts/dify_sync/fetch_tweets.py` | X API v2 |
| Sheets 抓取 | `scripts/dify_sync/fetch_sheets.py` | Google Sheets API |
| 知識庫同步 | `scripts/dify_sync/sync_vector_store.py` | Vector Store 差異同步 |
| Chat API | `scripts/dify_sync/web_demo.py` | HTTP 伺服器（Render 部署） |
| 設定 | `scripts/dify_sync/config.py` | 環境變數集中管理 |
| 前端核心 | `site/js/app.js` | 語言切換、資料載入 |
| Chat 模組 | `site/js/chat.js` | AI 問答介面 |
| 樣式 | `site/css/style.css` | 深色主題、響應式設計 |
| 部署設定 | `render.yaml` | Render 服務設定 |
| CI/CD | `.github/workflows/*.yml` | 6 個自動化工作流程 |
