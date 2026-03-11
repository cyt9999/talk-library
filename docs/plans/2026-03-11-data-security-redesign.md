# Data Security Redesign — 資料不落地架構

**Date**: 2026-03-11
**Status**: Approved
**Ticket**: AUTHOR-26644 (延伸)

## Problem

- Repo 是 public，`data/` 目錄含敏感公司資料（持倉、社團聊天室、Google Sheets）
- CI workflow 每日爬取資料後 commit 到 repo，等於公開
- GitHub Pages 部署時也把 `data/` 一起部署，任何人可瀏覽

## Design

### Architecture

```
┌─────────────────────────────────────────────────────┐
│  GitHub Repo (public)                               │
│  ├── site/          (HTML/CSS/JS only, no data)     │
│  ├── scripts/       (code only)                     │
│  └── .github/       (workflows)                     │
│       零敏感資料                                      │
└─────────────────────────────────────────────────────┘
         │                            │
    push site/**               CI workflow trigger
         ▼                            ▼
┌─────────────────┐    ┌──────────────────────────────┐
│  GitHub Pages   │    │  CI Runner (ephemeral)        │
│  Static UI only │    │  1. Fetch from MCP API        │
│  (CDN, fast)    │    │  2. Fetch from Google Sheets  │
└────────┬────────┘    │  3. Fetch YouTube summaries   │
         │             │  4. Convert to Markdown       │
    calls API          │  5. Upload to Vector Store    │
         │             │  6. NO git commit of data     │
         ▼             └──────────────┬───────────────┘
┌─────────────────┐                   │
│  Render API     │◄──────────────────┘
│  (web_demo.py)  │    Vector Store is the
│  ├── /api/ask   │    single source of truth
│  ├── /api/videos│ (new)
│  └── /health    │
└─────────────────┘
```

### Key Changes

#### 1. Remove `data/` from repo
- Delete `data/` directory from git history (or just remove and commit)
- Add `data/` to `.gitignore`
- Keep `data/` locally for dev but never commit

#### 2. CI Workflow: no commit, no deploy data
- Remove `git add data/` and commit steps
- Remove `cp -r data site/data` from Pages deployment
- Fetch → Convert → Upload to Vector Store → done

#### 3. New Render API endpoints
Frontend currently reads video list from static `data/index.json`. Replace with:

- `GET /api/videos` — return video list (from summaries in Vector Store or a lightweight index)
- `GET /api/summary/:id` — return single video summary

Options for serving video data:
- **Option A**: Store a lightweight `index.json` in the repo (just titles/dates/IDs, no sensitive content) — simplest
- **Option B**: Build index from Vector Store file listing at startup
- **Recommended**: Option A — video metadata (title, date, ID) is from public YouTube, not sensitive

#### 4. GitHub Pages: site/ only
- Deploy only `site/` directory (HTML/CSS/JS)
- No `data/` copied into deployment
- Frontend fetches dynamic data from Render API

#### 5. Disable X API auto-fetch
- X API rate limit reached, disable in CI
- Existing tweets in Vector Store remain available

### What stays in the repo
- `site/` — frontend UI code
- `scripts/` — pipeline code
- `.github/workflows/` — CI definitions
- `data/index.json` — video metadata only (public YouTube info: title, date, video ID)

### What gets removed
- `data/summaries/*.json` — full summary content
- `data/sheets/*.json` — portfolio, macro data
- `data/mcp/` — chatroom articles
- `data/tweets/` — X posts
- `data/test-reports/` — test results

### Security improvements
- Zero sensitive data in repo
- Zero sensitive data on GitHub Pages
- Data only exists in: source APIs (MCP, Sheets) + OpenAI Vector Store
- API keys remain in GitHub Secrets / Render env vars (unchanged)
