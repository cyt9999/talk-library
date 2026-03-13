# skill.md — AI 知識庫問答平台
## 這個 skill 的用途
當使用者要建立一個「自動彙整內容來源 → AI 問答」的平台時，照這份 skill 的架構與慣例產出所有程式碼。
---
## 產品目標
建立一個平台，能夠：
1. 定期自動從指定來源抓取內容（YouTube / Twitter / Google Sheets 或後端 API）
2. 用 AI 產出摘要並同步進知識庫
3. 讓使用者透過 AI 問答查詢所有內容，每個回答必須附來源，不可編造
---
## 技術選型（不要改，除非使用者明確要求）
| 用途 | 工具 |
|------|------|
| 前端 | 靜態 HTML + Vanilla JS，部署到 GitHub Pages |
| 問答後端 | Python HTTP Server，Docker 部署到 Render |
| AI 模型 | OpenAI GPT-4o（問答與摘要）、GPT-4o-mini（輕量任務） |
| 影音轉文字 | OpenAI Whisper API |
| 知識庫 | OpenAI Vector Store + file_search |
| 自動化排程 | GitHub Actions |
| 資料儲存 | JSON 檔案，commit 進 Git repo |
---
## 強制架構慣例
### 1. 資料抓取必須獨立成模組
將抓取資料的邏輯（fetch.py 或類似命名）與處理、摘要邏輯完全分離。
原因：現有資料來源（YouTube、Twitter 等）是暫時方案，未來會替換為後端工程師提供的統一 API，屆時只需替換這一個模組，其餘架構不動。
### 2. 三個腳本分工
- `fetch.py` — 從資料來源抓取原始內容
- `summarize.py` — 呼叫 GPT-4o 產摘要，存成 JSON
- `sync.py` — 將 JSON 轉為 Markdown，同步進 OpenAI Vector Store（智慧差異同步，只上傳新增或變動的檔案）
### 3. GitHub Actions 串聯順序
```
UTC 00:00
  ↓ daily-summarize（抓資料 → 產摘要）
  ↓ daily-sync-kb（同步 Vector Store）
  ↓ deploy-pages（重新部署前端）
```
---
## 必做事項（每次都要實作，不可省略）
### keep-alive
Render 免費方案閒置 15 分鐘會休眠。必須加一個 GitHub Actions workflow，每 14 分鐘 GET 一次 `/health` endpoint。
### 字幕優先，Whisper 備用
處理 YouTube 影片時，優先用 yt-dlp 取得免費字幕；只有在沒有字幕時才呼叫 Whisper API。
原因：Whisper 費用佔總成本 97%，有字幕時成本差距約 100 倍。
### 速率限制
問答 API 上線前必須加 Per-IP 速率限制（預設：每 IP 每分鐘最多 20 次請求，超過回傳 429）。
原因：API 公開且呼叫 OpenAI，沒有限制會導致費用失控。
---
## 產品說明文件
如果使用者有 BP（簡報），可透過 https://cmpmtools.streamlit.app/ 上傳 BP 自動產出 MD 說明文件。
將產出的 MD 檔加入 Vector Store，AI 即可回答關於產品功能的使用問題。
---
## System Prompt 規範
Chat API 的 system prompt 必須包含以下限制：
- 只根據 Vector Store 內的資料回答
- 每個回答必須附上引用來源（檔名或內容標題）
- 不提供任何投資建議（若產品涉及投資內容）
- 沒有資料時明確告知，不可編造
---
## CORS 設定
允許的 origin 預設包含：
- GitHub Pages 網址
- Render 服務網址
- `http://localhost:5500`（本地開發用）
---
## 完成確認清單
產出後請確認以下項目都已實作：
- [ ] fetch / summarize / sync 三個腳本分離
- [ ] GitHub Actions 三段串聯排程
- [ ] Render keep-alive workflow（每 14 分鐘）
- [ ] 字幕優先邏輯（yt-dlp 先，Whisper 備用）
- [ ] Per-IP 速率限制（20 req/min）
- [ ] System prompt 含來源引用規範
- [ ] CORS 設定