# MCP 資料源整合至 RAG 設計文件

**日期**: 2026-03-10
**對應票**: AUTHOR-26644
**目的**: 將後端 MCP API 已完成的 4 支資料服務整合進現有 RAG pipeline，上傳至 OpenAI Vector Store，讓 chatbot 能回答社團貼文、聊天室、投資網誌、影音課程相關問題。

## 背景

AUTHOR-26644 要求將投資Talk君的資料擷取層全面改由 MCP API 串接。目前 7 項資料來源中，後 3 類（社團/聊天室貼文、投資網誌、影音商品）已有 MCP API 可用，前 4 項（YouTube、X、Sheets、App指南）尚待後端開發，現有爬蟲繼續運作。

## MCP API 參數

- **author_id**: 17427140
- **Board IDs**:
  - 10918: 社團大廳
  - 10919: 持倉/總經
  - 10921: VIP會員專屬
  - 12784: VIP聊天室（僅聊天室）
- **pricing_model**: free + paid（皆抓取，分檔標記）
- **初次匯入時間範圍**: 近 90 天

## 整合架構

```
sync_vector_store.py
  ├── (現有) YouTube summaries → Markdown → Vector Store
  ├── (現有) Tweets → Markdown → Vector Store
  ├── (現有) Sheets → Markdown → Vector Store
  └── (新增) MCP content → Markdown → Vector Store
        ├── fetch_mcp_content.py (新腳本)
        │     ├── get_group_articles (board 10918, 10919, 10921)
        │     ├── get_chatroom_articles (board 10918, 10919, 10921, 12784)
        │     ├── get_investment_notes (author 17427140, free + paid)
        │     └── get_media_products (author 17427140, free + paid)
        └── 輸出 JSON → data/mcp/ 目錄
```

## Markdown 檔案規範

### 命名規則

| 來源 | 檔名格式 | 範例 |
|------|---------|------|
| 社團文章 | `club-{boardId}-{YYYY-MM-DD}.md` | `club-10918-2026-03-10.md` |
| 聊天室 | `chatroom-{boardId}-{YYYY-MM-DD}.md` | `chatroom-12784-2026-03-10.md` |
| 投資網誌 | `notes-{pricingModel}-{YYYY-MM-DD}.md` | `notes-paid-2026-03-10.md` |
| 影音商品 | `media-{pricingModel}-{YYYY-MM-DD}.md` | `media-free-2026-03-10.md` |

### Metadata Block

每個 Markdown 檔案開頭加 YAML front matter：

```yaml
---
source: group_article | chatroom | investment_notes | media_products
board_id: 10918          # 社團/聊天室才有
board_name: 社團大廳      # 社團/聊天室才有
author_id: 17427140      # 網誌/影音才有
pricing: free | paid     # 網誌/影音才有
date_range: 2026-03-10
fetched_at: 2026-03-10T16:00:00+08:00
---
```

### 內容格式

社團/聊天室文章：
```markdown
## {contentTitle}
- 發文者: {creatorName}
- 時間: {createTime 轉可讀格式}

{contentText}

---
```

投資網誌：
```markdown
## {title}
- 作者: {authorName}
- 更新時間: {updatedAt}
- 權限: {pricingModel}

{content}

---
```

影音商品：
```markdown
## {title}
- 作者: {authorName}
- 建立時間: {createTime}
- 權限: {pricingModel}

{description}

---
```

## 新增檔案

| 檔案 | 說明 |
|------|------|
| `scripts/dify_sync/fetch_mcp_content.py` | 呼叫 4 支 MCP API，輸出 JSON 至 `data/mcp/` |
| `scripts/dify_sync/convert_mcp.py` | 將 `data/mcp/` JSON 轉為 Markdown |
| `data/mcp/` | MCP 原始 JSON 資料存放目錄 |

## 修改檔案

| 檔案 | 修改內容 |
|------|---------|
| `scripts/dify_sync/sync_vector_store.py` | 新增 MCP Markdown 來源的轉換與上傳邏輯 |
| `site/js/chat.js` | citation 格式新增 MCP 來源的 icon mapping |
| `.github/workflows/daily-sync-kb.yml` | 新增 MCP fetch 步驟 |

## 不動的部分

- `web_demo.py` — Vector Store 查詢邏輯不變
- 前端 chat UI 結構不變
- 現有 YouTube / Tweets / Sheets 爬蟲繼續運作
- OpenAI Vector Store ID 不變

## 未來擴充

- **權限分流**: 依 Markdown metadata 中的 `pricing` 欄位，未來可建立 free / paid 兩個 Vector Store，chatbot 依用戶身分查詢不同 store
- **前 4 項 MCP**: 後端開發完成後，依相同模式替換現有爬蟲腳本
- **即時查詢**: 如需更即時的資料，可在 web_demo.py 加入 function calling 直接呼叫 MCP（Phase 2）

## 執行方式

由於 MCP API 是透過 MCP Server 呼叫（非 REST API），`fetch_mcp_content.py` 需要透過 MCP client SDK 連線至 MCP server 來取得資料。具體串接方式需確認 MCP server 的連線設定（stdio / SSE / HTTP）。
