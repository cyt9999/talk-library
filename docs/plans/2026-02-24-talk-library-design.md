# 投資Talk君 — Content Summarization Library

**Date**: 2026-02-24
**Status**: Approved

## Overview

投資Talk君 is a static web module that automatically summarizes Chinese-language US stock investment videos and audio content. It is loaded inside the CMoney mobile app via WebView.

Users browse pre-generated summaries of investment content, with search, filtering, bookmarks, and extracted stock ticker information with sentiment tags.

## Constraints

- Hosted on **GitHub Pages** (static, no backend)
- Opened via **CMoney app WebView** (mobile-first)
- Content in **Simplified Chinese**, with **Traditional Chinese** toggle
- **US stocks only**
- **Freemium** model (details TBD)
- Minimize cost

## Architecture

```
GitHub Actions (daily cron)
  │
  ├─ 1. Fetch YouTube channel RSS → detect new videos
  ├─ 2. Download audio via yt-dlp
  ├─ 3. Transcribe via OpenAI Whisper API
  ├─ 4. Summarize via Claude API
  │      ├─ Structured key points with timestamps
  │      ├─ Paragraph summary
  │      ├─ Extract US stock tickers with sentiment
  │      ├─ Map tickers to timestamp ranges in video
  │      └─ Output both 簡體 and 繁體
  ├─ 5. Save as JSON in data/summaries/
  ├─ 6. Rebuild index.json
  └─ 7. Commit & push → GitHub Pages auto-deploys

Manual upload workflow:
  Push audio/video to data/uploads/ → triggers same pipeline (steps 3-7)
```

## Data Model

### channels.json

```json
[
  {
    "id": "talk_yt",
    "name": "投资TALK君",
    "rssUrl": "https://www.youtube.com/@yttalkjun"
  }
]
```

### Summary JSON (data/summaries/YYYY-MM-DD-{videoId}.json)

```json
{
  "id": "abc123",
  "videoId": "dQw4w9WgXcQ",
  "source": "youtube",
  "channelName": "某投資頻道",
  "title": "2026年Q1美股展望",
  "publishedAt": "2026-02-24",
  "summarizedAt": "2026-02-24T08:00:00Z",
  "duration": 1845,
  "thumbnailUrl": "https://img.youtube.com/vi/.../hqdefault.jpg",
  "videoUrl": "https://youtube.com/watch?v=...",
  "summary": {
    "zh-Hans": {
      "keyPoints": [
        {
          "timestamp": 120,
          "text": "联准会可能在Q2降息一码，利好科技股"
        },
        {
          "timestamp": 480,
          "text": "NVDA财报超预期，AI资本支出持续增长"
        }
      ],
      "paragraph": "本期节目讨论了...",
      "tags": ["美股", "联准会", "半导体"]
    },
    "zh-Hant": {
      "keyPoints": [
        {
          "timestamp": 120,
          "text": "聯準會可能在Q2降息一碼，利好科技股"
        },
        {
          "timestamp": 480,
          "text": "NVDA財報超預期，AI資本支出持續增長"
        }
      ],
      "paragraph": "本期節目討論了...",
      "tags": ["美股", "聯準會", "半導體"]
    }
  },
  "tickers": [
    {
      "symbol": "NVDA",
      "name": "輝達",
      "sentiment": "bullish",
      "mentions": [
        { "start": 480, "end": 720, "context": "NVDA財報分析" },
        { "start": 1200, "end": 1350, "context": "AI晶片競爭格局" }
      ]
    },
    {
      "symbol": "AAPL",
      "name": "蘋果",
      "sentiment": "neutral",
      "mentions": [
        { "start": 900, "end": 1050, "context": "iPhone銷量展望" }
      ]
    }
  ]
}
```

### index.json

A lightweight index for client-side search and filtering:

```json
[
  {
    "id": "abc123",
    "title": "2026年Q1美股展望",
    "publishedAt": "2026-02-24",
    "channelName": "某投資頻道",
    "tags": ["美股", "联准会", "半导体"],
    "tickers": ["NVDA", "AAPL"],
    "thumbnailUrl": "..."
  }
]
```

## Frontend Design

### Tech Stack

- Vanilla HTML/CSS/JS (no framework, no build step)
- Mobile-first responsive design for WebView
- Client-side search over index.json
- localStorage for bookmarks

### Pages

**Home (`/`)**
- Header: 投資Talk君 logo + 繁體/簡體 toggle
- Search bar (client-side full-text search)
- Filter chips: by tag, by ticker, by date range
- Summary card list (newest first)
  - Thumbnail + title + date + channel
  - Tag pills
  - Ticker pills with sentiment color (green=bullish, red=bearish, gray=neutral)

**Summary Detail (`/summary/{id}`)**
- Video title + date + channel
- Embedded YouTube player (iframe)
- Key points list — click to jump to timestamp in video
- Full paragraph summary
- Tickers section
  - Each ticker card with sentiment indicator
  - "Mentioned at:" timestamp links that jump to video position
- Bookmark button

**Bookmarks (`/bookmarks`)**
- List of bookmarked summaries from localStorage
- Remove bookmark option

## Automation Details

### Daily Workflow (GitHub Actions)

- **Schedule**: Daily at 08:00 UTC+8
- **Manual trigger**: workflow_dispatch for on-demand runs
- **Steps**:
  1. `fetch-new-videos.py` — parse RSS feeds from channels.json, compare against existing summaries, output list of new video IDs
  2. `transcribe.py` — for each new video: download audio via yt-dlp, send to Whisper API, save transcript
  3. `summarize.py` — for each transcript: send to Claude API with structured prompt, save summary JSON
  4. `build-index.py` — scan all summary files, rebuild index.json
  5. Commit and push changes

### Manual Upload Workflow

- Triggered when files are pushed to `data/uploads/`
- Runs transcribe → summarize → build-index for uploaded files

### API Secrets

- `OPENAI_API_KEY` — for Whisper transcription
- `ANTHROPIC_API_KEY` — for Claude summarization
- Stored as GitHub Actions secrets

## Cost Estimate

| Item | Cost |
|---|---|
| GitHub Pages hosting | Free |
| GitHub Actions CI | Free (2000 min/month) |
| Whisper API (~30 min video) | ~$0.18 |
| Claude API (per summary) | ~$0.05-0.15 |
| **Per video total** | **~$0.20-0.35** |

## Future Enhancements (Deferred)

- **Stock deep linking**: Integrate CMoney onelink to navigate to stock pages in-app
- **User accounts / auth**: Sync bookmarks across devices via CMoney login
- **AI Q&A**: Let users ask follow-up questions about a summary
- **Podcast RSS support**: Monitor podcast feeds in addition to YouTube
- **Mind map output format**: Visual summary as a mind map

## Repo Structure

```
talk_library/
├── .github/
│   └── workflows/
│       ├── daily-summarize.yml
│       └── manual-upload.yml
├── scripts/
│   ├── fetch-new-videos.py
│   ├── transcribe.py
│   ├── summarize.py
│   └── build-index.py
├── data/
│   ├── channels.json
│   ├── index.json
│   ├── summaries/
│   └── uploads/
├── site/
│   ├── index.html
│   ├── summary.html
│   ├── bookmarks.html
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── app.js
│       ├── search.js
│       └── bookmarks.js
├── docs/
│   └── plans/
└── README.md
```
