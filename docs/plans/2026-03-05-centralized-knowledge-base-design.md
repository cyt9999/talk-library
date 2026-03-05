# Centralized Knowledge Base — Design Doc

> **Date**: 2026-03-05
> **Goal**: Unify all data sources (YouTube, X/Twitter, Google Sheets, 社團, app guide) into a single OpenAI Vector Store, with fully automated daily sync via GitHub Actions.

---

## Architecture Decision

**Use OpenAI Vector Store as the centralized knowledge base.** Skip Dify deployment.

- The vector store already works with the existing chat Q&A (CLI, web demo, site chat tab).
- Saves ~$25/month in GCP VM costs.
- All chat interfaces automatically gain access to new data without code changes.

---

## Data Sources

| # | Source | Location | Update Frequency | Sync Strategy |
|---|--------|----------|-------------------|---------------|
| 1 | YouTube summaries | `data/summaries/*.json` | Daily (existing `daily-summarize` workflow) | Convert new summaries to Markdown, upload |
| 2 | X/Twitter tweets | `data/tweets/tweets.json` | Daily (incremental fetch via X API v2) | Group by ISO week, re-upload current week |
| 3 | 投資talk君-總經公告 | Google Sheet | Daily (mixed: daily listings + fixed metrics) | Full re-fetch, overwrite in vector store |
| 4 | 投資Talk君-持倉績效 ytd | Google Sheet | Daily | Full re-fetch, overwrite |
| 5 | 投資talk君-資料來源 | Google Sheet | Daily | Full re-fetch, overwrite |
| 6 | 投資talk君-持倉Beta | Google Sheet | Daily | Full re-fetch, overwrite |
| 7 | 社團 posts (爬蟲-投資talk君2025文章) | Google Sheet (stale dump) | One-time ingest | Fetch once, re-fetch if sheet updates |
| 8 | App usage guide | `data/docs/app-guide.md` | Manual (author writes/updates) | Upload when changed |

### Future Source (Not in Scope)

- **社團 posts via company API**: CMoney is building an internal API for community posts. It will be on 內網 (internal network). When available, a new fetcher script will be added. The pipeline is designed to be extensible — each source is a separate fetcher with a common JSON output format.

---

## Vector Store Markdown Format

All sources are converted to Markdown before uploading to the OpenAI Vector Store.

| Source | File Naming | Content |
|--------|-------------|---------|
| YouTube summary | `video-{date}-{id}.md` | Title, date, key points with timestamps, full summary, tags, tickers with sentiment |
| Tweets | `tweets-{year}-W{week}.md` | Grouped by ISO week. Each tweet: date, text, engagement metrics |
| Google Sheets (daily) | `sheet-{slug}-latest.md` | Sheet name, fetch date, all rows as structured text. Overwrites previous version |
| 社團 dump | `community-posts.md` | All posts with dates and content |
| App guide | `app-guide.md` | Directly uploaded (already Markdown) |

---

## Sync Pipeline

### Flow

```
daily-sync-kb.yml (GitHub Action)
  │  Trigger: after daily-summarize completes, or manual dispatch
  │
  ├─ 1. fetch_tweets.py          → data/tweets/tweets.json (incremental)
  ├─ 2. fetch_sheets.py          → data/sheets/*.json (full refresh for daily sheets)
  ├─ 3. sync_vector_store.py
  │     ├─ Convert all sources to Markdown
  │     ├─ Diff against vector store (list existing files)
  │     ├─ Upload new/changed files
  │     └─ Delete removed files (optional)
  └─ 4. git commit + push         → data/*.json changes preserved in git history
```

### Smart Diff Logic

- List files in vector store via `client.vector_stores.files.list()`
- Compare local Markdown files by filename
- Video summaries: only upload new (filename includes date+id, so new = not in store)
- Tweets: re-upload current week's file (content changes as new tweets arrive)
- Google Sheets: always re-upload (daily data changes, overwrite previous)
- App guide: upload only if content hash changed

---

## New Files to Create

| File | Purpose |
|------|---------|
| `scripts/dify_sync/fetch_sheets.py` | Fetch 5 Google Sheets → JSON via Google Sheets API |
| `scripts/dify_sync/sync_vector_store.py` | Orchestrate: fetch → convert → diff → upload |
| `.github/workflows/daily-sync-kb.yml` | GitHub Action for daily knowledge base sync |
| `data/docs/app-guide.md` | Manually authored app usage guide (placeholder) |

## Files to Modify

| File | Change |
|------|--------|
| `scripts/dify_sync/convert_and_upload.py` | Refactor conversion logic into reusable functions for `sync_vector_store.py` |
| `scripts/dify_sync/config.py` | Add Google Sheets config (sheet IDs, slugs) |

---

## Secrets & Configuration

### GitHub Secrets

| Secret | Status |
|--------|--------|
| `OPENAI_API_KEY` | Already set |
| `GOOGLE_SERVICE_ACCOUNT_KEY` | Already set |
| `X_BEARER_TOKEN` | **Needs to be added** (currently only in local `.env`) |
| `VECTOR_STORE_ID` | **Needs to be added** (currently only in local `.env`) |

### Manual Setup Steps

1. Add `X_BEARER_TOKEN` and `VECTOR_STORE_ID` to GitHub repo secrets
2. Share remaining 4 Google Sheets with the service account email (read-only)

---

## Error Handling

- **Independent fetchers**: If one source fails (e.g., Google Sheets API down), others still sync
- **Retry**: Each fetcher retries 2x with exponential backoff on transient errors
- **Idempotent**: Running sync twice produces the same result
- **Logging**: GitHub Action summary shows per-source success/failure
- **No data loss**: All JSON files committed to git with history

---

## What Doesn't Change

- **Chat UI**: No frontend changes. The chat tab on the site already queries the vector store via `web_demo.py`. New data is automatically available to the bot.
- **YouTube pipeline**: `daily-summarize.yml` continues unchanged. The new workflow runs after it.
- **Site deployment**: `deploy-pages.yml` continues unchanged.

---

## Success Criteria

1. All 6 active data sources flow into the vector store daily without manual intervention
2. The AI chat bot can answer questions citing YouTube videos, tweets, Google Sheets data, and the app guide
3. Adding a new data source requires only: (a) a new fetcher script, (b) a conversion rule in `sync_vector_store.py`
